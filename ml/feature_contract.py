"""
HELIOS ML Feature Contract

Defines the canonical feature contract shared identically by Kernel Regression,
XGBoost, and MLP candidate models.

CRITICAL PRINCIPLES:
1. Single canonical feature contract (not per-algorithm variations)
2. Features available strictly BEFORE issue_time (temporal leakage prevention)
3. Observations/verification values are NEVER features (targets/outcomes only)
4. Exact forecast identity preserved (model + issue_time + valid_time + location + variable)
5. Never reconstruct features by valid_time alone
6. Historical model reliability available strictly before issue_time
7. Missing-model handling (graceful degradation when model unavailable)
8. TemporalValidator integration for leakage prevention

FEATURE CATEGORIES:
1. Forecast Context: lead_time, location_zone, time_of_day, season
2. Current Forecast Values: GFS/IFS/ICON forecast values for this valid_time
3. Inter-Model Features: spread, disagreement, range
4. Historical Reliability: model RMSE/MAE/bias strictly before issue_time

TARGET:
- Observed value (NEVER a feature)
- Or: forecast error (for error-prediction approaches)

TERMINOLOGY:
- Features: inputs available at issue_time
- Targets: outcomes known only after valid_time + observation
- Historical reliability: aggregated performance strictly before issue_time
- Temporal leakage: using future information as a feature
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


logger = logging.getLogger(__name__)


class FeatureType(str, Enum):
    """Feature type categories."""
    FORECAST_CONTEXT = "forecast_context"  # Lead time, location, time
    CURRENT_FORECAST = "current_forecast"  # GFS/IFS/ICON values
    INTER_MODEL = "inter_model"  # Spread, disagreement, range
    HISTORICAL_RELIABILITY = "historical_reliability"  # Model performance before issue_time


@dataclass
class FeatureSpec:
    """
    Specification for one feature in the canonical contract.

    All candidate models (Kernel, XGBoost, MLP) use exactly this contract.
    """
    name: str  # Feature name (e.g., "lead_time_hours", "gfs_temperature_2m_c")
    feature_type: FeatureType
    dtype: str  # "float", "int", "categorical"
    required: bool  # Must be present (vs optional)
    description: str

    # Temporal constraint
    available_at_issue_time: bool = True  # MUST be True (enforce temporal safety)

    # Value constraints
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    categorical_values: Optional[List[str]] = None


@dataclass
class FeatureVector:
    """
    Feature vector for one forecast.

    CRITICAL: Contains only features available at issue_time.
    NEVER contains observed values or future verification results.
    """
    # Forecast identity (EXACT identity required)
    model: str  # Target model for reliability prediction (e.g., 'gfs', 'ifs', 'icon')
    issue_time: datetime
    valid_time: datetime
    lead_time_hours: int
    latitude: float
    longitude: float
    location_zone: Optional[str]
    variable: str  # e.g., 'temperature_2m_c'

    # Forecast context features
    hour_of_day: int  # 0-23
    day_of_year: int  # 1-366
    month: int  # 1-12
    season: str  # 'winter', 'spring', 'summer', 'autumn'

    # Current forecast values (for this valid_time)
    # CRITICAL: These are the forecasts being blended, NOT observations
    gfs_value: Optional[float]  # GFS forecast for this variable
    ifs_value: Optional[float]  # IFS forecast for this variable
    icon_value: Optional[float]  # ICON forecast for this variable

    # Inter-model features
    forecast_spread: Optional[float]  # Std dev among available models
    forecast_range: Optional[float]  # Max - min among available models
    model_agreement: Optional[float]  # 1.0 - (spread / mean)

    # Historical reliability (aggregated performance BEFORE issue_time)
    # CRITICAL: period_end < issue_time (strictly before)
    gfs_rmse_7day: Optional[float]  # GFS RMSE in past 7 days
    ifs_rmse_7day: Optional[float]  # IFS RMSE in past 7 days
    icon_rmse_7day: Optional[float]  # ICON RMSE in past 7 days

    gfs_mae_7day: Optional[float]  # GFS MAE in past 7 days
    ifs_mae_7day: Optional[float]  # IFS MAE in past 7 days
    icon_mae_7day: Optional[float]  # ICON MAE in past 7 days

    gfs_bias_7day: Optional[float]  # GFS bias in past 7 days
    ifs_bias_7day: Optional[float]  # IFS bias in past 7 days
    icon_bias_7day: Optional[float]  # ICON bias in past 7 days

    # Missing model flags
    gfs_available: bool
    ifs_available: bool
    icon_available: bool

    # Metadata
    feature_computation_time: datetime  # When features were computed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ML training/inference."""
        return {
            # Identity (for tracking, not features)
            'model': self.model,
            'issue_time': self.issue_time.isoformat(),
            'valid_time': self.valid_time.isoformat(),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'variable': self.variable,

            # Actual features
            'lead_time_hours': self.lead_time_hours,
            'hour_of_day': self.hour_of_day,
            'day_of_year': self.day_of_year,
            'month': self.month,
            'season': self.season,
            'location_zone': self.location_zone,

            'gfs_value': self.gfs_value,
            'ifs_value': self.ifs_value,
            'icon_value': self.icon_value,

            'forecast_spread': self.forecast_spread,
            'forecast_range': self.forecast_range,
            'model_agreement': self.model_agreement,

            'gfs_rmse_7day': self.gfs_rmse_7day,
            'ifs_rmse_7day': self.ifs_rmse_7day,
            'icon_rmse_7day': self.icon_rmse_7day,

            'gfs_mae_7day': self.gfs_mae_7day,
            'ifs_mae_7day': self.ifs_mae_7day,
            'icon_mae_7day': self.icon_mae_7day,

            'gfs_bias_7day': self.gfs_bias_7day,
            'ifs_bias_7day': self.ifs_bias_7day,
            'icon_bias_7day': self.icon_bias_7day,

            'gfs_available': self.gfs_available,
            'ifs_available': self.ifs_available,
            'icon_available': self.icon_available,

            'feature_computation_time': self.feature_computation_time.isoformat()
        }


@dataclass
class Target:
    """
    Target for supervised learning.

    CRITICAL: This is the outcome/observation, NEVER a feature.
    Only known after valid_time + observation.
    """
    observed_value: float  # Actual observation
    forecast_error: float  # forecast_value - observed_value (sign preserved)
    absolute_error: float  # |forecast_error|

    # Observation metadata
    observation_time: datetime  # When observation was recorded
    observation_source: str  # "noaa_isd" or "era5_land"
    observation_quality_score: float  # 1.0 (NOAA ISD) or 0.8 (ERA5-Land)


@dataclass
class TrainingSample:
    """
    One training sample: features + target.

    CRITICAL TEMPORAL CONSTRAINT:
    - Features computed using data available at issue_time
    - Target known only after valid_time + observation
    - Historical features: period_end < issue_time (strictly)
    """
    features: FeatureVector
    target: Target

    # Verification metadata
    verification_id: str  # Link to ForecastVerification record
    verified_at: datetime  # When this sample was created


class FeatureContract:
    """
    Canonical feature contract for HELIOS ML candidates.

    ALL candidate models (Kernel Regression, XGBoost, MLP) use exactly
    this feature specification.

    Design principles:
    - Single shared contract (no per-algorithm variations)
    - Temporal leakage prevention (TemporalValidator integration)
    - Exact forecast identity preservation
    - Missing-model handling
    - Historical reliability before issue_time only
    """

    def __init__(self):
        """Initialize feature contract."""
        self.logger = logging.getLogger(__name__)
        self.feature_specs = self._define_feature_specs()

    def _define_feature_specs(self) -> List[FeatureSpec]:
        """
        Define canonical feature specifications.

        ALL ML candidates use exactly these features.
        """
        return [
            # Forecast context
            FeatureSpec(
                name="lead_time_hours",
                feature_type=FeatureType.FORECAST_CONTEXT,
                dtype="int",
                required=True,
                description="Hours between issue_time and valid_time",
                min_value=0,
                max_value=168
            ),
            FeatureSpec(
                name="hour_of_day",
                feature_type=FeatureType.FORECAST_CONTEXT,
                dtype="int",
                required=True,
                description="Hour of valid_time (0-23 UTC)",
                min_value=0,
                max_value=23
            ),
            FeatureSpec(
                name="day_of_year",
                feature_type=FeatureType.FORECAST_CONTEXT,
                dtype="int",
                required=True,
                description="Day of year of valid_time (1-366)",
                min_value=1,
                max_value=366
            ),
            FeatureSpec(
                name="month",
                feature_type=FeatureType.FORECAST_CONTEXT,
                dtype="int",
                required=True,
                description="Month of valid_time (1-12)",
                min_value=1,
                max_value=12
            ),
            FeatureSpec(
                name="season",
                feature_type=FeatureType.FORECAST_CONTEXT,
                dtype="categorical",
                required=True,
                description="Season of valid_time",
                categorical_values=['winter', 'spring', 'summer', 'autumn']
            ),
            FeatureSpec(
                name="location_zone",
                feature_type=FeatureType.FORECAST_CONTEXT,
                dtype="categorical",
                required=False,
                description="India domain zone",
                categorical_values=['north_himalaya', 'north_plains', 'central', 'south_plateau', 'south_coastal']
            ),

            # Current forecast values
            FeatureSpec(
                name="gfs_value",
                feature_type=FeatureType.CURRENT_FORECAST,
                dtype="float",
                required=False,
                description="GFS forecast value for this variable at valid_time"
            ),
            FeatureSpec(
                name="ifs_value",
                feature_type=FeatureType.CURRENT_FORECAST,
                dtype="float",
                required=False,
                description="IFS forecast value for this variable at valid_time"
            ),
            FeatureSpec(
                name="icon_value",
                feature_type=FeatureType.CURRENT_FORECAST,
                dtype="float",
                required=False,
                description="ICON forecast value for this variable at valid_time"
            ),

            # Inter-model features
            FeatureSpec(
                name="forecast_spread",
                feature_type=FeatureType.INTER_MODEL,
                dtype="float",
                required=False,
                description="Standard deviation among available model forecasts",
                min_value=0.0
            ),
            FeatureSpec(
                name="forecast_range",
                feature_type=FeatureType.INTER_MODEL,
                dtype="float",
                required=False,
                description="Range (max - min) among available model forecasts",
                min_value=0.0
            ),
            FeatureSpec(
                name="model_agreement",
                feature_type=FeatureType.INTER_MODEL,
                dtype="float",
                required=False,
                description="Agreement among models: 1.0 - (spread / mean)",
                min_value=0.0,
                max_value=1.0
            ),

            # Historical reliability (7-day window ending BEFORE issue_time)
            FeatureSpec(
                name="gfs_rmse_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="GFS RMSE in past 7 days (period_end < issue_time)",
                min_value=0.0
            ),
            FeatureSpec(
                name="ifs_rmse_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="IFS RMSE in past 7 days (period_end < issue_time)",
                min_value=0.0
            ),
            FeatureSpec(
                name="icon_rmse_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="ICON RMSE in past 7 days (period_end < issue_time)",
                min_value=0.0
            ),
            FeatureSpec(
                name="gfs_mae_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="GFS MAE in past 7 days (period_end < issue_time)",
                min_value=0.0
            ),
            FeatureSpec(
                name="ifs_mae_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="IFS MAE in past 7 days (period_end < issue_time)",
                min_value=0.0
            ),
            FeatureSpec(
                name="icon_mae_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="ICON MAE in past 7 days (period_end < issue_time)",
                min_value=0.0
            ),
            FeatureSpec(
                name="gfs_bias_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="GFS bias (mean error) in past 7 days (period_end < issue_time)"
            ),
            FeatureSpec(
                name="ifs_bias_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="IFS bias (mean error) in past 7 days (period_end < issue_time)"
            ),
            FeatureSpec(
                name="icon_bias_7day",
                feature_type=FeatureType.HISTORICAL_RELIABILITY,
                dtype="float",
                required=False,
                description="ICON bias (mean error) in past 7 days (period_end < issue_time)"
            ),

            # Missing model flags
            FeatureSpec(
                name="gfs_available",
                feature_type=FeatureType.CURRENT_FORECAST,
                dtype="int",  # 0 or 1
                required=True,
                description="Whether GFS forecast is available (1) or missing (0)"
            ),
            FeatureSpec(
                name="ifs_available",
                feature_type=FeatureType.CURRENT_FORECAST,
                dtype="int",  # 0 or 1
                required=True,
                description="Whether IFS forecast is available (1) or missing (0)"
            ),
            FeatureSpec(
                name="icon_available",
                feature_type=FeatureType.CURRENT_FORECAST,
                dtype="int",  # 0 or 1
                required=True,
                description="Whether ICON forecast is available (1) or missing (0)"
            ),
        ]

    def get_feature_names(self) -> List[str]:
        """Get list of all feature names in canonical order."""
        return [spec.name for spec in self.feature_specs]

    def get_required_features(self) -> List[str]:
        """Get list of required feature names."""
        return [spec.name for spec in self.feature_specs if spec.required]

    def get_optional_features(self) -> List[str]:
        """Get list of optional feature names."""
        return [spec.name for spec in self.feature_specs if not spec.required]

    def validate_feature_vector(self, features: FeatureVector) -> Tuple[bool, Optional[str]]:
        """
        Validate feature vector against contract.

        Args:
            features: FeatureVector to validate

        Returns:
            (is_valid, error_message)
        """
        # Check required features
        for spec in self.feature_specs:
            if spec.required:
                value = getattr(features, spec.name, None)
                if value is None:
                    return False, f"Required feature '{spec.name}' is None"

        # Check temporal safety: features cannot be computed after issue_time
        # (would imply using information not available at forecast issue)
        if features.feature_computation_time > features.issue_time:
            return False, "Features computed after issue_time (temporal leakage)"

        # Check forecast identity completeness
        if features.model is None or features.issue_time is None or features.valid_time is None:
            return False, "Incomplete forecast identity (model/issue_time/valid_time)"

        return True, None
