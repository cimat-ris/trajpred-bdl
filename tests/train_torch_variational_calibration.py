#!/usr/bin/env python
# coding: utf-8
# Autor: Mario Xavier Canche Uc
# Centro de Investigación en Matemáticas, A.C.
# mario.canche@cimat.mx

# Cargamos las librerias
import time
import sys,os,logging, argparse
''' TF_CPP_MIN_LOG_LEVEL
0 = all messages are logged (default behavior)
1 = INFO messages are not printed
2 = INFO and WARNING messages are not printeds
3 = INFO, WARNING, and ERROR messages are not printed
'''
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
sys.path.append('../bayesian-torch')
sys.path.append('..')

import math,numpy as np
import matplotlib.pyplot as plt
import pandas as pd

import torch
from torchvision import transforms
import torch.optim as optim

# Local models
from models.bayesian_models_gaussian_loss import lstm_encdec_variational
from utils.datasets_utils import Experiment_Parameters, setup_loo_experiment, traj_dataset
from utils.plot_utils import plot_traj
from utils.calibration import calibration
from utils.calibration import miscalibration_area, mean_absolute_calibration_error, root_mean_squared_calibration_error


# In[ ]:


logging.basicConfig(format='%(levelname)s: %(message)s',level=20)
# GPU
if torch.cuda.is_available():
    logging.info(torch.cuda.get_device_name(torch.cuda.current_device()))


# In[ ]:


# Load the default parameters
experiment_parameters = Experiment_Parameters(add_kp=False,obstacles=False)

dataset_dir   = "../datasets/"
dataset_names = ['eth-hotel','eth-univ','ucy-zara01','ucy-zara02','ucy-univ']
idTest        = 2
pickle        = False

# parameters models
num_epochs     = 20
initial_lr     = 0.000002
batch_size     = 64
num_mc = 5
band_train = True


# In[ ]:


prior_mu = 0.0
prior_sigma = 1.0
posterior_mu_init = 0.0
posterior_rho_init = -4


# In[ ]:


# Load the dataset and perform the split
training_data, validation_data, test_data, test_homography = setup_loo_experiment('ETH_UCY',dataset_dir,dataset_names,idTest,experiment_parameters,pickle_dir='../pickle',use_pickled_data=pickle)


# In[ ]:


# Creamos el dataset para torch
train_data = traj_dataset(training_data['obs_traj_rel'], training_data['pred_traj_rel'],training_data['obs_traj'], training_data['pred_traj'])
val_data = traj_dataset(validation_data['obs_traj_rel'], validation_data['pred_traj_rel'],validation_data['obs_traj'], validation_data['pred_traj'])
test_data = traj_dataset(test_data['obs_traj_rel'], test_data['pred_traj_rel'], test_data['obs_traj'], test_data['pred_traj'])


# In[ ]:


# Form batches
batched_train_data = torch.utils.data.DataLoader( train_data, batch_size = batch_size, shuffle=False)
batched_val_data =  torch.utils.data.DataLoader( val_data, batch_size = batch_size, shuffle=False)
batched_test_data =  torch.utils.data.DataLoader( test_data, batch_size = batch_size, shuffle=False)


# ## Entrenamos el modelo

# In[ ]:


# Model
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = lstm_encdec_variational(2,128,256,2,prior_mu,prior_sigma,posterior_mu_init,posterior_rho_init)
model.to(device)


# In[ ]:


import torch.optim as optim

if band_train:
    seed = 1
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    
    # Training the Model
    optimizer = optim.SGD(model.parameters(), lr=initial_lr)

    num_mc = 5

#    nl_loss_ = []
#    kl_loss_ = []
    list_loss_train = []
    list_loss_val = []
    for epoch in range(num_epochs):
        # Training
        print("----- ")
        print("epoch: ", epoch)
        error = 0
        total = 0
        M     = len(batched_train_data)
        for batch_idx, (data, target, data_abs, target_abs) in enumerate(batched_train_data):
            # Step 1. Remember that Pytorch accumulates gradients.
            # We need to clear them out before each instance
            model.zero_grad()

            if torch.cuda.is_available():
                data  = data.to(device)
                target=target.to(device)
                data_abs  = data_abs.to(device)
                target_abs=target_abs.to(device)

            # Step 2. Run our forward pass and compute the losses
            pred, nl_loss, kl_loss = model(data, target, data_abs , target_abs, num_mc=num_mc)
            
            # TODO: Divide by the batch size
            loss   = nl_loss+ kl_loss/M
            error += loss.detach().item()
            total += len(target)

            # Step 3. Compute the gradients, and update the parameters by
            loss.backward()
            optimizer.step()
        print("Average training loss: {:.3e}".format(error/total))
        #list_loss_train.append(error.detach().cpu().numpy()/total)
        print(error)
        list_loss_train.append(error/total)

        # Validation
        error = 0
        total = 0
        M     = len(batched_val_data)
        for batch_idx, (data_val, target_val, data_abs , target_abs) in enumerate(batched_val_data):
            if torch.cuda.is_available():
                data_val  = data_val.to(device)
                target_val=target_val.to(device)
                data_abs  = data_abs.to(device)
                target_abs = target_abs.to(device)

            pred_val, nl_loss, kl_loss = model(data_val, target_val, data_abs , target_abs)
            pi     = (2.0**(M-batch_idx))/(2.0**M-1) # From Blundell
            loss   = nl_loss+ pi*kl_loss
            error += loss.detach().item()
            total += len(target_val)

        print("Average validation loss: {:.3e}".format(error/total))
        list_loss_val.append(error/total)
    
    # Visualizamos los errores
    plt.figure(figsize=(12,12))
    plt.plot(list_loss_train, label="loss train")
    plt.plot(list_loss_val, label="loss val")
    plt.xlabel("Epochs")
    plt.ylabel("Loss")
    plt.legend()
    
    # Guardamos el Modelo
    torch.save(model.state_dict(), "../training_checkpoints/model_variational_"+str(idTest)+".pth")


# ## Visualizamos las predicciones

# In[ ]:


# Instanciamos el modelo
model = lstm_encdec_variational(2,128,256,2,prior_mu,prior_sigma,posterior_mu_init,posterior_rho_init)
# Cargamos el modelo
model.load_state_dict(torch.load("../training_checkpoints/model_variational_"+str(idTest)+".pth"))
model.to(device)
model.eval()


# In[ ]:


ind_sample = 1
num_monte_carlo = 20

bck = plt.imread(os.path.join(dataset_dir,dataset_names[idTest],'reference.png'))

# Testing
for batch_idx, (datarel_test, targetrel_test, data_test, target_test) in enumerate(batched_test_data):
    
    plt.figure(figsize=(12,12))
    plt.imshow(bck)

    # prediction
    for ind in range(num_monte_carlo):
        
        if torch.cuda.is_available():
              datarel_test  = datarel_test.to(device)

        pred, kl, sigmas = model.predict(datarel_test, dim_pred=12)

        # ploting
        plot_traj(pred[ind_sample,:,:], data_test[ind_sample,:,:], target_test[ind_sample,:,:], test_homography, bck)
    plt.legend()
    plt.title('Trajectory samples')
    plt.show()
    # Solo aplicamos a un elemento del batch
    break


# ## Calibramos la incertidumbre

# In[ ]:


draw_ellipse = True
num_monte_carlo = 20

# Testing
cont = 0
for batch_idx, (datarel_test, targetrel_test, data_test, target_test) in enumerate(batched_test_data):
    
    tpred_samples = []
    sigmas_samples = []
    # Muestreamos con cada modelo
    for ind in range(num_monte_carlo):

        if torch.cuda.is_available():
              datarel_test  = datarel_test.to(device)

        pred, kl, sigmas = model.predict(datarel_test, dim_pred=12)

        tpred_samples.append(pred)
        sigmas_samples.append(sigmas)

    plt.show()
    
    tpred_samples = np.array(tpred_samples)
    sigmas_samples = np.array(sigmas_samples)

    # HDR y Calibracion
    auc_cal, auc_unc, exp_proportions, obs_proportions_unc, obs_proportions_cal = calibration(tpred_samples, data_test, target_test, sigmas_samples, position = 11, alpha = 0.05, idTest=idTest)
    plt.show()

    # Solo se ejecuta para un batch
    break


# ## Metrics Calibration

# In[ ]:


ma1 = miscalibration_area(exp_proportions, obs_proportions_unc)
mace1 = mean_absolute_calibration_error(exp_proportions, obs_proportions_unc)
rmsce1 = root_mean_squared_calibration_error(exp_proportions, obs_proportions_unc)

print("Before Recalibration:  ", end="")
print("MACE: {:.5f}, RMSCE: {:.5f}, MA: {:.5f}".format(mace1, rmsce1, ma1))


# In[ ]:


ma2 = miscalibration_area(exp_proportions, obs_proportions_cal)
mace2 = mean_absolute_calibration_error(exp_proportions, obs_proportions_cal)
rmsce2 = root_mean_squared_calibration_error(exp_proportions, obs_proportions_cal)

print("After Recalibration:  ", end="")
print("MACE: {:.5f}, RMSCE: {:.5f}, MA: {:.5f}".format(mace2, rmsce2, ma2))


# In[ ]:


df = pd.DataFrame([["","MACE","RMSCE","MA"],["Before Recalibration", mace1, rmsce1, ma1],["After Recalibration", mace2, rmsce2, ma2]])
df.to_csv("images/metrics_calibration_"+str(idTest)+".csv")

