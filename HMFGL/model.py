import os
import sys

import networkx as nx
import numpy as np
import scipy.sparse as spsprs
import torch
import torch.autograd
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from collections import Counter
from sklearn.metrics import roc_auc_score
import matplotlib.cm
import networkx as nx
from sklearn.metrics import confusion_matrix

from network import *
from utils import *
from sklearn.metrics import f1_score

from sklearn.calibration import calibration_curve
import matplotlib.pyplot as plt


class EvalHelper:
    def __init__(self, input_data_dims, feat, label, hyperpm, train_index, test_index):
        use_cuda = torch.cuda.is_available()
        dev = torch.device('cuda' if use_cuda else 'cpu')
        feat = torch.from_numpy(feat).float().to(dev)
        label = torch.from_numpy(label).long().to(dev)
        self.dev = dev
        self.hyperpm = hyperpm
        self.GC_mode = hyperpm.GC_mode
        self.MP_mode = hyperpm.MP_mode
        self.MF_mode = hyperpm.MF_mode
        self.d_v = hyperpm.n_hidden
        self.modal_num = hyperpm.nmodal
        self.n_class = hyperpm.nclass
        self.dropout = hyperpm.dropout
        self.alpha = hyperpm.alpha
        self.n_head = hyperpm.n_head
        self.th = hyperpm.th
        self.feat = feat
        self.targ = label
        self.best_acc = 0
        self.best_acc_2 = 0
        self.MF_sav = tempfile.TemporaryFile()
        self.GCMP_sav = tempfile.TemporaryFile()
        # print(train_index.shape[0])
        num = train_index.shape[0]
        self.trn_idx = train_index
        self.val_idx = np.array(test_index)
        self.tst_idx = np.array(test_index)
        trn_label = label[self.trn_idx].cpu().numpy()

        # self.weight_ABIDE = nn.Parameter(torch.Tensor([0.28, 0.2,0.17,0.35]))
        self.weight_TADPOLE = nn.Parameter(torch.Tensor([0.28, 0.2, 0.17, 0.35]))


        counter = Counter(trn_label)
        # print(counter)
        weight = len(trn_label)/np.array(list(counter.values()))/self.n_class
        
        self.out_dim = self.d_v * self.n_head + self.modal_num**2
        self.weight = torch.from_numpy(weight).float().to(dev)
        if self.MF_mode == 'sum':
            self.ModalFusion = VLTransformer_Gate(input_data_dims, hyperpm).to(dev)
        else:
            if self.hyperpm.lsp == False:
                self.ModalFusion = VLTransformer(input_data_dims, hyperpm).to(dev)
            else:
                self.ModalFusion = VLTransformer2(input_data_dims, hyperpm).to(dev)
        self.GraphConstruct = GraphLearn(self.out_dim, feat.shape[1], th=self.th, mode=self.GC_mode,hyperpm=self.hyperpm,input_data_dims=input_data_dims).to(dev)
        
        if self.MP_mode == 'GCN':
            self.MessagePassing = GCN(self.out_dim, self.out_dim // 2, self.n_class, self.dropout).to(dev)
        elif self.MP_mode == 'GAT':
            self.MessagePassing = GAT(self.out_dim, self.out_dim // 2, self.n_class, self.dropout, self.alpha, nheads = 2).to(dev)
        
        self.optimizer_MF = optim.Adam(self.ModalFusion.parameters(), lr=hyperpm.lr, weight_decay=hyperpm.reg)
        self.optimizer_GC = optim.Adam(self.GraphConstruct.parameters(), lr=hyperpm.lr, weight_decay=hyperpm.reg)
        self.optimizer_MP = optim.Adam(self.MessagePassing.parameters(), lr=hyperpm.lr, weight_decay=hyperpm.reg)
        
        self.ModalFusion.apply(my_weight_init)
        
    def run_epoch(self, mode, iteration_MF=10, iteration_GC=10, end = ''):
        dev = self.dev
        if mode == 'pre-train':
            self.ModalFusion.train()
            self.GraphConstruct.eval()
            self.MessagePassing.eval()
            
            self.optimizer_MF.zero_grad()
            prob, hidden, attn = self.ModalFusion(self.feat)
            #cls_loss = ClsLoss(prob, self.targ, self.trn_idx, self.weight)
            cls_loss = ClsLoss_noweight(prob, self.targ, self.trn_idx)
            cls_loss.backward()
            self.optimizer_MF.step()
            # print('trn-loss-MF: %.4f' % cls_loss, end=' ')

            
        if mode == 'simple-2':
            self.ModalFusion.train()
            self.GraphConstruct.eval()
            self.MessagePassing.eval()
            
            self.optimizer_MF.zero_grad()
            self.optimizer_GC.zero_grad()
            self.optimizer_MP.zero_grad()

            if self.hyperpm.lsp == False:
                prob, fusion_feat, attn = self.ModalFusion(self.feat)
                cls_loss = ClsLoss(prob, self.targ, self.trn_idx, self.weight)
            else:
                prob_x, prob_attn, fusion_feat, attn = self.ModalFusion(self.feat)
                cls_loss_x = ClsLoss(prob_x, self.targ, self.trn_idx, self.weight)  # Hsh
                cls_loss_attn = ClsLoss(prob_attn, self.targ, self.trn_idx, self.weight)  # Hsp
                cls_loss = cls_loss_attn + cls_loss_x
            cls_loss.backward()
            
            self.optimizer_MF.step()
            self.optimizer_GC.step()
            self.optimizer_MP.step()
            # print('trn-loss-MF: %.4f ' % cls_loss, end=' ')
            
            self.ModalFusion.eval()
            self.GraphConstruct.train()
            self.MessagePassing.train()
            
            self.optimizer_MF.zero_grad()
            self.optimizer_GC.zero_grad()
            self.optimizer_MP.zero_grad()

            if self.hyperpm.lsp == False:
                _, embedding, attn = self.ModalFusion(self.feat)
            else:
                _, _, embedding, attn = self.ModalFusion(self.feat)
            fusion_feat = embedding.detach()
            # adj,score = self.GraphConstruct(fusion_feat)
            if self.hyperpm.Denoising == True:
                adj, scores = self.GraphConstruct(fusion_feat, self.feat, "train")
            else:
                adj, scores = self.GraphConstruct(fusion_feat, self.feat)
            if self.hyperpm.lg == False:
                graph_loss = GraphConstructLoss(fusion_feat, adj, self.hyperpm.theta_smooth, self.hyperpm.theta_degree, self.hyperpm.theta_sparsity)
            normalized_adj = normalize_adj(adj + torch.eye(adj.size(0)).to(dev))
            prob, xx = self.MessagePassing(fusion_feat, normalized_adj)
            cls_loss = ClsLoss(prob, self.targ, self.trn_idx, self.weight)

            if self.hyperpm.lg == False:
                loss = cls_loss + graph_loss
            else:
                loss = cls_loss
            loss.backward()
            
            self.optimizer_GC.step()
            self.optimizer_MP.step()
            # print('trn-loss-G: %.4f'% (cls_loss), end=' ')


    
    def print_trn_acc(self, mode = 'pre-train'):
        # print('trn-', end='')
        trn_acc, trn_auc, targ_trn, pred_trn,trn_f1,trn_spe,trn_sen = self._print_acc(self.trn_idx, mode, end=' val-')
        val_acc, val_auc, targ_val, pred_val,val_f1,val_spe,val_sen = self._print_acc(self.val_idx, mode)
        #print('pred:',pred_val[:10], 'targ:',targ_val[:10])
        return trn_acc, val_acc

    def print_tst_acc(self, mode = 'pre-train'):
        # print('tst-', end='')
        tst_acc, tst_auc, targ_tst, pred_tst,tst_f1,tst_spe,tst_sen = self._print_acc(self.tst_idx, mode, tst=True)
        conf_mat = confusion_matrix(targ_tst.detach().cpu().numpy(), pred_tst.detach().cpu().numpy())
        return tst_acc, tst_auc, conf_mat,tst_f1,tst_spe,tst_sen
    
    def print_acc_share_sp(self, mode = 'pre-train'):
        self.ModalFusion.eval()
        self.GraphConstruct.eval()
        self.MessagePassing.eval()
        if mode == 'pre-train':
            prob, _, attn = self.ModalFusion(self.feat)
        else:
            prob_MF, fusion_feat, attn = self.ModalFusion(self.feat)
            adj,score = self.GraphConstruct(fusion_feat, self.feat)
            _adj = adj.clone().detach()
            adj = normalize_adj(adj + torch.eye(adj.size(0)).to(self.dev))
            if self.hyperpm.datname == 'TADPOLE':
                supplement_share = torch.zeros(fusion_feat[:, -36:].shape).to(fusion_feat.device)
                supplement_sp = torch.zeros(fusion_feat[:, :-36].shape).to(fusion_feat.device)
                shared_emb = torch.cat((fusion_feat[:, :-36], supplement_share), dim=-1)
                sp_emb = torch.cat((fusion_feat[:, -36:], supplement_sp), dim=-1)
                shared_prob, xx = self.MessagePassing(shared_emb, adj)
                sp_prob, xx = self.MessagePassing(sp_emb, adj)
            elif self.hyperpm.datname == 'ABIDE':
                supplement_share = torch.zeros(fusion_feat[:, -16:].shape).to(fusion_feat.device)
                supplement_sp = torch.zeros(fusion_feat[:, :-16].shape).to(fusion_feat.device)
                shared_emb = torch.cat((fusion_feat[:, :-16], supplement_share), dim=-1)
                sp_emb = torch.cat((fusion_feat[:, -16:], supplement_sp), dim=-1)
                shared_prob, xx = self.MessagePassing(shared_emb, adj)
                sp_prob, xx = self.MessagePassing(sp_emb, adj)
        
            shared_acc, shared_auc, targ, pred = self.acc_compute(shared_prob, self.tst_idx)
            sp_acc, sp_auc, targ, pred = self.acc_compute(sp_prob, self.tst_idx)
            conf_mat = confusion_matrix(targ.detach().cpu().numpy(), pred.detach().cpu().numpy())
        
        return shared_acc, shared_auc, sp_acc, sp_auc, conf_mat
    
    def acc_compute(self, prob, eval_idx):
        prob = prob[eval_idx]
        targ = self.targ[eval_idx]
        pred = prob.max(1)[1].type_as(targ)
        acc = pred.eq(targ).double().sum() / len(targ)
        acc = acc.item()
        auc = roc_auc_score(one_hot(targ, self.n_class).cpu().numpy(), one_hot(pred, self.n_class).cpu().numpy())
        return acc, auc, targ, pred

    def _print_acc(self, eval_idx, mode, tst = False, end='\n'):
        self.ModalFusion.eval()
        self.GraphConstruct.eval()
        self.MessagePassing.eval()
        if mode == 'pre-train':
            prob, _, attn = self.ModalFusion(self.feat)
        else:
            if self.hyperpm.lsp == False:
                prob_MF, fusion_feat, attn = self.ModalFusion(self.feat)
            else:
                prob_MF_x, prob_MF_attn, fusion_feat, attn = self.ModalFusion(self.feat)
            adj,score = self.GraphConstruct(fusion_feat, self.feat)
            _adj = adj.clone().detach()
            _score = score.clone().detach()
            adj = normalize_adj(adj + torch.eye(adj.size(0)).to(self.dev))
            prob, xx = self.MessagePassing(fusion_feat, adj)
        prob = prob[eval_idx]
        targ = self.targ[eval_idx]
        pred = prob.max(1)[1].type_as(targ)
        prob_cali = prob[:,1]

        acc = pred.eq(targ).double().sum() / len(targ)
        acc = acc.item()
        conf_matrix = confusion_matrix(targ.cpu(), pred.cpu())
        tn, fp, fn, tp = conf_matrix.ravel()

        spe = tn / (tn + fp)
        sen = tp / (tp + fn)

        auc = roc_auc_score(one_hot(targ, self.n_class).cpu().numpy(), one_hot(pred, self.n_class).cpu().numpy())
        f1 = f1_score(targ.cpu().numpy(), pred.cpu().numpy(), average='weighted')
        # print('auc: %.4f  acc: %.4f f1: %.4f' % (auc, acc, f1), end=end)
        if tst == True and mode != 'pre-train':

            
            # print('attention maps have been saved.')
            np.save('./attn/attn_map_{}_.npy'.format(self.hyperpm.datname), attn)
            np.savez('./graph/{}_{}_graph_'.format(self.hyperpm.datname, self.GC_mode),
                     adj=_adj.detach().cpu().numpy(),
                     score=_score.detach().cpu().numpy(),
                     feat=self.feat.detach().cpu().numpy(), 
                     fused=fusion_feat.detach().cpu().numpy(), 
                     embedding = xx.detach().cpu().numpy(), 
                     label = self.targ.detach().cpu().numpy())
        return acc, auc, targ, pred,f1,spe,sen
    
    def cal_acc(self, eval_idx):
        self.ModalFusion.eval()
        self.GraphConstruct.eval()
        self.MessagePassing.eval()
        prob, fusion_feat, attn = self.ModalFusion(self.feat)
        adj = self.GraphConstruct(fusion_feat)
        adj = normalize_adj(adj + torch.eye(adj.size(0)).to(self.dev))
        prob, xx = self.MessagePassing(fusion_feat, adj)
        prob = prob[eval_idx]
        targ = self.targ[eval_idx]
        pred = prob.max(1)[1].type_as(targ)
        acc = pred.eq(targ).double().sum() / len(targ)
        acc = acc.item()
        return acc
    
    def visualize(self, sav_prefix):
        
        self.ModalFusion.eval()
        self.GraphConstruct.eval()
        self.MessagePassing.eval()
        
        prob_MF, fusion_feat, attn = self.ModalFusion(self.feat)
        adj_o = self.GraphConstruct(fusion_feat)
        adj = normalize_adj(adj_o + torch.eye(adj_o.size(0)).to(self.dev))
        prob, xx = self.MessagePassing(fusion_feat, adj)
        prob = prob[eval_idx]
        targ = self.targ[eval_idx]
        pred = prob.max(1)[1].type_as(targ)
        acc = pred.eq(targ).double().sum() / len(targ)
        acc = acc.item()
   
        g = nx.from_numpy_matrix(adj_o)
        n = self.feat.size(0)
        
        acc = [('.' if c else '?') for c in acc.astype(dtype=np.bool)]
        sets = np.zeros(n, dtype=np.float32)
        sets[self.trn_idx.cpu()] = 0
        sets[self.val_idx.cpu()] = 1
        sets[self.tst_idx.cpu()] = 2
        pos_gml = sav_prefix + '.gml'
        visualize_as_gdf(g, sav_prefix, list(range(n)), targ, pos_gml)
        visualize_as_gdf(g, sav_prefix + '_set', acc, sets, pos_gml)
        visualize_as_gdf(g, sav_prefix + '_trg', acc, targ, pos_gml)
        
        
        