"""
HELIOS Temporal Validator

Enforces temporal constraints to prevent information leakage in HELIOS continuous learning system.

CRITICAL REQUIREMENTS:
1. Forecast chronology: valid_time >= issue_time
2. Historical features: only records with period_end < issue_time
3. Verification matching: observation_time >= valid_time
4. Exact forecast identity: model + issue_time + valid_time + location + variable
5. Reject negative lead times
6. Reject future information
7. Reject performance records overlapping issue_time

TERMINOLOGY:
- issue_time: when forecast was issued
- valid_time: when forecast is valid for
- lead_time: valid_time - issue_time (must be >= 0)
- observation_time: when observation was recorded (must be >= valid_time for verification)
- period_end: end of historical performance window (must be < issue_time for features)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Temporal validation status."""
    VALID = "valid"
    INVALID_CHRONOLOGY = "invalid_chronology"  # valid_time < issue_time
    INVALID_NEGATIVE_LEAD_TIME = "invalid_negative_lead_time"
    INVALID_FUTURE_INFORMATION = "invalid_future_information"  # obs_time < valid_time
    INVALID_OBSERVATION_BEFORE_VALID = "invalid_observation_before_valid"
    INVALID_PERFORMANCE_OVERLAP = "invalid_performance_overlap"  # period_end >= issue_time
    INVALID_MISSING_IDENTITY = "invalid_missing_identity"  # incomplete forecast identity


@dataclass
class ValidationResult:
    """Result of temporal validation."""
    status: ValidationStatus
    is_valid: bool
    error_message: Optional[str] = None
    context: Optional[Dict] = None  # Additional validation context


class TemporalValidator:
    """
    Enforces temporal constraints to prevent information leakage.

    Design principles:
    - Forecast chronology: valid_time >= issue_time
    - Historical features: only records strictly before issue_time
    - Verification matching: observation_time >= valid_time
    - Exact forecast identity required for feature reconstruction
    - Reusable across ingestion, verification, feature generation

    CRITICAL FOR CONTINUOUS LEARNING:
    Never allow a forecast's own future verification result to become a feature for that forecast.
    """

    def __init__(self):
        """Initialize temporal validator."""
        self.logger = logging.getLogger(__name__)

    def validate_forecast_chronology(
        self,
        issue_time: datetime,
        valid_time: datetime
    ) -> ValidationResult:
        """
        Validate forecast temporal chronology.

        RULE: valid_time >= issue_time (lead_time >= 0)

        Args:
            issue_time: When forecast was issued
            valid_time: When forecast is valid for

        Returns:
            ValidationResult
        """
        if valid_time < issue_time:
            return ValidationResult(
                status=ValidationStatus.INVALID_CHRONOLOGY,
                is_valid=False,
                error_message=f"valid_time ({valid_time.isoformat()}) < issue_time ({issue_time.isoformat()})",
                context={
                    'issue_time': issue_time.isoformat(),
                    'valid_time': valid_time.isoformat(),
                    'lead_time_seconds': (valid_time - issue_time).total_seconds()
                }
            )

        # valid_time == issue_time is acceptable (0-hour lead time forecast)
        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={
                'issue_time': issue_time.isoformat(),
                'valid_time': valid_time.isoformat(),
                'lead_time_hours': (valid_time - issue_time).total_seconds() / 3600
            }
        )

    def validate_lead_time(
        self,
        issue_time: datetime,
        valid_time: datetime,
        lead_time_hours: int
    ) -> ValidationResult:
        """
        Validate lead time consistency.

        RULE: lead_time_hours >= 0 and consistent with (valid_time - issue_time)

        Args:
            issue_time: When forecast was issued
            valid_time: When forecast is valid for
            lead_time_hours: Declared lead time

        Returns:
            ValidationResult
        """
        # Check negative lead time
        if lead_time_hours < 0:
            return ValidationResult(
                status=ValidationStatus.INVALID_NEGATIVE_LEAD_TIME,
                is_valid=False,
                error_message=f"Negative lead_time_hours: {lead_time_hours}",
                context={'lead_time_hours': lead_time_hours}
            )

        # Check consistency with actual issue/valid time difference
        actual_lead_time_hours = (valid_time - issue_time).total_seconds() / 3600
        expected_lead_time_hours = round(actual_lead_time_hours)

        if abs(lead_time_hours - expected_lead_time_hours) > 0.5:
            return ValidationResult(
                status=ValidationStatus.INVALID_CHRONOLOGY,
                is_valid=False,
                error_message=(
                    f"lead_time_hours ({lead_time_hours}) inconsistent with "
                    f"valid_time - issue_time ({expected_lead_time_hours:.1f}h)"
                ),
                context={
                    'declared_lead_time_hours': lead_time_hours,
                    'actual_lead_time_hours': actual_lead_time_hours,
                    'difference_hours': abs(lead_time_hours - actual_lead_time_hours)
                }
            )

        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={'lead_time_hours': lead_time_hours}
        )

    def validate_observation_for_verification(
        self,
        valid_time: datetime,
        observation_time: datetime,
        tolerance_hours: Optional[float] = None
    ) -> ValidationResult:
        """
        Validate observation temporal suitability for verification.

        RULES:
        1. observation_time >= valid_time (observation cannot precede valid time)
        2. observation_time <= valid_time + tolerance (if tolerance specified)

        Args:
            valid_time: Forecast valid time
            observation_time: When observation was recorded
            tolerance_hours: Maximum time after valid_time (optional)

        Returns:
            ValidationResult
        """
        # observation_time must not precede valid_time
        if observation_time < valid_time:
            return ValidationResult(
                status=ValidationStatus.INVALID_OBSERVATION_BEFORE_VALID,
                is_valid=False,
                error_message=(
                    f"observation_time ({observation_time.isoformat()}) < "
                    f"valid_time ({valid_time.isoformat()})"
                ),
                context={
                    'valid_time': valid_time.isoformat(),
                    'observation_time': observation_time.isoformat(),
                    'difference_hours': (observation_time - valid_time).total_seconds() / 3600
                }
            )

        # observation_time exactly at valid_time is acceptable
        if observation_time == valid_time:
            return ValidationResult(
                status=ValidationStatus.VALID,
                is_valid=True,
                context={
                    'valid_time': valid_time.isoformat(),
                    'observation_time': observation_time.isoformat(),
                    'difference_hours': 0.0
                }
            )

        # Check tolerance if specified
        if tolerance_hours is not None:
            tolerance_end = valid_time + timedelta(hours=tolerance_hours)
            if observation_time > tolerance_end:
                return ValidationResult(
                    status=ValidationStatus.INVALID_FUTURE_INFORMATION,
                    is_valid=False,
                    error_message=(
                        f"observation_time ({observation_time.isoformat()}) > "
                        f"valid_time + tolerance ({tolerance_end.isoformat()})"
                    ),
                    context={
                        'valid_time': valid_time.isoformat(),
                        'observation_time': observation_time.isoformat(),
                        'tolerance_hours': tolerance_hours,
                        'tolerance_end': tolerance_end.isoformat(),
                        'excess_hours': (observation_time - tolerance_end).total_seconds() / 3600
                    }
                )

        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={
                'valid_time': valid_time.isoformat(),
                'observation_time': observation_time.isoformat(),
                'difference_hours': (observation_time - valid_time).total_seconds() / 3600,
                'tolerance_hours': tolerance_hours
            }
        )

    def validate_historical_features(
        self,
        issue_time: datetime,
        period_end: datetime
    ) -> ValidationResult:
        """
        Validate historical performance features for temporal safety.

        RULE: period_end < issue_time (strictly before)

        Historical reliability/performance features must only use records
        strictly prior to the current forecast's issue_time.

        CRITICAL: Never allow a forecast's own future verification result
        to become a feature for that same forecast.

        Args:
            issue_time: Current forecast issue time
            period_end: End of historical performance window

        Returns:
            ValidationResult
        """
        # period_end must be strictly before issue_time
        if period_end >= issue_time:
            return ValidationResult(
                status=ValidationStatus.INVALID_PERFORMANCE_OVERLAP,
                is_valid=False,
                error_message=(
                    f"period_end ({period_end.isoformat()}) >= "
                    f"issue_time ({issue_time.isoformat()}): "
                    f"future information leakage"
                ),
                context={
                    'issue_time': issue_time.isoformat(),
                    'period_end': period_end.isoformat(),
                    'overlap_hours': (period_end - issue_time).total_seconds() / 3600
                }
            )

        # period_end exactly at issue_time is REJECTED (must be strictly before)
        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={
                'issue_time': issue_time.isoformat(),
                'period_end': period_end.isoformat(),
                'gap_hours': (issue_time - period_end).total_seconds() / 3600
            }
        )

    def validate_forecast_identity(
        self,
        model: Optional[str],
        issue_time: Optional[datetime],
        valid_time: Optional[datetime],
        location: Optional[Tuple[float, float]],
        variable: Optional[str]
    ) -> ValidationResult:
        """
        Validate exact forecast identity for feature reconstruction.

        RULE: Feature reconstruction must use exact forecast identity:
        model + issue_time + valid_time + location + variable

        Never retrieve a forecast merely by valid_time.

        Args:
            model: Model identifier
            issue_time: Forecast issue time
            valid_time: Forecast valid time
            location: (latitude, longitude) tuple
            variable: Variable name

        Returns:
            ValidationResult
        """
        missing_fields = []

        if model is None:
            missing_fields.append('model')
        if issue_time is None:
            missing_fields.append('issue_time')
        if valid_time is None:
            missing_fields.append('valid_time')
        if location is None or len(location) != 2:
            missing_fields.append('location (latitude, longitude)')
        if variable is None:
            missing_fields.append('variable')

        if missing_fields:
            return ValidationResult(
                status=ValidationStatus.INVALID_MISSING_IDENTITY,
                is_valid=False,
                error_message=(
                    f"Incomplete forecast identity. Missing: {', '.join(missing_fields)}. "
                    f"Required: model + issue_time + valid_time + location + variable"
                ),
                context={'missing_fields': missing_fields}
            )

        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={
                'model': model,
                'issue_time': issue_time.isoformat(),
                'valid_time': valid_time.isoformat(),
                'location': location,
                'variable': variable
            }
        )

    def validate_forecast_for_ingestion(
        self,
        model: str,
        issue_time: datetime,
        valid_time: datetime,
        lead_time_hours: int
    ) -> ValidationResult:
        """
        Validate forecast for ingestion.

        Combines multiple checks for forecast ingestion:
        - Chronology (valid_time >= issue_time)
        - Lead time consistency
        - Model identity present

        Args:
            model: Model identifier
            issue_time: Forecast issue time
            valid_time: Forecast valid time
            lead_time_hours: Declared lead time

        Returns:
            ValidationResult
        """
        # Check chronology
        chronology_result = self.validate_forecast_chronology(issue_time, valid_time)
        if not chronology_result.is_valid:
            return chronology_result

        # Check lead time
        lead_time_result = self.validate_lead_time(issue_time, valid_time, lead_time_hours)
        if not lead_time_result.is_valid:
            return lead_time_result

        # Check model identity present
        if not model:
            return ValidationResult(
                status=ValidationStatus.INVALID_MISSING_IDENTITY,
                is_valid=False,
                error_message="Model identifier missing",
                context={'model': model}
            )

        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={
                'model': model,
                'issue_time': issue_time.isoformat(),
                'valid_time': valid_time.isoformat(),
                'lead_time_hours': lead_time_hours
            }
        )

    def validate_verification_record(
        self,
        forecast_issue_time: datetime,
        forecast_valid_time: datetime,
        observation_time: datetime,
        tolerance_hours: float
    ) -> ValidationResult:
        """
        Validate verification record creation.

        Combines multiple checks for verification:
        - Forecast chronology
        - Observation temporal suitability

        Args:
            forecast_issue_time: Forecast issue time
            forecast_valid_time: Forecast valid time
            observation_time: Observation time
            tolerance_hours: Verification tolerance

        Returns:
            ValidationResult
        """
        # Check forecast chronology
        chronology_result = self.validate_forecast_chronology(
            forecast_issue_time,
            forecast_valid_time
        )
        if not chronology_result.is_valid:
            return chronology_result

        # Check observation temporal suitability
        observation_result = self.validate_observation_for_verification(
            forecast_valid_time,
            observation_time,
            tolerance_hours
        )
        if not observation_result.is_valid:
            return observation_result

        return ValidationResult(
            status=ValidationStatus.VALID,
            is_valid=True,
            context={
                'forecast_issue_time': forecast_issue_time.isoformat(),
                'forecast_valid_time': forecast_valid_time.isoformat(),
                'observation_time': observation_time.isoformat(),
                'tolerance_hours': tolerance_hours
            }
        )
