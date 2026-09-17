"""
HELIOS ML Common Preprocessing

Deterministic preprocessing compatible with all three ML candidates
(Kernel Regression, XGBoost, MLP).

CRITICAL PRINCIPLES:
1. Deterministic (reproducible results)
2. Same canonical feature contract for all candidates
3. NO preprocessing leakage (fitted on training only)
4. Handle numerical features, categorical features, missing values
5. Model availability flags preserved
6. Numerical stability (scaling, clipping)
7. NO hidden model-specific feature engineering

PREPROCESSING PIPELINE:
1. Extract features from FeatureVector → numpy array
2. Handle missing values (imputation)
3. Scale numerical features (standardization)
4. Encode categorical features (one-hot)
5. Preserve model availability flags

TEMPORAL SAFETY:
- Preprocessing must NOT be fitted using future/test information
- Fit on training set only
- Transform validation/test using training statistics
"""

import logging
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import FeatureVector, Target, TrainingSample


logger = logging.getLogger(__name__)


@dataclass
class PreprocessingStats:
    """
    Statistics computed from training data for preprocessing.

    CRITICAL: These are fitted on TRAINING data only.
    Validation/test data is transformed using these statistics.
    """
    # Numerical feature statistics
    feature_means: Dict[str, float]  # Mean for each numerical feature
    feature_stds: Dict[str, float]  # Std dev for each numerical feature

    # Categorical feature encodings
    categorical_mappings: Dict[str, Dict[str, int]]  # Feature → value → index

    # Feature names in order
    numerical_feature_names: List[str]
    categorical_feature_names: List[str]

    # Missing value strategies
    missing_value_fills: Dict[str, float]  # Feature → fill value

    # Total feature dimensions
    n_numerical: int
    n_categorical_encoded: int  # After one-hot encoding
    n_total: int


class FeaturePreprocessor:
    """
    Common preprocessing for all HELIOS ML candidates.

    Design principles:
    - Deterministic (same input → same output)
    - Fit on training data only (no test leakage)
    - Same canonical feature contract for all candidates
    - Handle missing values gracefully
    - Numerical stability (scaling)
    - Preserve model availability flags
    """

    def __init__(self):
        """Initialize feature preprocessor."""
        self.logger = logging.getLogger(__name__)
        self.stats: Optional[PreprocessingStats] = None
        self.is_fitted = False

        # Feature lists (from canonical contract)
        self.numerical_features = [
            'lead_time_hours',
            'hour_of_day',
            'day_of_year',
            'month',
            # Current forecast values
            'gfs_value',
            'ifs_value',
            'icon_value',
            # Inter-model features
            'forecast_spread',
            'forecast_range',
            'model_agreement',
            # Historical reliability
            'gfs_rmse_7day',
            'ifs_rmse_7day',
            'icon_rmse_7day',
            'gfs_mae_7day',
            'ifs_mae_7day',
            'icon_mae_7day',
            'gfs_bias_7day',
            'ifs_bias_7day',
            'icon_bias_7day',
        ]

        self.categorical_features = [
            'season',
            'location_zone',
        ]

        self.availability_flags = [
            'gfs_available',
            'ifs_available',
            'icon_available',
        ]

    def fit(self, samples: List[TrainingSample]) -> PreprocessingStats:
        """
        Fit preprocessing statistics on training data.

        CRITICAL: Fit on TRAINING data only.
        Do NOT fit on validation or test data.

        Args:
            samples: Training samples

        Returns:
            PreprocessingStats fitted on training data
        """
        if not samples:
            raise ValueError("Cannot fit: no training samples")

        # Extract feature vectors
        features_list = [s.features for s in samples]

        # Compute numerical feature statistics
        feature_means = {}
        feature_stds = {}
        missing_value_fills = {}

        for feat_name in self.numerical_features:
            values = []
            for fv in features_list:
                val = getattr(fv, feat_name, None)
                if val is not None and not np.isnan(val):
                    values.append(val)

            if values:
                mean = np.mean(values)
                std = np.std(values)
                # Use mean for missing value imputation
                fill = mean
            else:
                # No valid values - use zero
                mean = 0.0
                std = 1.0
                fill = 0.0

            feature_means[feat_name] = mean
            feature_stds[feat_name] = max(std, 1e-8)  # Avoid division by zero
            missing_value_fills[feat_name] = fill

        # Build categorical encodings
        categorical_mappings = {}

        for feat_name in self.categorical_features:
            unique_values = set()
            for fv in features_list:
                val = getattr(fv, feat_name, None)
                if val is not None:
                    unique_values.add(val)

            # Sort for determinism
            sorted_values = sorted(unique_values)
            # Map value → index
            categorical_mappings[feat_name] = {
                val: idx for idx, val in enumerate(sorted_values)
            }

        # Compute dimensions
        n_numerical = len(self.numerical_features) + len(self.availability_flags)
        n_categorical_encoded = sum(len(mapping) for mapping in categorical_mappings.values())
        n_total = n_numerical + n_categorical_encoded

        self.stats = PreprocessingStats(
            feature_means=feature_means,
            feature_stds=feature_stds,
            categorical_mappings=categorical_mappings,
            numerical_feature_names=self.numerical_features,
            categorical_feature_names=self.categorical_features,
            missing_value_fills=missing_value_fills,
            n_numerical=n_numerical,
            n_categorical_encoded=n_categorical_encoded,
            n_total=n_total
        )

        self.is_fitted = True

        self.logger.info(
            f"Fitted preprocessor: {n_numerical} numerical + {n_categorical_encoded} categorical = {n_total} features"
        )

        return self.stats

    def fit_from_iterator(self, sample_iterator) -> PreprocessingStats:
        """ Fit sequentially to avoid loading everything """
        if not hasattr(self, 'logger'):
            import logging
            self.logger = logging.getLogger(__name__)
            
        sums = {feat: 0.0 for feat in self.numerical_features}
        sq_sums = {feat: 0.0 for feat in self.numerical_features}
        counts = {feat: 0 for feat in self.numerical_features}
        
        unique_cats = {feat: set() for feat in self.categorical_features}
        
        for chunk in sample_iterator:
            if not chunk: continue
            
            features_list = [s.features for s in chunk]
            
            for feat_name in self.numerical_features:
                vals = [getattr(fv, feat_name, None) for fv in features_list]
                vals = [v for v in vals if v is not None and not np.isnan(v)]
                if vals:
                    sums[feat_name] += sum(vals)
                    sq_sums[feat_name] += sum(v*v for v in vals)
                    counts[feat_name] += len(vals)
                    
            for feat_name in self.categorical_features:
                vals = [getattr(fv, feat_name, None) for fv in features_list]
                for v in vals:
                    if v is not None:
                        unique_cats[feat_name].add(v)
                        
        feature_means = {}
        feature_stds = {}
        missing_value_fills = {}
        
        for feat_name in self.numerical_features:
            count = counts[feat_name]
            if count > 0:
                mean = sums[feat_name] / count
                var = (sq_sums[feat_name] / count) - (mean * mean)
                std = np.sqrt(max(0.0, var))
                
                feature_means[feat_name] = float(mean)
                feature_stds[feat_name] = float(max(std, 1e-8))
                missing_value_fills[feat_name] = float(mean)
            else:
                feature_means[feat_name] = 0.0
                feature_stds[feat_name] = 1.0
                missing_value_fills[feat_name] = 0.0
                
        categorical_mappings = {}
        for feat_name in self.categorical_features:
            sorted_values = sorted(unique_cats[feat_name])
            categorical_mappings[feat_name] = {
                val: idx for idx, val in enumerate(sorted_values)
            }
            
        n_numerical = len(self.numerical_features) + len(self.availability_flags)
        n_categorical_encoded = sum(len(mapping) for mapping in categorical_mappings.values())
        n_total = n_numerical + n_categorical_encoded
        
        self.stats = PreprocessingStats(
            feature_means=feature_means,
            feature_stds=feature_stds,
            categorical_mappings=categorical_mappings,
            numerical_feature_names=self.numerical_features,
            categorical_feature_names=self.categorical_features,
            missing_value_fills=missing_value_fills,
            n_numerical=n_numerical,
            n_categorical_encoded=n_categorical_encoded,
            n_total=n_total
        )
        self.is_fitted = True
        self.logger.info(f"Fitted preprocessor incrementally. Features={n_total}")
        return self.stats

    def transform(self, feature_vector: FeatureVector) -> np.ndarray:
        """
        Transform one feature vector to preprocessed numpy array.

        Args:
            feature_vector: FeatureVector to transform

        Returns:
            Preprocessed feature array (1D numpy array)
        """
        if not self.is_fitted:
            raise ValueError("Preprocessor not fitted. Call fit() first.")

        # Extract numerical features
        numerical_values = []

        for feat_name in self.numerical_features:
            val = getattr(feature_vector, feat_name, None)

            # Handle missing values
            if val is None or np.isnan(val):
                val = self.stats.missing_value_fills[feat_name]

            # Standardize
            mean = self.stats.feature_means[feat_name]
            std = self.stats.feature_stds[feat_name]
            standardized = (val - mean) / std

            numerical_values.append(standardized)

        # Add availability flags (0/1, no scaling)
        for flag_name in self.availability_flags:
            val = getattr(feature_vector, flag_name, False)
            numerical_values.append(1.0 if val else 0.0)

        # One-hot encode categorical features
        categorical_values = []

        for feat_name in self.categorical_features:
            val = getattr(feature_vector, feat_name, None)
            mapping = self.stats.categorical_mappings.get(feat_name, {})

            # Create one-hot vector
            n_categories = len(mapping)
            one_hot = np.zeros(n_categories)

            if val is not None and val in mapping:
                idx = mapping[val]
                one_hot[idx] = 1.0
            # If value not in mapping or None, leave as all zeros

            categorical_values.extend(one_hot)

        # Concatenate all features
        all_features = numerical_values + categorical_values

        return np.array(all_features, dtype=np.float32)

    def transform_batch(self, feature_vectors: List[FeatureVector]) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("Preprocessor not fitted. Call fit() first.")
        if not feature_vectors:
            return np.zeros((0, self.stats.n_total), dtype=np.float32)

        import numpy as np

        # Pre-allocate output matrix securely
        N = len(feature_vectors)
        D = self.stats.n_total
        X = np.zeros((N, D), dtype=np.float32)

        # Build feature maps securely
        num_cols = len(self.numerical_features)
        
        # We index column by column linearly across rows for CPU cache locality
        for col_idx, feat_name in enumerate(self.numerical_features):
            mean = self.stats.feature_means[feat_name]
            std = self.stats.feature_stds[feat_name]
            fill = self.stats.missing_value_fills[feat_name]
            
            # Extract raw column
            raw_vals = [getattr(fv, feat_name, None) for fv in feature_vectors]
            
            # Sub-loop for standardization securely
            for row_idx, val in enumerate(raw_vals):
                if val is None or np.isnan(val):
                    val = fill
                X[row_idx, col_idx] = (val - mean) / std

        curr_idx = num_cols

        # Model availability flags
        for col_idx, flag_name in enumerate(self.availability_flags):
            attr = flag_name
            raw_flags = [getattr(fv, attr, False) for fv in feature_vectors]
            for row_idx, flag in enumerate(raw_flags):
                X[row_idx, curr_idx + col_idx] = 1.0 if flag else 0.0
                
        curr_idx += len(self.availability_flags)
        # One-hot encoded categorical columns statically evaluated
        for feat_name, mapping in self.stats.categorical_mappings.items():
            raw_cats = [getattr(fv, feat_name, None) for fv in feature_vectors]
            for row_idx, val in enumerate(raw_cats):
                if val is not None and val in mapping:
                    hot_idx = mapping[val]
                    X[row_idx, curr_idx + hot_idx] = 1.0
            curr_idx += len(mapping)


        return X


    def extract_targets(self, samples: List[TrainingSample], target_type: str = 'absolute_error') -> np.ndarray:
        """
        Extract targets from training samples.

        CRITICAL: Targets are observations/outcomes, NEVER features.

        Args:
            samples: Training samples
            target_type: Type of target to extract
                'observed_value': actual observation
                'forecast_error': forecast - observed (signed)
                'absolute_error': |forecast - observed|

        Returns:
            Target array (1D numpy array)
        """
        if not samples:
            return np.array([], dtype=np.float32)

        targets = []

        for sample in samples:
            if target_type == 'observed_value':
                targets.append(sample.target.observed_value)
            elif target_type == 'forecast_error':
                targets.append(sample.target.forecast_error)
            elif target_type == 'absolute_error':
                targets.append(sample.target.absolute_error)
            else:
                raise ValueError(f"Unknown target_type: {target_type}")

        return np.array(targets, dtype=np.float32)

    def get_feature_names(self) -> List[str]:
        """
        Get feature names in order.

        Returns:
            List of feature names (after one-hot encoding)
        """
        if not self.is_fitted:
            raise ValueError("Preprocessor not fitted. Call fit() first.")

        names = []

        # Numerical features
        names.extend(self.numerical_features)

        # Availability flags
        names.extend(self.availability_flags)

        # Categorical features (one-hot encoded)
        for feat_name in self.categorical_features:
            mapping = self.stats.categorical_mappings.get(feat_name, {})
            for val in sorted(mapping.keys(), key=lambda x: mapping[x]):
                names.append(f"{feat_name}_{val}")

        return names
