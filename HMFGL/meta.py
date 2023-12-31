#
# This is the script I use to tune the hyper-parameters automatically.
#
import subprocess
import argparse
import hyperopt

min_y = 0
min_c = None



def trial(hyperpm):
    global min_y, min_c
    # Plz set nbsz manually. Maybe a larger value if you have a large memory.
    cmd = 'python main.py'
    for k in hyperpm:
        v = hyperpm[k]
        cmd += ' --' + k
        
        if isinstance(v, str):
            cmd += ' %s' %v
        elif int(v) == v:
            cmd += ' %d' % int(v)
        else:
            cmd += ' %g' % float('%.1e' % float(v))
    try:
        val, tst = eval(subprocess.check_output(cmd, shell=True))
    except subprocess.CalledProcessError:
        print('...')
        return {'loss': 0, 'status': hyperopt.STATUS_FAIL}
    print('val=%5.2f%% @ %s' % (val * 100, cmd))
    print('>>>>>>>>>> min val now=%5.2f%% @ %s' % (-min_y * 100, min_c))
    score = -val
    if score < min_y:
        min_y, min_c = score, cmd
        f= open("logger-{}-{}-{}-{}.txt".format(args.datname, args.mode, args.MF_mode, args.GC_mode),"a+")
        f.write('>>>>>>>>>> min val now=%5.2f%% @ %s\n' % (-min_y * 100, min_c))
        f.close()
    
    return {'loss': score, 'status': hyperopt.STATUS_OK}


parser = argparse.ArgumentParser()
parser.add_argument('--datname', type=str, default='ABIDE',
                    help='ABIDE,TADPOLE')
parser.add_argument('--mode', type=str, default='simple-2',
                    help='strategy')
parser.add_argument('--MF_mode', type=str, default='concat',
                    help='strategy')
parser.add_argument('--GC_mode', type=str, default='weighted-cosine',
                    help='strategy')
parser.add_argument('--MP_mode', type=str, default='GCN',
                    help='strategy')
args = parser.parse_args()
space = {'lr': hyperopt.hp.loguniform('lr', -8, 0),
         'reg': hyperopt.hp.loguniform('reg', -10, 0),
         'nlayer': hyperopt.hp.quniform('nlayer', 1, 5, 1),
         'n_hidden': hyperopt.hp.quniform('n_hidden', 8, 32, 2),
         'n_head': hyperopt.hp.quniform('n_head', 2, 12, 2),
         'dropout': hyperopt.hp.quniform('dropout', 0, 0.9, 0.05),
        'kNum': hyperopt.hp.quniform('kNum', 5, 200, 5),

         'mode': args.mode,
         'MF_mode': args.MF_mode,
         'MP_mode': args.MP_mode,
         'GC_mode': args.GC_mode,
        'datname': args.datname}
hyperopt.fmin(trial, space, algo=hyperopt.tpe.suggest, max_evals=1250)
print('>>>>>>>>>> val=%5.2f%% @ %s' % (-min_y * 100, min_c))