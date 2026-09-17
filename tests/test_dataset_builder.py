"""
HELIOS Dataset Builder Tests

Synthetic-fixture tests for ml/dataset_builder.py. No real data is used; an
in-memory SQLite database is seeded with controlled ForecastVerification rows.

Test coverage (all required cases):
1.  Chronological ordering of emitted samples
2.  No random split (split is a deterministic function of issue_time)
3.  train < validation < test in time (no cross-split overlap)
4.  Historical reliability cutoff (period_end strictly < issue_time)
5.  Same-forecast outcome cannot enter its own historical features
6.  Future verification cannot enter features
7.  Missing model handling (missing != zero; availability flags correct)
8.  Deterministic output (identical repeated builds)
9.  Exact identity preservation (issue/valid/lead/location/variable/model)
10. Empty / no-match behavior
11. Larger-data scalability assumptions (reliability query cache; multi-model
    pivot; parameterised models/variables/windows)
12. lead_time_group boundary mapping
13. DatasetSplitConfig validation (rejects bad fractions/boundaries)
14. Explicit boundary-based split mode
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.connection import DatabaseManager, DatabaseConfig
from database.schema.helios_schema import ForecastVerification
from ml.dataset_builder import (
    DatasetBuilder,
    BuildConfig,
    DatasetSplitConfig,
    SplitName,
    lead_time_group,
)


# ----------------------------------------------------------------------
# Fixtures / helpers
# ----------------------------------------------------------------------

def _make_db() -> DatabaseManager:
    """Create a fresh in-memory SQLite database with schema."""
    # StaticPool keeps a single in-memory connection alive across sessions.
    config = DatabaseConfig(database_url="sqlite:///:memory:")
    db = DatabaseManager(config)
    db.initialize(create_tables=True)
    return db


def _verif(
    vid, model, issue_time, valid_time, lead, lat, lon, zone,
    forecast_value, observed_value, variable="temperature_2m_c",
    observation_time=None, obs_source="noaa_isd", quality=1.0,
):
    """Construct a ForecastVerification ORM row with derived errors."""
    error = forecast_value - observed_value
    return ForecastVerification(
        verification_id=vid,
        forecast_id=f"fc_{vid}",
        model=model,
        issue_time=issue_time,
        valid_time=valid_time,
        lead_time_hours=lead,
        latitude=lat,
        longitude=lon,
        location_zone=zone,
        variable=variable,
        forecast_value=forecast_value,
        observed_value=observed_value,
        observation_source=obs_source,
        observation_quality_score=quality,
        observation_time=observation_time or valid_time,
        error=error,
        absolute_error=abs(error),
        squared_error=error * error,
        verification_time=(observation_time or valid_time) + timedelta(hours=1),
    )


def _seed(db, rows):
    with db.get_session() as session:
        for r in rows:
            session.add(r)


def _daily_cycles(n_days, start=datetime(2025, 1, 1, 0, 0, 0)):
    """Yield one 00Z issue_time per day."""
    for d in range(n_days):
        yield start + timedelta(days=d)


def _seed_single_model_series(db, model="ifs", n_days=10, zone="central",
                              lat=20.0, lon=78.0, lead=24):
    """
    Seed one forecast per day at a fixed location. valid_time = issue + lead.
    Each row is a distinct canonical example (distinct issue/valid).
    """
    rows = []
    i = 0
    for issue in _daily_cycles(n_days):
        valid = issue + timedelta(hours=lead)
        rows.append(_verif(
            f"{model}_{i:03d}", model, issue, valid, lead, lat, lon, zone,
            forecast_value=25.0 + i * 0.1, observed_value=24.0 + i * 0.1,
        ))
        i += 1
    _seed(db, rows)
    return rows


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------

def test_lead_time_group_boundaries():
    """TEST: lead_time_group maps boundaries correctly."""
    print("TEST: lead_time_group boundary mapping")
    assert lead_time_group(0) == "0-24h"
    assert lead_time_group(6) == "0-24h"
    assert lead_time_group(24) == "0-24h"
    assert lead_time_group(25) == "24-48h"
    assert lead_time_group(48) == "24-48h"
    assert lead_time_group(72) == "48-72h"
    assert lead_time_group(120) == "72-120h"
    assert lead_time_group(121) == "120h+"
    assert lead_time_group(240) == "120h+"
    print("  ✓ boundaries correct")
    print()
    return True


def test_split_config_validation():
    """TEST: DatasetSplitConfig rejects invalid fractions/boundaries."""
    print("TEST: DatasetSplitConfig validation")
    DatasetSplitConfig(train_fraction=0.6, validation_fraction=0.2).validate()  # ok

    bad = DatasetSplitConfig(train_fraction=0.7, validation_fraction=0.4)
    try:
        bad.validate()
        assert False, "expected ValueError for fractions summing >= 1"
    except ValueError:
        pass

    bad_bounds = DatasetSplitConfig(
        train_end=datetime(2025, 1, 10), validation_end=datetime(2025, 1, 5)
    )
    try:
        bad_bounds.validate()
        assert False, "expected ValueError for train_end >= validation_end"
    except ValueError:
        pass
    print("  ✓ invalid configs rejected")
    print()
    return True


def test_empty_no_match():
    """TEST: empty / no-match behavior returns empty split."""
    print("TEST: empty / no-match behavior")
    db = _make_db()
    _seed_single_model_series(db, model="ifs", n_days=5)

    # No rows match variable 'wind_speed_10m_ms'
    builder = DatasetBuilder(db)
    split = builder.build(BuildConfig(variable="wind_speed_10m_ms"))
    assert split.total() == 0
    assert split.statistics.n_verification_rows == 0

    # No rows match models=('gfs',) when only ifs exists
    split2 = builder.build(BuildConfig(models=("gfs",)))
    assert split2.total() == 0
    db.close()
    print("  ✓ empty splits returned, no crash")
    print()
    return True


def test_chronological_split_ordering():
    """TEST: train < validation < test in issue_time; no overlap."""
    print("TEST: chronological split ordering (train < val < test)")
    db = _make_db()
    _seed_single_model_series(db, model="ifs", n_days=10)

    builder = DatasetBuilder(db)
    split = builder.build(BuildConfig(
        split=DatasetSplitConfig(train_fraction=0.6, validation_fraction=0.2),
        min_history_samples=1,
    ))

    assert split.total() == 10, f"expected 10 samples, got {split.total()}"
    assert len(split.train) > 0 and len(split.validation) > 0 and len(split.test) > 0

    train_max = max(s.features.issue_time for s in split.train)
    val_min = min(s.features.issue_time for s in split.validation)
    val_max = max(s.features.issue_time for s in split.validation)
    test_min = min(s.features.issue_time for s in split.test)

    assert train_max < val_min, "TRAIN must be strictly before VALIDATION"
    assert val_max < test_min, "VALIDATION must be strictly before TEST"
    assert split.statistics.leakage_violations == 0
    db.close()
    print(f"  ✓ split {len(split.train)}/{len(split.validation)}/{len(split.test)}; "
          f"train_max={train_max} < val_min={val_min}, val_max={val_max} < test_min={test_min}")
    print()
    return True


def test_no_random_deterministic():
    """TEST: no random split; repeated builds are identical (deterministic)."""
    print("TEST: deterministic output (no random split)")
    db = _make_db()
    _seed_single_model_series(db, model="ifs", n_days=12)

    builder = DatasetBuilder(db)
    cfg = BuildConfig()
    split_a = builder.build(cfg)
    split_b = builder.build(cfg)

    def ids(samples):
        return [s.verification_id for s in samples]

    assert ids(split_a.train) == ids(split_b.train)
    assert ids(split_a.validation) == ids(split_b.validation)
    assert ids(split_a.test) == ids(split_b.test)
    # Ordering within each split is deterministic (sorted by identity)
    train_times = [s.features.issue_time for s in split_a.train]
    assert train_times == sorted(train_times)
    db.close()
    print("  ✓ identical repeated builds; ordered by issue_time")
    print()
    return True


def test_explicit_boundary_split():
    """TEST: explicit datetime boundary split mode works."""
    print("TEST: explicit boundary split mode")
    db = _make_db()
    _seed_single_model_series(db, model="ifs", n_days=10)

    builder = DatasetBuilder(db)
    split = builder.build(BuildConfig(split=DatasetSplitConfig(
        train_end=datetime(2025, 1, 6, 0, 0, 0),      # days 1-5 train
        validation_end=datetime(2025, 1, 9, 0, 0, 0),  # days 6-8 val, 9-10 test
    )))
    # issue_time = day start (00Z). train: Jan1..Jan5 (5), val: Jan6..Jan8 (3), test: Jan9..Jan10 (2)
    assert len(split.train) == 5, f"got {len(split.train)}"
    assert len(split.validation) == 3, f"got {len(split.validation)}"
    assert len(split.test) == 2, f"got {len(split.test)}"
    assert split.statistics.leakage_violations == 0
    db.close()
    print("  ✓ 5/3/2 split by explicit boundaries")
    print()
    return True


def test_identity_preservation():
    """TEST: exact identity preserved (issue/valid/lead/location/variable/model)."""
    print("TEST: exact identity preservation")
    db = _make_db()
    issue = datetime(2025, 1, 5, 0, 0, 0)
    valid = issue + timedelta(hours=48)
    _seed(db, [_verif(
        "ifs_x", "ifs", issue, valid, 48, 19.5, 72.8, "south_coastal",
        forecast_value=30.5, observed_value=29.0,
    )])
    builder = DatasetBuilder(db)
    # Single cycle: use explicit boundaries so the split is well-defined.
    split = builder.build(BuildConfig(split=DatasetSplitConfig(
        train_end=datetime(2025, 1, 6, 0, 0, 0),
        validation_end=datetime(2025, 1, 6, 12, 0, 0),
    )))
    all_samples = split.train + split.validation + split.test
    assert len(all_samples) == 1
    s = all_samples[0]
    f = s.features
    assert f.model == "ifs"
    assert f.issue_time == issue
    assert f.valid_time == valid
    assert f.lead_time_hours == 48
    assert f.latitude == 19.5 and f.longitude == 72.8
    assert f.variable == "temperature_2m_c"
    assert f.location_zone == "south_coastal"
    assert s.verification_id == "ifs_x"
    # Target preserved
    assert abs(s.target.observed_value - 29.0) < 1e-9
    assert abs(s.target.forecast_error - 1.5) < 1e-9
    assert abs(s.target.absolute_error - 1.5) < 1e-9
    assert s.target.observation_source == "noaa_isd"
    db.close()
    print("  ✓ identity + target preserved exactly")
    print()
    return True


def test_missing_model_handling():
    """TEST: missing model != zero; availability flags reflect presence."""
    print("TEST: missing model handling")
    db = _make_db()
    issue = datetime(2025, 1, 5, 0, 0, 0)
    valid = issue + timedelta(hours=24)
    # Same identity, two models present (ifs + gfs), icon missing.
    _seed(db, [
        _verif("ifs_a", "ifs", issue, valid, 24, 20.0, 78.0, "central", 25.0, 24.0),
        _verif("gfs_a", "gfs", issue, valid, 24, 20.0, 78.0, "central", 26.0, 24.0),
    ])
    builder = DatasetBuilder(db)
    split = builder.build(BuildConfig(split=DatasetSplitConfig(
        train_end=datetime(2025, 1, 6, 0, 0, 0),
        validation_end=datetime(2025, 1, 6, 12, 0, 0),
    )))
    all_samples = split.train + split.validation + split.test
    # One canonical example, two present models => 2 training samples.
    assert len(all_samples) == 2, f"got {len(all_samples)}"
    for s in all_samples:
        f = s.features
        assert f.ifs_available is True
        assert f.gfs_available is True
        assert f.icon_available is False
        # Missing model is None, NOT zero.
        assert f.icon_value is None
        assert f.gfs_value == 26.0
        assert f.ifs_value == 25.0
    db.close()
    print("  ✓ icon missing => value None + available False; present models kept")
    print()
    return True


def test_historical_reliability_cutoff_and_own_outcome_excluded():
    """
    TEST: historical reliability uses only prior outcomes (period_end < issue_time),
    and a forecast's OWN outcome cannot enter its own features.
    """
    print("TEST: historical reliability cutoff + own-outcome exclusion")
    db = _make_db()
    zone, lat, lon, lead = "central", 20.0, 78.0, 24

    rows = []
    # 3 prior forecasts whose outcomes are known before the target issue_time.
    # issue Jan1/2/3, valid = issue+24h => outcomes on Jan2/3/4.
    for i, day in enumerate([1, 2, 3]):
        issue = datetime(2025, 1, day, 0, 0, 0)
        valid = issue + timedelta(hours=lead)
        rows.append(_verif(
            f"ifs_hist_{i}", "ifs", issue, valid, lead, lat, lon, zone,
            forecast_value=20.0, observed_value=18.0,  # error +2.0, abs 2.0
        ))
    # Target forecast: issue Jan6 00Z (all 3 prior outcomes are before Jan6).
    target_issue = datetime(2025, 1, 6, 0, 0, 0)
    target_valid = target_issue + timedelta(hours=lead)
    rows.append(_verif(
        "ifs_target", "ifs", target_issue, target_valid, lead, lat, lon, zone,
        forecast_value=100.0, observed_value=0.0,  # huge error 100 - must NOT appear in history
    ))
    _seed(db, rows)

    builder = DatasetBuilder(db)
    # Window large enough (7 days) to include Jan2-4 outcomes before Jan6.
    split = builder.build(BuildConfig(historical_window_days=7, min_history_samples=1))
    samples = {s.verification_id: s for s in (split.train + split.validation + split.test)}

    target = samples["ifs_target"]
    f = target.features
    # Historical IFS reliability should be present and reflect prior error (2.0),
    # NOT the target's own 100.0 error.
    assert f.ifs_mae_7day is not None, "expected historical reliability for target"
    assert abs(f.ifs_mae_7day - 2.0) < 1e-6, f"got {f.ifs_mae_7day}"
    assert f.ifs_rmse_7day is not None and abs(f.ifs_rmse_7day - 2.0) < 1e-6
    # The huge own error (100) is excluded.
    assert f.ifs_mae_7day < 3.0, "own outcome leaked into history!"

    # The earliest historical forecast (Jan1) has NO prior outcomes => None.
    first = samples["ifs_hist_0"]
    assert first.features.ifs_mae_7day is None, "earliest example must have no history"
    db.close()
    print(f"  ✓ target ifs_mae_7day={f.ifs_mae_7day} (prior only); "
          f"earliest has no history; own 100.0 error excluded")
    print()
    return True


def test_future_verification_cannot_enter_features():
    """
    TEST: outcomes with valid_time >= issue_time (future/current) never enter
    the historical features of an example.
    """
    print("TEST: future verification cannot enter features")
    db = _make_db()
    zone, lat, lon, lead = "north_plains", 28.0, 77.0, 24

    rows = []
    # Target issued Jan5.
    target_issue = datetime(2025, 1, 5, 0, 0, 0)
    target_valid = target_issue + timedelta(hours=lead)
    rows.append(_verif(
        "ifs_tgt", "ifs", target_issue, target_valid, lead, lat, lon, zone,
        forecast_value=10.0, observed_value=9.0,
    ))
    # A FUTURE forecast issued Jan10 whose outcome is well after target issue.
    fut_issue = datetime(2025, 1, 10, 0, 0, 0)
    fut_valid = fut_issue + timedelta(hours=lead)
    rows.append(_verif(
        "ifs_fut", "ifs", fut_issue, fut_valid, lead, lat, lon, zone,
        forecast_value=999.0, observed_value=0.0,  # extreme; must never leak backwards
    ))
    _seed(db, rows)

    builder = DatasetBuilder(db)
    split = builder.build(BuildConfig(
        historical_window_days=30, min_history_samples=1,
        split=DatasetSplitConfig(
            train_end=datetime(2025, 1, 8, 0, 0, 0),       # Jan5 -> TRAIN
            validation_end=datetime(2025, 1, 9, 0, 0, 0),  # Jan10 -> TEST
        ),
    ))
    samples = {s.verification_id: s for s in (split.train + split.validation + split.test)}

    # Target (Jan5) has no PRIOR outcomes => historical reliability None.
    tgt = samples["ifs_tgt"]
    assert tgt.features.ifs_mae_7day is None, "future outcome leaked into target features!"
    assert split.statistics.leakage_violations == 0
    db.close()
    print("  ✓ future outcome (Jan10) did not enter Jan5 example features")
    print()
    return True


def test_multi_model_pivot_and_scalability_assumptions():
    """
    TEST: multi-model pivot works (scales beyond IFS-only), reliability cache
    is populated, and parameterised models/variables are honored.
    """
    print("TEST: multi-model pivot + scalability assumptions")
    db = _make_db()
    zone, lat, lon, lead = "central", 20.0, 78.0, 48

    rows = []
    # Two cycles, three models each at same identity per cycle.
    for i, day in enumerate([1, 2, 3, 4]):
        issue = datetime(2025, 1, day, 0, 0, 0)
        valid = issue + timedelta(hours=lead)
        for model, fv in [("gfs", 25.0), ("ifs", 24.5), ("icon", 26.0)]:
            rows.append(_verif(
                f"{model}_{i}", model, issue, valid, lead, lat, lon, zone,
                forecast_value=fv, observed_value=24.0,
            ))
    _seed(db, rows)

    builder = DatasetBuilder(db)
    split = builder.build(BuildConfig(models=("gfs", "ifs", "icon"),
                                      historical_window_days=30,
                                      min_history_samples=1))
    all_samples = split.train + split.validation + split.test
    # 4 canonical examples * 3 models = 12 samples.
    assert len(all_samples) == 12, f"got {len(all_samples)}"

    # A later example should have all three models' historical reliability.
    later = [s for s in all_samples if s.features.issue_time == datetime(2025, 1, 4)]
    assert later, "expected Jan4 examples"
    f = later[0].features
    assert f.gfs_available and f.ifs_available and f.icon_available
    assert f.gfs_value == 25.0 and f.ifs_value == 24.5 and f.icon_value == 26.0
    assert f.gfs_mae_7day is not None
    assert f.ifs_mae_7day is not None
    assert f.icon_mae_7day is not None
    # Inter-model spread present (>=2 models).
    assert f.forecast_spread is not None and f.forecast_spread > 0

    # Reliability cache should be populated and reused (near-linear scaling).
    assert len(builder._reliability_cache) > 0
    db.close()
    print(f"  ✓ 12 samples; 3-model pivot; cache entries={len(builder._reliability_cache)}")
    print()
    return True


def test_min_history_samples_threshold():
    """TEST: min_history_samples suppresses reliability below threshold."""
    print("TEST: min_history_samples threshold")
    db = _make_db()
    zone, lat, lon, lead = "central", 20.0, 78.0, 24
    rows = []
    for i, day in enumerate([1, 2]):
        issue = datetime(2025, 1, day, 0, 0, 0)
        valid = issue + timedelta(hours=lead)
        rows.append(_verif(f"ifs_{i}", "ifs", issue, valid, lead, lat, lon, zone, 20.0, 18.0))
    target_issue = datetime(2025, 1, 6, 0, 0, 0)
    rows.append(_verif("ifs_t", "ifs", target_issue, target_issue + timedelta(hours=lead),
                       lead, lat, lon, zone, 20.0, 18.0))
    _seed(db, rows)

    builder = DatasetBuilder(db)
    # Require 5 prior samples; only 2 exist => reliability suppressed.
    split = builder.build(BuildConfig(historical_window_days=30, min_history_samples=5))
    samples = {s.verification_id: s for s in (split.train + split.validation + split.test)}
    assert samples["ifs_t"].features.ifs_mae_7day is None
    assert split.statistics.samples_without_historical_reliability >= 1
    db.close()
    print("  ✓ reliability suppressed when prior count < min_history_samples")
    print()
    return True
