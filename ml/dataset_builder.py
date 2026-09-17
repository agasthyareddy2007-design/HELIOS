"""
HELIOS ML Dataset Builder

Reconstructs the REAL, leakage-safe supervised learning dataset for HELIOS from
the permanent learning history stored in the `forecast_verification` table.

WHAT THIS MODULE DOES
---------------------
1. Reads verified forecast-outcome pairs (forecast_verification), which are the
   permanent, compact learning history of HELIOS.
2. Groups them into CANONICAL EXAMPLES keyed by the exact forecast identity
   (issue_time, valid_time, latitude, longitude, variable), pivoting each NWP
   model's forecast value into the gfs/ifs/icon slots of the FeatureContract.
3. Computes HISTORICAL RELIABILITY features on-the-fly using ONLY verification
   records whose outcome was known strictly BEFORE the example's issue_time.
4. Emits TrainingSample objects (FeatureVector + Target) via the existing
   FeatureBuilder / FeatureContract so the canonical contract is enforced.
5. Produces a deterministic, chronological TRAIN -> VALIDATION -> TEST split.

CRITICAL LEAKAGE RULES (see also validation/temporal_validator.py)
------------------------------------------------------------------
- The current NWP forecast issued AT issue_time is a valid feature.
- Historical performance features must use only records with period_end
  strictly < issue_time.
- The target (observed value / error) corresponds to the forecast valid_time
  and is NEVER a feature.
- A forecast's own outcome can NEVER enter its own historical features. This is
  structurally guaranteed: a usable historical record requires
  valid_time < issue_time, while the example's own outcome has
  valid_time >= issue_time.
- Missing model != zero forecast. Missing models are represented with value
  None and the availability flag set to False (FeatureContract mechanism).
- Splitting is chronological by issue_time. NEVER random.

SCALABILITY
-----------
- Nothing about the 28-day / 353-station / IFS-only V1 dataset is hard-coded.
- Verification rows are streamed in a single indexed, ORDER BY query.
- Historical reliability is computed with grouped aggregate queries and cached
  per (issue_time cutoff, model, variable, lead_time_group, zone); this avoids
  naive O(N^2) per-example historical scans.
- The module accepts model lists, variables, window sizes and split boundaries
  as parameters so that much larger post-V1 datasets (GFS + IFS + ICON, more
  variables, more stations, longer horizons) work without code changes.

This module performs DATASET PREPARATION ONLY. It does not train any model.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Iterable, Any

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func

from database.connection import DatabaseManager
from database.schema.helios_schema import ForecastVerification
from ml.feature_builder import FeatureBuilder, HistoricalReliability
from ml.feature_contract import FeatureContract, FeatureVector, Target, TrainingSample
from validation.temporal_validator import TemporalValidator


logger = logging.getLogger(__name__)


# Canonical model slots recognised by the FeatureContract.
CANONICAL_MODELS: Tuple[str, ...] = ("gfs", "ifs", "icon")

# Default variable of the V1 dataset. Not hard-coded into logic; only a default.
DEFAULT_VARIABLE = "temperature_2m_c"


class SplitName(str, Enum):
    """Chronological dataset split names."""
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


def lead_time_group(lead_time_hours: int) -> str:
    """
    Map a lead time (hours) to a coarse lead-time group used for aggregating
    historical reliability.

    Groups are open-ended at the top so arbitrarily long future horizons work.
    """
    if lead_time_hours < 0:
        raise ValueError(f"Negative lead_time_hours: {lead_time_hours}")
    if lead_time_hours <= 24:
        return "0-24h"
    if lead_time_hours <= 48:
        return "24-48h"
    if lead_time_hours <= 72:
        return "48-72h"
    if lead_time_hours <= 120:
        return "72-120h"
    return "120h+"


@dataclass
class VerificationRow:
    """A single verification record, decoupled from the ORM object."""
    verification_id: str
    forecast_id: str
    model: str
    issue_time: datetime
    valid_time: datetime
    lead_time_hours: int
    latitude: float
    longitude: float
    location_zone: Optional[str]
    variable: str
    forecast_value: float
    observed_value: float
    error: float
    absolute_error: float
    squared_error: float
    observation_time: datetime
    observation_source: str
    observation_quality_score: Optional[float]
    station_id: Optional[str] = None
    station_distance_km: Optional[float] = None


@dataclass
class DatasetSplitConfig:
    """
    Configuration of the chronological split.

    Two mutually exclusive modes:
    - Fraction mode (default): split the sorted distinct issue_times by
      train_fraction / validation_fraction; the remainder is TEST.
    - Boundary mode: explicit datetime boundaries. An example belongs to:
        TRAIN       if issue_time <  train_end
        VALIDATION  if train_end <= issue_time < validation_end
        TEST        if issue_time >= validation_end

    In both modes the split is purely a function of issue_time, so it is
    deterministic and never random. Boundaries always fall between distinct
    issue_times so a given forecast cycle is never split across sets.
    """
    train_fraction: float = 0.6
    validation_fraction: float = 0.2
    # remainder (1 - train - validation) is the TEST fraction

    train_end: Optional[datetime] = None
    validation_end: Optional[datetime] = None

    def uses_boundaries(self) -> bool:
        return self.train_end is not None and self.validation_end is not None

    def validate(self) -> None:
        if self.uses_boundaries():
            if not (self.train_end < self.validation_end):
                raise ValueError(
                    "Boundary split requires train_end < validation_end "
                    f"(got {self.train_end} and {self.validation_end})"
                )
            return
        if self.train_fraction <= 0 or self.validation_fraction <= 0:
            raise ValueError("Fractions must be positive")
        if self.train_fraction + self.validation_fraction >= 1.0:
            raise ValueError(
                "train_fraction + validation_fraction must be < 1.0 so that a "
                "non-empty TEST set remains "
                f"(got {self.train_fraction} + {self.validation_fraction})"
            )


@dataclass
class BuildConfig:
    """Configuration for a dataset build."""
    variable: str = DEFAULT_VARIABLE
    models: Tuple[str, ...] = CANONICAL_MODELS
    historical_window_days: int = 7
    # Minimum number of prior verified forecasts required before a historical
    # reliability feature is emitted (otherwise it is left as None / unknown).
    min_history_samples: int = 1
    split: DatasetSplitConfig = field(default_factory=DatasetSplitConfig)
    # Canonical spatial key for grouping models into one example:
    #   "lat_lon"  -> exact (latitude, longitude) [default; single-grid datasets]
    #   "station"  -> anchored NOAA station id [multi-model: GFS/IFS/ICON sit on
    #                 different native grids but share NOAA station anchors]
    # When "station", multiple grid points of a model mapping to the same station
    # in one (issue,valid) are reduced deterministically to the point NEAREST the
    # station (tie-break by verification_id). This does NOT alter any stored row.
    spatial_key: str = "lat_lon"


@dataclass
class DatasetStatistics:
    """Statistics collected during a build / dry-run."""
    n_verification_rows: int = 0
    n_canonical_examples: int = 0
    n_training_samples: int = 0

    issue_time_min: Optional[datetime] = None
    issue_time_max: Optional[datetime] = None
    valid_time_min: Optional[datetime] = None
    valid_time_max: Optional[datetime] = None

    model_counts: Dict[str, int] = field(default_factory=dict)
    variable_counts: Dict[str, int] = field(default_factory=dict)
    lead_time_counts: Dict[int, int] = field(default_factory=dict)
    zone_counts: Dict[str, int] = field(default_factory=dict)

    split_counts: Dict[str, int] = field(default_factory=dict)

    # Availability / missing-feature statistics
    model_available_counts: Dict[str, int] = field(default_factory=dict)
    samples_with_historical_reliability: int = 0
    samples_without_historical_reliability: int = 0

    # Target availability
    samples_with_target: int = 0
    samples_missing_target: int = 0

    # Leakage audit
    leakage_violations: int = 0
    leakage_violation_examples: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        def iso(d: Optional[datetime]) -> Optional[str]:
            return d.isoformat() if d else None
        return {
            "n_verification_rows": self.n_verification_rows,
            "n_canonical_examples": self.n_canonical_examples,
            "n_training_samples": self.n_training_samples,
            "issue_time_min": iso(self.issue_time_min),
            "issue_time_max": iso(self.issue_time_max),
            "valid_time_min": iso(self.valid_time_min),
            "valid_time_max": iso(self.valid_time_max),
            "model_counts": dict(self.model_counts),
            "variable_counts": dict(self.variable_counts),
            "lead_time_counts": {str(k): v for k, v in sorted(self.lead_time_counts.items())},
            "zone_counts": dict(self.zone_counts),
            "split_counts": dict(self.split_counts),
            "model_available_counts": dict(self.model_available_counts),
            "samples_with_historical_reliability": self.samples_with_historical_reliability,
            "samples_without_historical_reliability": self.samples_without_historical_reliability,
            "samples_with_target": self.samples_with_target,
            "samples_missing_target": self.samples_missing_target,
            "leakage_violations": self.leakage_violations,
            "leakage_violation_examples": list(self.leakage_violation_examples),
        }



@dataclass
class SplitMetadata:
    start_issue_time: Optional[datetime] = None
    end_issue_time: Optional[datetime] = None
    row_count: int = 0

@dataclass
class DatasetSplit:
    """A chronological dataset split representation."""
    train: List[TrainingSample] = field(default_factory=list) # kept for backward compat for V1
    validation: List[TrainingSample] = field(default_factory=list)
    test: List[TrainingSample] = field(default_factory=list)
    statistics: DatasetStatistics = field(default_factory=DatasetStatistics)
    train_bounds: Optional[SplitMetadata] = None
    validation_bounds: Optional[SplitMetadata] = None
    test_bounds: Optional[SplitMetadata] = None

    def total(self) -> int:
        return len(self.train) + len(self.validation) + len(self.test)


class DatasetBuilder:
    """
    Builds leakage-safe supervised datasets from forecast_verification.

    Usage:
        builder = DatasetBuilder(db_manager)
        split = builder.build(BuildConfig())
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        feature_builder: Optional[FeatureBuilder] = None,
        feature_contract: Optional[FeatureContract] = None,
    ):
        self.db_manager = db_manager
        self.feature_contract = feature_contract or FeatureContract()
        self.feature_builder = feature_builder or FeatureBuilder(self.feature_contract)
        self.temporal_validator = TemporalValidator()
        self.logger = logging.getLogger(__name__)

        # Cache: (cutoff_issue_time_iso, model, variable, lead_group, zone)
        #        -> HistoricalReliability | None
        # Because reliability depends only on the issue_time cutoff (not the
        # exact example), all examples sharing a forecast cycle + context reuse
        # the same computed statistic. This makes the build near-linear.
        self._reliability_cache: Dict[Tuple, Optional[HistoricalReliability]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build(self, config: Optional[BuildConfig] = None) -> DatasetSplit:
        """
        Build the full chronological dataset split.

        Returns a DatasetSplit containing train/validation/test TrainingSample
        lists plus DatasetStatistics.
        """
        config = config or BuildConfig()
        config.split.validate()

        self._reliability_cache.clear()

        rows = self._load_verification_rows(config)
        stats = DatasetStatistics()
        stats.n_verification_rows = len(rows)

        if not rows:
            self.logger.warning("No verification rows matched the build config.")
            return DatasetSplit(statistics=stats)

        # Determine split boundaries from actual data (never assume dates).
        distinct_issue_times = sorted({r.issue_time for r in rows})
        train_end, validation_end = self._resolve_boundaries(
            distinct_issue_times, config.split
        )
        self.logger.info(
            "Chronological split boundaries: TRAIN < %s <= VALIDATION < %s <= TEST",
            train_end.isoformat(), validation_end.isoformat(),
        )

        # Group into canonical examples keyed by exact identity.
        examples = self._group_canonical_examples(rows, config)
        stats.n_canonical_examples = len(examples)
        del rows
        import gc
        gc.collect()

        split = DatasetSplit(statistics=stats)

        # Deterministic ordering of examples.
        for key in sorted(examples.keys(), key=lambda k: tuple(str(x) for x in k)):
            issue_time = key[0]
            model_rows = examples[key]

            # Aggregate statistics over canonical examples.
            self._update_example_stats(stats, model_rows)

            # Build the shared feature dict (pivot models -> slot values).
            forecasts, availability, zone = self._pivot_models(model_rows, config)

            # Emit one TrainingSample per present target model (deterministic).
            for target_model in sorted(model_rows.keys()):
                row = model_rows[target_model]
                sample = self._build_training_sample(
                    target_model=target_model,
                    row=row,
                    forecasts=forecasts,
                    availability=availability,
                    zone=zone,
                    config=config,
                    stats=stats,
                )
                if sample is None:
                    continue

                bucket = self._assign_split(issue_time, train_end, validation_end)
                if bucket is SplitName.TRAIN:
                    split.train.append(sample)
                elif bucket is SplitName.VALIDATION:
                    split.validation.append(sample)
                else:
                    split.test.append(sample)

        stats.n_training_samples = split.total()
        stats.split_counts = {
            SplitName.TRAIN.value: len(split.train),
            SplitName.VALIDATION.value: len(split.validation),
            SplitName.TEST.value: len(split.test),
        }

        self._audit_split_ordering(split, stats)
        return split


    def stream_canonical_examples(self, config, start_issue=None, end_issue=None, chunk_size=20000):
        """
        Yields chunks of canonical examples directly from the database without
        accumulating everything. Each chunk is a Dict[(...): Dict[str, VerificationRow]].
        """
        use_station = (config.spatial_key == "station")
        
        with self.db_manager.get_session() as session:
            # We want to iterate chunks of issue_time to avoid keeping millions of rows.
            # But the order by must match canonical.
            query = (
                session.query(ForecastVerification)
                .filter(ForecastVerification.variable == config.variable)
                .filter(ForecastVerification.model.in_(list(config.models)))
            )
            if start_issue is not None:
                query = query.filter(ForecastVerification.issue_time >= start_issue)
            if end_issue is not None:
                query = query.filter(ForecastVerification.issue_time < end_issue)
                
            query = query.order_by(
                ForecastVerification.issue_time,
                ForecastVerification.valid_time,
                ForecastVerification.latitude,
                ForecastVerification.longitude,
                ForecastVerification.model,
            )
            
            # Using yield_per to stream results properly inside the server/ORM.
            # However, because we must group by canonical identity, we need to assemble over chunks.
            rows_chunk = []
            current_issue_time = None
            
            for v in query.yield_per(10000):
                if current_issue_time is not None and v.issue_time != current_issue_time:
                    # When issue_time changes, if buffer is large enough, yield it.
                    if len(rows_chunk) >= chunk_size:
                        yield self._group_canonical_examples(rows_chunk, config)
                        rows_chunk = []
                current_issue_time = v.issue_time
                
                rows_chunk.append(
                    VerificationRow(
                        verification_id=v.verification_id,
                        forecast_id=v.forecast_id,
                        model=v.model,
                        issue_time=v.issue_time,
                        valid_time=v.valid_time,
                        lead_time_hours=int(v.lead_time_hours),
                        latitude=float(v.latitude),
                        longitude=float(v.longitude),
                        location_zone=v.location_zone,
                        variable=v.variable,
                        forecast_value=float(v.forecast_value),
                        observed_value=float(v.observed_value),
                        error=float(v.error),
                        absolute_error=float(v.absolute_error),
                        squared_error=float(v.squared_error),
                        observation_time=v.observation_time,
                        observation_source=v.observation_source,
                        observation_quality_score=(float(v.observation_quality_score) if v.observation_quality_score is not None else None),
                        station_id=v.observation_station_ids,
                        station_distance_km=(float(v.observation_distance_km) if v.observation_distance_km is not None else None)
                    )
                )
                
            if rows_chunk:
                yield self._group_canonical_examples(rows_chunk, config)

    def stream_training_samples(self, config, start_issue=None, end_issue=None, chunk_size=20000):
        """
        Yields chunks of List[TrainingSample]. Safe for memory!
        """
        stats = DatasetStatistics()

        # clear cache so memory is stable
        self._reliability_cache.clear()
        
        for grouped_chunk in self.stream_canonical_examples(config, start_issue, end_issue, chunk_size):
            samples_out = []
            # Deterministic ordering of examples
            for key in sorted(grouped_chunk.keys(), key=lambda k: tuple(str(x) for x in k)):
                model_rows = grouped_chunk[key]
                self._update_example_stats(stats, model_rows)
                forecasts, availability, zone = self._pivot_models(model_rows, config)
                
                for target_model in sorted(model_rows.keys()):
                    row = model_rows[target_model]
                    sample = self._build_training_sample(
                        target_model=target_model,
                        row=row,
                        forecasts=forecasts,
                        availability=availability,
                        zone=zone,
                        config=config,
                        stats=stats,
                    )
                    if sample is not None:
                        samples_out.append(sample)
                        
            yield samples_out

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _load_verification_rows(self, config: BuildConfig) -> List[VerificationRow]:
        """
        Stream verification rows for the requested variable/models in a single
        indexed, deterministically-ordered query.
        """
        rows: List[VerificationRow] = []
        with self.db_manager.get_session() as session:
            query = (
                session.query(ForecastVerification)
                .filter(ForecastVerification.variable == config.variable)
                .filter(ForecastVerification.model.in_(list(config.models)))
                .order_by(
                    ForecastVerification.issue_time,
                    ForecastVerification.valid_time,
                    ForecastVerification.latitude,
                    ForecastVerification.longitude,
                    ForecastVerification.model,
                )
            )
            for v in query.yield_per(5000):
                rows.append(
                    VerificationRow(
                        verification_id=v.verification_id,
                        forecast_id=v.forecast_id,
                        model=v.model,
                        issue_time=v.issue_time,
                        valid_time=v.valid_time,
                        lead_time_hours=int(v.lead_time_hours),
                        latitude=float(v.latitude),
                        longitude=float(v.longitude),
                        location_zone=v.location_zone,
                        variable=v.variable,
                        forecast_value=float(v.forecast_value),
                        observed_value=float(v.observed_value),
                        error=float(v.error),
                        absolute_error=float(v.absolute_error),
                        squared_error=float(v.squared_error),
                        observation_time=v.observation_time,
                        observation_source=v.observation_source,
                        observation_quality_score=(
                            float(v.observation_quality_score)
                            if v.observation_quality_score is not None else None
                        ),
                        station_id=v.observation_station_ids,
                        station_distance_km=(
                            float(v.observation_distance_km)
                            if v.observation_distance_km is not None else None
                        ),
                    )
                )
        return rows

    # ------------------------------------------------------------------
    # Grouping / pivoting
    # ------------------------------------------------------------------
    def _group_canonical_examples(
        self, rows: List[VerificationRow], config: BuildConfig
    ) -> Dict[Tuple, Dict[str, VerificationRow]]:
        """
        Group verification rows into canonical examples.

        spatial_key="lat_lon" (default): key = (issue, valid, lat, lon, variable).
        spatial_key="station": key = (issue, valid, station_id, variable). Because
        GFS/IFS/ICON sit on different native grids but are anchored to shared NOAA
        stations, station keying is required to form true multi-model examples.
        When several grid points of the SAME model map to one station in one
        (issue,valid), we keep the point NEAREST the station (tie-break: smaller
        verification_id) so each model contributes exactly one value per example.
        """
        use_station = (config.spatial_key == "station")
        examples: Dict[Tuple, Dict[str, VerificationRow]] = {}
        for r in rows:
            if use_station:
                if not r.station_id:
                    continue  # cannot station-key a row without a station anchor
                key = (r.issue_time, r.valid_time, r.station_id, r.variable)
            else:
                key = (r.issue_time, r.valid_time, r.latitude, r.longitude, r.variable)
            model_map = examples.setdefault(key, {})
            existing = model_map.get(r.model)
            if existing is None:
                model_map[r.model] = r
                continue
            if use_station:
                # Keep the grid point nearest the station (deterministic).
                new_d = r.station_distance_km if r.station_distance_km is not None else float("inf")
                old_d = existing.station_distance_km if existing.station_distance_km is not None else float("inf")
                if (new_d, r.verification_id) < (old_d, existing.verification_id):
                    model_map[r.model] = r
            else:
                self.logger.warning(
                    "Duplicate verification for identity %s model %s; keeping first.",
                    key, r.model,
                )
        return examples

    def _pivot_models(
        self, model_rows: Dict[str, VerificationRow], config: BuildConfig
    ) -> Tuple[Dict[str, float], Dict[str, bool], Optional[str]]:
        """
        Pivot present models into the canonical gfs/ifs/icon slots.

        Missing model => NOT present in `forecasts` dict and availability False.
        This preserves the FeatureContract rule: missing model != zero value.
        """
        forecasts: Dict[str, float] = {}
        availability: Dict[str, bool] = {m: False for m in CANONICAL_MODELS}
        zone: Optional[str] = None

        for model in CANONICAL_MODELS:
            if model in model_rows:
                row = model_rows[model]
                forecasts[model] = row.forecast_value
                availability[model] = True
                if zone is None:
                    zone = row.location_zone
        # Fallback zone from any present model if canonical ones absent.
        if zone is None and model_rows:
            zone = next(iter(model_rows.values())).location_zone
        return forecasts, availability, zone

    # ------------------------------------------------------------------
    # Sample construction
    # ------------------------------------------------------------------
    def _build_training_sample(
        self,
        target_model: str,
        row: VerificationRow,
        forecasts: Dict[str, float],
        availability: Dict[str, bool],
        zone: Optional[str],
        config: BuildConfig,
        stats: DatasetStatistics,
    ) -> Optional[TrainingSample]:
        """
        Build one TrainingSample for a given target model within a canonical
        example. Historical reliability is computed leakage-safely.
        """
        issue_time = row.issue_time
        valid_time = row.valid_time

        # Compute historical reliability for every present/available model,
        # strictly before issue_time.
        historical_reliability: Dict[str, HistoricalReliability] = {}
        for model in CANONICAL_MODELS:
            if not availability.get(model, False):
                continue
            reliability = self._historical_reliability(
                model=model,
                variable=row.variable,
                issue_time=issue_time,
                lead_group=lead_time_group(row.lead_time_hours),
                zone=zone,
                config=config,
            )
            if reliability is not None:
                historical_reliability[model] = reliability

        if historical_reliability:
            stats.samples_with_historical_reliability += 1
        else:
            stats.samples_without_historical_reliability += 1

        try:
            feature_vector: FeatureVector = self.feature_builder.build_feature_vector(
                target_model=target_model,
                issue_time=issue_time,
                valid_time=valid_time,
                location=(row.latitude, row.longitude),
                location_zone=zone,
                variable=row.variable,
                forecasts=forecasts,
                historical_reliability=historical_reliability or None,
            )
        except ValueError as e:
            # A temporal-constraint violation here is a genuine leakage signal.
            stats.leakage_violations += 1
            if len(stats.leakage_violation_examples) < 20:
                stats.leakage_violation_examples.append(
                    f"{row.verification_id}: {e}"
                )
            self.logger.error("Feature construction rejected (leakage?): %s", e)
            return None

        # Availability accounting.
        for model in CANONICAL_MODELS:
            if getattr(feature_vector, f"{model}_available"):
                stats.model_available_counts[model] = (
                    stats.model_available_counts.get(model, 0) + 1
                )

        # Target: outcome for the target model's forecast at valid_time.
        target = Target(
            observed_value=row.observed_value,
            forecast_error=row.error,
            absolute_error=row.absolute_error,
            observation_time=row.observation_time,
            observation_source=row.observation_source,
            observation_quality_score=(
                row.observation_quality_score
                if row.observation_quality_score is not None else 1.0
            ),
        )
        stats.samples_with_target += 1

        return TrainingSample(
            features=feature_vector,
            target=target,
            verification_id=row.verification_id,
            verified_at=row.observation_time,
        )

    # ------------------------------------------------------------------
    # Historical reliability (leakage-safe, cached, aggregate query)
    # ------------------------------------------------------------------
    def _historical_reliability(
        self,
        model: str,
        variable: str,
        issue_time: datetime,
        lead_group: str,
        zone: Optional[str],
        config: BuildConfig,
    ) -> Optional[HistoricalReliability]:
        """
        Compute rolling reliability (RMSE/MAE/bias) for `model` over the window
        [issue_time - window, issue_time) using ONLY verification records whose
        outcome is known strictly before issue_time.

        A verification record's outcome is known at valid_time. We therefore
        require valid_time < issue_time (strict). This structurally prevents a
        forecast's own outcome (valid_time >= issue_time) from ever entering its
        own features.

        Results are cached by (issue_time, model, variable, lead_group, zone).
        Aggregation is performed by an indexed grouped SQL query, not a Python
        O(N) scan per example, so the build scales.
        """
        cache_key = (issue_time.isoformat(), model, variable, lead_group, zone)
        if cache_key in self._reliability_cache:
            return self._reliability_cache[cache_key]

        window_start = issue_time - timedelta(days=config.historical_window_days)

        # Lead group -> lead-hour bounds (inclusive-exclusive) for filtering.
        lead_lo, lead_hi = self._lead_group_bounds(lead_group)

        with self.db_manager.get_session() as session:
            q = (
                session.query(
                    func.count(ForecastVerification.verification_id),
                    func.avg(ForecastVerification.squared_error),
                    func.avg(ForecastVerification.absolute_error),
                    func.avg(ForecastVerification.error),
                )
                .filter(ForecastVerification.model == model)
                .filter(ForecastVerification.variable == variable)
                # CRITICAL leakage cutoff: outcome known strictly before issue.
                .filter(ForecastVerification.valid_time < issue_time)
                .filter(ForecastVerification.valid_time >= window_start)
                .filter(ForecastVerification.lead_time_hours >= lead_lo)
            )
            if lead_hi is not None:
                q = q.filter(ForecastVerification.lead_time_hours < lead_hi)
            if zone is not None:
                q = q.filter(ForecastVerification.location_zone == zone)

            n, mean_sq, mean_abs, mean_err = q.one()

        n = int(n or 0)
        if n < config.min_history_samples or mean_sq is None:
            self._reliability_cache[cache_key] = None
            return None

        # period_end is the newest outcome time that could be included, strictly
        # before issue_time. Use issue_time - 1 microsecond to remain strictly
        # earlier while representing "as of issue_time".
        period_end = issue_time - timedelta(microseconds=1)

        # Validate leakage constraint (period_end < issue_time strictly).
        result = self.temporal_validator.validate_historical_features(
            issue_time, period_end
        )
        if not result.is_valid:
            self._reliability_cache[cache_key] = None
            return None

        reliability = HistoricalReliability(
            model=model,
            variable=variable,
            lead_time_group=lead_group,
            location_zone=zone,
            period_end=period_end,
            window_days=config.historical_window_days,
            rmse=float(mean_sq) ** 0.5,
            mae=float(mean_abs),
            bias=float(mean_err),
            n_forecasts=n,
        )
        self._reliability_cache[cache_key] = reliability
        return reliability

    @staticmethod
    def _lead_group_bounds(lead_group: str) -> Tuple[int, Optional[int]]:
        """Return (lower_inclusive, upper_exclusive) hour bounds for a group."""
        bounds = {
            "0-24h": (0, 25),
            "24-48h": (25, 49),
            "48-72h": (49, 73),
            "72-120h": (73, 121),
            "120h+": (121, None),
        }
        return bounds.get(lead_group, (0, None))

    # ------------------------------------------------------------------
    # Splitting
    # ------------------------------------------------------------------
    def _resolve_boundaries(
        self, distinct_issue_times: List[datetime], split: DatasetSplitConfig
    ) -> Tuple[datetime, datetime]:
        """
        Determine (train_end, validation_end) from actual data.

        Boundaries always fall ON a distinct issue_time value so that a forecast
        cycle is never split across sets:
          TRAIN      : issue_time <  train_end
          VALIDATION : train_end <= issue_time < validation_end
          TEST       : issue_time >= validation_end
        """
        if split.uses_boundaries():
            return split.train_end, split.validation_end

        n = len(distinct_issue_times)
        if n < 3:
            raise ValueError(
                f"Need at least 3 distinct issue_times for a TRAIN/VAL/TEST "
                f"split; found {n}."
            )

        # Index of the first VALIDATION cycle and first TEST cycle.
        train_count = max(1, int(round(n * split.train_fraction)))
        val_count = max(1, int(round(n * split.validation_fraction)))
        # Ensure at least one TEST cycle remains.
        if train_count + val_count >= n:
            val_count = max(1, n - train_count - 1)
        if train_count + val_count >= n:
            train_count = max(1, n - val_count - 1)

        train_end = distinct_issue_times[train_count]
        validation_end = distinct_issue_times[train_count + val_count]
        return train_end, validation_end

    @staticmethod
    def _assign_split(
        issue_time: datetime, train_end: datetime, validation_end: datetime
    ) -> SplitName:
        if issue_time < train_end:
            return SplitName.TRAIN
        if issue_time < validation_end:
            return SplitName.VALIDATION
        return SplitName.TEST

    # ------------------------------------------------------------------
    # Statistics & audits
    # ------------------------------------------------------------------
    def _update_example_stats(
        self, stats: DatasetStatistics, model_rows: Dict[str, VerificationRow]
    ) -> None:
        for model, row in model_rows.items():
            stats.model_counts[model] = stats.model_counts.get(model, 0) + 1
            stats.variable_counts[row.variable] = (
                stats.variable_counts.get(row.variable, 0) + 1
            )
            stats.lead_time_counts[row.lead_time_hours] = (
                stats.lead_time_counts.get(row.lead_time_hours, 0) + 1
            )
            zone_key = row.location_zone or "unknown"
            stats.zone_counts[zone_key] = stats.zone_counts.get(zone_key, 0) + 1

            if stats.issue_time_min is None or row.issue_time < stats.issue_time_min:
                stats.issue_time_min = row.issue_time
            if stats.issue_time_max is None or row.issue_time > stats.issue_time_max:
                stats.issue_time_max = row.issue_time
            if stats.valid_time_min is None or row.valid_time < stats.valid_time_min:
                stats.valid_time_min = row.valid_time
            if stats.valid_time_max is None or row.valid_time > stats.valid_time_max:
                stats.valid_time_max = row.valid_time

    def _audit_split_ordering(self, split: DatasetSplit, stats: DatasetStatistics) -> None:
        """
        Verify chronological ordering across splits:
        max(train.issue_time) <= min(validation.issue_time)
        max(validation.issue_time) <= min(test.issue_time)

        Records any violation as a leakage violation.
        """
        def issue_times(samples: List[TrainingSample]) -> List[datetime]:
            return [s.features.issue_time for s in samples]

        train_t = issue_times(split.train)
        val_t = issue_times(split.validation)
        test_t = issue_times(split.test)

        if train_t and val_t and max(train_t) > min(val_t):
            stats.leakage_violations += 1
            stats.leakage_violation_examples.append(
                "TRAIN overlaps VALIDATION in issue_time"
            )
        if val_t and test_t and max(val_t) > min(test_t):
            stats.leakage_violations += 1
            stats.leakage_violation_examples.append(
                "VALIDATION overlaps TEST in issue_time"
            )
        if train_t and test_t and max(train_t) > min(test_t):
            stats.leakage_violations += 1
            stats.leakage_violation_examples.append(
                "TRAIN overlaps TEST in issue_time"
            )


def summarize_split(split: DatasetSplit) -> str:
    """Human-readable summary of a DatasetSplit (for dry-run reporting)."""
    s = split.statistics
    lines = [
        "HELIOS Dataset Build Summary",
        "=" * 60,
        f"Verification rows read : {s.n_verification_rows}",
        f"Canonical examples     : {s.n_canonical_examples}",
        f"Training samples        : {s.n_training_samples}",
        f"  TRAIN                 : {len(split.train)}",
        f"  VALIDATION            : {len(split.validation)}",
        f"  TEST                  : {len(split.test)}",
        f"Issue time range        : {s.issue_time_min} .. {s.issue_time_max}",
        f"Valid time range        : {s.valid_time_min} .. {s.valid_time_max}",
        f"Model counts            : {s.model_counts}",
        f"Variable counts         : {s.variable_counts}",
        f"Lead-time counts        : {dict(sorted(s.lead_time_counts.items()))}",
        f"Zone counts             : {s.zone_counts}",
        f"Model available counts  : {s.model_available_counts}",
        f"With hist reliability   : {s.samples_with_historical_reliability}",
        f"Without hist reliability: {s.samples_without_historical_reliability}",
        f"With target             : {s.samples_with_target}",
        f"Missing target          : {s.samples_missing_target}",
        f"Leakage violations      : {s.leakage_violations}",
    ]
    if s.leakage_violation_examples:
        lines.append("Leakage examples:")
        for ex in s.leakage_violation_examples:
            lines.append(f"  - {ex}")
    return "\n".join(lines)
