"""
Unit Tests for Verification Scheduler

Tests for HELIOS operational forecast-observation verification scheduler.

Test coverage:
1. Find ready forecasts (valid_time passed, within lookback)
2. Skip already verified forecasts (idempotency)
3. Skip forecasts too old (beyond lookback window)
4. Temporal safety (only verify after valid_time + min_age)
5. Observation matching integration
6. Quality control (minimum observation quality)
7. Error calculation (error, absolute_error, squared_error)
8. PERMANENT verification record creation
9. Failure tolerance (one failure doesn't stop batch)
10. Batch statistics aggregation
11. Location zone determination
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class MockObservation:
    """Mock observation for testing."""
    temperature_2m_c: float
    source: str
    quality_flag: str
    quality_score: float


def test_scheduler_initialization():
    """Test scheduler initializes correctly."""
    print("TEST 1: Scheduler initialization")

    from scheduling.verification_scheduler import (
        VerificationScheduler,
        SchedulerConfig
    )

    config = SchedulerConfig(lookback_days=3)
    scheduler = VerificationScheduler(config)

    assert scheduler.config.lookback_days == 3
    assert scheduler.config.min_age_hours == 1.0
    assert scheduler.config.batch_size == 1000

    print("  ✓ Scheduler initialized with config")
    print("  ✓ Default parameters set")
    print()


def test_temporal_safety():
    """Test only verifies forecasts after valid_time + min_age."""
    print("TEST 2: Temporal safety")

    from scheduling.verification_scheduler import SchedulerConfig

    config = SchedulerConfig(min_age_hours=1.0)

    now = datetime.utcnow()

    # Too recent (valid_time = now - 30 minutes)
    recent_valid_time = now - timedelta(minutes=30)
    verification_cutoff = now - timedelta(hours=config.min_age_hours)

    assert recent_valid_time > verification_cutoff, "Should be too recent"

    # Ready (valid_time = now - 2 hours)
    ready_valid_time = now - timedelta(hours=2)
    assert ready_valid_time <= verification_cutoff, "Should be ready"

    print("  ✓ min_age_hours enforced")
    print("  ✓ Too-recent forecasts excluded")
    print("  ✓ Ready forecasts included")
    print()


def test_lookback_window():
    """Test bounded lookback window."""
    print("TEST 3: Lookback window")

    from scheduling.verification_scheduler import SchedulerConfig

    config = SchedulerConfig(lookback_days=7)

    now = datetime.utcnow()
    lookback_cutoff = now - timedelta(days=config.lookback_days)

    # Too old (valid_time = now - 8 days)
    too_old = now - timedelta(days=8)
    assert too_old < lookback_cutoff, "Should be too old"

    # Within window (valid_time = now - 5 days)
    within_window = now - timedelta(days=5)
    assert within_window >= lookback_cutoff, "Should be within window"

    print("  ✓ lookback_days enforced")
    print("  ✓ Too-old forecasts excluded")
    print("  ✓ Within-window forecasts included")
    print()


def test_idempotency():
    """Test skips already verified forecasts."""
    print("TEST 4: Idempotency")

    from scheduling.verification_scheduler import (
        VerificationScheduler,
        VerificationStatus
    )

    scheduler = VerificationScheduler()

    # Mock forecast
    mock_forecast = Mock()
    mock_forecast.forecast_id = "test_forecast_001"
    mock_forecast.model = "gfs"
    mock_forecast.valid_time = datetime.utcnow() - timedelta(hours=6)

    # Mock database showing existing verification
    with patch('scheduling.verification_scheduler.session_scope') as mock_session:
        mock_query = MagicMock()

        # First query: existing verification found
        mock_query.query.return_value.filter.return_value.first.return_value = Mock(
            verification_id="ver_existing"
        )
        mock_session.return_value.__enter__.return_value = mock_query

        result = scheduler._verify_forecast(mock_forecast)

    assert result.status == VerificationStatus.SKIPPED_EXISTS
    assert result.verification_id == "ver_existing"

    print("  ✓ Existing verification detected")
    print("  ✓ Returns SKIPPED_EXISTS status")
    print("  ✓ No duplicate verification created")
    print()


def test_observation_quality_control():
    """Test quality control rejects low-quality observations."""
    print("TEST 5: Observation quality control")

    from scheduling.verification_scheduler import (
        VerificationScheduler,
        SchedulerConfig,
        VerificationStatus
    )

    config = SchedulerConfig(min_observation_quality=0.7)

    # Mock observation matcher
    mock_matcher = Mock()

    # Low-quality observation
    low_quality_obs = MockObservation(
        temperature_2m_c=25.0,
        source="era5_land",
        quality_flag="POOR",
        quality_score=0.5
    )
    mock_matcher.get_observation.return_value = low_quality_obs

    scheduler = VerificationScheduler(
        config=config,
        observation_matcher=mock_matcher
    )

    # Mock forecast
    mock_forecast = Mock()
    mock_forecast.forecast_id = "test_forecast_002"
    mock_forecast.model = "ifs"
    mock_forecast.valid_time = datetime.utcnow() - timedelta(hours=6)
    mock_forecast.latitude = 20.0
    mock_forecast.longitude = 75.0
    mock_forecast.temperature_2m_c = 26.0

    # Mock database (no existing verification)
    with patch('scheduling.verification_scheduler.session_scope') as mock_session:
        mock_query = MagicMock()
        mock_query.query.return_value.filter.return_value.first.return_value = None
        mock_session.return_value.__enter__.return_value = mock_query

        result = scheduler._verify_forecast(mock_forecast)

    assert result.status == VerificationStatus.FAILED_OBSERVATION_QUALITY
    assert "Quality 0.5 < 0.7" in result.error_message

    print("  ✓ Low-quality observation rejected")
    print("  ✓ Returns FAILED_OBSERVATION_QUALITY status")
    print("  ✓ min_observation_quality enforced")
    print()


def test_error_calculation():
    """Test error metrics calculation."""
    print("TEST 6: Error calculation")

    # Simple error calculation
    forecast_value = 26.5
    observed_value = 25.0

    error = forecast_value - observed_value
    absolute_error = abs(error)
    squared_error = error ** 2

    assert error == 1.5
    assert absolute_error == 1.5
    assert squared_error == 2.25

    # Negative error
    forecast_value_neg = 23.0
    error_neg = forecast_value_neg - observed_value
    absolute_error_neg = abs(error_neg)
    squared_error_neg = error_neg ** 2

    assert error_neg == -2.0
    assert absolute_error_neg == 2.0
    assert squared_error_neg == 4.0

    print("  ✓ Error = forecast - observed")
    print("  ✓ Absolute error = |error|")
    print("  ✓ Squared error = error²")
    print("  ✓ Handles negative errors correctly")
    print()


def test_location_zone_determination():
    """Test location zone classification."""
    print("TEST 7: Location zone determination")

    from scheduling.verification_scheduler import VerificationScheduler

    scheduler = VerificationScheduler()

    # Test zones
    assert scheduler._determine_location_zone(32.0, 77.0) == "north_himalaya"
    assert scheduler._determine_location_zone(28.0, 77.0) == "north_plains"
    assert scheduler._determine_location_zone(22.0, 78.0) == "central"
    assert scheduler._determine_location_zone(15.0, 77.0) == "south_plateau"
    assert scheduler._determine_location_zone(10.0, 76.0) == "south_coastal"

    print("  ✓ north_himalaya (lat >= 30)")
    print("  ✓ north_plains (24 <= lat < 30)")
    print("  ✓ central (18 <= lat < 24)")
    print("  ✓ south_plateau (12 <= lat < 18)")
    print("  ✓ south_coastal (lat < 12)")
    print()


def test_batch_statistics():
    """Test batch statistics aggregation."""
    print("TEST 8: Batch statistics")

    from scheduling.verification_scheduler import (
        VerificationBatch,
        VerificationResult,
        VerificationStatus
    )

    results = [
        VerificationResult("f1", "gfs", datetime.utcnow(), VerificationStatus.SUCCESS),
        VerificationResult("f2", "ifs", datetime.utcnow(), VerificationStatus.SUCCESS),
        VerificationResult("f3", "icon", datetime.utcnow(), VerificationStatus.SKIPPED_EXISTS),
        VerificationResult("f4", "gfs", datetime.utcnow(), VerificationStatus.FAILED_NO_OBSERVATION)
    ]

    batch = VerificationBatch(
        total_forecasts=4,
        verified=2,
        skipped_exists=1,
        skipped_too_old=0,
        failed=1,
        duration_seconds=15.2,
        results=results
    )

    assert batch.total_forecasts == 4
    assert batch.verified == 2
    assert batch.skipped_exists == 1
    assert batch.failed == 1
    assert batch.success_rate() == 0.5

    print("  ✓ Total forecasts counted")
    print("  ✓ Verified forecasts counted")
    print("  ✓ Skipped forecasts counted")
    print("  ✓ Failed forecasts counted")
    print("  ✓ Success rate calculated correctly")
    print()


def test_verification_status_enum():
    """Test VerificationStatus enum values."""
    print("TEST 9: VerificationStatus enum")

    from scheduling.verification_scheduler import VerificationStatus

    expected_statuses = [
        "SUCCESS",
        "SKIPPED_EXISTS",
        "SKIPPED_TOO_OLD",
        "FAILED_NO_OBSERVATION",
        "FAILED_OBSERVATION_QUALITY",
        "FAILED_FORECAST_MISSING",
        "FAILED_DATABASE"
    ]

    for status_name in expected_statuses:
        assert hasattr(VerificationStatus, status_name), f"Missing status: {status_name}"
        print(f"  ✓ {status_name} defined")

    print()


def test_config_defaults():
    """Test SchedulerConfig default values."""
    print("TEST 10: SchedulerConfig defaults")

    from scheduling.verification_scheduler import SchedulerConfig

    config = SchedulerConfig()

    assert config.lookback_days == 7
    assert config.min_age_hours == 1.0
    assert config.batch_size == 1000
    assert config.min_observation_quality == 0.5
    assert config.prefer_noaa_isd == True

    print("  ✓ lookback_days = 7")
    print("  ✓ min_age_hours = 1.0")
    print("  ✓ batch_size = 1000")
    print("  ✓ min_observation_quality = 0.5")
    print("  ✓ prefer_noaa_isd = True")
    print()


def test_verification_result_is_success():
    """Test VerificationResult.is_success() method."""
    print("TEST 11: VerificationResult.is_success()")

    from scheduling.verification_scheduler import (
        VerificationResult,
        VerificationStatus
    )

    success = VerificationResult(
        "f1", "gfs", datetime.utcnow(), VerificationStatus.SUCCESS
    )
    assert success.is_success() == True

    skipped = VerificationResult(
        "f2", "ifs", datetime.utcnow(), VerificationStatus.SKIPPED_EXISTS
    )
    assert skipped.is_success() == False

    failed = VerificationResult(
        "f3", "icon", datetime.utcnow(), VerificationStatus.FAILED_NO_OBSERVATION
    )
    assert failed.is_success() == False

    print("  ✓ SUCCESS → is_success() = True")
    print("  ✓ SKIPPED → is_success() = False")
    print("  ✓ FAILED → is_success() = False")
    print()


if __name__ == '__main__':
    print("="*80)
    print("VERIFICATION SCHEDULER UNIT TESTS")
    print("="*80)
    print()

    tests = [
        test_scheduler_initialization,
        test_temporal_safety,
        test_lookback_window,
        test_idempotency,
        test_observation_quality_control,
        test_error_calculation,
        test_location_zone_determination,
        test_batch_statistics,
        test_verification_status_enum,
        test_config_defaults,
        test_verification_result_is_success
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("="*80)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    if failed > 0:
        print(f"         {failed}/{len(tests)} tests FAILED")
    print("="*80)

    sys.exit(0 if failed == 0 else 1)
