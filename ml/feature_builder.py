"""
HELIOS Feature Builder

Reconstructs canonical FeatureVector from database records using ONLY information
available at issue_time.

CRITICAL TEMPORAL CONSTRAINTS:
1. Historical reliability: period_end < issue_time (strictly before)
2. Current NWP forecasts: issued AT issue_time (valid input)
3. Observations: targets/outcomes only (NEVER features)
4. Exact forecast identity: model + issue_time + valid_time + location + variable

NEVER reconstruct features using valid_time alone.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import FeatureVector, FeatureContract
from validation.temporal_validator import TemporalValidator


logger = logging.getLogger(__name__)


@dataclass
class ForecastRecord:
    """
    Simplified forecast record for feature reconstruction.

    Represents one NWP model's forecast for a specific valid_time.
    """
    model: str  # 'gfs', 'ifs', or 'icon'
    issue_time: datetime
    valid_time: datetime
    lead_time_hours: int
    latitude: float
    longitude: float
    location_zone: Optional[str]
    variable: str
    forecast_value: float


@dataclass
class HistoricalReliability:
    """
    Historical reliability statistics for one model.

    CRITICAL: period_end < issue_time (strictly before)
    """
    model: str
    variable: str
    lead_time_group: str  # e.g., '0-24h', '24-72h'
    location_zone: Optional[str]
    period_end: datetime  # MUST be < issue_time
    window_days: int
    rmse: float
    mae: float
    bias: float
    n_forecasts: int


class FeatureBuilder:
    """
    Builds canonical FeatureVector from database records.

    Design principles:
    - Uses ONLY information available at issue_time
    - Enforces temporal leakage prevention
    - Exact forecast identity (never reconstruct by valid_time alone)
    - Historical reliability strictly before issue_time
    - Observations are targets, never features

    Integration with:
    - FeatureContract (canonical 24-feature specification)
    - TemporalValidator (temporal constraint enforcement)
    """

    def __init__(self, feature_contract: Optional[FeatureContract] = None):
        """
        Initialize feature builder.

        Args:
            feature_contract: Feature contract for validation
        """
        self.logger = logging.getLogger(__name__)
        self.feature_contract = feature_contract or FeatureContract()
        self.temporal_validator = TemporalValidator()

    def build_feature_vector(
        self,
        target_model: str,
        issue_time: datetime,
        valid_time: datetime,
        location: Tuple[float, float],  # (latitude, longitude)
        location_zone: Optional[str],
        variable: str,
        forecasts: Dict[str, float],  # model → forecast_value
        historical_reliability: Optional[Dict[str, HistoricalReliability]] = None
    ) -> FeatureVector:
        """
        Build canonical FeatureVector for one forecast.

        CRITICAL: Uses ONLY information available at issue_time.

        Args:
            target_model: Model being evaluated ('gfs', 'ifs', or 'icon')
            issue_time: Forecast issue time
            valid_time: Forecast valid time
            location: (latitude, longitude)
            location_zone: India domain zone
            variable: Weather variable (e.g., 'temperature_2m_c')
            forecasts: Current forecasts from all available models
                       Keys: 'gfs', 'ifs', 'icon'
                       Values: forecast values
            historical_reliability: Historical performance for each model
                                   (optional, None during cold start)

        Returns:
            FeatureVector with all 24 features

        Raises:
            ValueError: If temporal constraints violated
        """
        latitude, longitude = location
        lead_time_hours = int((valid_time - issue_time).total_seconds() / 3600)

        # Validate chronology
        result = self.temporal_validator.validate_forecast_chronology(issue_time, valid_time)
        if not result.is_valid:
            raise ValueError(f"Invalid forecast chronology: {result.error_message}")

        # Forecast context features
        hour_of_day = valid_time.hour
        day_of_year = valid_time.timetuple().tm_yday
        month = valid_time.month
        season = self._get_season(month)

        # Current forecast values (issued AT issue_time)
        gfs_value = forecasts.get('gfs')
        ifs_value = forecasts.get('ifs')
        icon_value = forecasts.get('icon')

        gfs_available = 'gfs' in forecasts and gfs_value is not None
        ifs_available = 'ifs' in forecasts and ifs_value is not None
        icon_available = 'icon' in forecasts and icon_value is not None

        # Inter-model features
        forecast_spread, forecast_range, model_agreement = self._compute_inter_model_features(
            forecasts
        )

        # Historical reliability features (period_end < issue_time)
        gfs_rmse_7day, ifs_rmse_7day, icon_rmse_7day = None, None, None
        gfs_mae_7day, ifs_mae_7day, icon_mae_7day = None, None, None
        gfs_bias_7day, ifs_bias_7day, icon_bias_7day = None, None, None

        if historical_reliability:
            for model, reliability in historical_reliability.items():
                # CRITICAL: Validate period_end < issue_time
                result = self.temporal_validator.validate_historical_features(
                    issue_time, reliability.period_end
                )
                if not result.is_valid:
                    raise ValueError(
                        f"Historical reliability for {model} violates temporal constraint: "
                        f"period_end ({reliability.period_end}) >= issue_time ({issue_time})"
                    )

                # Extract statistics
                if model == 'gfs':
                    gfs_rmse_7day = reliability.rmse
                    gfs_mae_7day = reliability.mae
                    gfs_bias_7day = reliability.bias
                elif model == 'ifs':
                    ifs_rmse_7day = reliability.rmse
                    ifs_mae_7day = reliability.mae
                    ifs_bias_7day = reliability.bias
                elif model == 'icon':
                    icon_rmse_7day = reliability.rmse
                    icon_mae_7day = reliability.mae
                    icon_bias_7day = reliability.bias

        # Create feature vector
        feature_vector = FeatureVector(
            model=target_model,
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=lead_time_hours,
            latitude=latitude,
            longitude=longitude,
            location_zone=location_zone,
            variable=variable,
            hour_of_day=hour_of_day,
            day_of_year=day_of_year,
            month=month,
            season=season,
            gfs_value=gfs_value,
            ifs_value=ifs_value,
            icon_value=icon_value,
            forecast_spread=forecast_spread,
            forecast_range=forecast_range,
            model_agreement=model_agreement,
            gfs_rmse_7day=gfs_rmse_7day,
            ifs_rmse_7day=ifs_rmse_7day,
            icon_rmse_7day=icon_rmse_7day,
            gfs_mae_7day=gfs_mae_7day,
            ifs_mae_7day=ifs_mae_7day,
            icon_mae_7day=icon_mae_7day,
            gfs_bias_7day=gfs_bias_7day,
            ifs_bias_7day=ifs_bias_7day,
            icon_bias_7day=icon_bias_7day,
            gfs_available=gfs_available,
            ifs_available=ifs_available,
            icon_available=icon_available,
            feature_computation_time=issue_time  # Computed AT issue_time
        )

        # Validate against feature contract
        is_valid, error_msg = self.feature_contract.validate_feature_vector(feature_vector)
        if not is_valid:
            raise ValueError(f"Feature vector validation failed: {error_msg}")

        return feature_vector

    def _get_season(self, month: int) -> str:
        """Get season from month (Northern Hemisphere)."""
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:  # [9, 10, 11]
            return 'autumn'

    def _compute_inter_model_features(
        self,
        forecasts: Dict[str, float]
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Compute inter-model features (spread, range, agreement).

        Args:
            forecasts: Available forecasts (model → value)

        Returns:
            (forecast_spread, forecast_range, model_agreement)
        """
        available_values = [v for v in forecasts.values() if v is not None]

        if len(available_values) < 2:
            # Need at least 2 models for inter-model features
            return None, None, None

        import numpy as np

        values_array = np.array(available_values)

        # Spread (standard deviation)
        forecast_spread = float(np.std(values_array))

        # Range (max - min)
        forecast_range = float(np.max(values_array) - np.min(values_array))

        # Agreement (1.0 - normalized spread)
        mean_value = np.mean(values_array)
        if abs(mean_value) > 1e-6:
            model_agreement = 1.0 - (forecast_spread / abs(mean_value))
            model_agreement = max(0.0, min(1.0, model_agreement))  # Clip to [0, 1]
        else:
            model_agreement = 1.0  # Perfect agreement if all near zero

        return forecast_spread, forecast_range, model_agreement
