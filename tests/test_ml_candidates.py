"""
HELIOS ML Candidates Tests

Comprehensive tests for Kernel Regression, XGBoost, and MLP candidates.

Test coverage:
1. Candidate instantiation
2. Feature contract compatibility
3. Prediction interface compatibility
4. Missing-model handling
5. Zero/near-zero error protection
6. NaN/Inf protection
7. AS-OF leakage prevention (critical temporal safety)
8. Current NWP forecast at issue_time IS permitted
9. Future verification cannot enter historical features
10. Weight normalization (sum to 1.0)
11. Training/evaluation on synthetic data
12. Reliability → weights conversion
"""

import numpy as np
from datetime import datetime, timedelta
from typing import List

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import FeatureVector, Target, TrainingSample, FeatureContract
from ml.candidate_interface import CandidateType
from ml.kernel_candidate import KernelRegressionCandidate, KernelConfig
from ml.xgboost_candidate import XGBoostCandidate, XGBoostConfig
from ml.mlp_candidate import MLPCandidate, MLPConfig


# Fixtures (no pytest required)

import pytest
@pytest.fixture
def feature_contract():
    """Feature contract instance."""
    return FeatureContract()


@pytest.fixture
def synthetic_training_samples():
    """Generate synthetic training samples for testing."""
    samples = []
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    for i in range(100):
        issue_time = base_time + timedelta(hours=i*6)
        valid_time = issue_time + timedelta(hours=24)

        # Rotate through models
        model = ['gfs', 'ifs', 'icon'][i % 3]

        features = FeatureVector(
            model=model,
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=24,
            latitude=20.0,
            longitude=77.0,
            location_zone='central',
            variable='temperature_2m_c',
            hour_of_day=0,
            day_of_year=1 + i % 365,
            month=1 + (i // 30) % 12,
            season='winter',
            gfs_value=25.0 + np.random.randn(),
            ifs_value=25.5 + np.random.randn(),
            icon_value=24.8 + np.random.randn(),
            forecast_spread=0.5,
            forecast_range=0.7,
            model_agreement=0.95,
            gfs_rmse_7day=1.2,
            ifs_rmse_7day=1.1,
            icon_rmse_7day=1.3,
            gfs_mae_7day=0.9,
            ifs_mae_7day=0.8,
            icon_mae_7day=1.0,
            gfs_bias_7day=0.1,
            ifs_bias_7day=-0.05,
            icon_bias_7day=0.15,
            gfs_available=True,
            ifs_available=True,
            icon_available=True,
            feature_computation_time=issue_time
        )

        # Synthetic observation
        observed_value = 25.0 + np.random.randn()
        forecast_value = features.gfs_value if model == 'gfs' else (
            features.ifs_value if model == 'ifs' else features.icon_value
        )

        target = Target(
            observed_value=observed_value,
            forecast_error=forecast_value - observed_value,
            absolute_error=abs(forecast_value - observed_value),
            observation_time=valid_time + timedelta(hours=1),
            observation_source='noaa_isd',
            observation_quality_score=1.0
        )

        sample = TrainingSample(
            features=features,
            target=target,
            verification_id=f'ver_{i}',
            verified_at=valid_time + timedelta(hours=2)
        )

        samples.append(sample)

    return samples


# Test 1: Candidate instantiation

def test_kernel_instantiation(feature_contract):
    """Test Kernel Regression candidate instantiation."""
    config = KernelConfig(n_neighbors=30, bandwidth=1.0)
    candidate = KernelRegressionCandidate(feature_contract, config)

    assert candidate.candidate_type == CandidateType.KERNEL_REGRESSION
    assert candidate.is_trained is False
    assert candidate.config.n_neighbors == 30


def test_xgboost_instantiation(feature_contract):
    """Test XGBoost candidate instantiation."""
    config = XGBoostConfig(n_estimators=50, max_depth=4)
    candidate = XGBoostCandidate(feature_contract, config)

    assert candidate.candidate_type == CandidateType.XGBOOST
    assert candidate.is_trained is False
    assert candidate.config.n_estimators == 50


def test_mlp_instantiation(feature_contract):
    """Test MLP candidate instantiation."""
    config = MLPConfig(hidden_layers=[32, 16], n_epochs=10)
    candidate = MLPCandidate(feature_contract, config)

    assert candidate.candidate_type == CandidateType.MLP
    assert candidate.is_trained is False
    assert candidate.config.hidden_layers == [32, 16]


# Test 2: Feature contract compatibility

def test_kernel_feature_contract_compatibility(feature_contract, synthetic_training_samples):
    """Test Kernel Regression uses canonical feature contract."""
    candidate = KernelRegressionCandidate(feature_contract)

    # Train
    metadata = candidate.train(synthetic_training_samples[:80])

    assert metadata.feature_contract_version == "1.0.0"
    assert candidate.preprocessor.is_fitted

    # Check feature dimensions
    n_features = candidate.preprocessor.stats.n_total
    assert n_features > 0  # Should have features
    assert candidate.X_train.shape[1] == n_features


def test_xgboost_feature_contract_compatibility(feature_contract, synthetic_training_samples):
    """Test XGBoost uses canonical feature contract."""
    config = XGBoostConfig(n_estimators=10)  # Small for fast test
    candidate = XGBoostCandidate(feature_contract, config)

    # Train
    metadata = candidate.train(synthetic_training_samples[:80])

    assert metadata.feature_contract_version == "1.0.0"
    assert candidate.preprocessor.is_fitted


def test_mlp_feature_contract_compatibility(feature_contract, synthetic_training_samples):
    """Test MLP uses canonical feature contract."""
    config = MLPConfig(hidden_layers=[16], n_epochs=5)  # Small for fast test
    candidate = MLPCandidate(feature_contract, config)

    # Train
    metadata = candidate.train(synthetic_training_samples[:80])

    assert metadata.feature_contract_version == "1.0.0"
    assert candidate.preprocessor.is_fitted


# Test 3: Prediction interface compatibility

def test_kernel_prediction_interface(feature_contract, synthetic_training_samples):
    """Test Kernel Regression prediction interface."""
    candidate = KernelRegressionCandidate(feature_contract)
    candidate.train(synthetic_training_samples[:80])

    test_features = synthetic_training_samples[80].features

    # Predict reliability
    reliability = candidate.predict_reliability(test_features)

    assert 'gfs' in reliability
    assert 'ifs' in reliability
    assert 'icon' in reliability

    # Check ReliabilityPrediction structure
    assert reliability['gfs'].model == 'gfs'
    assert reliability['gfs'].expected_absolute_error > 0
    assert reliability['gfs'].expected_squared_error > 0

    # Get weights
    weights = candidate.get_weights(test_features)

    assert abs(weights.gfs_weight + weights.ifs_weight + weights.icon_weight - 1.0) < 1e-6


def test_xgboost_prediction_interface(feature_contract, synthetic_training_samples):
    """Test XGBoost prediction interface."""
    config = XGBoostConfig(n_estimators=10)
    candidate = XGBoostCandidate(feature_contract, config)
    candidate.train(synthetic_training_samples[:80])

    test_features = synthetic_training_samples[80].features

    # Predict reliability
    reliability = candidate.predict_reliability(test_features)

    assert 'gfs' in reliability
    assert 'ifs' in reliability
    assert 'icon' in reliability

    # Get weights
    weights = candidate.get_weights(test_features)

    assert abs(weights.gfs_weight + weights.ifs_weight + weights.icon_weight - 1.0) < 1e-6


def test_mlp_prediction_interface(feature_contract, synthetic_training_samples):
    """Test MLP prediction interface."""
    config = MLPConfig(hidden_layers=[16], n_epochs=5)
    candidate = MLPCandidate(feature_contract, config)
    candidate.train(synthetic_training_samples[:80])

    test_features = synthetic_training_samples[80].features

    # Predict reliability
    reliability = candidate.predict_reliability(test_features)

    assert 'gfs' in reliability
    assert 'ifs' in reliability
    assert 'icon' in reliability

    # Get weights
    weights = candidate.get_weights(test_features)

    assert abs(weights.gfs_weight + weights.ifs_weight + weights.icon_weight - 1.0) < 1e-6


# Test 4: Missing-model handling

def test_missing_model_handling(feature_contract, synthetic_training_samples):
    """Test graceful degradation when models are missing."""
    candidate = KernelRegressionCandidate(feature_contract)
    candidate.train(synthetic_training_samples[:80])

    # Create test features with one model missing
    test_features = synthetic_training_samples[80].features
    test_features.icon_available = False
    test_features.icon_value = None

    weights = candidate.get_weights(test_features)

    # ICON should have zero weight
    assert weights.icon_weight == 0.0
    assert weights.icon_available is False

    # GFS + IFS should sum to 1.0
    assert abs(weights.gfs_weight + weights.ifs_weight - 1.0) < 1e-6


# Test 5: Zero/near-zero error protection

def test_zero_error_protection(feature_contract):
    """Test protection against zero/near-zero expected errors."""
    candidate = KernelRegressionCandidate(feature_contract)

    # Create mock training samples with zero errors
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    samples = []

    for i in range(20):
        issue_time = base_time + timedelta(hours=i*6)
        valid_time = issue_time + timedelta(hours=24)

        features = FeatureVector(
            model='gfs',
            issue_time=issue_time,
            valid_time=valid_time,
            lead_time_hours=24,
            latitude=20.0,
            longitude=77.0,
            location_zone='central',
            variable='temperature_2m_c',
            hour_of_day=0,
            day_of_year=1,
            month=1,
            season='winter',
            gfs_value=25.0,
            ifs_value=25.0,
            icon_value=25.0,
            forecast_spread=0.0,
            forecast_range=0.0,
            model_agreement=1.0,
            gfs_rmse_7day=0.0,  # Zero historical error
            ifs_rmse_7day=0.0,
            icon_rmse_7day=0.0,
            gfs_mae_7day=0.0,
            ifs_mae_7day=0.0,
            icon_mae_7day=0.0,
            gfs_bias_7day=0.0,
            ifs_bias_7day=0.0,
            icon_bias_7day=0.0,
            gfs_available=True,
            ifs_available=True,
            icon_available=True,
            feature_computation_time=issue_time
        )

        target = Target(
            observed_value=25.0,
            forecast_error=0.0,  # Zero error
            absolute_error=0.0,
            observation_time=valid_time + timedelta(hours=1),
            observation_source='noaa_isd',
            observation_quality_score=1.0
        )

        samples.append(TrainingSample(
            features=features,
            target=target,
            verification_id=f'ver_{i}',
            verified_at=valid_time + timedelta(hours=2)
        ))

    candidate.train(samples)

    # Predict weights (should not crash on zero errors)
    test_features = samples[0].features
    weights = candidate.get_weights(test_features, epsilon=0.001)

    # Weights should still be valid
    assert weights.gfs_weight >= 0
    assert weights.ifs_weight >= 0
    assert weights.icon_weight >= 0
    assert abs(weights.gfs_weight + weights.ifs_weight + weights.icon_weight - 1.0) < 1e-6


# Test 6: NaN/Inf protection

def test_nan_inf_protection(feature_contract, synthetic_training_samples):
    """Test protection against NaN/Inf in features."""
    candidate = KernelRegressionCandidate(feature_contract)
    candidate.train(synthetic_training_samples[:80])

    # Create test features with NaN
    test_features = synthetic_training_samples[80].features
    test_features.gfs_rmse_7day = None  # Missing historical feature
    test_features.forecast_spread = None

    # Should not crash
    weights = candidate.get_weights(test_features)

    assert not np.isnan(weights.gfs_weight)
    assert not np.isnan(weights.ifs_weight)
    assert not np.isnan(weights.icon_weight)
    assert not np.isinf(weights.gfs_weight)


# Test 7: AS-OF leakage prevention (CRITICAL)

def test_as_of_leakage_prevention(feature_contract):
    """
    Test AS-OF leakage prevention.

    CRITICAL: Verification at or after issue_time cannot enter historical features.
    Historical features must use period_end < issue_time (strictly before).
    """
    candidate = KernelRegressionCandidate(feature_contract)

    base_time = datetime(2024, 1, 1, 0, 0, 0)
    issue_time = base_time + timedelta(days=7)

    # VALID: Historical features end BEFORE issue_time
    valid_features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=issue_time + timedelta(hours=24),
        lead_time_hours=24,
        latitude=20.0,
        longitude=77.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=0,
        day_of_year=7,
        month=1,
        season='winter',
        gfs_value=25.0,
        ifs_value=25.0,
        icon_value=25.0,
        forecast_spread=0.3,
        forecast_range=0.5,
        model_agreement=0.9,
        gfs_rmse_7day=1.2,  # Computed from data ending BEFORE issue_time
        ifs_rmse_7day=1.1,
        icon_rmse_7day=1.3,
        gfs_mae_7day=0.9,
        ifs_mae_7day=0.8,
        icon_mae_7day=1.0,
        gfs_bias_7day=0.1,
        ifs_bias_7day=-0.05,
        icon_bias_7day=0.15,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time  # Computed AT issue_time
    )

    is_valid, error_msg = feature_contract.validate_feature_vector(valid_features)
    assert is_valid, f"Valid features rejected: {error_msg}"

    # INVALID: Features computed AFTER issue_time (temporal leakage)
    invalid_features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=issue_time + timedelta(hours=24),
        lead_time_hours=24,
        latitude=20.0,
        longitude=77.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=0,
        day_of_year=7,
        month=1,
        season='winter',
        gfs_value=25.0,
        ifs_value=25.0,
        icon_value=25.0,
        forecast_spread=0.3,
        forecast_range=0.5,
        model_agreement=0.9,
        gfs_rmse_7day=1.2,
        ifs_rmse_7day=1.1,
        icon_rmse_7day=1.3,
        gfs_mae_7day=0.9,
        ifs_mae_7day=0.8,
        icon_mae_7day=1.0,
        gfs_bias_7day=0.1,
        ifs_bias_7day=-0.05,
        icon_bias_7day=0.15,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time + timedelta(hours=1)  # AFTER issue_time!
    )

    is_valid, error_msg = feature_contract.validate_feature_vector(invalid_features)
    assert not is_valid, "Temporal leakage not detected"
    assert "temporal leakage" in error_msg.lower() or "after issue_time" in error_msg.lower()


# Test 8: Current NWP forecast at issue_time IS permitted

def test_current_forecast_at_issue_time_permitted(feature_contract):
    """
    Test that current NWP forecasts issued AT issue_time are permitted.

    CRITICAL: This is NOT leakage. The forecasts being blended are issued
    at issue_time and are valid inputs to the reliability prediction.
    """
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    issue_time = base_time + timedelta(days=7)

    # Current forecasts issued AT issue_time (valid)
    features = FeatureVector(
        model='gfs',
        issue_time=issue_time,
        valid_time=issue_time + timedelta(hours=24),
        lead_time_hours=24,
        latitude=20.0,
        longitude=77.0,
        location_zone='central',
        variable='temperature_2m_c',
        hour_of_day=0,
        day_of_year=7,
        month=1,
        season='winter',
        gfs_value=25.0,  # Current forecast (issued at issue_time)
        ifs_value=25.5,
        icon_value=24.8,
        forecast_spread=0.3,
        forecast_range=0.7,
        model_agreement=0.95,
        gfs_rmse_7day=1.2,
        ifs_rmse_7day=1.1,
        icon_rmse_7day=1.3,
        gfs_mae_7day=0.9,
        ifs_mae_7day=0.8,
        icon_mae_7day=1.0,
        gfs_bias_7day=0.1,
        ifs_bias_7day=-0.05,
        icon_bias_7day=0.15,
        gfs_available=True,
        ifs_available=True,
        icon_available=True,
        feature_computation_time=issue_time  # Computed AT issue_time
    )

    is_valid, error_msg = feature_contract.validate_feature_vector(features)
    assert is_valid, f"Current forecasts rejected: {error_msg}"


# Test 9: Future verification cannot enter historical features

def test_future_verification_rejected(feature_contract):
    """
    Test that verifications from the future cannot enter historical features.

    CRITICAL: Historical reliability (gfs_rmse_7day, etc.) must be computed
    from verifications with period_end < issue_time (strictly before).
    """
    # This test is enforced at the feature construction level
    # (see TemporalValidator and historical feature computation)
    # Here we verify that features with implausible historical stats are caught

    base_time = datetime(2024, 1, 1, 0, 0, 0)
    issue_time = base_time + timedelta(days=1)  # Day 1

    # INVALID: Historical features would require verifications from the future
    # (if only 1 day has passed, we can't have 7 days of history)
    # This is enforced at feature construction, not validation
    # But we can verify the temporal validator catches it

    from validation.temporal_validator import TemporalValidator

    validator = TemporalValidator()

    # Historical features must have period_end < issue_time
    period_end = issue_time - timedelta(hours=1)  # Valid (before issue_time)
    result = validator.validate_historical_features(issue_time, period_end)
    assert result.is_valid

    # Period_end >= issue_time is rejected
    period_end_invalid = issue_time  # AT issue_time (invalid)
    result = validator.validate_historical_features(issue_time, period_end_invalid)
    assert not result.is_valid


# Test 10: Weight normalization

def test_weight_normalization(feature_contract, synthetic_training_samples):
    """Test that weights always sum to 1.0."""
    candidates = [
        KernelRegressionCandidate(feature_contract),
        XGBoostCandidate(feature_contract, XGBoostConfig(n_estimators=10)),
        MLPCandidate(feature_contract, MLPConfig(hidden_layers=[16], n_epochs=5))
    ]

    for candidate in candidates:
        candidate.train(synthetic_training_samples[:80])

        for test_sample in synthetic_training_samples[80:85]:
            weights = candidate.get_weights(test_sample.features)

            # Weights sum to 1.0
            total_weight = weights.gfs_weight + weights.ifs_weight + weights.icon_weight
            assert abs(total_weight - 1.0) < 1e-6, f"{candidate.candidate_type}: weights sum to {total_weight}"

            # All weights non-negative
            assert weights.gfs_weight >= 0
            assert weights.ifs_weight >= 0
            assert weights.icon_weight >= 0


# Test 11: Training and evaluation

def test_kernel_training_and_evaluation(feature_contract, synthetic_training_samples):
    """Test Kernel Regression training and evaluation."""
    candidate = KernelRegressionCandidate(feature_contract)

    # Train
    metadata = candidate.train(synthetic_training_samples[:80])

    assert candidate.is_trained
    assert metadata.training_samples_count == 80

    # Evaluate
    metrics = candidate.evaluate(synthetic_training_samples[80:])

    assert metrics.n_test_samples == 20
    assert metrics.n_train_samples == 80
    assert metrics.weighted_forecast_rmse >= 0
    assert metrics.simple_average_rmse >= 0


def test_xgboost_training_and_evaluation(feature_contract, synthetic_training_samples):
    """Test XGBoost training and evaluation."""
    config = XGBoostConfig(n_estimators=10)
    candidate = XGBoostCandidate(feature_contract, config)

    # Train
    metadata = candidate.train(synthetic_training_samples[:80])

    assert candidate.is_trained
    assert metadata.training_samples_count == 80

    # Evaluate
    metrics = candidate.evaluate(synthetic_training_samples[80:])

    assert metrics.n_test_samples == 20
    assert metrics.weighted_forecast_rmse >= 0


def test_mlp_training_and_evaluation(feature_contract, synthetic_training_samples):
    """Test MLP training and evaluation."""
    config = MLPConfig(hidden_layers=[16], n_epochs=5)
    candidate = MLPCandidate(feature_contract, config)

    # Train
    metadata = candidate.train(synthetic_training_samples[:80])

    assert candidate.is_trained
    assert metadata.training_samples_count == 80

    # Evaluate
    metrics = candidate.evaluate(synthetic_training_samples[80:])

    assert metrics.n_test_samples == 20
    assert metrics.weighted_forecast_rmse >= 0


# Test 12: Reliability to weights conversion

def test_reliability_to_weights_conversion(feature_contract, synthetic_training_samples):
    """Test that reliability predictions correctly convert to weights."""
    candidate = KernelRegressionCandidate(feature_contract)
    candidate.train(synthetic_training_samples[:80])

    test_features = synthetic_training_samples[80].features

    # Get reliability predictions
    reliability = candidate.predict_reliability(test_features)

    # Get weights
    weights = candidate.get_weights(test_features, epsilon=0.001)

    # Verify inverse-error weighting formula
    # weight_i = (1 / expected_error_i) / sum_j(1 / expected_error_j)

    gfs_error = reliability['gfs'].expected_absolute_error
    ifs_error = reliability['ifs'].expected_absolute_error
    icon_error = reliability['icon'].expected_absolute_error

    # Bound errors
    epsilon = 0.001
    gfs_error = max(gfs_error, epsilon)
    ifs_error = max(ifs_error, epsilon)
    icon_error = max(icon_error, epsilon)

    # Compute expected weights
    raw_gfs = 1.0 / gfs_error
    raw_ifs = 1.0 / ifs_error
    raw_icon = 1.0 / icon_error

    total = raw_gfs + raw_ifs + raw_icon

    expected_gfs_weight = raw_gfs / total
    expected_ifs_weight = raw_ifs / total
    expected_icon_weight = raw_icon / total

    # Verify actual weights match
    assert abs(weights.gfs_weight - expected_gfs_weight) < 1e-4
    assert abs(weights.ifs_weight - expected_ifs_weight) < 1e-4
    assert abs(weights.icon_weight - expected_icon_weight) < 1e-4


if __name__ == '__main__':
    # Run tests without pytest
    print("Running HELIOS ML Candidates Tests...")
    print("=" * 80)

    # Note: This test file is designed to work with pytest but can run standalone
    # Individual test functions can be called directly for verification
    print("Tests defined. Import and run individual test functions to verify.")
    print("Example: test_kernel_instantiation(feature_contract())")
    print("=" * 80)
