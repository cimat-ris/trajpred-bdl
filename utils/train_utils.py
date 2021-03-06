#!/usr/bin/env python
# coding: utf-8
# Autor: Mario Xavier Canche Uc
# Centro de Investigación en Matemáticas, A.C.
# mario.canche@cimat.mx

# Cargamos las librerias
import time
import sys,os,logging,argparse
sys.path.append('.')
import math,numpy as np
import matplotlib as mpl
mpl.use('TkAgg')  # or whatever other backend that you want
import matplotlib.pyplot as plt
import pandas as pd

import torch
from torchvision import transforms
import torch.optim as optim

# Local models
from utils.datasets_utils import Experiment_Parameters, setup_loo_experiment, traj_dataset
from utils.plot_utils import plot_traj_img,plot_traj_world,plot_cov_world
from utils.directory_utils import mkdir_p
import torch.optim as optim

# Local constants
from utils.constants import IMAGES_DIR, TRAINING_CKPT_DIR

# Function to train the models
def train(model,device,ind,train_data,val_data,args,model_name):
    # Optimizer
    # optimizer = optim.SGD(model.parameters(), lr=initial_lr)
    optimizer = optim.Adam(model.parameters(),lr=args.learning_rate, betas=(.5, .999),weight_decay=0.003)
    list_loss_train = []
    list_loss_val   = []
    min_val_error   = 1000.0
    for epoch in range(args.epochs):
        # Training
        logging.info("----- ")
        logging.info("Epoch: {}".format(epoch))
        error = 0
        total = 0
        # Recorremos cada batch
        for batch_idx, (observations_vel, target_vel, observations_abs , target_abs) in enumerate(train_data):
            # Remember that Pytorch accumulates gradients.
            # We need to clear them out before each instance
            model.zero_grad()
            if torch.cuda.is_available():
              observations_vel = observations_vel.to(device)
              target_vel       = target_vel.to(device)
              observations_abs = observations_abs.to(device)
              target_abs       = target_abs.to(device)

            # Run our forward pass and compute the loss
            loss   = model(observations_vel, target_vel, observations_abs , target_abs, teacher_forcing=args.teacher_forcing)
            error += loss
            total += len(target_vel)

            # Step 3. Compute the gradients, and update the parameters by
            loss.backward()
            optimizer.step()
        logging.info("Trn loss: {:.4f}".format(error.detach().cpu().numpy()/total))
        list_loss_train.append(error.detach().cpu().numpy()/total)

        # Validation
        error = 0
        total = 0
        ade   = 0
        fde   = 0
        for batch_idx, (data_val, target_val, data_abs , target_abs) in enumerate(val_data):

            if torch.cuda.is_available():
              data_val  = data_val.to(device)
              target_val = target_val.to(device)
              data_abs  = data_abs.to(device)
              target_abs = target_abs.to(device)

            loss_val = model(data_val, target_val, data_abs , target_abs)
            error   += loss_val
            total   += len(target_val)
            # prediction
            init_pos  = np.expand_dims(data_abs.cpu().numpy()[:,-1,:],axis=1)
            pred_val  = model.predict(data_val, dim_pred=12)
            if len(pred_val)==2:
                pred_val = pred_val[0]
            pred_val += init_pos
            ade    = ade + np.sum(np.average(np.sqrt(np.square(target_abs.cpu().numpy()-pred_val).sum(2)),axis=1))
            fde    = fde + np.sum(np.sqrt(np.square(target_abs.cpu().numpy()[:,-1,:]-pred_val[:,-1,:]).sum(1)))

        error = error.detach().cpu().numpy()/total
        ade   = ade/total
        fde   = fde/total
        logging.info("Val loss: {:.4f} ".format(error))
        logging.info("Val ade : {:.4f} ".format(ade))
        logging.info("Val fde : {:.4f} ".format(fde))
        list_loss_val.append(error)
        if error<min_val_error:
            min_val_error = error
            # Keep the model
            logging.info("Saving model")
            torch.save(model.state_dict(), TRAINING_CKPT_DIR+"/"+model_name+"_"+str(ind)+"_"+str(args.id_test)+".pth")

    # Error visualization
    if args.plot_losses:
        # Create new directory
        output_dir = os.path.join(IMAGES_DIR, "loss_" + model_name)
        mkdir_p(output_dir)

        plt.figure(figsize=(12,12))
        plt.plot(list_loss_train, label="loss train")
        plt.plot(list_loss_val, label="loss val")
        plt.xlabel("Epochs")
        plt.ylabel("Loss")
        plt.legend()
        plt.savefig(os.path.join(output_dir , str(ind)+"_"+str(args.id_test)+".pdf"))
        plt.show()
