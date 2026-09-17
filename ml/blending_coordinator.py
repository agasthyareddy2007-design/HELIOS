"""
HELIOS Blending Pipeline Coordinator

Coordinates the complete pathway from database records to HELIOS blend:

Database records
    ↓
Feature reconstruction
    ↓
Canonical 24-feature vector
    ↓
Preprocessing
    ↓
ML candidate (Kernel/XGBoost/MLP)
    ↓
Reliability prediction
    ↓
Dynamic weights
    ↓
HELIOS blend

Integrates:
- FeatureBuilder (feature reconstruction)
- DataSufficiencyChecker (training eligibility gate)
- TemporalValidator (temporal safety)
- FeatureContract (canonical contract)
- BaseCandidateModel (all ML candidates)
- SimpleAverageBlender (permanent baseline)

CRITICAL: This is integration infrastructure only.
Does NOT perform real training or real-data evaluation.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_builder import FeatureBuilder, ForecastRecord, HistoricalReliability
from ml.feature_contract import FeatureVector, FeatureContract
from ml.candidate_interface import BaseCandidateModel, WeightPrediction
from validation.data_sufficiency_checker import DataSufficiencyChecker, SufficiencyResult
from validation.temporal_validator import TemporalValidator


logger = logging.getLogger(__name__)


class BlendingMode(str, Enum):
    """Blending mode based on data sufficiency."""
    SIMPLE_AVERAGE = "simple_average"  # Cold start / insufficient data
    ML_DYNAMIC = "ml_dynamic"  # Sufficient data, ML candidate deployed


@dataclass
class BlendRequest:
    """
    Request for HELIOS blend at one (issue_time, valid_time, location, variable).

    Contains current NWP forecasts and optional historical reliability.
    """
    issue_time: datetime
    valid_time: datetime
    latitude: float
    longitude: float
    location_zone: Optional[str]
    variable: str
    forecasts: Dict[str, float]  # model → forecast_value
    historical_reliability: Optional[Dict[str, HistoricalReliability]] = None


@dataclass
class BlendResult:
    """
    HELIOS blend result with weights and blended value.
    """
    blended_value: float
    mode: BlendingMode
    weights: WeightPrediction
    gfs_forecast: Optional[float]
    ifs_forecast: Optional[float]
    icon_forecast: Optional[float]
    issue_time: datetime
    valid_time: datetime
    blend_time: datetime


class BlendingPipelineCoordinator:
    """
    Coordinates the complete HELIOS blending pipeline.

    Design principles:
    - Integration infrastructure (NOT training/evaluation)
    - Data sufficiency gates ML usage (cold start → SimpleAverage)
    - Temporal safety enforced throughout
    - Exact forecast identity preserved
    - SimpleAverage permanent baseline fallback

    Integration points:
    - FeatureBuilder: Reconstruct canonical features
    - DataSufficiencyChecker: Gate ML candidate eligibility
    - ML candidates: Predict reliability → weights
    - SimpleAverage: Permanent baseline fallback
    """

    def __init__(
        self,
        ml_candidate: Optional[BaseCandidateModel] = None,
        data_sufficiency_checker: Optional[DataSufficiencyChecker] = None,
        feature_builder: Optional[FeatureBuilder] = None
    ):
        """
        Initialize blending pipeline coordinator.

        Args:
            ml_candidate: Trained ML candidate (Kernel/XGBoost/MLP)
                         If None, always uses SimpleAverage
            data_sufficiency_checker: Data sufficiency checker
                                     If None, creates default
            feature_builder: Feature builder
                           If None, creates default
        """
        self.logger = logging.getLogger(__name__)

        self.ml_candidate = ml_candidate
        self.data_sufficiency_checker = data_sufficiency_checker or DataSufficiencyChecker()
        self.feature_builder = feature_builder or FeatureBuilder()

        self.feature_contract = FeatureContract()
        self.temporal_validator = TemporalValidator()

    def blend(
        self,
        request: BlendRequest,
        force_mode: Optional[BlendingMode] = None
    ) -> BlendResult:
        """
        Produce HELIOS blend for one forecast scenario.

        CRITICAL: Uses ONLY information available at issue_time.

        Args:
            request: Blend request with forecasts and optional history
            force_mode: Force specific blending mode (for testing)
                       None = automatic (data sufficiency decides)

        Returns:
            BlendResult with weights and blended value

        Raises:
            ValueError: If temporal constraints violated
            ValueError: If no models available
        """
        # Validate chronology
        result = self.temporal_validator.validate_forecast_chronology(
            request.issue_time, request.valid_time
        )
        if not result.is_valid:
            raise ValueError(f"Invalid forecast chronology: {result.error_message}")

        # Check available models
        available_models = [
            model for model, value in request.forecasts.items()
            if value is not None
        ]

        if not available_models:
            raise ValueError("No forecast models available")

        # Determine blending mode
        if force_mode:
            mode = force_mode
        else:
            mode = self._determine_blending_mode(
                request.variable,
                request.location_zone
            )

        # Select blending strategy
        if mode == BlendingMode.ML_DYNAMIC and self.ml_candidate and self.ml_candidate.is_trained:
            # Use ML candidate for dynamic weighting
            weights, blended_value = self._blend_with_ml_candidate(request)
        else:
            # Fall back to SimpleAverage
            mode = BlendingMode.SIMPLE_AVERAGE
            weights, blended_value = self._blend_with_simple_average(request)

        return BlendResult(
            blended_value=blended_value,
            mode=mode,
            weights=weights,
            gfs_forecast=request.forecasts.get('gfs'),
            ifs_forecast=request.forecasts.get('ifs'),
            icon_forecast=request.forecasts.get('icon'),
            issue_time=request.issue_time,
            valid_time=request.valid_time,
            blend_time=datetime.utcnow()
        )

    def _determine_blending_mode(
        self,
        variable: str,
        location_zone: Optional[str]
    ) -> BlendingMode:
        """
        Determine blending mode based on data sufficiency.

        CRITICAL: Data sufficiency is a TRAINING ELIGIBILITY GATE only.
        It does NOT:
        - Promote a model
        - Select a winning model
        - Replace SimpleAverage in production
        - Trigger production deployment

        Args:
            variable: Weather variable
            location_zone: Location zone

        Returns:
            BlendingMode (SIMPLE_AVERAGE or ML_DYNAMIC)
        """
        # Check data sufficiency for this modeling slice
        sufficiency = self.data_sufficiency_checker.check_sufficiency(
            variable=variable,
            location_zone=location_zone
        )

        # Gate: ML only if sufficient data
        if sufficiency.is_sufficient and self.ml_candidate and self.ml_candidate.is_trained:
            return BlendingMode.ML_DYNAMIC
        else:
            return BlendingMode.SIMPLE_AVERAGE

    def _blend_with_ml_candidate(
        self,
        request: BlendRequest
    ) -> Tuple[WeightPrediction, float]:
        """
        Blend using ML candidate (Kernel/XGBoost/MLP).

        CRITICAL: Uses ONLY features available at issue_time.

        Args:
            request: Blend request

        Returns:
            (weights, blended_value)
        """
        # Reconstruct canonical feature vector
        # Use first available model as target (arbitrary choice for weighting)
        available_models = [m for m, v in request.forecasts.items() if v is not None]
        target_model = available_models[0]

        feature_vector = self.feature_builder.build_feature_vector(
            target_model=target_model,
            issue_time=request.issue_time,
            valid_time=request.valid_time,
            location=(request.latitude, request.longitude),
            location_zone=request.location_zone,
            variable=request.variable,
            forecasts=request.forecasts,
            historical_reliability=request.historical_reliability
        )

        # Get dynamic weights from ML candidate
        weights = self.ml_candidate.get_weights(feature_vector)

        # Compute weighted blend
        blended_value = 0.0

        if request.forecasts.get('gfs') is not None:
            blended_value += weights.gfs_weight * request.forecasts['gfs']

        if request.forecasts.get('ifs') is not None:
            blended_value += weights.ifs_weight * request.forecasts['ifs']

        if request.forecasts.get('icon') is not None:
            blended_value += weights.icon_weight * request.forecasts['icon']

        return weights, blended_value

    def _blend_with_simple_average(
        self,
        request: BlendRequest
    ) -> Tuple[WeightPrediction, float]:
        """
        Blend using SimpleAverage (permanent baseline).

        Args:
            request: Blend request

        Returns:
            (weights, blended_value)
        """
        # Get available forecasts
        available_forecasts = {
            model: value
            for model, value in request.forecasts.items()
            if value is not None
        }

        if not available_forecasts:
            raise ValueError("No forecasts available")

        # Equal weights
        n_models = len(available_forecasts)
        equal_weight = 1.0 / n_models

        # Assign weights
        gfs_weight = equal_weight if 'gfs' in available_forecasts else 0.0
        ifs_weight = equal_weight if 'ifs' in available_forecasts else 0.0
        icon_weight = equal_weight if 'icon' in available_forecasts else 0.0

        # Create WeightPrediction (with dummy reliability predictions)
        from ml.candidate_interface import ReliabilityPrediction

        uniform_reliability = 1.0  # Arbitrary (equal weights regardless)

        weights = WeightPrediction(
            gfs_weight=gfs_weight,
            ifs_weight=ifs_weight,
            icon_weight=icon_weight,
            gfs_reliability=ReliabilityPrediction(
                model='gfs',
                expected_absolute_error=uniform_reliability,
                expected_squared_error=uniform_reliability ** 2,
                prediction_time=datetime.utcnow()
            ),
            ifs_reliability=ReliabilityPrediction(
                model='ifs',
                expected_absolute_error=uniform_reliability,
                expected_squared_error=uniform_reliability ** 2,
                prediction_time=datetime.utcnow()
            ),
            icon_reliability=ReliabilityPrediction(
                model='icon',
                expected_absolute_error=uniform_reliability,
                expected_squared_error=uniform_reliability ** 2,
                prediction_time=datetime.utcnow()
            ),
            gfs_available='gfs' in available_forecasts,
            ifs_available='ifs' in available_forecasts,
            icon_available='icon' in available_forecasts,
            prediction_time=datetime.utcnow()
        )

        # Simple average
        blended_value = sum(available_forecasts.values()) / n_models

        return weights, blended_value
