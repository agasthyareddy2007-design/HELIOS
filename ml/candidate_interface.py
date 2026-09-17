"""
HELIOS ML Candidate Interface

Defines the common interface for all ML candidate models competing in HELIOS
forecast blending: Kernel Regression, XGBoost, and MLP.

CRITICAL PRINCIPLES:
1. Single common interface (all candidates implement this)
2. Identical feature contract for all candidates
3. Reliability/expected-error outputs (not direct forecasts)
4. Convertible to non-negative normalized weights
5. No assumption of universal winner (competition-based selection)
6. Temporal leakage prevention (TemporalValidator integration)
7. Model promotion via unseen-future evaluation (not automatic)

DESIGN:
All candidates predict model reliability (expected error) rather than
direct forecast values. This allows natural conversion to blending weights:
    weight_i = (1 / expected_error_i) / sum_j(1 / expected_error_j)

INTERFACE CONTRACT:
- train(training_samples): Train on verified forecast-outcome pairs
- predict_reliability(features): Predict expected error for each model
- get_weights(features): Convert reliability to normalized weights
- evaluate(test_samples): Evaluate on held-out chronological test set
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import (
    FeatureVector,
    Target,
    TrainingSample,
    FeatureContract
)


logger = logging.getLogger(__name__)


class CandidateType(str, Enum):
    """ML candidate model types."""
    KERNEL_REGRESSION = "kernel_regression"
    XGBOOST = "xgboost"
    MLP = "mlp"
    SIMPLE_AVERAGE = "simple_average"  # Baseline (not learned)


@dataclass
class ReliabilityPrediction:
    """
    Reliability prediction for one forecast.

    Predicts expected error (reliability) rather than direct forecast value.
    """
    # Model being evaluated
    model: str  # 'gfs', 'ifs', or 'icon'

    # Reliability prediction
    expected_absolute_error: float  # Predicted MAE for this forecast
    expected_squared_error: float  # Predicted MSE for this forecast

    # Confidence/uncertainty (optional)
    prediction_std: Optional[float] = None  # Standard deviation of prediction
    confidence_interval: Optional[Tuple[float, float]] = None  # (lower, upper)

    # Metadata
    prediction_time: datetime = None  # When prediction was made


@dataclass
class WeightPrediction:
    """
    Blending weights for GFS/IFS/ICON.

    Weights sum to 1.0 and are non-negative.
    Derived from reliability predictions via inverse-error weighting.
    """
    # Weights (sum to 1.0, all >= 0)
    gfs_weight: float
    ifs_weight: float
    icon_weight: float

    # Reliability predictions that produced these weights
    gfs_reliability: ReliabilityPrediction
    ifs_reliability: ReliabilityPrediction
    icon_reliability: ReliabilityPrediction

    # Missing model handling
    gfs_available: bool
    ifs_available: bool
    icon_available: bool

    # Metadata
    prediction_time: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'gfs_weight': self.gfs_weight,
            'ifs_weight': self.ifs_weight,
            'icon_weight': self.icon_weight,
            'gfs_available': self.gfs_available,
            'ifs_available': self.ifs_available,
            'icon_available': self.icon_available,
            'prediction_time': self.prediction_time.isoformat()
        }


@dataclass
class EvaluationMetrics:
    """
    Evaluation metrics for candidate model.

    Measured on held-out chronological test set.
    """
    # Sample counts
    n_test_samples: int
    n_train_samples: int

    # Weight prediction quality
    weighted_forecast_rmse: float  # RMSE of weighted blend vs observation
    weighted_forecast_mae: float  # MAE of weighted blend vs observation
    weighted_forecast_bias: float  # Bias of weighted blend

    # Comparison to baseline
    simple_average_rmse: float  # RMSE of simple average blend
    improvement_over_baseline: float  # (baseline - learned) / baseline

    # Reliability prediction quality
    reliability_prediction_rmse: float  # How well we predict model errors

    # Temporal coverage
    test_period_start: datetime
    test_period_end: datetime
    test_span_days: float

    # Breakdown by context (optional)
    metrics_by_lead_time: Optional[Dict[int, Dict[str, float]]] = None
    metrics_by_zone: Optional[Dict[str, Dict[str, float]]] = None


@dataclass
class CandidateMetadata:
    """
    Metadata for candidate model.

    Tracks training history, version, hyperparameters.
    """
    candidate_type: CandidateType
    candidate_id: str  # Unique identifier
    version: str

    # Training metadata
    trained_at: datetime
    training_samples_count: int
    training_period_start: datetime
    training_period_end: datetime

    # Feature contract
    feature_contract_version: str  # Version of feature contract used

    # Hyperparameters (candidate-specific)
    hyperparameters: Dict[str, Any]

    # Performance on validation set (used for hyperparameter tuning)
    validation_metrics: Optional[EvaluationMetrics] = None


class BaseCandidateModel(ABC):
    """
    Base class for all HELIOS ML candidate models.

    ALL candidates (Kernel Regression, XGBoost, MLP) implement this interface.

    Design principles:
    - Identical feature contract (no per-candidate variations)
    - Predict reliability (expected error), not direct forecast values
    - Convert reliability to normalized weights
    - Temporal leakage prevention (no future information)
    - Chronological evaluation (never random splits)
    - Model promotion via unseen-future performance
    """

    def __init__(
        self,
        candidate_type: CandidateType,
        feature_contract: FeatureContract,
        candidate_id: Optional[str] = None
    ):
        """
        Initialize candidate model.

        Args:
            candidate_type: Type of candidate (Kernel/XGBoost/MLP)
            feature_contract: Feature contract (shared by all candidates)
            candidate_id: Unique identifier (auto-generated if None)
        """
        self.candidate_type = candidate_type
        self.feature_contract = feature_contract
        self.candidate_id = candidate_id or self._generate_candidate_id()
        self.logger = logging.getLogger(__name__)

        # Training state
        self.is_trained = False
        self.metadata: Optional[CandidateMetadata] = None

    def _generate_candidate_id(self) -> str:
        """Generate unique candidate ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{self.candidate_type.value}_{timestamp}"

    @abstractmethod
    def train(
        self,
        training_samples: List[TrainingSample],
        validation_samples: Optional[List[TrainingSample]] = None
    ) -> CandidateMetadata:
        """
        Train candidate model on verified forecast-outcome pairs.

        CRITICAL: Training samples must satisfy temporal constraints:
        - Features computed using data available at issue_time
        - Targets known only after valid_time + observation
        - Historical features: period_end < issue_time (strictly)

        Args:
            training_samples: Verified forecast-outcome pairs (chronological)
            validation_samples: Optional validation set (chronological, after training)

        Returns:
            CandidateMetadata with training history

        Raises:
            ValueError: If samples violate temporal constraints
        """
        pass

    @abstractmethod
    def predict_reliability(
        self,
        features: FeatureVector,
        models: List[str] = ['gfs', 'ifs', 'icon']
    ) -> Dict[str, ReliabilityPrediction]:
        """
        Predict reliability (expected error) for each model.

        CRITICAL: Predictions use ONLY features available at issue_time.
        NEVER use observed values or future verification results.

        Args:
            features: Feature vector (available at issue_time)
            models: Models to predict reliability for

        Returns:
            Dict mapping model name to ReliabilityPrediction
            Example: {'gfs': ReliabilityPrediction(...), 'ifs': ..., 'icon': ...}

        Raises:
            ValueError: If model not trained
            ValueError: If features violate temporal constraints
        """
        pass

    def get_weights(
        self,
        features: FeatureVector,
        models: List[str] = ['gfs', 'ifs', 'icon'],
        epsilon: float = 0.001
    ) -> WeightPrediction:
        """
        Convert reliability predictions to normalized blending weights.

        Weights are computed via inverse-error weighting:
            raw_weight_i = 1 / (expected_error_i + epsilon)
            weight_i = raw_weight_i / sum_j(raw_weight_j)

        Args:
            features: Feature vector (available at issue_time)
            models: Models to compute weights for
            epsilon: Small constant to avoid division by zero

        Returns:
            WeightPrediction with normalized weights (sum to 1.0, all >= 0)

        Raises:
            ValueError: If model not trained
        """
        if not self.is_trained:
            raise ValueError("Cannot predict weights: model not trained")

        # Get reliability predictions
        reliability_preds = self.predict_reliability(features, models)

        # Compute raw weights via inverse-error weighting
        raw_weights = {}
        for model, pred in reliability_preds.items():
            # Use expected absolute error (MAE) for weighting
            expected_error = pred.expected_absolute_error
            # Bound error to avoid division by zero
            bounded_error = max(expected_error, epsilon)
            raw_weights[model] = 1.0 / bounded_error

        # Normalize to sum to 1.0
        total_weight = sum(raw_weights.values())
        normalized_weights = {
            model: weight / total_weight
            for model, weight in raw_weights.items()
        }

        # Extract individual model weights
        gfs_weight = normalized_weights.get('gfs', 0.0)
        ifs_weight = normalized_weights.get('ifs', 0.0)
        icon_weight = normalized_weights.get('icon', 0.0)

        # Check availability
        gfs_available = features.gfs_available
        ifs_available = features.ifs_available
        icon_available = features.icon_available

        # If model unavailable, zero its weight and renormalize
        if not gfs_available:
            gfs_weight = 0.0
        if not ifs_available:
            ifs_weight = 0.0
        if not icon_available:
            icon_weight = 0.0

        # Renormalize among available models
        total_available = gfs_weight + ifs_weight + icon_weight
        if total_available > 0:
            gfs_weight /= total_available
            ifs_weight /= total_available
            icon_weight /= total_available

        return WeightPrediction(
            gfs_weight=gfs_weight,
            ifs_weight=ifs_weight,
            icon_weight=icon_weight,
            gfs_reliability=reliability_preds.get('gfs'),
            ifs_reliability=reliability_preds.get('ifs'),
            icon_reliability=reliability_preds.get('icon'),
            gfs_available=gfs_available,
            ifs_available=ifs_available,
            icon_available=icon_available,
            prediction_time=datetime.utcnow()
        )

    @abstractmethod
    def evaluate(
        self,
        test_samples: List[TrainingSample]
    ) -> EvaluationMetrics:
        """
        Evaluate candidate on held-out chronological test set.

        CRITICAL: Test set must be chronologically AFTER training/validation.
        NEVER use random splits or future-to-past evaluation.

        Args:
            test_samples: Held-out test samples (chronological, after training)

        Returns:
            EvaluationMetrics with performance on unseen future data

        Raises:
            ValueError: If model not trained
            ValueError: If test samples violate chronological ordering
        """
        pass

    def get_metadata(self) -> Optional[CandidateMetadata]:
        """
        Get candidate metadata (training history, hyperparameters).

        Returns:
            CandidateMetadata if model trained, None otherwise
        """
        return self.metadata

    def is_eligible_for_promotion(
        self,
        test_metrics: EvaluationMetrics,
        baseline_metrics: EvaluationMetrics,
        min_improvement: float = 0.01,
        min_test_samples: int = 500
    ) -> Tuple[bool, str]:
        """
        Check if candidate is eligible for promotion to production.

        CRITICAL: Promotion requires BOTH:
        1. Data sufficiency (enough test samples)
        2. Performance improvement over baseline on unseen future data

        Args:
            test_metrics: Performance on held-out test set
            baseline_metrics: SimpleAverage baseline performance on same test set
            min_improvement: Minimum improvement over baseline (e.g., 0.01 = 1%)
            min_test_samples: Minimum test samples required

        Returns:
            (is_eligible, reason)
        """
        # Check data sufficiency
        if test_metrics.n_test_samples < min_test_samples:
            return False, f"Insufficient test samples ({test_metrics.n_test_samples} < {min_test_samples})"

        # Check performance improvement
        improvement = test_metrics.improvement_over_baseline
        if improvement < min_improvement:
            return False, f"Insufficient improvement over baseline ({improvement:.3f} < {min_improvement})"

        # Check that learned blend is actually better
        if test_metrics.weighted_forecast_rmse >= baseline_metrics.weighted_forecast_rmse:
            return False, "Learned blend does not outperform SimpleAverage baseline"

        return True, "Eligible for promotion (sufficient data + performance improvement)"


class SimpleAverageCandidateAdapter(BaseCandidateModel):
    """
    Adapter to expose SimpleAverageBlender as a candidate.

    This is the permanent baseline, NOT a learned model.
    Always uses equal weights (1/N among available models).

    Used for comparison only.
    """

    def __init__(self, feature_contract: FeatureContract):
        """Initialize SimpleAverage candidate adapter."""
        super().__init__(
            candidate_type=CandidateType.SIMPLE_AVERAGE,
            feature_contract=feature_contract,
            candidate_id="simple_average_baseline"
        )
        # SimpleAverage is always "trained" (no parameters to learn)
        self.is_trained = True
        self.metadata = CandidateMetadata(
            candidate_type=CandidateType.SIMPLE_AVERAGE,
            candidate_id=self.candidate_id,
            version="1.0.0",
            trained_at=datetime.utcnow(),
            training_samples_count=0,
            training_period_start=datetime.utcnow(),
            training_period_end=datetime.utcnow(),
            feature_contract_version="1.0.0",
            hyperparameters={}
        )

    def train(
        self,
        training_samples: List[TrainingSample],
        validation_samples: Optional[List[TrainingSample]] = None
    ) -> CandidateMetadata:
        """SimpleAverage requires no training."""
        return self.metadata

    def predict_reliability(
        self,
        features: FeatureVector,
        models: List[str] = ['gfs', 'ifs', 'icon']
    ) -> Dict[str, ReliabilityPrediction]:
        """
        SimpleAverage predicts equal reliability (no learned preference).

        Returns uniform expected error for all models.
        """
        # Use same expected error for all models (equal reliability assumption)
        uniform_error = 1.0  # Arbitrary constant (weights will be equal regardless)

        predictions = {}
        for model in models:
            predictions[model] = ReliabilityPrediction(
                model=model,
                expected_absolute_error=uniform_error,
                expected_squared_error=uniform_error ** 2,
                prediction_time=datetime.utcnow()
            )

        return predictions

    def evaluate(
        self,
        test_samples: List[TrainingSample]
    ) -> EvaluationMetrics:
        """
        Evaluate SimpleAverage on test set.

        Computes equal-weight blend performance.
        """
        if not test_samples:
            raise ValueError("Cannot evaluate: no test samples")

        # Compute equal-weight blend for each sample
        squared_errors = []
        absolute_errors = []
        errors = []

        for sample in test_samples:
            features = sample.features
            target = sample.target

            # Get available forecast values
            available_forecasts = []
            if features.gfs_available and features.gfs_value is not None:
                available_forecasts.append(features.gfs_value)
            if features.ifs_available and features.ifs_value is not None:
                available_forecasts.append(features.ifs_value)
            if features.icon_available and features.icon_value is not None:
                available_forecasts.append(features.icon_value)

            if not available_forecasts:
                continue  # Skip if no models available

            # Equal-weight blend
            blended_forecast = sum(available_forecasts) / len(available_forecasts)

            # Compute errors
            error = blended_forecast - target.observed_value
            absolute_error = abs(error)
            squared_error = error ** 2

            errors.append(error)
            absolute_errors.append(absolute_error)
            squared_errors.append(squared_error)

        # Aggregate metrics
        import math
        rmse = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else 0.0
        mae = sum(absolute_errors) / len(absolute_errors) if absolute_errors else 0.0
        bias = sum(errors) / len(errors) if errors else 0.0

        # Extract temporal coverage
        if test_samples:
            times = [s.features.valid_time for s in test_samples]
            test_period_start = min(times)
            test_period_end = max(times)
            test_span_days = (test_period_end - test_period_start).total_seconds() / 86400
        else:
            test_period_start = datetime.utcnow()
            test_period_end = datetime.utcnow()
            test_span_days = 0.0

        return EvaluationMetrics(
            n_test_samples=len(test_samples),
            n_train_samples=0,  # SimpleAverage uses no training
            weighted_forecast_rmse=rmse,
            weighted_forecast_mae=mae,
            weighted_forecast_bias=bias,
            simple_average_rmse=rmse,  # Same as weighted (equal weights)
            improvement_over_baseline=0.0,  # Baseline = itself
            reliability_prediction_rmse=0.0,  # N/A for baseline
            test_period_start=test_period_start,
            test_period_end=test_period_end,
            test_span_days=test_span_days
        )
