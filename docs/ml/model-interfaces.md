# HELIOS Model Architecture

## Overview

HELIOS implements multiple ML approaches for weather forecast blending, with the goal of creating ensemble forecasts that outperform individual NWP models and simple baselines.

## Baseline Models

### 1. Individual NWP Models
- **Purpose**: Establish baseline performance
- **Models**: GFS, ECMWF IFS, ICON (post-MVP), GEM (post-MVP)
- **Evaluation**: Track each model's performance independently
- **Metrics**: MAE, RMSE, bias by variable/lead time/location/season

### 2. Simple Mean Ensemble
- **Purpose**: Baseline ensemble approach
- **Method**: Arithmetic mean of all available NWP forecasts
- **Formula**: `T_mean = (T_GFS + T_ECMWF + ...) / N`
- **Expectation**: Should outperform worst individual model, may not beat best model

### 3. Persistence
- **Purpose**: Baseline for very short lead times
- **Method**: Most recent observation as forecast
- **Formula**: `T_forecast(t+Δt) = T_observed(t)`
- **Applicable**: 0-24 hour lead times

### 4. Climatology
- **Purpose**: Long-term seasonal baseline
- **Method**: Historical average for location/day/hour
- **Data**: Multi-year ERA5-Land climatology
- **Applicable**: All lead times, especially seasonal patterns

## ML Competitor Models

### 1. Kernel Regression

**Concept**: Weight NWP forecasts based on similarity of current conditions to historical situations.

**Architecture**:
```python
class KernelRegression:
    def __init__(self, kernel='rbf', bandwidth='auto'):
        self.kernel = kernel
        self.bandwidth = bandwidth
        self.training_features = None  # Historical feature vectors
        self.training_targets = None   # Corresponding observations
    
    def predict(self, current_features):
        # Compute similarity weights between current situation and historical data
        weights = kernel_function(current_features, self.training_features)
        # Weighted average of historical outcomes
        return np.average(self.training_targets, weights=weights)
```

**Features**:
- Current NWP forecast values
- Model agreement/disagreement
- Recent forecast errors for each model
- Location, time of day, season
- Recent observations (if available at forecast issue time)

**Challenges**:
- Scalability: Naive O(N²) approach with large historical dataset
- Solution: Use localized nearest-neighbor approach
  - Find K most similar historical situations (K=100-1000)
  - Compute kernel weights only over those K samples
  - Tree-based indexing for fast nearest-neighbor search

**Storage**: ~500-800 MB per checkpoint (stores training data)

### 2. XGBoost

**Concept**: Gradient-boosted decision trees learn non-linear relationships between NWP forecasts and observations.

**Architecture**:
```python
class XGBoostBlender:
    def __init__(self):
        self.model = xgb.XGBRegressor(
            objective='reg:squarederror',
            tree_method='hist',  # or 'gpu_hist' for GPU
            device='cuda',       # GPU acceleration
            max_depth=8,
            learning_rate=0.05,
            n_estimators=500,
            subsample=0.8,
            colsample_bytree=0.8
        )
    
    def fit(self, features, target):
        self.model.fit(features, target)
    
    def predict(self, features):
        return self.model.predict(features)
```

**Features**:
- All NWP model forecasts (temperature, wind, pressure, etc.)
- Model spread/disagreement
- Lead time
- Location identifiers
- Time features (hour, day of year, season)
- Recent model performance (MAE last 7 days for each model)
- Elevation, latitude, longitude

**Hyperparameter Tuning**: Optuna-based optimization
- Objective: Minimize validation RMSE
- Search space: depth, learning rate, regularization, sampling

**GPU Acceleration**: Use `tree_method='gpu_hist'` on RTX 5080

**Storage**: ~200-400 MB per checkpoint

### 3. Multi-Layer Perceptron (MLP)

**Concept**: Deep neural network learns complex non-linear forecast transformations.

**Architecture**:
```python
class MLPBlender(nn.Module):
    def __init__(self, input_dim, hidden_dims=[256, 128, 64]):
        super().__init__()
        layers = []
        prev_dim = input_dim
        for hidden_dim in hidden_dims:
            layers.append(nn.Linear(prev_dim, hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.Dropout(0.2))
            prev_dim = hidden_dim
        layers.append(nn.Linear(prev_dim, 1))  # Output: corrected temperature
        self.network = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.network(x)
```

**Training**:
- Framework: PyTorch
- Hardware: NVIDIA RTX 5080 (16GB, CUDA 13.3)
- Optimizer: Adam with learning rate scheduling
- Loss: MSE (Mean Squared Error)
- Batch size: 256-1024 (depending on available GPU memory)
- Early stopping: Monitor validation loss

**Features**: Same as XGBoost

**Storage**: ~50-150 MB per checkpoint (smaller than XGBoost)

## HELIOS Meta-Blender (Future)

**Concept**: Second-level ensemble that combines predictions from Kernel Regression, XGBoost, and MLP.

**Approaches**:
1. **Weighted Average**: Learn optimal weights for each model
2. **Stacking**: Train another ML model on top of base model predictions
3. **Dynamic Weighting**: Select best model based on current conditions

**Implementation**: Deferred to post-MVP

## Feature Engineering

### Temporal Features
- Hour of day (cyclical: sin/cos encoding)
- Day of year (cyclical)
- Season indicator
- Lead time
- Forecast issue hour

### Spatial Features
- Latitude, longitude (normalized)
- Elevation
- Distance to coast (if applicable)
- Location identifier (categorical)

### NWP Features
- All forecast variables from each model
- Model spread: `spread = max(forecasts) - min(forecasts)`
- Model standard deviation
- Distance from climatology: `anomaly = forecast - climatology`

### Historical Performance Features
- Each model's MAE over last 7 days
- Each model's bias over last 7 days
- Each model's RMSE over last 7 days
- Best-performing model indicator (last 7 days)

### Observation Context (if available at issue time)
- Most recent observation (T-0, T-6h, T-12h)
- Recent observation trend
- Observation-forecast difference at previous valid time

**CRITICAL**: All features must respect temporal leakage constraints. Never include information from after the forecast issue time.

## Model Comparison

All models must be compared fairly:
- **Same training data**: Identical historical period, locations, variables
- **Same validation data**: Temporal split (e.g., train on 2023 Jan-Oct, validate on Nov-Dec)
- **Same test data**: Held-out 2024 data (if extending to 2 years)
- **Same metrics**: MAE, RMSE, bias computed identically
- **Stratified evaluation**: By lead time, location, season, variable

## Success Criteria

HELIOS is successful if:
1. **Beats all individual NWP models** on average across lead times/locations
2. **Beats simple mean ensemble** consistently
3. **Shows improvement across multiple variables** (not just temperature)
4. **Generalizes to held-out test period** (not overfitted)
5. **Provides interpretable model weights** (which models are trusted when/where)

If HELIOS does not beat baselines, the honest outcome is reported. The system design allows for objective comparison.
