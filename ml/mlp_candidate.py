"""
HELIOS MLP Candidate

Multi-layer perceptron (neural network) for forecast reliability prediction.

CRITICAL DESIGN PRINCIPLES:
1. Predict reliability (expected error), not direct forecast values
2. Use canonical 24-feature contract
3. PyTorch implementation, CPU-compatible
4. Configurable architecture (hidden layers, dropout)
5. Separate model for each forecast source (GFS/IFS/ICON)
6. Temporal leakage prevention
7. Missing-model handling

ARCHITECTURE:
- Train separate MLP for each model (GFS/IFS/ICON)
- Each MLP predicts expected absolute error
- Target: absolute_error from verification records
- Features: canonical 24-feature contract (preprocessed)
- Convert predictions to blending weights via inverse-error weighting

TEMPORAL SAFETY:
- Training data: features available at issue_time, targets after verification
- Prediction: uses only features available at issue_time
- NO access to future observations
"""

import logging
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import FeatureVector, Target, TrainingSample, FeatureContract
from ml.candidate_interface import (
    BaseCandidateModel,
    CandidateType,
    CandidateMetadata,
    ReliabilityPrediction,
    EvaluationMetrics
)
from ml.preprocessing import FeaturePreprocessor


logger = logging.getLogger(__name__)


@dataclass
class MLPConfig:
    """Configuration for MLP candidate."""
    # Architecture
    hidden_layers: List[int] = None  # Default: [64, 32]
    activation: str = 'relu'  # 'relu', 'tanh', or 'sigmoid'
    dropout_rate: float = 0.2

    # Training parameters
    n_epochs: int = 100
    batch_size: int = 32
    learning_rate: float = 0.001
    weight_decay: float = 0.0001  # L2 regularization
    early_stopping_patience: int = 10

    # Device
    device: str = 'cpu'  # Force CPU for Phase 5a

    # Random state
    random_state: int = 42

    def __post_init__(self):
        """Set defaults."""
        if self.hidden_layers is None:
            self.hidden_layers = [64, 32]


class MLPCandidate(BaseCandidateModel):
    """
    MLP (Multi-Layer Perceptron) candidate for HELIOS forecast blending.

    Design:
    - Separate MLP for each model (GFS/IFS/ICON)
    - Predicts expected absolute error (reliability)
    - Converts to blending weights via inverse-error weighting
    - PyTorch implementation, CPU-compatible

    Temporal safety:
    - Training: features before issue_time, targets after verification
    - Prediction: uses only features available at issue_time
    """

    def __init__(
        self,
        feature_contract: FeatureContract,
        config: Optional[MLPConfig] = None,
        candidate_id: Optional[str] = None
    ):
        """
        Initialize MLP candidate.

        Args:
            feature_contract: Feature contract (shared by all candidates)
            config: MLP configuration
            candidate_id: Unique identifier (auto-generated if None)
        """
        super().__init__(
            candidate_type=CandidateType.MLP,
            feature_contract=feature_contract,
            candidate_id=candidate_id
        )

        self.config = config or MLPConfig()
        self.preprocessor = FeaturePreprocessor()

        # Trained models (one per forecast source)
        self.models: Dict[str, Any] = {}  # model_name → PyTorch model

        # Training metadata
        self.training_samples_count: int = 0

    def _create_mlp(self, input_dim: int) -> Any:
        """
        Create MLP model.

        Args:
            input_dim: Input feature dimension

        Returns:
            PyTorch MLP model
        """
        import torch
        import torch.nn as nn

        class MLP(nn.Module):
            def __init__(self, input_dim: int, hidden_layers: List[int], dropout_rate: float, activation: str):
                super().__init__()

                layers = []
                prev_dim = input_dim

                # Hidden layers
                for hidden_dim in hidden_layers:
                    layers.append(nn.Linear(prev_dim, hidden_dim))

                    # Activation
                    if activation == 'relu':
                        layers.append(nn.ReLU())
                    elif activation == 'tanh':
                        layers.append(nn.Tanh())
                    elif activation == 'sigmoid':
                        layers.append(nn.Sigmoid())

                    # Dropout
                    if dropout_rate > 0:
                        layers.append(nn.Dropout(dropout_rate))

                    prev_dim = hidden_dim

                # Output layer (single output: expected absolute error)
                layers.append(nn.Linear(prev_dim, 1))

                # Ensure positive output (reliability must be >= 0)
                layers.append(nn.ReLU())

                self.network = nn.Sequential(*layers)

            def forward(self, x):
                return self.network(x)

        return MLP(
            input_dim=input_dim,
            hidden_layers=self.config.hidden_layers,
            dropout_rate=self.config.dropout_rate,
            activation=self.config.activation
        )

    def stream_train(self, dataset_builder, config, train_bounds, validation_samples=None, kernel_support_limit=None):
        """True stream training from the builder - bounded."""
        import torch
        import torch.nn as nn
        import torch.optim as optim
        import gc
        
        # Set seeds
        torch.manual_seed(self.config.random_state)
        import numpy as np
        np.random.seed(self.config.random_state)
        
        input_dim = self.preprocessor.stats.n_total
        
        # If models don't exist, create them
        if not self.models:
            for m in ['gfs', 'ifs', 'icon']:
                mlp = self._create_mlp(input_dim).to(self.config.device)
                optimizer = optim.Adam(mlp.parameters(), lr=self.config.learning_rate, weight_decay=self.config.weight_decay)
                self.models[m] = {'net': mlp, 'opt': optimizer, 'count': 0}
                
        criterion = nn.MSELoss()
        
        # Train for one epoch over the entire stream, updating models continuously
        chunk_idx = 1
        for chunk in dataset_builder.stream_training_samples(config, start_issue=train_bounds[0], end_issue=train_bounds[1], chunk_size=20000):
            if not chunk: continue

            if chunk_idx % 10 == 0:
                print(f"  [MLP] Streamed {chunk_idx} chunks (current chunk size: {len(chunk)} rows)")
            chunk_idx += 1

            # Group chunk by model
            samples_by_model = {'gfs': [], 'ifs': [], 'icon': []}
            for s in chunk:
                samples_by_model[s.features.model].append(s)
                
            for m_key, m_samples in samples_by_model.items():
                if not m_samples: continue
                m_state = self.models[m_key]
                net = m_state['net']
                opt = m_state['opt']
                m_state['count'] += len(m_samples)
                
                # Preprocess batch
                features = [s.features for s in m_samples]
                X = self.preprocessor.transform_batch(features)
                y = np.array([s.target.absolute_error for s in m_samples], dtype=np.float32)
                
                if not isinstance(X, np.ndarray):
                    raise ValueError("X must be a numpy array")
                
                # Loop through standard batch sizes
                batch_size = self.config.batch_size
                n_samples = X.shape[0]
                
                net.train()
                for i in range(0, n_samples, batch_size):
                    X_b = torch.from_numpy(X[i:i+batch_size]).to(self.config.device)
                    y_b = torch.from_numpy(y[i:i+batch_size]).unsqueeze(1).to(self.config.device)
                    
                    opt.zero_grad()
                    out = net(X_b)
                    loss = criterion(out, y_b)
                    loss.backward()
                    opt.step()
                
            del chunk
            del samples_by_model
            gc.collect()
            
        self.is_trained = True
        return None  # Or return metadata if needed

        
    def train(

        self,
        training_samples: List[TrainingSample],
        validation_samples: Optional[List[TrainingSample]] = None
    ) -> CandidateMetadata:
        """
        Train MLP candidate.

        Trains separate MLP for each model (GFS/IFS/ICON).

        Args:
            training_samples: Verified forecast-outcome pairs (chronological)
            validation_samples: Optional validation set (for early stopping)

        Returns:
            CandidateMetadata with training history
        """
        if not training_samples:
            raise ValueError("Cannot train: no training samples")

        self.logger.info(f"Training MLP on {len(training_samples)} samples")

        try:
            import torch
            import torch.nn as nn
            import torch.optim as optim
            from torch.utils.data import TensorDataset, DataLoader
        except ImportError:
            raise ImportError(
                "PyTorch not installed. Install with: pip install torch"
            )

        # Set random seed for reproducibility
        torch.manual_seed(self.config.random_state)
        np.random.seed(self.config.random_state)

        # Fit preprocessor on training data
        self.preprocessor.fit(training_samples)
        input_dim = self.preprocessor.stats.n_total

        # Group samples by model
        samples_by_model = {}
        for sample in training_samples:
            model = sample.features.model
            if model not in samples_by_model:
                samples_by_model[model] = []
            samples_by_model[model].append(sample)

        # Train separate MLP for each model
        for model, model_samples in samples_by_model.items():
            self.logger.info(f"Training MLP for {model}: {len(model_samples)} samples")

            # Extract features and targets
            feature_vectors = [s.features for s in model_samples]
            X_train = self.preprocessor.transform_batch(feature_vectors)
            y_train = np.array([s.target.absolute_error for s in model_samples], dtype=np.float32)
            del feature_vectors
            import gc; gc.collect()

            # Convert to PyTorch tensors
            X_train_tensor = torch.from_numpy(X_train)
            y_train_tensor = torch.from_numpy(y_train).unsqueeze(1)

            # Create data loader
            train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
            train_loader = DataLoader(
                train_dataset,
                batch_size=self.config.batch_size,
                shuffle=True
            )

            # Prepare validation data if provided
            val_loader = None
            if validation_samples:
                val_model_samples = [s for s in validation_samples if s.features.model == model]
                if val_model_samples:
                    val_features = [s.features for s in val_model_samples]
                    X_val = self.preprocessor.transform_batch(val_features)
                    y_val = np.array([s.target.absolute_error for s in val_model_samples], dtype=np.float32)
                    del val_features
                    import gc; gc.collect()

                    X_val_tensor = torch.from_numpy(X_val)
                    y_val_tensor = torch.from_numpy(y_val).unsqueeze(1)

                    val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
                    val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size)

            # Create model
            mlp = self._create_mlp(input_dim)
            mlp = mlp.to(self.config.device)

            # Optimizer and loss
            optimizer = optim.Adam(
                mlp.parameters(),
                lr=self.config.learning_rate,
                weight_decay=self.config.weight_decay
            )
            criterion = nn.MSELoss()

            # Training loop
            best_val_loss = float('inf')
            patience_counter = 0

            for epoch in range(self.config.n_epochs):
                # Training phase
                mlp.train()
                train_loss = 0.0
                n_batches = 0

                for X_batch, y_batch in train_loader:
                    X_batch = X_batch.to(self.config.device)
                    y_batch = y_batch.to(self.config.device)

                    # Forward pass
                    optimizer.zero_grad()
                    y_pred = mlp(X_batch)
                    loss = criterion(y_pred, y_batch)

                    # Backward pass
                    loss.backward()
                    optimizer.step()

                    train_loss += loss.item()
                    n_batches += 1

                train_loss /= n_batches

                # Validation phase
                if val_loader:
                    mlp.eval()
                    val_loss = 0.0
                    n_val_batches = 0

                    with torch.no_grad():
                        for X_batch, y_batch in val_loader:
                            X_batch = X_batch.to(self.config.device)
                            y_batch = y_batch.to(self.config.device)

                            y_pred = mlp(X_batch)
                            loss = criterion(y_pred, y_batch)

                            val_loss += loss.item()
                            n_val_batches += 1

                    val_loss /= n_val_batches

                    # Early stopping
                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        patience_counter = 0
                    else:
                        patience_counter += 1

                    if patience_counter >= self.config.early_stopping_patience:
                        self.logger.info(f"Early stopping at epoch {epoch+1}")
                        break

            self.models[model] = mlp

        # Mark as trained
        self.is_trained = True
        self.training_samples_count = len(training_samples)

        # Create metadata
        times = [s.features.issue_time for s in training_samples]
        self.metadata = CandidateMetadata(
            candidate_type=self.candidate_type,
            candidate_id=self.candidate_id,
            version="1.0.0",
            trained_at=datetime.utcnow(),
            training_samples_count=len(training_samples),
            training_period_start=min(times),
            training_period_end=max(times),
            feature_contract_version="1.0.0",
            hyperparameters={
                'hidden_layers': self.config.hidden_layers,
                'activation': self.config.activation,
                'dropout_rate': self.config.dropout_rate,
                'n_epochs': self.config.n_epochs,
                'batch_size': self.config.batch_size,
                'learning_rate': self.config.learning_rate,
                'weight_decay': self.config.weight_decay,
                'random_state': self.config.random_state
            }
        )

        self.logger.info(
            f"MLP trained: {len(training_samples)} samples, {len(samples_by_model)} models"
        )

        return self.metadata

    def predict_reliability(
        self,
        features: FeatureVector,
        models: List[str] = ['gfs', 'ifs', 'icon']
    ) -> Dict[str, ReliabilityPrediction]:
        """
        Predict reliability (expected error) for each model.

        Uses trained MLP models.

        Args:
            features: Feature vector (available at issue_time)
            models: Models to predict reliability for

        Returns:
            Dict mapping model name to ReliabilityPrediction
        """
        if not self.is_trained:
            raise ValueError("Cannot predict: model not trained")

        import torch

        # Validate features
        is_valid, error_msg = self.feature_contract.validate_feature_vector(features)
        if not is_valid:
            raise ValueError(f"Invalid feature vector: {error_msg}")

        # Preprocess features
        x_query = self.preprocessor.transform(features)
        x_query_tensor = torch.FloatTensor(x_query).unsqueeze(0).to(self.config.device)

        # Predict expected error for each model
        predictions = {}

        for model in models:
            if model not in self.models:
                # Model not in training data - use conservative default
                predictions[model] = ReliabilityPrediction(
                    model=model,
                    expected_absolute_error=1.0,  # Conservative default
                    expected_squared_error=1.0,
                    prediction_time=datetime.utcnow()
                )
                continue

            # Predict expected absolute error
            mlp_state = self.models[model]
            mlp = mlp_state['net'] if isinstance(mlp_state, dict) else mlp_state
            mlp.eval()

            with torch.no_grad():
                expected_mae = float(mlp(x_query_tensor).item())

            # Bound to positive values (ReLU should handle this, but extra safeguard)
            expected_mae = max(expected_mae, 1e-6)

            # Estimate squared error (approximate)
            expected_mse = expected_mae ** 2

            predictions[model] = ReliabilityPrediction(
                model=model,
                expected_absolute_error=expected_mae,
                expected_squared_error=expected_mse,
                prediction_time=datetime.utcnow()
            )

        return predictions

    def evaluate(
        self,
        test_samples: List[TrainingSample]
    ) -> EvaluationMetrics:
        """
        Evaluate MLP on held-out chronological test set.

        Args:
            test_samples: Held-out test samples (chronological, after training)

        Returns:
            EvaluationMetrics with performance on unseen future data
        """
        if not self.is_trained:
            raise ValueError("Cannot evaluate: model not trained")

        if not test_samples:
            raise ValueError("Cannot evaluate: no test samples")

        self.logger.info(f"Evaluating MLP on {len(test_samples)} test samples")

        # Compute weighted blend for each test sample
        squared_errors = []
        absolute_errors = []
        errors = []

        # For baseline comparison
        simple_avg_squared_errors = []

        # For reliability prediction quality
        reliability_errors = []

        for sample in test_samples:
            features = sample.features
            target = sample.target

            # Get blending weights
            try:
                weight_pred = self.get_weights(features)
            except Exception as e:
                self.logger.warning(f"Failed to get weights: {e}")
                continue

            # Compute weighted blend
            available_forecasts = []
            weights_used = []

            if features.gfs_available and features.gfs_value is not None:
                available_forecasts.append(features.gfs_value)
                weights_used.append(weight_pred.gfs_weight)

            if features.ifs_available and features.ifs_value is not None:
                available_forecasts.append(features.ifs_value)
                weights_used.append(weight_pred.ifs_weight)

            if features.icon_available and features.icon_value is not None:
                available_forecasts.append(features.icon_value)
                weights_used.append(weight_pred.icon_weight)

            if not available_forecasts:
                continue  # Skip if no models available

            # Weighted blend
            blended_forecast = sum(
                f * w for f, w in zip(available_forecasts, weights_used)
            )

            # Simple average (baseline)
            simple_avg_forecast = sum(available_forecasts) / len(available_forecasts)

            # Compute errors
            error = blended_forecast - target.observed_value
            simple_avg_error = simple_avg_forecast - target.observed_value

            errors.append(error)
            absolute_errors.append(abs(error))
            squared_errors.append(error ** 2)
            simple_avg_squared_errors.append(simple_avg_error ** 2)

            # Reliability prediction error
            model = features.model
            if model in self.models:
                reliability_pred = weight_pred.gfs_reliability if model == 'gfs' else (
                    weight_pred.ifs_reliability if model == 'ifs' else weight_pred.icon_reliability
                )
                if reliability_pred:
                    predicted_error = reliability_pred.expected_absolute_error
                    actual_error = target.absolute_error
                    reliability_errors.append((predicted_error - actual_error) ** 2)

        # Aggregate metrics
        import math
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else 0.0
        mae = sum(absolute_errors) / len(absolute_errors) if absolute_errors else 0.0
        bias = sum(errors) / len(errors) if errors else 0.0

        simple_avg_rmse = math.sqrt(
            sum(simple_avg_squared_errors) / len(simple_avg_squared_errors)
        ) if simple_avg_squared_errors else 0.0

        improvement = (simple_avg_rmse - rmse) / simple_avg_rmse if simple_avg_rmse > 0 else 0.0

        reliability_rmse = math.sqrt(
            sum(reliability_errors) / len(reliability_errors)
        ) if reliability_errors else 0.0

        # Extract temporal coverage
        times = [s.features.valid_time for s in test_samples]
        test_period_start = min(times)
        test_period_end = max(times)
        test_span_days = (test_period_end - test_period_start).total_seconds() / 86400

        return EvaluationMetrics(
            n_test_samples=len(test_samples),
            n_train_samples=self.training_samples_count,
            weighted_forecast_rmse=rmse,
            weighted_forecast_mae=mae,
            weighted_forecast_bias=bias,
            simple_average_rmse=simple_avg_rmse,
            improvement_over_baseline=improvement,
            reliability_prediction_rmse=reliability_rmse,
            test_period_start=test_period_start,
            test_period_end=test_period_end,
            test_span_days=test_span_days
        )
