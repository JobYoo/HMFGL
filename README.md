# Hybrid Multimodal Fusion for Graph Learning in Disease Prediction(HMFGL)

This is a PyTorch version of HMFGL model as proposed in our paper.

## Introduction

Graph neural networks (GNNs) have gained significant attention in disease prediction where the node represents users' latent features and the edge denotes the similarity relationship between two users. The graph plays a crucial role in graph learning by determining information aggregation and propagation. However, recent methods typically construct graphs based on user's latent embeddings, which may not accurately reflect real-world connections. We observe meta data (e.g., demographic attributes, genetic markers) provide abundant information to gauge user similarities, and could compensate the weakness of graph construction from latent representation. Therefore, we propose to combine graphs learned from patient meta data and multimodal representation through a weighted summation.  Considering the graphs could include irrelevant and noisy connections, we employ the degree-sensitive edge pruning and KNN sparsification to sparsify and prune such edges.

For more details about HMFGL, please refer to our paper [[TMI](https://ieeexplore.ieee.org/abstract/document/9733917)] [[Arxiv](https://arxiv.org/abs/2203.05880)].

![HMFGL](https://github.com/JobYoo/HMFGL/assets/153283474/5b04258d-09c1-47ba-ba99-30761c15b690)

## Requirements

* PyTorch = 1.9.1
* python 3.6
* networkx
* scikit-learn
* scipy
* munkres

## Code running

### Step 1: Data prprocessing

Running the code of data preprocessing in ./data/{dataset}/xxx.ipynb to preprocess the raw data to standard data as the input of HMFGL.

The download link for the TADPOLE dataset is https://tadpole.grand-challenge.org/Data/.

### Step 2: Training and test

Running

```
./{dataset}-simple-2-concat-weighted-cosine.sh
```

## Data

The data preprocessing process are provided in [[./data/{dataset}](https://github.com/JobYoo/MMGL/blob/main/data/)].

If you want to use your own data, you have to provide :

* a csv.file which contains multi-modal features, and
* a multi-modal feature dict.

If you find our work useful, please consider citing： 

```

```
