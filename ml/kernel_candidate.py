"""
HELIOS Kernel Regression Candidate

Scalable localized kernel regression for forecast reliability prediction.

CRITICAL DESIGN PRINCIPLES:
1. NOT naive O(N²) kernel regression
2. Scalable nearest-neighbor approach using KDTree
3. Gaussian kernel weighting
4. Predict reliability (expected error), not direct forecast values
5. Use canonical 24-feature contract
6. Temporal leakage prevention
7. Missing-model handling

ARCHITECTURE:
- Store training data efficiently (KDTree for fast lookup)
- Predict by finding K nearest neighbors in feature space
- Weight neighbors by Gaussian kernel
- Predict expected error for each model
- Convert to blending weights via inverse-error weighting

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
class KernelConfig:
    """Configuration for kernel regression."""
    n_neighbors: int = 50  # Number of nearest neighbors
    bandwidth: float = 1.0  # Gaussian kernel bandwidth
    min_neighbors: int = 5  # Minimum neighbors required for prediction


class KernelRegressionCandidate(BaseCandidateModel):
    """
    Scalable kernel regression candidate for HELIOS forecast blending.

    Design:
    - Localized approach (K-nearest neighbors, not full O(N²))
    - Gaussian kernel weighting
    - Separate prediction for each model (GFS/IFS/ICON)
    - Predicts expected absolute error (reliability)
    - Converts to blending weights via inverse-error weighting

    Temporal safety:
    - Training: features before issue_time, targets after verification
    - Prediction: uses only features available at issue_time
    """

    def __init__(
        self,
        feature_contract: FeatureContract,
        config: Optional[KernelConfig] = None,
        candidate_id: Optional[str] = None
    ):
        """
        Initialize kernel regression candidate.

        Args:
            feature_contract: Feature contract (shared by all candidates)
            config: Kernel configuration
            candidate_id: Unique identifier (auto-generated if None)
        """
        super().__init__(
            candidate_type=CandidateType.KERNEL_REGRESSION,
            feature_contract=feature_contract,
            candidate_id=candidate_id
        )

        self.config = config or KernelConfig()
        self.preprocessor = FeaturePreprocessor()

        # Per-model training representation (SCALABILITY FIX).
        # Each model gets its OWN KDTree over ONLY that model's preprocessed
        # feature rows, plus an aligned array of that model's absolute errors.
        # This makes prediction a bounded k-NN query in the target model's tree
        # (O(k log N_model)) instead of an O(N) scan + post-hoc filter per query.
        self.X_train_by_model: Dict[str, np.ndarray] = {}   # model -> (N_m, D) features
        self.y_train_by_model: Dict[str, np.ndarray] = {}   # model -> (N_m,) abs errors
        self.kdtree_by_model: Dict[str, Any] = {}           # model -> cKDTree | None

        # Backward-compatible view of ALL preprocessed training features
        # (kept for tests/introspection; NOT used for per-query filtering).
        self.X_train: Optional[np.ndarray] = None

        # Whether a fast spatial index (scipy cKDTree/KDTree) is available.
        self._use_kdtree: bool = True

        # Training metadata
        self.training_samples_count: int = 0


    def stream_train(self, dataset_builder, config, train_bounds, validation_samples=None, kernel_support_limit=20000):
        import collections
        buffer = collections.deque(maxlen=kernel_support_limit)
        
        for chunk in dataset_builder.stream_training_samples(config, start_issue=train_bounds[0], end_issue=train_bounds[1], chunk_size=20000):
            if chunk:
                buffer.extend(chunk)
                
        return self.train(list(buffer))

    def train(
        self,
        training_samples: List[TrainingSample],
        validation_samples: Optional[List[TrainingSample]] = None
    ) -> CandidateMetadata:
        """
        Train kernel regression candidate.

        CRITICAL: Training is preparation, not learning parameters.
        We store the training data and build KDTree for fast lookup.

        Args:
            training_samples: Verified forecast-outcome pairs (chronological)
            validation_samples: Optional validation set (not used by kernel regression)

        Returns:
            CandidateMetadata with training history
        """
        if not training_samples:
            raise ValueError("Cannot train: no training samples")

        self.logger.info(f"Training kernel regression on {len(training_samples)} samples")

        # Fit preprocessor on training data ONLY.
        self.preprocessor.fit(training_samples)

        # Transform all training features once (deterministic, order-preserving).
        feature_vectors = [s.features for s in training_samples]
        X_all = self.preprocessor.transform_batch(feature_vectors)
        self.X_train = X_all  # retained for introspection/tests only

        # Group row indices by model, preserving the (chronological) input order.
        indices_by_model: Dict[str, List[int]] = {}
        for i, sample in enumerate(training_samples):
            model = sample.features.model
            indices_by_model.setdefault(model, []).append(i)

        # Build a SEPARATE feature matrix, target array, and KDTree per model.
        # Rationale: reliability is predicted per model, so neighbors must come
        # from the SAME model's history. Per-model trees make each query a
        # bounded k-NN search in only that model's rows (no global scan/filter).
        self.X_train_by_model = {}
        self.y_train_by_model = {}
        self.kdtree_by_model = {}

        # Detect a fast spatial index once.
        KDTreeImpl = None
        try:
            from scipy.spatial import cKDTree as KDTreeImpl  # type: ignore
        except ImportError:
            try:
                from scipy.spatial import KDTree as KDTreeImpl  # type: ignore
            except ImportError:
                KDTreeImpl = None
        self._use_kdtree = KDTreeImpl is not None
        if not self._use_kdtree:
            self.logger.warning(
                "scipy KDTree unavailable; falling back to per-model brute-force "
                "search (still bounded to each model's rows)."
            )

        for model, idxs in indices_by_model.items():
            idx_arr = np.asarray(idxs, dtype=np.int64)
            Xm = X_all[idx_arr]
            ym = np.array(
                [training_samples[i].target.absolute_error for i in idxs],
                dtype=np.float32,
            )
            self.X_train_by_model[model] = Xm
            self.y_train_by_model[model] = ym
            self.kdtree_by_model[model] = (
                KDTreeImpl(Xm) if (self._use_kdtree and len(Xm) > 0) else None
            )

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
                'n_neighbors': self.config.n_neighbors,
                'bandwidth': self.config.bandwidth,
                'min_neighbors': self.config.min_neighbors
            }
        )

        self.logger.info(
            f"Kernel regression trained: {len(training_samples)} samples, "
            f"{len(self.kdtree_by_model)} models"
        )

        return self.metadata

    def predict_reliability(
        self,
        features: FeatureVector,
        models: List[str] = ['gfs', 'ifs', 'icon']
    ) -> Dict[str, ReliabilityPrediction]:
        """
        Predict reliability (expected error) for each model.

        Uses K-nearest neighbors with Gaussian kernel weighting.

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

        # Preprocess the query into the SAME numeric representation used to
        # build the per-model indices.
        x_query = self.preprocessor.transform(features)

        predictions: Dict[str, ReliabilityPrediction] = {}
        for model in models:
            predictions[model] = self._predict_single_model(model, x_query)
        return predictions

    def _predict_single_model(
        self, model: str, x_query: np.ndarray
    ) -> ReliabilityPrediction:
        """
        Predict expected absolute error for ONE model using that model's own
        KDTree (or bounded brute force if scipy is unavailable).

        Complexity: O(k log N_model) with a KDTree, versus the previous
        O(N) per-query scan + post-hoc filter. Semantics are preserved:
        Gaussian-kernel-weighted average of the nearest neighbours' absolute
        errors, weights renormalised within the model's own neighbourhood.
        """
        now = datetime.utcnow()

        # Model absent from training data -> conservative default.
        Xm = self.X_train_by_model.get(model)
        ym = self.y_train_by_model.get(model)
        if Xm is None or ym is None or len(ym) < self.config.min_neighbors:
            return ReliabilityPrediction(
                model=model,
                expected_absolute_error=1.0,  # conservative default
                expected_squared_error=1.0,
                prediction_time=now,
            )

        k = int(min(self.config.n_neighbors, len(ym)))
        tree = self.kdtree_by_model.get(model)

        if tree is not None:
            # Bounded k-NN search in ONLY this model's tree.
            distances, indices = tree.query(x_query, k=k)
            distances = np.atleast_1d(np.asarray(distances, dtype=np.float64))
            indices = np.atleast_1d(np.asarray(indices, dtype=np.int64))
        else:
            # Fallback: brute force over ONLY this model's rows (still bounded
            # to N_model, never the whole dataset), then take k smallest.
            dist_all = np.linalg.norm(Xm - x_query, axis=1)
            indices = np.argsort(dist_all)[:k]
            distances = dist_all[indices]

        if len(indices) < self.config.min_neighbors:
            return ReliabilityPrediction(
                model=model,
                expected_absolute_error=1.0,
                expected_squared_error=1.0,
                prediction_time=now,
            )

        # Gaussian kernel weights over the neighbour distances.
        weights = np.exp(-(distances ** 2) / (2.0 * self.config.bandwidth ** 2))
        weight_sum = weights.sum()
        if weight_sum > 0:
            weights = weights / weight_sum
        else:
            weights = np.ones_like(weights) / len(weights)

        neighbor_errors = ym[indices].astype(np.float64)
        expected_mae = float(np.sum(weights * neighbor_errors))
        expected_mse = float(np.sum(weights * (neighbor_errors ** 2)))
        variance = float(np.sum(weights * ((neighbor_errors - expected_mae) ** 2)))
        prediction_std = float(np.sqrt(max(variance, 0.0)))

        # Reliability (expected absolute error) is non-negative by construction
        # (weighted average of non-negative absolute errors); clamp for safety.
        expected_mae = max(expected_mae, 0.0)

        return ReliabilityPrediction(
            model=model,
            expected_absolute_error=expected_mae,
            expected_squared_error=expected_mse,
            prediction_std=prediction_std,
            prediction_time=now,
        )

    def evaluate(
        self,
        test_samples: List[TrainingSample]
    ) -> EvaluationMetrics:
        """
        Evaluate kernel regression on held-out chronological test set.

        Args:
            test_samples: Held-out test samples (chronological, after training)

        Returns:
            EvaluationMetrics with performance on unseen future data
        """
        if not self.is_trained:
            raise ValueError("Cannot evaluate: model not trained")

        if not test_samples:
            raise ValueError("Cannot evaluate: no test samples")

        self.logger.info(f"Evaluating kernel regression on {len(test_samples)} test samples")

        # Compute weighted blend for each test sample
        squared_errors = []
        absolute_errors = []
        errors = []

        # For baseline comparison
        simple_avg_squared_errors = []

        for sample in test_samples:
            features = sample.features
            target = sample.target

            # Get blending weights
            weight_pred = self.get_weights(features)

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

        # Aggregate metrics
        import math
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else 0.0
        mae = sum(absolute_errors) / len(absolute_errors) if absolute_errors else 0.0
        bias = sum(errors) / len(errors) if errors else 0.0

        simple_avg_rmse = math.sqrt(
            sum(simple_avg_squared_errors) / len(simple_avg_squared_errors)
        ) if simple_avg_squared_errors else 0.0

        improvement = (simple_avg_rmse - rmse) / simple_avg_rmse if simple_avg_rmse > 0 else 0.0

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
            reliability_prediction_rmse=0.0,  # TODO: implement
            test_period_start=test_period_start,
            test_period_end=test_period_end,
            test_span_days=test_span_days
        )
