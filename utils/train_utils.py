#!/usr/bin/env python
# coding: utf-8
# Autor: Mario Xavier Canche Uc
# Centro de Investigación en Matemáticas, A.C.
# mario.canche@cimat.mx

# Cargamos las librerias
import time
import sys,os,logging, argparse
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
from models.bayesian_models_gaussian_loss import lstm_encdec
from utils.datasets_utils import Experiment_Parameters, setup_loo_experiment, traj_dataset
from utils.plot_utils import plot_traj_img,plot_traj_world,plot_cov_world
import torch.optim as optim


# Function to train the models
def train(model,device,ind,idTest,train_data,val_data,args):
    # Optimizer
    # optimizer = optim.SGD(model.parameters(), lr=initial_lr)
    optimizer = optim.Adam(model.parameters(),lr=args.learning_rate, betas=(.5, .999),weight_decay=0.8)
    list_loss_train = []
    list_loss_val   = []
    min_val_error   = 1000.0
    for epoch in range(args.epochs):
        # Training
        print("----- ")
        print("Epoch: ", epoch)
        error = 0
        total = 0
        # Recorremos cada batch
        for batch_idx, (data, target, data_abs , target_abs) in enumerate(train_data):
            # Remember that Pytorch accumulates gradients.
            # We need to clear them out before each instance
            model.zero_grad()
            if torch.cuda.is_available():
              data  = data.to(device)
              target=target.to(device)
              data_abs  = data_abs.to(device)
              target_abs=target_abs.to(device)

            # Run our forward pass and compute the loss
            loss   = model(data, target, data_abs , target_abs)# , training=True)
            error += loss
            total += len(target)

            # Step 3. Compute the gradients, and update the parameters by
            loss.backward()
            optimizer.step()
        print("Trn loss: ", error.detach().cpu().numpy()/total)
        list_loss_train.append(error.detach().cpu().numpy()/total)

        # Validation
        error = 0
        total = 0
        for batch_idx, (data_val, target_val, data_abs , target_abs) in enumerate(val_data):

            if torch.cuda.is_available():
              data_val  = data_val.to(device)
              target_val = target_val.to(device)
              data_abs  = data_abs.to(device)
              target_abs = target_abs.to(device)

            loss_val = model(data_val, target_val, data_abs , target_abs)
            error += loss_val
            total += len(target_val)
        error = error.detach().cpu().numpy()/total
        print("Val loss: ", error)
        list_loss_val.append(error)
        if error<min_val_error:
            min_val_error = error
            # Keep the model
            print("Saving model")
            torch.save(model.state_dict(), "training_checkpoints/model_deterministic_"+str(ind)+"_"+str(idTest)+".pth")

    # Visualizamos los errores
    plt.figure(figsize=(12,12))
    plt.plot(list_loss_train, label="loss train")
    plt.plot(list_loss_val, label="loss val")
    plt.xlabel("Epochs")
    plt.ylabel("Loss")
    plt.legend()
