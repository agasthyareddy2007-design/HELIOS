"""
HELIOS XGBoost Candidate

Gradient-boosted decision trees for forecast reliability prediction.

CRITICAL DESIGN PRINCIPLES:
1. Predict reliability (expected error), not direct forecast values
2. Use canonical 24-feature contract
3. Configurable hyperparameters (deterministic training)
4. Separate model for each forecast source (GFS/IFS/ICON)
5. Temporal leakage prevention
6. Missing-model handling

ARCHITECTURE:
- Train separate XGBoost regressor for each model (GFS/IFS/ICON)
- Each regressor predicts expected absolute error
- Target: absolute_error from verification records
- Features: canonical 24-feature contract
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
class XGBoostConfig:
    """Configuration for XGBoost candidate."""
    # XGBoost hyperparameters
    n_estimators: int = 100
    max_depth: int = 6
    learning_rate: float = 0.1
    min_child_weight: int = 1
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    gamma: float = 0.0
    reg_alpha: float = 0.0
    reg_lambda: float = 1.0

    # Training parameters
    early_stopping_rounds: Optional[int] = 10
    random_state: int = 42  # For reproducibility


class XGBoostCandidate(BaseCandidateModel):
    """
    XGBoost candidate for HELIOS forecast blending.

    Design:
    - Separate XGBoost regressor for each model (GFS/IFS/ICON)
    - Predicts expected absolute error (reliability)
    - Converts to blending weights via inverse-error weighting
    - Deterministic training (fixed random_state)

    Temporal safety:
    - Training: features before issue_time, targets after verification
    - Prediction: uses only features available at issue_time
    """

    def __init__(
        self,
        feature_contract: FeatureContract,
        config: Optional[XGBoostConfig] = None,
        candidate_id: Optional[str] = None
    ):
        """
        Initialize XGBoost candidate.

        Args:
            feature_contract: Feature contract (shared by all candidates)
            config: XGBoost configuration
            candidate_id: Unique identifier (auto-generated if None)
        """
        super().__init__(
            candidate_type=CandidateType.XGBOOST,
            feature_contract=feature_contract,
            candidate_id=candidate_id
        )

        self.config = config or XGBoostConfig()
        self.preprocessor = FeaturePreprocessor()

        # Trained models (one per forecast source)
        self.models: Dict[str, Any] = {}  # model_name → XGBoost regressor

        # Training metadata
        self.training_samples_count: int = 0


    def stream_train(self, dataset_builder, config, train_bounds, validation_samples=None, kernel_support_limit=None):
        import numpy as np
        import xgboost as xgb
        import gc

        if not hasattr(self, 'models'):
            self.models = {}

        # We accumulate preprocessed numpy batches for each model, then fit exactly once.
        # This completely decouples chunking from tree generation, preserving the strict
        # n_estimators limit (XGBoost can easily buffer ~300MB of float32 arrays in memory).
        accumulated_X = {'gfs': [], 'ifs': [], 'icon': []}
        accumulated_y = {'gfs': [], 'ifs': [], 'icon': []}

        # Get standard params
        regressor_kwargs = dict(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            learning_rate=self.config.learning_rate,
            min_child_weight=self.config.min_child_weight,
            subsample=self.config.subsample,
            colsample_bytree=self.config.colsample_bytree,
            gamma=self.config.gamma,
            reg_alpha=self.config.reg_alpha,
            reg_lambda=self.config.reg_lambda,
            random_state=self.config.random_state,
        )
        if hasattr(self.config, 'device'):
            regressor_kwargs['device'] = self.config.device
            regressor_kwargs['tree_method'] = 'hist'

        chunk_idx = 1
        for chunk in dataset_builder.stream_training_samples(config, start_issue=train_bounds[0], end_issue=train_bounds[1], chunk_size=40000):
            if not chunk: continue

            if chunk_idx % 10 == 0:
                print(f"  [XGBoost] Streamed {chunk_idx} chunks into memory buffers...")
            chunk_idx += 1

            samples_by_model = {'gfs': [], 'ifs': [], 'icon': []}
            for s in chunk:
                samples_by_model[s.features.model].append(s)

            for m_key, m_samples in samples_by_model.items():
                if not m_samples: continue

                features = [s.features for s in m_samples]
                X = self.preprocessor.transform_batch(features)
                y = np.array([s.target.absolute_error for s in m_samples], dtype=np.float32)

                accumulated_X[m_key].append(X)
                accumulated_y[m_key].append(y)

            del chunk
            del samples_by_model
            gc.collect()

        print(f"  [XGBoost] Stream complete. Fitting {self.config.n_estimators} trees per model natively...")
        for m_key in ['gfs', 'ifs', 'icon']:
            if not accumulated_X[m_key]:
                continue

            X_all = np.concatenate(accumulated_X[m_key], axis=0)
            y_all = np.concatenate(accumulated_y[m_key], axis=0)

            # Clear intermediate buffers before invoking heavy C++ memory alloc
            accumulated_X[m_key] = []
            accumulated_y[m_key] = []
            gc.collect()

            model = xgb.XGBRegressor(**regressor_kwargs)
            model.fit(X_all, y_all)
            self.models[m_key] = model
            print(f"  [XGBoost] {m_key.upper()} trained. Trees: {model.get_booster().num_boosted_rounds()} (Shape: {X_all.shape})")

        self.is_trained = True
        return None

    def train(
        self,
        training_samples: List[TrainingSample],
        validation_samples: Optional[List[TrainingSample]] = None
    ) -> CandidateMetadata:
        """
        Train XGBoost candidate.

        Trains separate regressor for each model (GFS/IFS/ICON).

        Args:
            training_samples: Verified forecast-outcome pairs (chronological)
            validation_samples: Optional validation set (for early stopping)

        Returns:
            CandidateMetadata with training history
        """
        if not training_samples:
            raise ValueError("Cannot train: no training samples")

        self.logger.info(f"Training XGBoost on {len(training_samples)} samples")

        try:
            import xgboost as xgb
        except ImportError:
            raise ImportError(
                "XGBoost not installed. Install with: pip install xgboost"
            )

        # Fit preprocessor on training data
        self.preprocessor.fit(training_samples)

        # Group samples by model
        samples_by_model = {}
        for sample in training_samples:
            model = sample.features.model
            if model not in samples_by_model:
                samples_by_model[model] = []
            samples_by_model[model].append(sample)

        # Train separate regressor for each model
        for model, model_samples in samples_by_model.items():
            self.logger.info(f"Training XGBoost for {model}: {len(model_samples)} samples")

            # Extract features and targets
            feature_vectors = [s.features for s in model_samples]
            X_train = self.preprocessor.transform_batch(feature_vectors)
            y_train = np.array([s.target.absolute_error for s in model_samples], dtype=np.float32)

            # Prepare validation data if provided
            eval_set = None
            if validation_samples:
                val_model_samples = [s for s in validation_samples if s.features.model == model]
                if val_model_samples:
                    val_features = [s.features for s in val_model_samples]
                    X_val = self.preprocessor.transform_batch(val_features)
                    y_val = np.array([s.target.absolute_error for s in val_model_samples], dtype=np.float32)
                    eval_set = [(X_val, y_val)]

            # Determine whether early stopping is active for this model.
            # NOTE: In XGBoost >= 2.0 (this project uses 3.x), `early_stopping_rounds`
            # is a CONSTRUCTOR parameter and is no longer accepted by `fit()`.
            # We therefore configure it on the regressor only when a validation
            # eval_set is available. Semantics are unchanged: early stopping uses
            # ONLY the provided VALIDATION eval_set, never TRAIN or TEST.
            use_early_stopping = bool(eval_set) and bool(self.config.early_stopping_rounds)

            regressor_kwargs = dict(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                min_child_weight=self.config.min_child_weight,
                subsample=self.config.subsample,
                colsample_bytree=self.config.colsample_bytree,
                gamma=self.config.gamma,
                reg_alpha=self.config.reg_alpha,
                reg_lambda=self.config.reg_lambda,
                random_state=self.config.random_state,
                objective='reg:squarederror',
                tree_method='hist', device='cuda'  # RTX 5080
            )
            if use_early_stopping:
                regressor_kwargs['early_stopping_rounds'] = self.config.early_stopping_rounds

            # Create XGBoost regressor
            regressor = xgb.XGBRegressor(**regressor_kwargs)

            # Train (eval_set drives early stopping when configured above).
            if use_early_stopping:
                regressor.fit(
                    X_train,
                    y_train,
                    eval_set=eval_set,
                    verbose=False
                )
            else:
                regressor.fit(X_train, y_train, verbose=False)

            self.models[model] = regressor

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
                'n_estimators': self.config.n_estimators,
                'max_depth': self.config.max_depth,
                'learning_rate': self.config.learning_rate,
                'min_child_weight': self.config.min_child_weight,
                'subsample': self.config.subsample,
                'colsample_bytree': self.config.colsample_bytree,
                'gamma': self.config.gamma,
                'reg_alpha': self.config.reg_alpha,
                'reg_lambda': self.config.reg_lambda,
                'random_state': self.config.random_state
            }
        )

        self.logger.info(
            f"XGBoost trained: {len(training_samples)} samples, {len(samples_by_model)} models"
        )

        return self.metadata

    def predict_reliability(
        self,
        features: FeatureVector,
        models: List[str] = ['gfs', 'ifs', 'icon']
    ) -> Dict[str, ReliabilityPrediction]:
        """
        Predict reliability (expected error) for each model.

        Uses trained XGBoost regressors.

        Args:
            features: Feature vector (available at issue_time)
            models: Models to predict reliability for

        Returns:
            Dict mapping model name to ReliabilityPrediction
        """
        if not self.is_trained:
            raise ValueError("Cannot predict: model not trained")

        # Validate features
        is_valid, error_msg = self.feature_contract.validate_feature_vector(features)
        if not is_valid:
            raise ValueError(f"Invalid feature vector: {error_msg}")

        # Preprocess features
        x_query = self.preprocessor.transform(features)
        x_query = x_query.reshape(1, -1)  # Shape: (1, n_features)

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
            regressor = self.models[model]
            expected_mae = float(regressor.predict(x_query)[0])

            # Bound to positive values (safeguard against negative predictions)
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
        Evaluate XGBoost on held-out chronological test set.

        Args:
            test_samples: Held-out test samples (chronological, after training)

        Returns:
            EvaluationMetrics with performance on unseen future data
        """
        if not self.is_trained:
            raise ValueError("Cannot evaluate: model not trained")

        if not test_samples:
            raise ValueError("Cannot evaluate: no test samples")

        self.logger.info(f"Evaluating XGBoost on {len(test_samples)} test samples")

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

            # Reliability prediction error (predicted MAE vs actual absolute error)
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
