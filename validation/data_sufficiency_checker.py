"""
HELIOS Data Sufficiency Checker

Determines whether HELIOS has enough verified forecast-observation history
to safely enable increasingly sophisticated reliability/blending behavior.

CRITICAL PRINCIPLES:
1. DATA-SUFFICIENCY gate, NOT calendar-based gate
2. Do NOT use fixed calendar rules (e.g., "after 7 days → ML enabled")
3. Evaluate actual available verified data
4. Model/variable/lead-time/location-specific sufficiency checks
5. Observation quality matters (NOAA ISD vs ERA5-Land)
6. Cold-start: SimpleAverage baseline always allowed
7. Advanced ML: requires sufficient verified history
8. Sufficiency ≠ performance (promotion requires unseen-future evaluation)
9. Chronological evaluation support (no random splits)
10. Configurable thresholds (engineering starting points, NOT scientifically proven)
11. Experiment-specific sufficiency (query by modeling slice)
12. Temporal/spatial correlation acknowledged (records ≠ independent samples)

TERMINOLOGY:
- "sufficient" = enough verified data for learning stage (configurable threshold)
- "insufficient" = too little data, remain in simpler stage
- "cold start" = no verification history yet, use SimpleAverage baseline
- "correlation" = verification records are temporally/spatially correlated,
                 NOT independent training samples

IMPORTANT CAVEATS:
- Record counts do NOT equal independent training samples
- Verification records are temporally/spatially correlated
- Thresholds are INITIAL CONFIGURATION, not scientifically established constants
- Sufficiency enables training eligibility, NOT model promotion
- Model promotion requires separate unseen-future evaluation
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


logger = logging.getLogger(__name__)


class SufficiencyLevel(str, Enum):
    """Data sufficiency level."""
    COLD_START = "cold_start"  # No/minimal data, SimpleAverage only
    WARMING = "warming"  # Some data, continue collecting
    SUFFICIENT = "sufficient"  # Enough for ML training/evaluation
    ABUNDANT = "abundant"  # Rich data, all methods viable


@dataclass
class SufficiencyResult:
    """Result of data sufficiency check."""
    level: SufficiencyLevel
    is_sufficient: bool  # True if level >= SUFFICIENT

    # Counts
    total_verifications: int
    verifications_by_model: Dict[str, int]
    verifications_by_variable: Dict[str, int]
    verifications_by_lead_time: Dict[int, int]  # lead_time_hours → count
    verifications_by_location_zone: Dict[str, int]

    # Quality
    high_quality_count: int  # NOAA ISD observations (quality_score >= 0.9)
    fallback_count: int  # ERA5-Land fallback (quality_score < 0.9)

    # Temporal
    historical_span_days: float  # Time span of verification history
    most_recent_verification: Optional[datetime]
    oldest_verification: Optional[datetime]

    # Gaps/issues
    missing_models: List[str]  # Expected models with insufficient data
    insufficient_variables: List[str]  # Variables with insufficient data
    insufficient_lead_times: List[int]  # Lead times with insufficient data
    insufficient_zones: List[str]  # Location zones with insufficient data

    # Details
    details: Dict  # Additional diagnostic information


@dataclass
class SufficiencyConfig:
    """
    Configuration for data sufficiency thresholds.

    IMPORTANT: These are INITIAL CONFIGURATION values (engineering starting points),
    NOT scientifically established constants or proven minimum sample sizes.

    All thresholds are configurable and should be adjusted based on:
    - Actual model performance
    - Domain-specific requirements
    - Data availability constraints
    - Computational resources

    CORRELATION CAVEAT: Record counts do NOT equal independent training samples.
    Verification records are temporally and spatially correlated. Effective sample
    size for ML training is smaller than raw record count.
    """

    # Minimum counts for SUFFICIENT level (CONFIGURABLE - engineering starting points)
    min_total_verifications: int = 1000  # Total across all dimensions
    min_verifications_per_model: int = 250  # Per model (GFS/IFS/ICON)
    min_verifications_per_variable: int = 200  # Per variable
    min_verifications_per_lead_time: int = 50  # Per lead time bucket
    min_verifications_per_zone: int = 100  # Per location zone

    # Minimum historical span (CONFIGURABLE - initial threshold)
    min_historical_span_days: float = 14.0  # At least 2 weeks of history

    # Quality thresholds (CONFIGURABLE)
    min_high_quality_fraction: float = 0.5  # At least 50% high-quality (NOAA ISD)
    high_quality_threshold: float = 0.9  # quality_score >= 0.9 = high quality

    # Expected models/variables/zones (CONFIGURABLE)
    expected_models: List[str] = None  # Default: ['gfs', 'ifs', 'icon']
    expected_variables: List[str] = None  # Default: ['temperature_2m_c'] (Phase 5a only)
    expected_zones: List[str] = None  # Default: 5 India zones

    # Lead time buckets (hours) (CONFIGURABLE - not scientifically optimal partitions)
    lead_time_buckets: List[int] = None  # Default: [24, 72, 168] (short/medium/long)

    def __post_init__(self):
        """Set defaults for Phase 5a configuration."""
        if self.expected_models is None:
            self.expected_models = ['gfs', 'ifs', 'icon']

        if self.expected_variables is None:
            # Phase 5a: temperature_2m_c currently supported
            # Future expansion: dewpoint_2m_c, wind_u_10m_ms, wind_v_10m_ms,
            #                   pressure_msl_hpa, precipitation_mm
            self.expected_variables = ['temperature_2m_c']

        if self.expected_zones is None:
            # India domain zones (Phase 5a initial partitioning)
            # NOT scientifically optimal - configurable for experimentation
            self.expected_zones = [
                'north_himalaya',
                'north_plains',
                'central',
                'south_plateau',
                'south_coastal'
            ]

        if self.lead_time_buckets is None:
            # Short (0-24h), medium (24-72h), long (72-168h)
            # NOT scientifically optimal - configurable for experimentation
            self.lead_time_buckets = [24, 72, 168]


class DataSufficiencyChecker:
    """
    Determines whether HELIOS has sufficient verified forecast-observation history
    to enable advanced learning stages.

    Design principles:
    - DATA-SUFFICIENCY gate (NOT calendar-based)
    - Experiment-specific sufficiency queries (by modeling slice)
    - Model/variable/lead-time/location-specific checks
    - Observation quality matters (NOAA ISD vs ERA5-Land provenance)
    - Cold-start: SimpleAverage baseline ALWAYS allowed (never blocked)
    - Advanced ML: requires sufficient verified history
    - Sufficiency enables training eligibility, NOT model promotion
    - Model promotion requires separate unseen-future evaluation
    - Chronological evaluation support (no random splits)
    - Configurable thresholds (engineering starting points)
    - Temporal/spatial correlation acknowledged (records ≠ independent samples)

    CRITICAL DISTINCTIONS:
    - Data sufficiency → training eligibility
    - Model performance on unseen future data → promotion eligibility
    - Sufficiency alone NEVER promotes a model

    COLD-START NEVER BLOCKS:
    - Live forecast ingestion
    - Verification record creation
    - Permanent error history collection
    - SimpleAverage baseline blending

    ONLY GATES:
    - Advanced learned blending (Kernel Regression, XGBoost, MLP)
    """

    def __init__(
        self,
        config: Optional[SufficiencyConfig] = None,
        verification_reader=None  # Injected for testing
    ):
        """
        Initialize data sufficiency checker.

        Args:
            config: Sufficiency configuration
            verification_reader: Database reader for verification records (injected for testing)
        """
        self.config = config or SufficiencyConfig()
        self.logger = logging.getLogger(__name__)
        self.verification_reader = verification_reader

    def check_sufficiency(
        self,
        model: Optional[str] = None,
        variable: Optional[str] = None,
        lead_time_hours: Optional[int] = None,
        location_zone: Optional[str] = None
    ) -> SufficiencyResult:
        """
        Check data sufficiency for HELIOS learning stages.

        EXPERIMENT-SPECIFIC SUFFICIENCY:
        This method supports checking whether data is sufficient for a SPECIFIC
        modeling slice, not merely whether the entire database is sufficient.

        Example use cases:
        - Overall sufficiency: check_sufficiency() (all parameters None)
        - Temperature at 24h in central zone: check_sufficiency(
              variable='temperature_2m_c',
              lead_time_hours=24,
              location_zone='central'
          )
        - GFS model specifically: check_sufficiency(model='gfs')

        Different modeling slices may have different sufficiency levels:
        - temperature + 24h + central → SUFFICIENT
        - temperature + 168h + north_himalaya → WARMING (insufficient)

        IMPORTANT: Verification records are temporally and spatially correlated.
        Record counts do NOT equal independent training samples. Effective sample
        size for ML training is smaller than raw record count.

        Args:
            model: Optional model filter (e.g., 'gfs', 'ifs', 'icon')
            variable: Optional variable filter (e.g., 'temperature_2m_c')
            lead_time_hours: Optional lead time filter (exact hours, e.g., 24, 72)
            location_zone: Optional location zone filter (e.g., 'central', 'north_plains')

        Returns:
            SufficiencyResult with level and detailed breakdown for the queried slice
        """
        if self.verification_reader is None:
            # No verification data available (cold start)
            return self._cold_start_result()

        # Query verification records
        verifications = self.verification_reader.get_verifications(
            model=model,
            variable=variable,
            lead_time_hours=lead_time_hours,
            location_zone=location_zone
        )

        if not verifications:
            return self._cold_start_result()

        # Aggregate counts by dimension
        total_count = len(verifications)

        counts_by_model = {}
        counts_by_variable = {}
        counts_by_lead_time = {}
        counts_by_zone = {}
        high_quality_count = 0
        fallback_count = 0

        oldest_time = None
        most_recent_time = None

        for v in verifications:
            # Model
            counts_by_model[v['model']] = counts_by_model.get(v['model'], 0) + 1

            # Variable
            counts_by_variable[v['variable']] = counts_by_variable.get(v['variable'], 0) + 1

            # Lead time bucket
            lead_bucket = self._get_lead_time_bucket(v['lead_time_hours'])
            counts_by_lead_time[lead_bucket] = counts_by_lead_time.get(lead_bucket, 0) + 1

            # Location zone
            if v.get('location_zone'):
                counts_by_zone[v['location_zone']] = counts_by_zone.get(v['location_zone'], 0) + 1

            # Quality
            if v['observation_quality_score'] >= self.config.high_quality_threshold:
                high_quality_count += 1
            else:
                fallback_count += 1

            # Temporal span
            # CRITICAL: Historical span must be derived from the canonical forecast
            # issue_time domain, NOT from row insertion / verification_time. A dataset
            # batch-inserted today still has a real forecast issue_time span (e.g. 28
            # days). Fall back to verification_time only if issue_time is unavailable
            # (backward compatibility for records lacking issue_time).
            span_time = v.get('issue_time') or v.get('verification_time')
            if span_time is not None:
                if oldest_time is None or span_time < oldest_time:
                    oldest_time = span_time
                if most_recent_time is None or span_time > most_recent_time:
                    most_recent_time = span_time

        # Calculate historical span (from forecast issue_time domain)
        if oldest_time and most_recent_time:
            span = (most_recent_time - oldest_time).total_seconds() / 86400  # days
        else:
            span = 0.0

        # Identify gaps
        missing_models = [
            m for m in self.config.expected_models
            if counts_by_model.get(m, 0) < self.config.min_verifications_per_model
        ]

        insufficient_variables = [
            v for v in self.config.expected_variables
            if counts_by_variable.get(v, 0) < self.config.min_verifications_per_variable
        ]

        insufficient_lead_times = [
            bucket for bucket in self.config.lead_time_buckets
            if counts_by_lead_time.get(bucket, 0) < self.config.min_verifications_per_lead_time
        ]

        insufficient_zones = [
            z for z in self.config.expected_zones
            if counts_by_zone.get(z, 0) < self.config.min_verifications_per_zone
        ]

        # Quality check
        high_quality_fraction = high_quality_count / total_count if total_count > 0 else 0.0

        # Determine sufficiency level
        level = self._determine_level(
            total_count=total_count,
            missing_models=missing_models,
            insufficient_variables=insufficient_variables,
            insufficient_lead_times=insufficient_lead_times,
            insufficient_zones=insufficient_zones,
            historical_span_days=span,
            high_quality_fraction=high_quality_fraction
        )

        return SufficiencyResult(
            level=level,
            is_sufficient=(level in [SufficiencyLevel.SUFFICIENT, SufficiencyLevel.ABUNDANT]),
            total_verifications=total_count,
            verifications_by_model=counts_by_model,
            verifications_by_variable=counts_by_variable,
            verifications_by_lead_time=counts_by_lead_time,
            verifications_by_location_zone=counts_by_zone,
            high_quality_count=high_quality_count,
            fallback_count=fallback_count,
            historical_span_days=span,
            most_recent_verification=most_recent_time,
            oldest_verification=oldest_time,
            missing_models=missing_models,
            insufficient_variables=insufficient_variables,
            insufficient_lead_times=insufficient_lead_times,
            insufficient_zones=insufficient_zones,
            details={
                'high_quality_fraction': high_quality_fraction,
                'min_required_total': self.config.min_total_verifications,
                'min_required_per_model': self.config.min_verifications_per_model,
                'min_required_span_days': self.config.min_historical_span_days
            }
        )

    def _cold_start_result(self) -> SufficiencyResult:
        """Return cold-start result (no verification data)."""
        return SufficiencyResult(
            level=SufficiencyLevel.COLD_START,
            is_sufficient=False,
            total_verifications=0,
            verifications_by_model={},
            verifications_by_variable={},
            verifications_by_lead_time={},
            verifications_by_location_zone={},
            high_quality_count=0,
            fallback_count=0,
            historical_span_days=0.0,
            most_recent_verification=None,
            oldest_verification=None,
            missing_models=self.config.expected_models,
            insufficient_variables=self.config.expected_variables,
            insufficient_lead_times=self.config.lead_time_buckets,
            insufficient_zones=self.config.expected_zones,
            details={'reason': 'No verification records available'}
        )

    def _get_lead_time_bucket(self, lead_time_hours: int) -> int:
        """
        Get lead time bucket for a given lead time.

        Args:
            lead_time_hours: Lead time in hours

        Returns:
            Bucket upper bound (e.g., 24, 72, 168)
        """
        for bucket in sorted(self.config.lead_time_buckets):
            if lead_time_hours <= bucket:
                return bucket

        # Beyond all buckets - use largest bucket
        return max(self.config.lead_time_buckets)

    def _determine_level(
        self,
        total_count: int,
        missing_models: List[str],
        insufficient_variables: List[str],
        insufficient_lead_times: List[int],
        insufficient_zones: List[str],
        historical_span_days: float,
        high_quality_fraction: float
    ) -> SufficiencyLevel:
        """
        Determine sufficiency level based on data characteristics.

        Args:
            total_count: Total verification count
            missing_models: Models with insufficient data
            insufficient_variables: Variables with insufficient data
            insufficient_lead_times: Lead times with insufficient data
            insufficient_zones: Zones with insufficient data
            historical_span_days: Historical time span
            high_quality_fraction: Fraction of high-quality observations

        Returns:
            SufficiencyLevel
        """
        # COLD_START: Minimal/no data
        if total_count < 100:  # Absolute minimum
            return SufficiencyLevel.COLD_START

        # WARMING: Some data, but gaps remain
        if (missing_models or
            insufficient_variables or
            insufficient_lead_times or
            insufficient_zones or
            historical_span_days < self.config.min_historical_span_days or
            total_count < self.config.min_total_verifications):
            return SufficiencyLevel.WARMING

        # Quality check for SUFFICIENT
        if high_quality_fraction < self.config.min_high_quality_fraction:
            return SufficiencyLevel.WARMING  # Insufficient quality

        # SUFFICIENT: Meets all minimum thresholds
        if total_count >= self.config.min_total_verifications:
            # ABUNDANT: Significantly exceeds thresholds
            if (total_count >= self.config.min_total_verifications * 3 and
                historical_span_days >= self.config.min_historical_span_days * 2):
                return SufficiencyLevel.ABUNDANT

            return SufficiencyLevel.SUFFICIENT

        return SufficiencyLevel.WARMING

    def is_ml_training_eligible(self, result: SufficiencyResult) -> bool:
        """
        Check if ML training is eligible based on sufficiency.

        CRITICAL DISTINCTIONS:
        - Data sufficiency → training eligibility (this method)
        - Model performance on unseen future data → promotion eligibility (separate)
        - Sufficiency alone NEVER promotes a model

        Sufficiency is a NECESSARY but NOT SUFFICIENT condition for production deployment.
        Model promotion additionally requires:
        - Unseen-future evaluation (chronological test set)
        - Performance improvement over SimpleAverage baseline
        - Stability across lead times and locations

        Args:
            result: SufficiencyResult from check_sufficiency

        Returns:
            True if data sufficient for ML training/evaluation
            False otherwise (remain in SimpleAverage baseline)
        """
        return result.is_sufficient

    def is_cold_start(self, result: SufficiencyResult) -> bool:
        """
        Check if system is in cold-start phase.

        COLD-START NEVER BLOCKS:
        - Live forecast ingestion (continues normally)
        - Verification record creation (continues normally)
        - Permanent error history collection (continues normally)
        - SimpleAverage baseline blending (ALWAYS allowed)

        COLD-START ONLY GATES:
        - Advanced learned blending (Kernel Regression, XGBoost, MLP)

        During cold start, the system operates in permanent baseline mode
        while collecting the verification history needed for advanced methods.

        Args:
            result: SufficiencyResult from check_sufficiency

        Returns:
            True if in cold-start phase (level == COLD_START)
        """
        return result.level == SufficiencyLevel.COLD_START

    def get_chronological_split_recommendation(
        self,
        result: SufficiencyResult
    ) -> Optional[Dict]:
        """
        Recommend chronological train/validation/test split.

        CRITICAL: NEVER use random splits.
        Always use chronological splits for time-series forecasting.

        IMPORTANT CAVEATS:
        - Verification records are temporally/spatially correlated
        - Record counts do NOT equal independent samples
        - Split recommendation accounts for time span, not correlation structure
        - Actual ML evaluation must use chronological and appropriately grouped evaluation
        - Effective sample size is smaller than raw record count

        Args:
            result: SufficiencyResult from check_sufficiency

        Returns:
            Dict with recommended split or None if insufficient data
            Includes warning about data density and correlation
        """
        if not result.is_sufficient:
            return None

        # Recommend chronological split
        # Typical: 60% train, 20% validation, 20% test (chronologically)
        total_span_days = result.historical_span_days

        train_end_offset = total_span_days * 0.6
        val_end_offset = total_span_days * 0.8

        oldest = result.oldest_verification

        train_end = oldest + timedelta(days=train_end_offset)
        val_end = oldest + timedelta(days=val_end_offset)
        test_end = result.most_recent_verification

        return {
            'split_type': 'chronological',
            'train_start': oldest,
            'train_end': train_end,
            'validation_start': train_end,
            'validation_end': val_end,
            'test_start': val_end,
            'test_end': test_end,
            'train_fraction': 0.6,
            'validation_fraction': 0.2,
            'test_fraction': 0.2,
            'warning': (
                'This is a recommendation. Actual split should account for data density and gaps. '
                'IMPORTANT: Verification records are temporally/spatially correlated. '
                'Record counts do NOT equal independent samples. '
                'Effective sample size is smaller than raw record count.'
            )
        }
