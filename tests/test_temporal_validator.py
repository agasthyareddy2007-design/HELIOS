"""
Unit Tests for Temporal Validator

Tests for HELIOS temporal constraint enforcement to prevent information leakage.

Test coverage:
1. Forecast chronology (valid_time >= issue_time)
2. valid_time == issue_time (0-hour lead time, acceptable)
3. valid_time < issue_time (reject)
4. Negative lead time (reject)
5. Lead time consistency
6. Observation before valid_time (reject for verification)
7. Observation exactly at valid_time (accept)
8. Observation within tolerance (accept)
9. Observation beyond tolerance (reject)
10. Historical performance ending exactly at issue_time (reject)
11. Historical performance ending before issue_time (accept)
12. Future performance record (reject)
13. Exact forecast identity requirement (model + issue_time + valid_time + location + variable)
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_valid_chronology():
    """Test valid forecast chronology (valid_time >= issue_time)."""
    print("TEST 1: Valid forecast chronology")

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    # Normal case: valid_time > issue_time
    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 18, 0, 0)

    result = validator.validate_forecast_chronology(issue_time, valid_time)

    assert result.is_valid == True
    assert result.context['lead_time_hours'] == 6.0

    print("  ✓ valid_time > issue_time accepted")
    print("  ✓ Lead time calculated correctly")
    print()
    return True


def test_zero_hour_lead_time():
    """Test valid_time == issue_time (0-hour lead time, acceptable)."""
    print("TEST 2: Zero-hour lead time")

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    # valid_time == issue_time (0-hour analysis)
    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 12, 0, 0)

    result = validator.validate_forecast_chronology(issue_time, valid_time)

    assert result.is_valid == True
    assert result.context['lead_time_hours'] == 0.0

    print("  ✓ valid_time == issue_time accepted (0-hour lead time)")
    print("  ✓ Lead time = 0.0 hours")
    print()
    return True


def test_invalid_chronology():
    """Test invalid chronology (valid_time < issue_time, reject)."""
    print("TEST 3: Invalid chronology (valid_time < issue_time)")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    # valid_time < issue_time (INVALID)
    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 6, 0, 0)  # 6 hours BEFORE issue

    result = validator.validate_forecast_chronology(issue_time, valid_time)

    assert result.is_valid == False
    assert result.status == ValidationStatus.INVALID_CHRONOLOGY
    assert result.context['lead_time_seconds'] < 0

    print("  ✓ valid_time < issue_time rejected")
    print("  ✓ Status = INVALID_CHRONOLOGY")
    print("  ✓ Negative lead time detected")
    print()
    return True


def test_negative_lead_time():
    """Test negative lead time rejection."""
    print("TEST 4: Negative lead time")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 18, 0, 0)
    lead_time_hours = -6  # NEGATIVE

    result = validator.validate_lead_time(issue_time, valid_time, lead_time_hours)

    assert result.is_valid == False
    assert result.status == ValidationStatus.INVALID_NEGATIVE_LEAD_TIME

    print("  ✓ Negative lead_time_hours rejected")
    print("  ✓ Status = INVALID_NEGATIVE_LEAD_TIME")
    print()
    return True


def test_lead_time_consistency():
    """Test lead time consistency check."""
    print("TEST 5: Lead time consistency")

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 18, 0, 0)
    lead_time_hours = 6  # Consistent

    result = validator.validate_lead_time(issue_time, valid_time, lead_time_hours)

    assert result.is_valid == True

    # Inconsistent lead time
    lead_time_hours_wrong = 12  # Says 12h but actual is 6h

    result_wrong = validator.validate_lead_time(issue_time, valid_time, lead_time_hours_wrong)

    assert result_wrong.is_valid == False

    print("  ✓ Consistent lead_time accepted")
    print("  ✓ Inconsistent lead_time rejected")
    print()
    return True


def test_observation_before_valid_time():
    """Test observation before valid_time (reject for verification)."""
    print("TEST 6: Observation before valid_time")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    observation_time = datetime(2026, 9, 7, 11, 30, 0)  # BEFORE valid_time

    result = validator.validate_observation_for_verification(
        valid_time, observation_time
    )

    assert result.is_valid == False
    assert result.status == ValidationStatus.INVALID_OBSERVATION_BEFORE_VALID
    assert result.context['difference_hours'] < 0

    print("  ✓ observation_time < valid_time rejected")
    print("  ✓ Status = INVALID_OBSERVATION_BEFORE_VALID")
    print()
    return True


def test_observation_exactly_at_valid_time():
    """Test observation exactly at valid_time (accept)."""
    print("TEST 7: Observation exactly at valid_time")

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    observation_time = datetime(2026, 9, 7, 12, 0, 0)  # EXACTLY at valid_time

    result = validator.validate_observation_for_verification(
        valid_time, observation_time
    )

    assert result.is_valid == True
    assert result.context['difference_hours'] == 0.0

    print("  ✓ observation_time == valid_time accepted")
    print("  ✓ Difference = 0.0 hours")
    print()
    return True


def test_observation_within_tolerance():
    """Test observation within tolerance (accept)."""
    print("TEST 8: Observation within tolerance")

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    observation_time = datetime(2026, 9, 7, 12, 30, 0)  # 30 minutes after
    tolerance_hours = 1.0

    result = validator.validate_observation_for_verification(
        valid_time, observation_time, tolerance_hours
    )

    assert result.is_valid == True
    assert result.context['difference_hours'] == 0.5
    assert result.context['tolerance_hours'] == 1.0

    print("  ✓ observation_time within tolerance accepted")
    print("  ✓ 30 minutes after valid_time, tolerance=1h")
    print()
    return True


def test_observation_beyond_tolerance():
    """Test observation beyond tolerance (reject)."""
    print("TEST 9: Observation beyond tolerance")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    observation_time = datetime(2026, 9, 7, 14, 30, 0)  # 2.5 hours after
    tolerance_hours = 1.0

    result = validator.validate_observation_for_verification(
        valid_time, observation_time, tolerance_hours
    )

    assert result.is_valid == False
    assert result.status == ValidationStatus.INVALID_FUTURE_INFORMATION
    assert result.context['excess_hours'] == 1.5

    print("  ✓ observation_time beyond tolerance rejected")
    print("  ✓ Status = INVALID_FUTURE_INFORMATION")
    print("  ✓ Excess = 1.5 hours beyond tolerance")
    print()
    return True


def test_historical_performance_exactly_at_issue_time():
    """Test historical performance ending exactly at issue_time (reject)."""
    print("TEST 10: Historical performance ending exactly at issue_time")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    period_end = datetime(2026, 9, 7, 12, 0, 0)  # EXACTLY at issue_time

    result = validator.validate_historical_features(issue_time, period_end)

    assert result.is_valid == False
    assert result.status == ValidationStatus.INVALID_PERFORMANCE_OVERLAP
    assert "future information leakage" in result.error_message

    print("  ✓ period_end == issue_time rejected (must be strictly before)")
    print("  ✓ Status = INVALID_PERFORMANCE_OVERLAP")
    print("  ✓ Error message mentions future information leakage")
    print()
    return True


def test_historical_performance_before_issue_time():
    """Test historical performance ending before issue_time (accept)."""
    print("TEST 11: Historical performance ending before issue_time")

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    period_end = datetime(2026, 9, 7, 11, 0, 0)  # 1 hour BEFORE issue_time

    result = validator.validate_historical_features(issue_time, period_end)

    assert result.is_valid == True
    assert result.context['gap_hours'] == 1.0

    print("  ✓ period_end < issue_time accepted")
    print("  ✓ Gap = 1.0 hours")
    print()
    return True


def test_future_performance_record():
    """Test future performance record (reject)."""
    print("TEST 12: Future performance record")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    period_end = datetime(2026, 9, 7, 18, 0, 0)  # 6 hours AFTER issue_time

    result = validator.validate_historical_features(issue_time, period_end)

    assert result.is_valid == False
    assert result.status == ValidationStatus.INVALID_PERFORMANCE_OVERLAP
    assert result.context['overlap_hours'] == 6.0

    print("  ✓ period_end > issue_time rejected (future information)")
    print("  ✓ Status = INVALID_PERFORMANCE_OVERLAP")
    print("  ✓ Overlap = 6.0 hours into future")
    print()
    return True


def test_exact_forecast_identity_requirement():
    """Test exact forecast identity requirement."""
    print("TEST 13: Exact forecast identity requirement")

    from validation.temporal_validator import TemporalValidator, ValidationStatus

    validator = TemporalValidator()

    # Complete identity (valid)
    result_complete = validator.validate_forecast_identity(
        model="gfs",
        issue_time=datetime(2026, 9, 7, 12, 0, 0),
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        location=(20.0, 75.0),
        variable="temperature_2m_c"
    )

    assert result_complete.is_valid == True

    # Missing model (invalid)
    result_missing_model = validator.validate_forecast_identity(
        model=None,  # MISSING
        issue_time=datetime(2026, 9, 7, 12, 0, 0),
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        location=(20.0, 75.0),
        variable="temperature_2m_c"
    )

    assert result_missing_model.is_valid == False
    assert result_missing_model.status == ValidationStatus.INVALID_MISSING_IDENTITY
    assert 'model' in result_missing_model.context['missing_fields']

    # Missing issue_time (invalid)
    result_missing_issue = validator.validate_forecast_identity(
        model="gfs",
        issue_time=None,  # MISSING
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        location=(20.0, 75.0),
        variable="temperature_2m_c"
    )

    assert result_missing_issue.is_valid == False
    assert 'issue_time' in result_missing_issue.context['missing_fields']

    # Missing location (invalid)
    result_missing_location = validator.validate_forecast_identity(
        model="gfs",
        issue_time=datetime(2026, 9, 7, 12, 0, 0),
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        location=None,  # MISSING
        variable="temperature_2m_c"
    )

    assert result_missing_location.is_valid == False

    print("  ✓ Complete identity (model + issue_time + valid_time + location + variable) accepted")
    print("  ✓ Missing model rejected")
    print("  ✓ Missing issue_time rejected")
    print("  ✓ Missing location rejected")
    print("  ✓ Never retrieve forecast by valid_time alone")
    print()
    return True


if __name__ == '__main__':
    print("="*80)
    print("TEMPORAL VALIDATOR UNIT TESTS")
    print("="*80)
    print()

    tests = [
        test_valid_chronology,
        test_zero_hour_lead_time,
        test_invalid_chronology,
        test_negative_lead_time,
        test_lead_time_consistency,
        test_observation_before_valid_time,
        test_observation_exactly_at_valid_time,
        test_observation_within_tolerance,
        test_observation_beyond_tolerance,
        test_historical_performance_exactly_at_issue_time,
        test_historical_performance_before_issue_time,
        test_future_performance_record,
        test_exact_forecast_identity_requirement
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
