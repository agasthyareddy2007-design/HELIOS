# HELIOS ML Architecture

## Overview

HELIOS evaluates three machine learning approaches for weather-model blending, each with distinct strengths for the post-processing task.

## Core Philosophy

**HELIOS is NOT an independent NWP model**. It is an ensemble blending and post-processing system that:

1. **Learns historical model performance** - Which models perform best under what conditions
2. **Blends predictions intelligently** - Weight models based on past skill and current uncertainty
3. **Calibrates forecasts** - Correct systematic biases using historical verification
4. **Quantifies confidence** - Provide uncertainty estimates and model agreement metrics

## ML Competitor 1: Kernel Regression

### Concept

Kernel regression weights historical situations based on **similarity** to current conditions, allowing very old data to remain useful when atmospheric regimes are similar.

### Key Principle

```
Recent + Similar Atmospheric Situation → Higher Influence
Old + Dissimilar Situation → Lower Influence
Old + Highly Similar Atmospheric Regime → Can Still Be Useful
```

Do not simply discard old data based only on age.

### Similarity Factors

The kernel approach weights historical forecasts based on:

1. **Temporal Recency**
   - More recent situations have baseline higher influence
   - Exponential decay function with tunable bandwidth

2. **Geographic Similarity**
   - Distance between forecast location and historical location
   - Similar topography and land/water characteristics

3. **Seasonal Similarity**
   - Same time of year
   - Similar solar forcing and typical weather patterns

4. **Forecast Lead Time**
   - Similar lead times (models perform differently at 6h vs 72h vs 168h)

5. **Recent Weather State**
   - Similar initial conditions
   - Similar observed weather in preceding days

6. **Atmospheric Conditions**
   - Similar weather regimes (monsoon, dry, transitional, etc.)
   - Similar synoptic patterns

7. **NWP Model Disagreement**
   - Similar ensemble spread
   - Similar model disagreement patterns

8. **Other Engineered Features**
   - Season-specific features
   - Location-specific features

### Mathematical Form

```
y_pred = Σ w_i * y_i

where:
w_i = K(x, x_i) / Σ K(x, x_j)

K(x, x_i) = exp(-||x - x_i||² / (2 * h²))
```

Where:
- `x` is the current feature vector
- `x_i` is a historical feature vector
- `h` is the kernel bandwidth (hyperparameter)
- `K()` is the kernel function (Gaussian/RBF shown, but others possible)

### Feature Engineering

Features for kernel similarity include:

```python
features = {
    # Temporal
    "day_of_year": 1-366,
    "hour_of_day": 0-23,
    "days_since_reference": continuous,
    
    # Spatial
    "latitude": degrees,
    "longitude": degrees,
    "elevation": meters,
    "distance_to_coast": km,
    
    # Forecast
    "lead_time_hours": 0-384,
    "initialization_hour": 0-23,
    
    # NWP Features
    "gfs_temperature": °C,
    "ecmwf_temperature": °C,
    "icon_temperature": °C,
    "ukmo_temperature": °C,
    "gem_temperature": °C,
    "ensemble_spread": °C,
    "model_disagreement": °C,
    
    # Atmospheric State
    "recent_temperature_mean_3d": °C,
    "recent_temperature_trend_3d": °C/day,
    "season": categorical,
    "weather_regime": categorical,
    
    # Historical Performance
    "gfs_recent_mae": °C,
    "ecmwf_recent_mae": °C,
    # ... other models
}
```

### Implementation

```python
from sklearn.neighbors import KernelDensity
from sklearn.metrics.pairwise import rbf_kernel

class KernelRegressor:
    def __init__(self, bandwidth='scott', kernel='gaussian'):
        self.bandwidth = bandwidth
        self.kernel = kernel
        self.X_train = None
        self.y_train = None
        
    def fit(self, X, y):
        """Store training data for similarity computation"""
        self.X_train = self._scale_features(X)
        self.y_train = y
        
        # Estimate bandwidth if not fixed
        if self.bandwidth == 'scott':
            self.h = self._scott_bandwidth(X)
        else:
            self.h = self.bandwidth
            
    def predict(self, X):
        """Weight historical observations by similarity"""
        X_scaled = self._scale_features(X)
        
        # Compute kernel weights
        weights = rbf_kernel(X_scaled, self.X_train, gamma=1/(2*self.h**2))
        
        # Normalize weights
        weights = weights / weights.sum(axis=1, keepdims=True)
        
        # Weighted average of historical observations
        y_pred = weights @ self.y_train
        
        return y_pred
```

### Hyperparameters

- **Bandwidth** (`h`): Controls how quickly similarity decays with distance
- **Kernel function**: Gaussian (RBF), Epanechnikov, etc.
- **Feature scaling**: Standardization vs min-max
- **Feature selection**: Which similarity factors to include

### Advantages

- **Interpretable**: Clear similarity-based weighting
- **Flexible**: No strong parametric assumptions
- **Adaptive**: Automatically adjusts to local patterns
- **Handles non-stationarity**: Can adapt as climate/models change

### Challenges

- **Computational cost**: Requires distance computation to all training points
- **Memory**: Stores entire training set
- **Curse of dimensionality**: Performance degrades with many features
- **Bandwidth selection**: Critical hyperparameter to tune

## ML Competitor 2: XGBoost

### Concept

Gradient boosting builds an ensemble of decision trees sequentially, where each tree corrects errors made by previous trees.

### Why XGBoost for Weather?

- **Tabular data**: Weather features are inherently tabular
- **Non-linear relationships**: Captures complex interactions between models
- **Feature importance**: Identifies which features matter most
- **Robust to outliers**: Tree-based models handle extreme values well
- **Fast training**: Efficient implementation with GPU support

### Feature Engineering

```python
features = {
    # NWP Model Forecasts
    "gfs_temp": float,
    "gfs_dewpoint": float,
    "gfs_wind_speed": float,
    "ecmwf_temp": float,
    "ecmwf_dewpoint": float,
    # ... all variables from all models
    
    # Ensemble Statistics
    "temp_ensemble_mean": float,
    "temp_ensemble_std": float,
    "temp_ensemble_spread": float,
    "temp_model_disagreement": float,
    
    # Temporal Features
    "hour": 0-23,
    "day_of_year": 1-366,
    "month": 1-12,
    "season": 0-3,  # or one-hot encoded
    "lead_time_hours": 0-384,
    "forecast_hour_of_day": 0-23,
    
    # Spatial Features
    "latitude": float,
    "longitude": float,
    "elevation": float,
    "distance_to_coast": float,
    
    # Historical Context
    "recent_temp_mean_3d": float,
    "recent_temp_std_3d": float,
    "temp_trend_3d": float,
    
    # Model Performance Features
    "gfs_mae_recent_7d": float,
    "gfs_bias_recent_7d": float,
    "gfs_mae_by_lead": float,  # for this lead time
    # ... for all models
    
    # ERA5 Climatology
    "era5_climatology_mean": float,
    "era5_climatology_std": float,
    "temp_anomaly_from_clim": float,
    
    # NASA POWER Auxiliary
    "nasa_temp": float,
    "nasa_humidity": float,
    "nasa_wind_speed": float,
    
    # Interaction Features (optional)
    "temp_spread_x_lead_time": float,
    "model_disagreement_x_season": float,
}

target = "observed_temperature"  # from verification data
```

### Implementation

```python
import xgboost as xgb

class XGBoostBlender:
    def __init__(self, params=None):
        self.params = params or {
            'objective': 'reg:squarederror',
            'max_depth': 6,
            'learning_rate': 0.05,
            'n_estimators': 500,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'tree_method': 'gpu_hist',  # Use RTX 5080
            'gpu_id': 0,
            'eval_metric': ['mae', 'rmse']
        }
        self.model = None
        
    def fit(self, X_train, y_train, X_val, y_val):
        """Train with early stopping"""
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)
        
        self.model = xgb.train(
            self.params,
            dtrain,
            num_boost_round=1000,
            evals=[(dtrain, 'train'), (dval, 'val')],
            early_stopping_rounds=50,
            verbose_eval=50
        )
        
    def predict(self, X):
        """Generate blended forecast"""
        dtest = xgb.DMatrix(X)
        return self.model.predict(dtest)
        
    def feature_importance(self):
        """Return feature importance scores"""
        return self.model.get_score(importance_type='gain')
```

### Hyperparameters

- **max_depth**: Maximum tree depth (controls complexity)
- **learning_rate**: Shrinkage to prevent overfitting
- **n_estimators**: Number of boosting rounds
- **subsample**: Row sampling ratio
- **colsample_bytree**: Feature sampling ratio
- **min_child_weight**: Minimum sum of instance weight in a child
- **gamma**: Minimum loss reduction required for split
- **reg_alpha**: L1 regularization
- **reg_lambda**: L2 regularization

### Advantages

- **High accuracy**: Often best-performing for tabular data
- **Feature interactions**: Automatically captures complex relationships
- **Feature importance**: Clear which inputs matter
- **Robust**: Handles missing values and outliers well
- **Fast**: Efficient training and inference

### Challenges

- **Hyperparameter tuning**: Many parameters to optimize
- **Overfitting risk**: Requires careful regularization
- **Less interpretable**: Than kernel regression (but more than neural networks)

## ML Competitor 3: MLP (Multi-Layer Perceptron)

### Concept

A feedforward neural network that learns non-linear mappings from NWP forecasts to corrected predictions.

### Architecture

```python
import torch
import torch.nn as nn

class MLPBlender(nn.Module):
    def __init__(self, input_dim, hidden_dims=[256, 128, 64], dropout=0.2):
        super().__init__()
        
        layers = []
        prev_dim = input_dim
        
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout)
            ])
            prev_dim = hidden_dim
            
        # Output layer
        layers.append(nn.Linear(prev_dim, 1))
        
        self.network = nn.Sequential(*layers)
        
    def forward(self, x):
        return self.network(x).squeeze(-1)
```

### Training Configuration

```python
# Hardware
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')  # RTX 5080

# Loss
criterion = nn.MSELoss()  # or MAE (L1Loss)

# Optimizer
optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=1e-3,
    weight_decay=1e-4
)

# Learning rate schedule
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer,
    mode='min',
    factor=0.5,
    patience=10
)

# Training loop
for epoch in range(max_epochs):
    model.train()
    for batch_X, batch_y in train_loader:
        batch_X, batch_y = batch_X.to(device), batch_y.to(device)
        
        optimizer.zero_grad()
        pred = model(batch_X)
        loss = criterion(pred, batch_y)
        loss.backward()
        optimizer.step()
        
    # Validation
    model.eval()
    val_loss = evaluate(model, val_loader)
    scheduler.step(val_loss)
```

### Hyperparameters

- **hidden_dims**: Number and size of hidden layers
- **dropout**: Dropout rate for regularization
- **learning_rate**: Initial learning rate
- **weight_decay**: L2 regularization strength
- **batch_size**: Training batch size
- **activation**: ReLU, LeakyReLU, GELU, etc.

### Advantages

- **Flexible**: Can model any non-linear function (universal approximation)
- **GPU acceleration**: Fast training on RTX 5080
- **Scalable**: Can handle large feature sets
- **End-to-end learning**: Learns preprocessing implicitly

### Challenges

- **Requires more data**: Than tree-based methods
- **Hyperparameter sensitive**: Architecture and training settings critical
- **Less interpretable**: Black box compared to trees/kernels
- **Overfitting**: Requires careful regularization

## Feature Engineering for All Models

### Critical Principle: No Temporal Leakage

**Rule**: Only use data available at forecast issue time

```python
# CORRECT
forecast_time = "2026-09-05 00:00 UTC"
features = {
    "gfs_temp": 28.5,  # Forecast for future time
    "recent_temp_mean_3d": 27.2,  # Observed BEFORE forecast_time
    "gfs_mae_7d": 1.5,  # Computed from forecasts BEFORE forecast_time
}

# WRONG - TEMPORAL LEAKAGE
features = {
    "future_observation": 29.1,  # Observation at valid time!
    "full_period_statistics": 1.2,  # Computed using future data!
}
```

### Feature Categories

1. **NWP Features** - Raw model outputs
2. **Spatial Features** - Location characteristics
3. **Temporal Features** - Time-based patterns
4. **Historical Reference** - ERA5 climatology
5. **Rolling Performance** - Recent model skill
6. **Auxiliary Features** - NASA POWER, etc.
7. **Disagreement Features** - Model spread/uncertainty

## Model Comparison Framework

### Baseline Models

HELIOS must prove it improves upon:

1. **Individual NWP Models** (no blending)
2. **Simple Ensemble Mean** (arithmetic average)
3. **Persistence** (assume no change)
4. **Climatology** (historical average)

### Evaluation Metrics

**Continuous Variables** (temperature, wind speed):
- MAE (Mean Absolute Error)
- RMSE (Root Mean Squared Error)
- Bias (Mean Error)

**Probabilistic Forecasts**:
- Brier Score
- Calibration curves
- Reliability diagrams

**Stratified by**:
- Lead time (0-6h, 6-24h, 24-72h, 72-168h, 168h+)
- Season (summer, winter, monsoon, etc.)
- Location/region
- Weather regime

### Skill Score

```
Skill Score = 1 - (MAE_helios / MAE_baseline)

Positive score = HELIOS improves over baseline
Zero score = HELIOS matches baseline
Negative score = Baseline is better
```

## Training Strategy

### Data Split

```
Train:      1979-2004  (26 years)
Validation: 2005-2014  (10 years)
Test:       2015-2024  (10 years)
```

**Critical**: Strict temporal ordering to prevent leakage

### Cross-Validation

Time-series cross-validation (forward chaining):

```
Fold 1: Train [1979-2000], Val [2001-2002]
Fold 2: Train [1979-2002], Val [2003-2004]
Fold 3: Train [1979-2004], Val [2005-2006]
...
```

### Hyperparameter Optimization

```python
from optuna import create_study

def objective(trial):
    # Suggest hyperparameters
    params = {
        'max_depth': trial.suggest_int('max_depth', 3, 10),
        'learning_rate': trial.suggest_float('learning_rate', 1e-4, 1e-1, log=True),
        # ... other params
    }
    
    # Train model
    model = XGBoostBlender(params)
    model.fit(X_train, y_train, X_val, y_val)
    
    # Evaluate
    y_pred = model.predict(X_val)
    mae = mean_absolute_error(y_val, y_pred)
    
    return mae

study = create_study(direction='minimize')
study.optimize(objective, n_trials=100)
```

## Model Versioning

Each trained model version includes:

```
models/checkpoints/helios-0.2/
├── model.pt                    # PyTorch weights (MLP)
├── model.json                  # XGBoost model (XGBoost)
├── kernel_params.pkl           # Kernel parameters
├── feature_config.json         # Feature engineering config
├── preprocessing.pkl           # Scalers, encoders
├── metadata.json              # Training info
└── metrics.json               # Evaluation results
```

**metadata.json**:
```json
{
  "version": "0.2",
  "model_type": "xgboost",
  "training_period": {
    "start": "1979-01-01",
    "end": "2004-12-31"
  },
  "data_sources": {
    "gfs": "16.3",
    "ecmwf": "47r3",
    "era5": "v1"
  },
  "hyperparameters": {...},
  "git_commit": "a1b2c3d",
  "trained_at": "2026-09-05T12:00:00Z",
  "trained_by": "user@example.com"
}
```

## Inference Pipeline

```python
def predict_helios(location, valid_time, nwp_forecasts):
    """Generate HELIOS blended forecast"""
    
    # 1. Load champion model
    model = load_model("models/champion/")
    
    # 2. Engineer features (using only available data)
    features = engineer_features(
        nwp_forecasts=nwp_forecasts,
        location=location,
        valid_time=valid_time,
        historical_performance=load_recent_performance(),
        era5_climatology=load_climatology(location),
        # NO future data!
    )
    
    # 3. Predict
    prediction = model.predict(features)
    
    # 4. Compute confidence
    confidence = compute_confidence(
        ensemble_spread=features['ensemble_spread'],
        model_disagreement=features['model_disagreement'],
        recent_model_skill=features['recent_mae']
    )
    
    return {
        "temperature": prediction,
        "confidence": confidence,
        "model_version": "0.2",
        "nwp_sources": ["gfs", "ecmwf", "icon", "ukmo", "gem"]
    }
```

## Next Steps

1. **Implement baseline blenders** (simple mean, weighted average)
2. **Build kernel regression** with scikit-learn
3. **Implement XGBoost blender** with GPU support
4. **Build MLP architecture** in PyTorch
5. **Create feature engineering pipeline**
6. **Implement verification system**
7. **Hyperparameter optimization** with Optuna
8. **Model comparison framework**
9. **Champion model selection**
10. **Production inference API**

---

**Status**: Architecture documented
**Next**: Implement baseline blenders and feature engineering pipeline
