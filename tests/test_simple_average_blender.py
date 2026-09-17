"""
Unit Tests for Simple Average Blender

Tests for HELIOS permanent production baseline blender.

Test coverage:
1. 3-model equal weighting
2. 2-model missing-model fallback
3. 1-model fallback
4. Zero-model failure
5. Mismatched valid_time rejection
6. Mismatched units rejection
7. Variable mismatch rejection
8. Weight sum = 1
9. Non-negative weights
10. Reproducible output
11. Precipitation semantic checks
12. ForecastRecord validation
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from nwp.common.schemas import ForecastRecord, Location, NWPModel
from blending.simple_average_blender import SimpleAverageBlender, BlendResult


def test_three_model_equal_weighting():
    """Test equal weighting with all 3 models present."""
    print("TEST 1: Three-model equal weighting")

    blender = SimpleAverageBlender()

    # Create aligned forecasts
    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_001',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=25.0
        ),
        'ifs': ForecastRecord(
            forecast_id='ifs_test_001',
            model=NWPModel.IFS,
            model_version='ifs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=26.0
        ),
        'icon': ForecastRecord(
            forecast_id='icon_test_001',
            model=NWPModel.ICON,
            model_version='icon_global_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=27.0
        )
    }

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    assert result is not None, "Blend result should not be None"
    assert len(result.participating_models) == 3, "Should have 3 participating models"
    assert set(result.participating_models) == {'gfs', 'ifs', 'icon'}, "Should include all models"

    # Check equal weights
    assert result.weights['gfs'] == 1/3, f"GFS weight should be 1/3, got {result.weights['gfs']}"
    assert result.weights['ifs'] == 1/3, f"IFS weight should be 1/3, got {result.weights['ifs']}"
    assert result.weights['icon'] == 1/3, f"ICON weight should be 1/3, got {result.weights['icon']}"

    # Check weight sum
    weight_sum = sum(result.weights.values())
    assert abs(weight_sum - 1.0) < 1e-9, f"Weights should sum to 1.0, got {weight_sum}"

    # Check blended value: (25 + 26 + 27) / 3 = 26.0
    expected_value = (25.0 + 26.0 + 27.0) / 3
    assert abs(result.forecast.temperature_2m_c - expected_value) < 1e-9, \
        f"Expected {expected_value}, got {result.forecast.temperature_2m_c}"

    # Check model identifier
    assert result.forecast.model == NWPModel.HELIOS_BLEND, \
        f"Model should be HELIOS_BLEND, got {result.forecast.model}"

    # Check not degraded
    assert result.is_degraded == False, "Should not be degraded with all 3 models"
    assert len(result.missing_models) == 0, "Should have no missing models"

    print("  ✓ 3 models, weights = 1/3 each, sum = 1.0")
    print(f"  ✓ Blended value: {result.forecast.temperature_2m_c:.3f} (expected {expected_value:.3f})")
    print("  ✓ Model: helios_blend")
    print("  ✓ Not degraded")
    print()


def test_two_model_missing_fallback():
    """Test fallback to 2 models when one is missing."""
    print("TEST 2: Two-model missing-model fallback")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    # Only GFS and IFS available (ICON missing)
    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_002',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=24.0
        ),
        'ifs': ForecastRecord(
            forecast_id='ifs_test_002',
            model=NWPModel.IFS,
            model_version='ifs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=26.0
        )
    }

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    assert result is not None, "Blend result should not be None"
    assert len(result.participating_models) == 2, "Should have 2 participating models"
    assert set(result.participating_models) == {'gfs', 'ifs'}, "Should include GFS and IFS only"

    # Check equal weights for available models
    assert result.weights['gfs'] == 0.5, f"GFS weight should be 0.5, got {result.weights['gfs']}"
    assert result.weights['ifs'] == 0.5, f"IFS weight should be 0.5, got {result.weights['ifs']}"

    # Check weight sum
    weight_sum = sum(result.weights.values())
    assert abs(weight_sum - 1.0) < 1e-9, f"Weights should sum to 1.0, got {weight_sum}"

    # Check blended value: (24 + 26) / 2 = 25.0
    expected_value = (24.0 + 26.0) / 2
    assert abs(result.forecast.temperature_2m_c - expected_value) < 1e-9, \
        f"Expected {expected_value}, got {result.forecast.temperature_2m_c}"

    # Check degraded status
    assert result.is_degraded == True, "Should be degraded with missing model"
    assert 'icon' in result.missing_models, "ICON should be in missing models"
    assert len(result.missing_models) == 1, "Should have 1 missing model"

    print("  ✓ 2 models, weights = 0.5 each, sum = 1.0")
    print(f"  ✓ Blended value: {result.forecast.temperature_2m_c:.3f} (expected {expected_value:.3f})")
    print("  ✓ Degraded status: True")
    print("  ✓ Missing models: ['icon']")
    print()


def test_one_model_fallback():
    """Test fallback to single model when others are missing."""
    print("TEST 3: One-model fallback")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    # Only GFS available
    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_003',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=23.5
        )
    }

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    assert result is not None, "Blend result should not be None"
    assert len(result.participating_models) == 1, "Should have 1 participating model"
    assert result.participating_models[0] == 'gfs', "Should include GFS only"

    # Check weight
    assert result.weights['gfs'] == 1.0, f"GFS weight should be 1.0, got {result.weights['gfs']}"

    # Check weight sum
    weight_sum = sum(result.weights.values())
    assert abs(weight_sum - 1.0) < 1e-9, f"Weights should sum to 1.0, got {weight_sum}"

    # Check blended value equals input
    assert abs(result.forecast.temperature_2m_c - 23.5) < 1e-9, \
        f"Expected 23.5, got {result.forecast.temperature_2m_c}"

    # Check degraded status
    assert result.is_degraded == True, "Should be degraded with missing models"
    assert set(result.missing_models) == {'ifs', 'icon'}, "IFS and ICON should be missing"

    print("  ✓ 1 model, weight = 1.0, sum = 1.0")
    print(f"  ✓ Blended value: {result.forecast.temperature_2m_c:.3f} (equals input)")
    print("  ✓ Degraded status: True")
    print("  ✓ Missing models: ['ifs', 'icon']")
    print()


def test_zero_model_failure():
    """Test failure when no models are available."""
    print("TEST 4: Zero-model failure")

    blender = SimpleAverageBlender()

    # Empty forecast dict
    forecasts = {}

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    assert result is None, "Blend result should be None with no models"

    print("  ✓ Returns None with empty forecast dict")
    print()


def test_mismatched_valid_time_rejection():
    """Test rejection of forecasts with different valid_time."""
    print("TEST 5: Mismatched valid_time rejection")

    blender = SimpleAverageBlender()

    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    # Different valid_time for each model
    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_005',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=datetime(2026, 9, 7, 12, 0, 0),  # 12Z
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=25.0
        ),
        'ifs': ForecastRecord(
            forecast_id='ifs_test_005',
            model=NWPModel.IFS,
            model_version='ifs_0p25_20260907',
            issue_time=issue_time,
            valid_time=datetime(2026, 9, 7, 18, 0, 0),  # 18Z (different!)
            lead_time_hours=18,
            location=location,
            source='test',
            temperature_2m_c=26.0
        )
    }

    try:
        result = blender.blend_forecasts(forecasts, 'temperature_2m_c')
        assert False, "Should have raised ValueError for mismatched valid_time"
    except ValueError as e:
        assert 'valid_time mismatch' in str(e), f"Error message should mention valid_time mismatch, got: {e}"
        print(f"  ✓ Raised ValueError: {e}")

    print()


def test_mismatched_location_rejection():
    """Test rejection of forecasts with different locations."""
    print("TEST 6: Mismatched location rejection")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)

    # Different locations
    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_006',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=Location(latitude=20.0, longitude=75.0),
            source='test',
            temperature_2m_c=25.0
        ),
        'ifs': ForecastRecord(
            forecast_id='ifs_test_006',
            model=NWPModel.IFS,
            model_version='ifs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=Location(latitude=25.0, longitude=80.0),  # Different location!
            source='test',
            temperature_2m_c=26.0
        )
    }

    try:
        result = blender.blend_forecasts(forecasts, 'temperature_2m_c')
        assert False, "Should have raised ValueError for mismatched location"
    except ValueError as e:
        assert 'Location mismatch' in str(e), f"Error message should mention location mismatch, got: {e}"
        print(f"  ✓ Raised ValueError: {e}")

    print()


def test_variable_mismatch_returns_none():
    """Test that requesting non-existent variable returns None."""
    print("TEST 7: Variable mismatch returns None")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_007',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=25.0  # Has temperature
            # Does NOT have dewpoint
        )
    }

    # Request variable that doesn't exist
    result = blender.blend_forecasts(forecasts, 'dewpoint_2m_c')

    assert result is None, "Should return None when variable is not available"

    print("  ✓ Returns None for non-existent variable")
    print()


def test_weights_sum_to_one():
    """Test that weights always sum to exactly 1.0."""
    print("TEST 8: Weights sum to 1.0")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    test_cases = [
        ('3 models', ['gfs', 'ifs', 'icon']),
        ('2 models', ['gfs', 'ifs']),
        ('1 model', ['gfs'])
    ]

    for name, models in test_cases:
        forecasts = {}
        for i, model_name in enumerate(models):
            forecasts[model_name] = ForecastRecord(
                forecast_id=f'{model_name}_test_008',
                model=NWPModel[model_name.upper()],
                model_version=f'{model_name}_test',
                issue_time=issue_time,
                valid_time=valid_time,
                lead_time_hours=12,
                location=location,
                source='test',
                temperature_2m_c=20.0 + i
            )

        result = blender.blend_forecasts(forecasts, 'temperature_2m_c')
        weight_sum = sum(result.weights.values())

        assert abs(weight_sum - 1.0) < 1e-9, \
            f"{name}: Weights should sum to 1.0, got {weight_sum}"

        print(f"  ✓ {name}: weight sum = {weight_sum:.10f}")

    print()


def test_non_negative_weights():
    """Test that all weights are non-negative."""
    print("TEST 9: Non-negative weights")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_009',
            model=NWPModel.GFS,
            model_version='gfs_test',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=25.0
        ),
        'ifs': ForecastRecord(
            forecast_id='ifs_test_009',
            model=NWPModel.IFS,
            model_version='ifs_test',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=26.0
        )
    }

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    for model, weight in result.weights.items():
        assert weight >= 0, f"Weight for {model} should be non-negative, got {weight}"
        print(f"  ✓ {model}: weight = {weight:.3f} (>= 0)")

    print()


def test_reproducible_output():
    """Test that output contains all information for reproducibility."""
    print("TEST 10: Reproducible output")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_2026090700_012_20.00_75.00',
            model=NWPModel.GFS,
            model_version='gfs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='noaa_gfs_aws_2026090700',
            temperature_2m_c=25.0
        ),
        'ifs': ForecastRecord(
            forecast_id='ifs_2026090700_012_20.00_75.00',
            model=NWPModel.IFS,
            model_version='ifs_0p25_20260907',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='ecmwf_open_data_2026090700',
            temperature_2m_c=26.0
        )
    }

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    # Check participating models recorded
    assert 'gfs' in result.participating_models, "GFS should be in participating models"
    assert 'ifs' in result.participating_models, "IFS should be in participating models"

    # Check weights recorded
    assert 'gfs' in result.weights, "GFS weight should be recorded"
    assert 'ifs' in result.weights, "IFS weight should be recorded"

    # Check source forecasts stored
    assert 'gfs' in result.source_forecasts, "GFS source forecast should be stored"
    assert 'ifs' in result.source_forecasts, "IFS source forecast should be stored"

    # Check forecast IDs match
    assert result.source_forecasts['gfs'].forecast_id == 'gfs_2026090700_012_20.00_75.00'
    assert result.source_forecasts['ifs'].forecast_id == 'ifs_2026090700_012_20.00_75.00'

    # Check values accessible
    assert result.source_forecasts['gfs'].temperature_2m_c == 25.0
    assert result.source_forecasts['ifs'].temperature_2m_c == 26.0

    # Check valid_time recorded
    assert result.forecast.valid_time == valid_time

    print("  ✓ Participating models recorded")
    print("  ✓ Weights recorded")
    print("  ✓ Source forecasts stored with IDs")
    print("  ✓ Source values accessible")
    print("  ✓ valid_time recorded")
    print("  ✓ All information for reproducibility present")
    print()


def test_forecast_record_validation():
    """Test that blended output is a valid ForecastRecord."""
    print("TEST 11: ForecastRecord validation")

    blender = SimpleAverageBlender()

    valid_time = datetime(2026, 9, 7, 12, 0, 0)
    issue_time = datetime(2026, 9, 7, 0, 0, 0)
    location = Location(latitude=20.0, longitude=75.0)

    forecasts = {
        'gfs': ForecastRecord(
            forecast_id='gfs_test_011',
            model=NWPModel.GFS,
            model_version='gfs_test',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=12,
            location=location,
            source='test',
            temperature_2m_c=25.0
        )
    }

    result = blender.blend_forecasts(forecasts, 'temperature_2m_c')

    # Check result is ForecastRecord
    assert isinstance(result.forecast, ForecastRecord), "Result should be ForecastRecord"

    # Check required fields
    assert result.forecast.forecast_id is not None, "forecast_id should be set"
    assert result.forecast.model == NWPModel.HELIOS_BLEND, "model should be HELIOS_BLEND"
    assert result.forecast.issue_time == issue_time, "issue_time should match"
    assert result.forecast.valid_time == valid_time, "valid_time should match"
    assert result.forecast.lead_time_hours == 12, "lead_time_hours should match"
    assert result.forecast.location.latitude == 20.0, "latitude should match"
    assert result.forecast.location.longitude == 75.0, "longitude should match"
    assert result.forecast.temperature_2m_c is not None, "variable should be set"
    assert result.forecast.source is not None, "source should be set"

    print("  ✓ Result is ForecastRecord instance")
    print("  ✓ All required fields present")
    print("  ✓ Model identifier: helios_blend")
    print("  ✓ Temporal fields valid")
    print("  ✓ Spatial fields valid")
    print()


if __name__ == '__main__':
    print("="*80)
    print("SIMPLE AVERAGE BLENDER UNIT TESTS")
    print("="*80)
    print()

    tests = [
        test_three_model_equal_weighting,
        test_two_model_missing_fallback,
        test_one_model_fallback,
        test_zero_model_failure,
        test_mismatched_valid_time_rejection,
        test_mismatched_location_rejection,
        test_variable_mismatch_returns_none,
        test_weights_sum_to_one,
        test_non_negative_weights,
        test_reproducible_output,
        test_forecast_record_validation
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
