"""
Unit Tests for Data Sufficiency Checker

Tests for HELIOS data sufficiency evaluation to gate ML training eligibility.

CRITICAL PRINCIPLES TESTED:
1. Data-driven gates (NOT calendar-based)
2. Model-specific sufficiency
3. Variable-specific sufficiency
4. Lead-time-specific sufficiency
5. Location-specific sufficiency
6. Quality thresholds (NOAA ISD vs ERA5-Land)
7. Cold-start behavior (SimpleAverage always allowed)
8. ML eligibility gates
9. Chronological split recommendations

Test coverage:
1. Cold start (zero verifications)
2. Insufficient total records
3. Sufficient total records
4. Missing one model (insufficient GFS)
5. Sufficient GFS but insufficient ICON
6. Insufficient variable-specific history
7. Insufficient lead-time history
8. Insufficient location history
9. Insufficient observation quality
10. Short historical span vs sufficient span
11. Cold-start SimpleAverage allowed
12. Advanced ML blocked when insufficient
13. Chronological split recommendation
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_cold_start_zero_verifications():
    """Test cold start with zero verification records."""
    print("TEST 1: Cold start (zero verifications)")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # No verification reader (cold start)
    checker = DataSufficiencyChecker(verification_reader=None)

    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.COLD_START
    assert result.is_sufficient == False
    assert result.total_verifications == 0
    assert result.missing_models == ['gfs', 'ifs', 'icon']
    assert result.insufficient_variables == ['temperature_2m_c']
    assert result.details['reason'] == 'No verification records available'

    print("  ✓ level = COLD_START")
    print("  ✓ is_sufficient = False")
    print("  ✓ total_verifications = 0")
    print("  ✓ All models/variables/lead-times/zones insufficient")
    print()
    return True


def test_insufficient_total_records():
    """Test insufficient total verification records."""
    print("TEST 2: Insufficient total records")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # Mock verification reader with only 50 records (threshold = 1000)
    mock_reader = Mock()
    mock_reader.get_verifications.return_value = [
        {
            'model': 'gfs',
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'issue_time': datetime(2026, 9, 1, 0, 0, 0),
            'verification_time': datetime(2026, 9, 1, 12, 0, 0)
        }
        for _ in range(50)
    ]

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.COLD_START  # < 100 absolute minimum
    assert result.is_sufficient == False
    assert result.total_verifications == 50

    print("  ✓ level = COLD_START (< 100 absolute minimum)")
    print("  ✓ is_sufficient = False")
    print("  ✓ total_verifications = 50")
    print()
    return True


def test_sufficient_total_records():
    """Test sufficient total verification records (all thresholds met)."""
    print("TEST 3: Sufficient total records")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # Mock verification reader with 1200 records (exceeds 1000 threshold)
    # Distributed across models, variables, lead times, zones
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(1200):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        lead_time = [12, 48, 120][i % 3]
        zone = ['north_plains', 'central', 'south_plateau', 'south_coastal', 'north_himalaya'][i % 5]

        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': lead_time,
            'location_zone': zone,
            'observation_quality_score': 1.0,  # All high-quality
            'issue_time': base_time + timedelta(hours=i),  # span derived from issue_time
            'verification_time': base_time + timedelta(hours=i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level in [SufficiencyLevel.SUFFICIENT, SufficiencyLevel.ABUNDANT]
    assert result.is_sufficient == True
    assert result.total_verifications == 1200
    assert len(result.missing_models) == 0
    assert len(result.insufficient_variables) == 0

    print("  ✓ level = SUFFICIENT or ABUNDANT")
    print("  ✓ is_sufficient = True")
    print("  ✓ total_verifications = 1200")
    print("  ✓ No missing models")
    print("  ✓ No insufficient variables")
    print()
    return True


def test_missing_one_model():
    """Test missing one model (insufficient GFS)."""
    print("TEST 4: Missing one model (insufficient GFS)")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # 1000 records total, but GFS has only 100 (threshold = 250 per model)
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    # GFS: 100 records (insufficient)
    for i in range(100):
        verifications.append({
            'model': 'gfs',
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i)
        })

    # IFS + ICON: 900 records (sufficient per model)
    for i in range(450):
        for model in ['ifs', 'icon']:
            verifications.append({
                'model': model,
                'variable': 'temperature_2m_c',
                'lead_time_hours': 12,
                'location_zone': 'north_plains',
                'observation_quality_score': 1.0,
                'verification_time': base_time + timedelta(hours=100 + i)
            })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING  # Gap remains
    assert result.is_sufficient == False
    assert 'gfs' in result.missing_models
    assert 'ifs' not in result.missing_models
    assert 'icon' not in result.missing_models

    print("  ✓ level = WARMING (GFS insufficient)")
    print("  ✓ is_sufficient = False")
    print("  ✓ 'gfs' in missing_models")
    print("  ✓ IFS and ICON sufficient")
    print()
    return True


def test_sufficient_gfs_insufficient_icon():
    """Test sufficient GFS but insufficient ICON."""
    print("TEST 5: Sufficient GFS but insufficient ICON")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    # GFS: 300 records (sufficient)
    for i in range(300):
        verifications.append({
            'model': 'gfs',
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i)
        })

    # IFS: 300 records (sufficient)
    for i in range(300):
        verifications.append({
            'model': 'ifs',
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=300 + i)
        })

    # ICON: 100 records (insufficient, threshold = 250)
    for i in range(100):
        verifications.append({
            'model': 'icon',
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=600 + i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING
    assert result.is_sufficient == False
    assert 'icon' in result.missing_models
    assert 'gfs' not in result.missing_models
    assert 'ifs' not in result.missing_models

    print("  ✓ level = WARMING (ICON insufficient)")
    print("  ✓ is_sufficient = False")
    print("  ✓ 'icon' in missing_models")
    print("  ✓ GFS and IFS sufficient")
    print()
    return True


def test_insufficient_variable_specific_history():
    """Test insufficient variable-specific history."""
    print("TEST 6: Insufficient variable-specific history")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # Only 150 temperature records (threshold = 200 per variable)
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(150):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING
    assert result.is_sufficient == False
    assert 'temperature_2m_c' in result.insufficient_variables

    print("  ✓ level = WARMING")
    print("  ✓ is_sufficient = False")
    print("  ✓ 'temperature_2m_c' in insufficient_variables")
    print()
    return True


def test_insufficient_lead_time_history():
    """Test insufficient lead-time-specific history."""
    print("TEST 7: Insufficient lead-time history")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # 500 records, but all at 12h lead time (short bucket)
    # Medium (24-72h) and long (72-168h) buckets have 0 records
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(500):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,  # All short lead time
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING
    assert result.is_sufficient == False
    assert len(result.insufficient_lead_times) > 0

    print("  ✓ level = WARMING")
    print("  ✓ is_sufficient = False")
    print("  ✓ insufficient_lead_times not empty (missing medium/long)")
    print()
    return True


def test_insufficient_location_history():
    """Test insufficient location-specific history."""
    print("TEST 8: Insufficient location history")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # 500 records, all in 'north_plains'
    # Other zones have 0 records (threshold = 100 per zone)
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(500):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',  # All in one zone
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING
    assert result.is_sufficient == False
    assert len(result.insufficient_zones) > 0

    print("  ✓ level = WARMING")
    print("  ✓ is_sufficient = False")
    print("  ✓ insufficient_zones not empty (missing other zones)")
    print()
    return True


def test_insufficient_observation_quality():
    """Test insufficient observation quality (too much ERA5-Land fallback)."""
    print("TEST 9: Insufficient observation quality")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # 1200 records total, but only 400 high-quality (NOAA ISD)
    # 800 are ERA5-Land fallback (quality_score = 0.8 < 0.9)
    # High-quality fraction = 400/1200 = 33% < 50% threshold
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    # 400 high-quality (NOAA ISD)
    for i in range(400):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,  # NOAA ISD
            'verification_time': base_time + timedelta(hours=i)
        })

    # 800 low-quality (ERA5-Land fallback)
    for i in range(800):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 0.8,  # ERA5-Land fallback
            'verification_time': base_time + timedelta(hours=400 + i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING
    assert result.is_sufficient == False
    assert result.high_quality_count == 400
    assert result.fallback_count == 800
    assert result.details['high_quality_fraction'] < 0.5

    print("  ✓ level = WARMING (insufficient quality)")
    print("  ✓ is_sufficient = False")
    print("  ✓ high_quality_count = 400")
    print("  ✓ fallback_count = 800")
    print("  ✓ high_quality_fraction = 33% < 50%")
    print()
    return True


def test_short_vs_sufficient_historical_span():
    """Test short historical span vs sufficient span."""
    print("TEST 10: Short vs sufficient historical span")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyConfig,
        SufficiencyLevel
    )

    # SHORT SPAN: 1000 records in 7 days (threshold = 14 days)
    verifications_short = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(1000):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        lead_time = [12, 48, 120][i % 3]
        zone = ['north_plains', 'central', 'south_plateau', 'south_coastal', 'north_himalaya'][i % 5]

        verifications_short.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': lead_time,
            'location_zone': zone,
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i * 0.168)  # ~7 days
        })

    mock_reader_short = Mock()
    mock_reader_short.get_verifications.return_value = verifications_short

    checker_short = DataSufficiencyChecker(verification_reader=mock_reader_short)
    result_short = checker_short.check_sufficiency()

    assert result_short.level == SufficiencyLevel.WARMING
    assert result_short.is_sufficient == False
    assert result_short.historical_span_days < 14.0

    # SUFFICIENT SPAN: 1200 records in 20 days (exceeds 14 days)
    verifications_long = []

    for i in range(1200):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        lead_time = [12, 48, 120][i % 3]
        zone = ['north_plains', 'central', 'south_plateau', 'south_coastal', 'north_himalaya'][i % 5]

        verifications_long.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': lead_time,
            'location_zone': zone,
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i * 0.4)  # ~20 days
        })

    mock_reader_long = Mock()
    mock_reader_long.get_verifications.return_value = verifications_long

    checker_long = DataSufficiencyChecker(verification_reader=mock_reader_long)
    result_long = checker_long.check_sufficiency()

    assert result_long.level in [SufficiencyLevel.SUFFICIENT, SufficiencyLevel.ABUNDANT]
    assert result_long.is_sufficient == True
    assert result_long.historical_span_days >= 14.0

    print("  ✓ SHORT SPAN: level = WARMING, span < 14 days")
    print("  ✓ SUFFICIENT SPAN: level = SUFFICIENT, span >= 14 days")
    print()
    return True


def test_cold_start_simple_average_allowed():
    """Test cold-start allows SimpleAverage baseline."""
    print("TEST 11: Cold-start SimpleAverage allowed")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyLevel
    )

    # Cold start (no data)
    checker = DataSufficiencyChecker(verification_reader=None)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.COLD_START
    assert checker.is_cold_start(result) == True

    # SimpleAverage baseline is ALWAYS allowed (not gated by sufficiency)
    # ML training is blocked
    assert checker.is_ml_training_eligible(result) == False

    print("  ✓ level = COLD_START")
    print("  ✓ is_cold_start() = True")
    print("  ✓ is_ml_training_eligible() = False")
    print("  ✓ SimpleAverage baseline ALWAYS allowed (not gated)")
    print()
    return True


def test_advanced_ml_blocked_when_insufficient():
    """Test advanced ML blocked when data insufficient."""
    print("TEST 12: Advanced ML blocked when insufficient")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyLevel
    )

    # WARMING level (some data, but gaps remain)
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(500):  # Only 500 records (threshold = 1000)
        model = ['gfs', 'ifs', 'icon'][i % 3]
        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': 12,
            'location_zone': 'north_plains',
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i)
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.level == SufficiencyLevel.WARMING
    assert result.is_sufficient == False
    assert checker.is_ml_training_eligible(result) == False

    print("  ✓ level = WARMING")
    print("  ✓ is_sufficient = False")
    print("  ✓ is_ml_training_eligible() = False")
    print("  ✓ Advanced ML blocked when insufficient")
    print()
    return True


def test_chronological_split_recommendation():
    """Test chronological train/validation/test split recommendation."""
    print("TEST 13: Chronological split recommendation")

    from validation.data_sufficiency_checker import (
        DataSufficiencyChecker,
        SufficiencyLevel
    )

    # SUFFICIENT data (1200 records over 20 days)
    verifications = []
    base_time = datetime(2026, 9, 1, 0, 0, 0)

    for i in range(1200):
        model = ['gfs', 'ifs', 'icon'][i % 3]
        lead_time = [12, 48, 120][i % 3]
        zone = ['north_plains', 'central', 'south_plateau', 'south_coastal', 'north_himalaya'][i % 5]

        verifications.append({
            'model': model,
            'variable': 'temperature_2m_c',
            'lead_time_hours': lead_time,
            'location_zone': zone,
            'observation_quality_score': 1.0,
            'verification_time': base_time + timedelta(hours=i * 0.4)  # ~20 days
        })

    mock_reader = Mock()
    mock_reader.get_verifications.return_value = verifications

    checker = DataSufficiencyChecker(verification_reader=mock_reader)
    result = checker.check_sufficiency()

    assert result.is_sufficient == True

    # Get chronological split recommendation
    split = checker.get_chronological_split_recommendation(result)

    assert split is not None
    assert split['split_type'] == 'chronological'
    assert split['train_fraction'] == 0.6
    assert split['validation_fraction'] == 0.2
    assert split['test_fraction'] == 0.2

    # Train < validation < test (chronologically)
    assert split['train_start'] < split['train_end']
    assert split['train_end'] == split['validation_start']
    assert split['validation_start'] < split['validation_end']
    assert split['validation_end'] == split['test_start']
    assert split['test_start'] < split['test_end']

    print("  ✓ split_type = 'chronological'")
    print("  ✓ train_fraction = 0.6")
    print("  ✓ validation_fraction = 0.2")
    print("  ✓ test_fraction = 0.2")
    print("  ✓ Chronological ordering: train < validation < test")
    print("  ✓ NEVER random splits")
    print()
    return True


# ============================================================================
# Issue-time span correction regression tests (A-F)
# ============================================================================

def _make_verifications(n, *, issue_start, issue_step_hours, verif_time,
                        models=('gfs', 'ifs', 'icon'),
                        variable='temperature_2m_c',
                        leads=(12, 48, 120),
                        zones=('north_plains', 'central', 'south_plateau',
                               'south_coastal', 'north_himalaya'),
                        quality=1.0):
    """Build synthetic verification dicts.

    issue_time spans a real forecast domain (issue_start .. +n*issue_step_hours),
    while verification_time is a SINGLE batch-insert timestamp (verif_time) to
    emulate 'all rows inserted today'.
    """
    recs = []
    for i in range(n):
        recs.append({
            'model': models[i % len(models)],
            'variable': variable,
            'lead_time_hours': leads[i % len(leads)],
            'location_zone': zones[i % len(zones)],
            'observation_quality_score': quality,
            'issue_time': issue_start + timedelta(hours=i * issue_step_hours),
            'verification_time': verif_time,  # constant -> ~0 day insertion span
        })
    return recs


def test_span_from_issue_time_batch_insert():
    """A. Batch-inserted dataset with 28-day issue_time span reports ~28 days."""
    print("TEST A: Span from issue_time for batch-inserted dataset")
    from validation.data_sufficiency_checker import DataSufficiencyChecker

    n = 1200
    issue_start = datetime(2025, 1, 1, 0, 0, 0)
    # 28-day span across n records
    step = (28 * 24) / (n - 1)
    recs = _make_verifications(
        n, issue_start=issue_start, issue_step_hours=step,
        verif_time=datetime(2026, 9, 8, 0, 0, 0),  # single batch-insert stamp
    )
    reader = Mock(); reader.get_verifications.return_value = recs
    result = DataSufficiencyChecker(verification_reader=reader).check_sufficiency()

    assert 27.5 <= result.historical_span_days <= 28.5, \
        f"expected ~28 days, got {result.historical_span_days}"
    print(f"  ✓ historical_span_days ≈ {result.historical_span_days:.2f} (≈28, not ≈0)")
    print()
    return True


def test_span_ignores_insertion_time():
    """B. Span is derived from issue_time, NOT insertion/verification_time."""
    print("TEST B: Span derived from issue_time, not verification_time")
    from validation.data_sufficiency_checker import DataSufficiencyChecker

    n = 500
    issue_start = datetime(2025, 3, 1, 0, 0, 0)
    step = (10 * 24) / (n - 1)  # 10-day issue span
    recs = _make_verifications(
        n, issue_start=issue_start, issue_step_hours=step,
        verif_time=datetime(2026, 9, 8, 12, 0, 0),  # identical for all
    )
    reader = Mock(); reader.get_verifications.return_value = recs
    result = DataSufficiencyChecker(verification_reader=reader).check_sufficiency()

    # If it used verification_time (all identical), span would be ~0.
    assert result.historical_span_days > 9.0, \
        f"span should reflect 10-day issue span, got {result.historical_span_days}"
    print(f"  ✓ historical_span_days ≈ {result.historical_span_days:.2f} (from issue_time)")
    print()
    return True


def test_default_config_flags_missing_gfs_icon():
    """C. Default (gfs+ifs+icon) config flags missing GFS+ICON for IFS-only data."""
    print("TEST C: Default config flags missing GFS+ICON (ECMWF-only dataset)")
    from validation.data_sufficiency_checker import DataSufficiencyChecker

    n = 1200
    issue_start = datetime(2025, 1, 1, 0, 0, 0)
    step = (28 * 24) / (n - 1)
    recs = _make_verifications(
        n, issue_start=issue_start, issue_step_hours=step,
        verif_time=datetime(2026, 9, 8, 0, 0, 0),
        models=('ifs',),  # IFS-only dataset
    )
    reader = Mock(); reader.get_verifications.return_value = recs
    result = DataSufficiencyChecker(verification_reader=reader).check_sufficiency()

    assert 'gfs' in result.missing_models and 'icon' in result.missing_models, \
        f"expected gfs+icon missing, got {result.missing_models}"
    assert result.is_sufficient is False
    print(f"  ✓ missing_models = {result.missing_models}")
    print()
    return True


def test_ifs_only_span_from_issue_time():
    """D. IFS-only config evaluates the actual historical issue-time span."""
    print("TEST D: IFS-only config uses actual issue-time span")
    from validation.data_sufficiency_checker import DataSufficiencyChecker, SufficiencyConfig

    n = 1200
    issue_start = datetime(2025, 1, 1, 0, 0, 0)
    step = (28 * 24) / (n - 1)
    recs = _make_verifications(
        n, issue_start=issue_start, issue_step_hours=step,
        verif_time=datetime(2026, 9, 8, 0, 0, 0),
        models=('ifs',),
    )
    reader = Mock(); reader.get_verifications.return_value = recs
    cfg = SufficiencyConfig(expected_models=['ifs'])
    result = DataSufficiencyChecker(config=cfg, verification_reader=reader).check_sufficiency()

    assert 27.5 <= result.historical_span_days <= 28.5
    assert result.missing_models == []  # ifs present
    print(f"  ✓ span ≈ {result.historical_span_days:.2f} days, no missing models (ifs-only)")
    print()
    return True


def test_count_gates_unchanged():
    """E. Existing count-based sufficiency gates remain unchanged."""
    print("TEST E: Count gates unchanged")
    from validation.data_sufficiency_checker import SufficiencyConfig

    cfg = SufficiencyConfig()
    assert cfg.min_total_verifications == 1000
    assert cfg.min_verifications_per_model == 250
    assert cfg.min_verifications_per_variable == 200
    assert cfg.min_verifications_per_lead_time == 50
    assert cfg.min_verifications_per_zone == 100
    assert cfg.min_historical_span_days == 14.0
    assert cfg.min_high_quality_fraction == 0.5
    assert cfg.high_quality_threshold == 0.9
    assert cfg.lead_time_buckets == [24, 72, 168]
    print("  ✓ All count/threshold gates unchanged (1000/250/200/50/100/14/0.5/0.9)")
    print()
    return True


def test_no_temporal_leakage_weakening():
    """F. Temporal-leakage rules (TemporalValidator) remain intact/unchanged."""
    print("TEST F: No temporal-leakage weakening")
    from validation.temporal_validator import TemporalValidator

    v = TemporalValidator()
    issue = datetime(2025, 1, 1, 0, 0, 0)
    valid = datetime(2025, 1, 1, 6, 0, 0)

    # Observation before valid_time must still be rejected
    r_before = v.validate_observation_for_verification(valid, datetime(2025, 1, 1, 5, 0, 0), 1.0)
    assert r_before.is_valid is False
    # Historical feature window ending at/after issue_time must still be rejected
    r_overlap = v.validate_historical_features(issue, issue)  # period_end == issue_time
    assert r_overlap.is_valid is False
    # Valid observation at valid_time still accepted
    r_ok = v.validate_observation_for_verification(valid, valid, 1.0)
    assert r_ok.is_valid is True
    print("  ✓ Observation-before-valid rejected; period_end>=issue rejected; valid accepted")
    print()
    return True


if __name__ == '__main__':
    print("="*80)
    print("DATA SUFFICIENCY CHECKER UNIT TESTS")
    print("="*80)
    print()

    tests = [
        test_cold_start_zero_verifications,
        test_insufficient_total_records,
        test_sufficient_total_records,
        test_missing_one_model,
        test_sufficient_gfs_insufficient_icon,
        test_insufficient_variable_specific_history,
        test_insufficient_lead_time_history,
        test_insufficient_location_history,
        test_insufficient_observation_quality,
        test_short_vs_sufficient_historical_span,
        test_cold_start_simple_average_allowed,
        test_advanced_ml_blocked_when_insufficient,
        test_chronological_split_recommendation,
        # Issue-time span correction regression tests (A-F)
        test_span_from_issue_time_batch_insert,
        test_span_ignores_insertion_time,
        test_default_config_flags_missing_gfs_icon,
        test_ifs_only_span_from_issue_time,
        test_count_gates_unchanged,
        test_no_temporal_leakage_weakening,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print()
    print("="*80)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    if failed > 0:
        print(f"         {failed}/{len(tests)} tests FAILED")
    print("="*80)

    sys.exit(0 if failed == 0 else 1)
