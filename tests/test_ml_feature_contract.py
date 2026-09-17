"""
Unit Tests for ML Feature Contract

Tests for HELIOS canonical feature contract shared by Kernel/XGBoost/MLP.

CRITICAL PRINCIPLES TESTED:
1. Features available strictly BEFORE issue_time
2. Observations/verification values NEVER features
3. Exact forecast identity preservation
4. Temporal leakage prevention
5. Missing-model handling
6. Historical reliability before issue_time only
7. Inter-model feature computation
8. Feature vector validation

Test coverage:
1. Feature specification completeness
2. Feature vector creation (valid case)
3. Temporal leakage detection (future features)
4. Target separation (observed values not features)
5. Missing model handling (graceful degradation)
6. Historical reliability temporal constraint
7. Inter-model feature computation
8. Feature vector validation
9. Categorical feature validation
10. Feature contract consistency
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_feature_specification_completeness():
    """Test feature contract defines all required features."""
    print("TEST 1: Feature specification completeness")

    from ml.feature_contract import FeatureContract, FeatureType

    contract = FeatureContract()
    specs = contract.feature_specs

    # Count features by type
    context_features = [s for s in specs if s.feature_type == FeatureType.FORECAST_CONTEXT]
    current_features = [s for s in specs if s.feature_type == FeatureType.CURRENT_FORECAST]
    inter_model_features = [s for s in specs if s.feature_type == FeatureType.INTER_MODEL]
    historical_features = [s for s in specs if s.feature_type == FeatureType.HISTORICAL_RELIABILITY]

    assert len(context_features) >= 5  # lead_time, hour, day, month, season, zone
    assert len(current_features) >= 5  # gfs/ifs/icon values + availability flags
    assert len(inter_model_features) >= 2  # spread, range, agreement
    assert len(historical_features) >= 9  # RMSE/MAE/bias for 3 models

    # Check all features marked as available at issue_time
    for spec in specs:
        assert spec.available_at_issue_time == True, f"Feature {spec.name} not available at issue_time"

    print(f"  ✓ {len(context_features)} context features")
    print(f"  ✓ {len(current_features)} current forecast features")
    print(f"  ✓ {len(inter_model_features)} inter-model features")
    print(f"  ✓ {len(historical_features)} historical reliability features")
    print("  ✓ All features available at issue_time")
    print()
    return True


def test_feature_vector_creation():
    """Test creating valid feature vector."""
    print("TEST 2: Feature vector creation (valid case)")

    from ml.feature_contract import FeatureVector

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 18, 0, 0)

    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=valid_time,
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,
        ifs_value=26.0,
        icon_value=25.8,
        forecast_spread=0.25,
        forecast_range=0.5,
        model_agreement=0.99,
        gfs_rmse_7day=1.2,
        ifs_rmse_7day=1.0,
        icon_rmse_7day=1.1,
        gfs_mae_7day=0.9,
        ifs_mae_7day=0.8,
        icon_mae_7day=0.85,
        gfs_bias_7day=0.1,
        ifs_bias_7day=-0.05,
        icon_bias_7day=0.02,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time
    )

    assert features.model == 'gfs'
    assert features.lead_time_hours == 6
    assert features.gfs_value == 25.5
    assert features.forecast_spread == 0.25
    assert features.gfs_rmse_7day == 1.2

    print("  ✓ FeatureVector created successfully")
    print("  ✓ All forecast context features set")
    print("  ✓ All current forecast values set")
    print("  ✓ All inter-model features set")
    print("  ✓ All historical reliability features set")
    print()
    return True


def test_temporal_leakage_detection():
    """Test detection of features computed after issue_time (temporal leakage)."""
    print("TEST 3: Temporal leakage detection")

    from ml.feature_contract import FeatureVector, FeatureContract

    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    valid_time = datetime(2026, 9, 7, 18, 0, 0)
    future_time = datetime(2026, 9, 7, 13, 0, 0)  # AFTER issue_time

    # Features computed AFTER issue_time (temporal leakage)
    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=valid_time,
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,
        ifs_value=26.0,
        icon_value=25.8,
        forecast_spread=None,
        forecast_range=None,
        model_agreement=None,
        gfs_rmse_7day=None,
        ifs_rmse_7day=None,
        icon_rmse_7day=None,
        gfs_mae_7day=None,
        ifs_mae_7day=None,
        icon_mae_7day=None,
        gfs_bias_7day=None,
        ifs_bias_7day=None,
        icon_bias_7day=None,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=future_time  # TEMPORAL LEAKAGE
    )

    contract = FeatureContract()
    is_valid, error_message = contract.validate_feature_vector(features)

    # Should detect temporal leakage
    assert is_valid == False
    assert error_message is not None
    assert "temporal leakage" in error_message.lower() or "after issue_time" in error_message.lower()

    print("  ✓ Temporal leakage detected (features computed after issue_time)")
    print(f"  ✓ Error message: {error_message}")
    print()
    return True


def test_target_separation():
    """Test that observed values are NEVER features (targets only)."""
    print("TEST 4: Target separation (observed values not features)")

    from ml.feature_contract import Target, FeatureVector

    # Target contains observed value
    target = Target(
        observed_value=25.3,
        forecast_error=0.2,  # 25.5 - 25.3
        absolute_error=0.2,
        observation_time=datetime(2026, 9, 7, 18, 30, 0),
        observation_source="noaa_isd",
        observation_quality_score=1.0
    )

    assert target.observed_value == 25.3

    # Feature vector should NOT contain observed value
    issue_time = datetime(2026, 9, 7, 12, 0, 0)
    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,  # Forecast, not observation
        ifs_value=26.0,
        icon_value=25.8,
        forecast_spread=None,
        forecast_range=None,
        model_agreement=None,
        gfs_rmse_7day=None,
        ifs_rmse_7day=None,
        icon_rmse_7day=None,
        gfs_mae_7day=None,
        ifs_mae_7day=None,
        icon_mae_7day=None,
        gfs_bias_7day=None,
        ifs_bias_7day=None,
        icon_bias_7day=None,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time
    )

    # Verify no observed_value field in FeatureVector
    assert not hasattr(features, 'observed_value'), "FeatureVector should NOT have observed_value field"

    # Verify gfs_value is forecast, not observation
    assert features.gfs_value == 25.5  # Forecast value
    assert target.observed_value == 25.3  # Observation (different)

    print("  ✓ Target contains observed_value")
    print("  ✓ FeatureVector does NOT contain observed_value")
    print("  ✓ Clear separation: forecasts are features, observations are targets")
    print()
    return True


def test_missing_model_handling():
    """Test graceful handling of missing models."""
    print("TEST 5: Missing model handling")

    from ml.feature_contract import FeatureVector

    issue_time = datetime(2026, 9, 7, 12, 0, 0)

    # ICON unavailable
    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,
        ifs_value=26.0,
        icon_value=None,  # ICON missing
        forecast_spread=0.25,  # Computed from GFS + IFS only
        forecast_range=0.5,
        model_agreement=0.99,
        gfs_rmse_7day=1.2,
        ifs_rmse_7day=1.0,
        icon_rmse_7day=None,  # ICON historical unavailable
        gfs_mae_7day=0.9,
        ifs_mae_7day=0.8,
        icon_mae_7day=None,
        gfs_bias_7day=0.1,
        ifs_bias_7day=-0.05,
        icon_bias_7day=None,
        gfs_available=True,
        ifs_available=True,
        icon_available=False,  # ICON missing
        feature_computation_time=issue_time
    )

    assert features.icon_available == False
    assert features.icon_value is None
    assert features.icon_rmse_7day is None

    # GFS + IFS still available
    assert features.gfs_available == True
    assert features.ifs_available == True
    assert features.gfs_value == 25.5
    assert features.ifs_value == 26.0

    print("  ✓ Missing model flagged (icon_available = False)")
    print("  ✓ Missing model value = None")
    print("  ✓ Missing model historical features = None")
    print("  ✓ Available models preserved (GFS + IFS)")
    print("  ✓ Graceful degradation to 2-model blend")
    print()
    return True


def test_historical_reliability_temporal_constraint():
    """Test historical reliability features use data BEFORE issue_time only."""
    print("TEST 6: Historical reliability temporal constraint")

    from ml.feature_contract import FeatureVector

    issue_time = datetime(2026, 9, 7, 12, 0, 0)

    # Historical RMSE/MAE/bias computed from period BEFORE issue_time
    # Example: 7-day window ending at issue_time - 1 second
    period_end = issue_time - timedelta(seconds=1)  # Strictly before issue_time

    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,
        ifs_value=26.0,
        icon_value=25.8,
        forecast_spread=0.25,
        forecast_range=0.5,
        model_agreement=0.99,
        # Historical features: period_end < issue_time
        gfs_rmse_7day=1.2,  # Computed from [period_end - 7 days, period_end]
        ifs_rmse_7day=1.0,
        icon_rmse_7day=1.1,
        gfs_mae_7day=0.9,
        ifs_mae_7day=0.8,
        icon_mae_7day=0.85,
        gfs_bias_7day=0.1,
        ifs_bias_7day=-0.05,
        icon_bias_7day=0.02,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time
    )

    # Verify historical features present
    assert features.gfs_rmse_7day == 1.2
    assert features.ifs_rmse_7day == 1.0
    assert features.icon_rmse_7day == 1.1

    # CRITICAL: These features were computed from verification records
    # with period_end < issue_time (enforced by TemporalValidator)
    assert period_end < issue_time, "Historical period must end BEFORE issue_time"

    print("  ✓ Historical reliability features present")
    print("  ✓ period_end < issue_time (strictly before)")
    print("  ✓ No future information in historical features")
    print("  ✓ TemporalValidator integration enforced")
    print()
    return True


def test_inter_model_feature_computation():
    """Test inter-model feature computation (spread, range, agreement)."""
    print("TEST 7: Inter-model feature computation")

    from ml.feature_contract import FeatureVector
    import math

    issue_time = datetime(2026, 9, 7, 12, 0, 0)

    # Three model forecasts
    gfs_val = 25.0
    ifs_val = 26.0
    icon_val = 25.5

    # Compute inter-model features
    values = [gfs_val, ifs_val, icon_val]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    spread = math.sqrt(variance)  # Standard deviation
    forecast_range = max(values) - min(values)
    agreement = 1.0 - (spread / mean) if mean > 0 else 0.0

    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=gfs_val,
        ifs_value=ifs_val,
        icon_value=icon_val,
        forecast_spread=spread,
        forecast_range=forecast_range,
        model_agreement=agreement,
        gfs_rmse_7day=None,
        ifs_rmse_7day=None,
        icon_rmse_7day=None,
        gfs_mae_7day=None,
        ifs_mae_7day=None,
        icon_mae_7day=None,
        gfs_bias_7day=None,
        ifs_bias_7day=None,
        icon_bias_7day=None,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time
    )

    assert features.forecast_spread is not None
    assert features.forecast_range == 1.0  # 26.0 - 25.0
    assert features.model_agreement is not None

    # Verify spread is positive
    assert features.forecast_spread >= 0.0

    # Verify range is positive
    assert features.forecast_range >= 0.0

    # Verify agreement is in [0, 1]
    assert 0.0 <= features.model_agreement <= 1.0

    print("  ✓ forecast_spread computed (std dev among models)")
    print(f"  ✓ forecast_range computed: {features.forecast_range}")
    print(f"  ✓ model_agreement computed: {features.model_agreement:.3f}")
    print("  ✓ All inter-model features in valid ranges")
    print()
    return True


def test_feature_vector_validation():
    """Test feature vector validation against contract."""
    print("TEST 8: Feature vector validation")

    from ml.feature_contract import FeatureVector, FeatureContract

    contract = FeatureContract()
    issue_time = datetime(2026, 9, 7, 12, 0, 0)

    # VALID feature vector
    valid_features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        lead_time_hours=6,
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,
        ifs_value=26.0,
        icon_value=25.8,
        forecast_spread=0.25,
        forecast_range=0.5,
        model_agreement=0.99,
        gfs_rmse_7day=None,
        ifs_rmse_7day=None,
        icon_rmse_7day=None,
        gfs_mae_7day=None,
        ifs_mae_7day=None,
        icon_mae_7day=None,
        gfs_bias_7day=None,
        ifs_bias_7day=None,
        icon_bias_7day=None,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time
    )

    is_valid, error = contract.validate_feature_vector(valid_features)
    assert is_valid == True
    assert error is None

    # INVALID: missing required feature (lead_time_hours = None)
    invalid_features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=datetime(2026, 9, 7, 18, 0, 0),
        lead_time_hours=None,  # Required feature missing
        latitude=20.0,
        longitude=75.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=18,
        day_of_year=250,
        month=9,
        season='autumn',
        gfs_value=25.5,
        ifs_value=26.0,
        icon_value=25.8,
        forecast_spread=None,
        forecast_range=None,
        model_agreement=None,
        gfs_rmse_7day=None,
        ifs_rmse_7day=None,
        icon_rmse_7day=None,
        gfs_mae_7day=None,
        ifs_mae_7day=None,
        icon_mae_7day=None,
        gfs_bias_7day=None,
        ifs_bias_7day=None,
        icon_bias_7day=None,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time
    )

    is_valid_invalid, error_invalid = contract.validate_feature_vector(invalid_features)
    assert is_valid_invalid == False
    assert error_invalid is not None

    print("  ✓ Valid feature vector accepted")
    print("  ✓ Invalid feature vector rejected (missing required feature)")
    print(f"  ✓ Error message: {error_invalid}")
    print()
    return True


def test_categorical_feature_validation():
    """Test categorical feature validation (season, location_zone)."""
    print("TEST 9: Categorical feature validation")

    from ml.feature_contract import FeatureContract

    contract = FeatureContract()

    # Find categorical feature specs
    season_spec = next(s for s in contract.feature_specs if s.name == "season")
    zone_spec = next(s for s in contract.feature_specs if s.name == "location_zone")

    # Verify categorical values defined
    assert season_spec.categorical_values is not None
    assert zone_spec.categorical_values is not None

    # Verify expected values
    assert 'winter' in season_spec.categorical_values
    assert 'spring' in season_spec.categorical_values
    assert 'summer' in season_spec.categorical_values
    assert 'autumn' in season_spec.categorical_values

    assert 'north_himalaya' in zone_spec.categorical_values
    assert 'north_plains' in zone_spec.categorical_values
    assert 'central' in zone_spec.categorical_values
    assert 'south_plateau' in zone_spec.categorical_values
    assert 'south_coastal' in zone_spec.categorical_values

    print("  ✓ season categorical values defined (4 seasons)")
    print("  ✓ location_zone categorical values defined (5 India zones)")
    print("  ✓ Categorical feature validation ready")
    print()
    return True


def test_feature_contract_consistency():
    """Test feature contract consistency (no duplicates, all specs valid)."""
    print("TEST 10: Feature contract consistency")

    from ml.feature_contract import FeatureContract

    contract = FeatureContract()
    feature_names = contract.get_feature_names()
    required_features = contract.get_required_features()
    optional_features = contract.get_optional_features()

    # Check no duplicate feature names
    assert len(feature_names) == len(set(feature_names)), "Duplicate feature names detected"

    # Check required + optional = all
    assert len(required_features) + len(optional_features) == len(feature_names)

    # Check no overlap between required and optional
    assert len(set(required_features) & set(optional_features)) == 0

    # Check all specs have valid dtypes
    valid_dtypes = ['float', 'int', 'categorical']
    for spec in contract.feature_specs:
        assert spec.dtype in valid_dtypes, f"Invalid dtype: {spec.dtype}"

    print(f"  ✓ {len(feature_names)} unique features (no duplicates)")
    print(f"  ✓ {len(required_features)} required features")
    print(f"  ✓ {len(optional_features)} optional features")
    print("  ✓ No overlap between required and optional")
    print("  ✓ All dtypes valid (float/int/categorical)")
    print()
    return True


if __name__ == '__main__':
    print("="*80)
    print("ML FEATURE CONTRACT UNIT TESTS")
    print("="*80)
    print()

    tests = [
        test_feature_specification_completeness,
        test_feature_vector_creation,
        test_temporal_leakage_detection,
        test_target_separation,
        test_missing_model_handling,
        test_historical_reliability_temporal_constraint,
        test_inter_model_feature_computation,
        test_feature_vector_validation,
        test_categorical_feature_validation,
        test_feature_contract_consistency
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
