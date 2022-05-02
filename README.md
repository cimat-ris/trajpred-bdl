# trajpred-bdl

To train the deterministic model:

```
python tests/train_torch_deterministic.py 
```

To train the deterministic model with variances as output:

```
 python3 tests/train_torch_deterministic_with_variances.py
```

To train the ensemble model and calibrate the uncertainties:

```
python tests/train_torch_ensembles_calibration.py
```
