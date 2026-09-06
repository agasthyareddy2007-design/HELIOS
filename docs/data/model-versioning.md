# HELIOS Model Versioning and Checkpointing

## Overview

HELIOS uses semantic versioning for trained models, with comprehensive checkpoint artifacts that enable rollback, reproducibility, and audit trails.

## Version Naming Convention

```
helios-{major}.{minor}[.{patch}][-{pre-release}]
```

**Examples**:
- `helios-0.1` - Initial MVP model
- `helios-0.2` - Second iteration with expanded data
- `helios-1.0` - Production-ready release
- `helios-1.1-rc1` - Release candidate
- `helios-2.0-beta` - Major architecture change beta

### Version Incrementing Rules

**Major version** (X.0):
- Architectural changes (new ML approach, different feature engineering)
- Breaking changes to inference API
- Incompatible checkpoint format changes

**Minor version** (x.Y):
- Expanded training data (1 year → 2 years)
- New features or variables
- Hyperparameter retuning
- Performance improvements
- Backward-compatible changes

**Patch version** (x.y.Z):
- Bug fixes
- Minor improvements
- Retraining on same data with same configuration

**Pre-release suffixes**:
- `-alpha` - Early experimental
- `-beta` - Feature-complete, testing
- `-rc1`, `-rc2` - Release candidates

## Checkpoint Structure

Each model version has a complete checkpoint directory:

```
models/checkpoints/helios-0.2/
├── metadata.json              # Training metadata
├── config.json               # Model configuration
├── hyperparameters.json      # Hyperparameter values
├── feature_config.json       # Feature engineering configuration
├── preprocessing.pkl         # Scikit-learn preprocessing pipelines
├── kernel/                   # Kernel regression artifacts
│   ├── model.pkl
│   ├── bandwidth.json
│   └── feature_weights.npy
├── xgboost/                  # XGBoost artifacts
│   ├── model.json
│   ├── model.ubj
│   └── feature_importance.json
├── mlp/                      # PyTorch MLP artifacts
│   ├── model.pt
│   ├── model_state_dict.pt
│   ├── optimizer_state.pt
│   └── architecture.json
├── metrics/                  # Evaluation results
│   ├── train_metrics.json
│   ├── val_metrics.json
│   ├── test_metrics.json
│   └── comparison.json
├── plots/                    # Visualization artifacts
│   ├── learning_curve.png
│   ├── residual_plot.png
│   ├── feature_importance.png
│   └── performance_by_lead_time.png
└── README.md                 # Human-readable summary
```

## metadata.json Schema

```json
{
  "version": "helios-0.2",
  "model_type": "xgboost",
  "created_at": "2026-09-06T12:00:00Z",
  "created_by": "user@example.com",
  "git_commit": "a1b2c3d4e5f6",
  "git_branch": "main",
  "git_dirty": false,
  
  "training_period": {
    "start": "1979-01-01",
    "end": "2004-12-31",
    "duration_years": 26
  },
  
  "validation_period": {
    "start": "2005-01-01",
    "end": "2014-12-31",
    "duration_years": 10
  },
  
  "test_period": {
    "start": "2015-01-01",
    "end": "2024-12-31",
    "duration_years": 10
  },
  
  "data_sources": {
    "gfs": "16.3",
    "ecmwf": "47r3",
    "icon": "2.6.4",
    "ukmo": "15.1",
    "gem": "5.2",
    "era5": "v1",
    "nasa_power": "v9"
  },
  
  "dataset": {
    "total_samples": 9467280,
    "train_samples": 6552496,
    "val_samples": 1473292,
    "test_samples": 1441492,
    "variables": ["temperature_2m", "dewpoint_2m", "wind_speed_10m"],
    "locations": 120,
    "max_lead_time_hours": 168
  },
  
  "training_environment": {
    "python_version": "3.10.12",
    "cuda_version": "12.1",
    "gpu": "NVIDIA RTX 5080",
    "os": "Linux 6.5.0"
  },
  
  "training_duration": {
    "wall_clock_hours": 4.5,
    "gpu_hours": 4.5
  },
  
  "previous_version": "helios-0.1",
  "next_version": null,
  
  "deployment_status": "champion",
  "deployed_at": "2026-09-06T18:30:00Z"
}
```

## config.json Schema

```json
{
  "model_type": "xgboost",
  "target_variable": "temperature_2m",
  "loss_function": "mae",
  
  "features": {
    "nwp_models": ["gfs", "ecmwf", "icon", "ukmo", "gem"],
    "temporal": ["hour", "day_of_year", "lead_time_hours"],
    "spatial": ["latitude", "longitude", "elevation"],
    "ensemble": ["mean", "std", "spread", "disagreement"],
    "historical": ["model_mae_7d", "model_bias_7d"],
    "climatology": ["era5_mean", "era5_std", "anomaly"],
    "auxiliary": ["nasa_temp", "nasa_humidity"]
  },
  
  "preprocessing": {
    "scaler": "StandardScaler",
    "categorical_encoding": "one-hot",
    "missing_value_strategy": "drop",
    "outlier_removal": "iqr"
  },
  
  "validation_strategy": {
    "method": "time_series_split",
    "n_splits": 5,
    "test_size": 0.15
  }
}
```

## hyperparameters.json Schema

```json
{
  "xgboost": {
    "objective": "reg:squarederror",
    "eval_metric": ["mae", "rmse"],
    "max_depth": 6,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 1,
    "gamma": 0,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "tree_method": "gpu_hist",
    "gpu_id": 0,
    "early_stopping_rounds": 50,
    "random_state": 42
  },
  
  "mlp": {
    "architecture": [256, 128, 64],
    "activation": "relu",
    "dropout": 0.2,
    "batch_size": 512,
    "learning_rate": 0.001,
    "weight_decay": 0.0001,
    "optimizer": "adamw",
    "scheduler": "reduce_lr_on_plateau",
    "scheduler_patience": 10,
    "scheduler_factor": 0.5,
    "max_epochs": 100,
    "early_stopping_patience": 15
  },
  
  "kernel": {
    "kernel_type": "gaussian",
    "bandwidth": "scott",
    "bandwidth_value": 0.5,
    "distance_metric": "euclidean",
    "n_neighbors": 1000
  },
  
  "optimization": {
    "method": "optuna",
    "n_trials": 100,
    "optimization_metric": "val_mae",
    "direction": "minimize",
    "sampler": "tpe",
    "pruner": "median"
  }
}
```

## Metrics Schema

```json
{
  "overall": {
    "mae": 1.234,
    "rmse": 1.789,
    "bias": -0.123,
    "r2": 0.912,
    "samples": 1441492
  },
  
  "by_lead_time": [
    {
      "lead_time_hours": 6,
      "mae": 0.89,
      "rmse": 1.23,
      "samples": 240248
    },
    {
      "lead_time_hours": 24,
      "mae": 1.12,
      "rmse": 1.56,
      "samples": 240248
    }
  ],
  
  "by_season": [
    {
      "season": "winter",
      "mae": 1.45,
      "rmse": 2.01,
      "samples": 360373
    },
    {
      "season": "summer",
      "mae": 1.08,
      "rmse": 1.52,
      "samples": 360373
    }
  ],
  
  "by_location_type": [
    {
      "type": "coastal",
      "mae": 1.15,
      "rmse": 1.67
    },
    {
      "type": "inland",
      "mae": 1.31,
      "rmse": 1.88
    }
  ],
  
  "baseline_comparison": {
    "gfs_mae": 1.89,
    "ecmwf_mae": 1.67,
    "icon_mae": 1.92,
    "simple_mean_mae": 1.56,
    "helios_improvement_vs_best_nwp": "26.3%",
    "helios_improvement_vs_simple_mean": "20.9%"
  }
}
```

## Champion Model Management

Only ONE model version is the "champion" at any time - the production model serving live forecasts.

### Champion Selection Criteria

A new model becomes champion ONLY if:

1. **Better validation performance** - Lower MAE/RMSE than current champion on held-out validation set
2. **Better test performance** - Confirmed improvement on completely unseen test period
3. **Consistent across stratifications** - Not worse on any critical stratification (lead time, season, location)
4. **No regressions** - Does not degrade performance on any baseline comparison
5. **Stable predictions** - Similar confidence intervals, no erratic behavior
6. **Manual approval** - Human verification of metrics and behavior

### Champion Deployment Process

```bash
# 1. Train new model
python scripts/train_model.py --version helios-0.3

# 2. Evaluate on test set
python scripts/evaluate_model.py \
    --checkpoint models/checkpoints/helios-0.3 \
    --test-period 2015-2024

# 3. Compare against champion
python scripts/compare_models.py \
    --challenger models/checkpoints/helios-0.3 \
    --champion models/champion

# 4. If better, run shadow deployment
python scripts/shadow_deploy.py \
    --version helios-0.3 \
    --duration-days 7

# 5. If shadow confirms improvement, promote
python scripts/promote_champion.py \
    --version helios-0.3
```

### Champion Directory

```
models/champion/  -> symlink to models/checkpoints/helios-0.2/
```

The `champion` directory is a symlink to the current production model. This allows:
- Fast rollback (repoint symlink)
- Clear production state
- Version-agnostic inference code

### Deployment Record

Every champion promotion is logged in the database:

```sql
INSERT INTO model_deployments (
    model_version,
    deployment_type,
    deployed_at,
    deployed_by,
    validation_mae,
    test_mae
) VALUES (
    'helios-0.3',
    'champion',
    NOW(),
    'user@example.com',
    1.123,
    1.234
);
```

## Rollback Procedure

If the new champion underperforms in production:

```bash
# 1. Stop inference
systemctl stop helios-inference

# 2. Repoint champion symlink
rm models/champion
ln -s checkpoints/helios-0.2 models/champion

# 3. Update database
python scripts/rollback_champion.py --to-version helios-0.2

# 4. Restart inference
systemctl start helios-inference

# 5. Record incident
python scripts/log_rollback.py \
    --from helios-0.3 \
    --to helios-0.2 \
    --reason "Degraded performance on coastal locations"
```

## Storage Management

### Retention Policy

**Keep forever**:
- All champion model checkpoints
- All production-deployed model checkpoints
- Metadata and metrics for all trained models

**Keep for 90 days**:
- Experimental model checkpoints (never deployed)
- Intermediate training artifacts
- Training logs

**Delete immediately after verification**:
- Raw training data
- Processed feature datasets
- Temporary files

### Checkpoint Verification

Before deleting training data, verify checkpoint integrity:

```python
def verify_checkpoint(checkpoint_dir):
    """Verify checkpoint can be loaded and used for inference"""
    
    # 1. Load model
    model = load_model(checkpoint_dir)
    
    # 2. Load preprocessing
    preprocessor = load_preprocessor(checkpoint_dir)
    
    # 3. Run inference on test sample
    test_sample = load_test_sample()
    features = preprocessor.transform(test_sample)
    prediction = model.predict(features)
    
    # 4. Verify prediction is reasonable
    assert not np.isnan(prediction).any()
    assert prediction.shape == test_sample.shape[0]
    
    # 5. Verify metrics file exists and is valid
    metrics = load_metrics(checkpoint_dir)
    assert 'mae' in metrics
    assert 'rmse' in metrics
    
    return True
```

Only after `verify_checkpoint()` passes is it safe to delete training data.

## Reproducibility

Every checkpoint must enable exact reproduction of training:

**Git commit**: Exact code state
**Random seeds**: Fixed in all components
**Data versions**: Exact NWP model versions
**Environment**: Python/CUDA/library versions
**Hyperparameters**: Complete configuration

To reproduce a training run:

```bash
# 1. Checkout exact code
git checkout a1b2c3d4e5f6

# 2. Recreate environment
conda env create -f environment-helios-0.2.yml

# 3. Use same data (if available) or re-download
python scripts/download_data.py --config checkpoints/helios-0.2/config.json

# 4. Re-run training
python scripts/train_model.py --config checkpoints/helios-0.2/config.json

# Result should match original metrics within numerical tolerance
```

## Version Comparison Reports

Before promoting a new champion, generate comparison report:

```
HELIOS Model Comparison Report
==============================

Challenger: helios-0.3
Champion:   helios-0.2

Overall Performance
-------------------
Metric          Champion    Challenger    Δ          Improvement
MAE             1.234       1.123        -0.111      9.0%
RMSE            1.789       1.667        -0.122      6.8%
Bias           -0.123      -0.089        0.034      27.6%

Performance by Lead Time
------------------------
Lead Time    Champion MAE    Challenger MAE    Δ
6h           0.89            0.82             -0.07 ✓
24h          1.12            1.05             -0.07 ✓
72h          1.45            1.38             -0.07 ✓
168h         1.89            1.79             -0.10 ✓

Performance by Season
---------------------
Season       Champion MAE    Challenger MAE    Δ
Winter       1.45            1.35             -0.10 ✓
Summer       1.08            1.02             -0.06 ✓
Monsoon      1.32            1.21             -0.11 ✓

Baseline Comparisons
--------------------
Baseline           Champion Improvement    Challenger Improvement    Δ
vs GFS             34.7%                   40.6%                    +5.9% ✓
vs ECMWF           26.1%                   32.7%                    +6.6% ✓
vs Simple Mean     20.9%                   28.0%                    +7.1% ✓

RECOMMENDATION: PROMOTE to champion
All metrics improved. No regressions detected.
```

## Checkpoint Compression

To save storage, compress old experimental checkpoints:

```bash
# Compress checkpoint (keep only essentials)
python scripts/compress_checkpoint.py \
    --checkpoint models/checkpoints/helios-0.2-experimental \
    --output models/checkpoints/helios-0.2-experimental.tar.gz \
    --keep-essentials

# Essentials: metadata, config, hyperparameters, metrics
# Remove: plots, optimizer states, intermediate files
```

## Next Steps

1. Implement checkpoint save/load utilities
2. Create model comparison framework
3. Build champion promotion pipeline
4. Set up rollback procedures
5. Implement integrity verification
6. Create compression utilities
7. Build version comparison reports
8. Set up automated retention policies

---

**Status**: Versioning strategy documented
**Next**: Implement checkpoint management utilities
