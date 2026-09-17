"""
HELIOS Full V1 Training Configurations

Deterministic, reproducible, explicitly-documented configurations for the FIRST
proper real-data TRAIN -> VALIDATION fit of the three mandatory HELIOS
candidates (Kernel Regression, XGBoost, MLP).

WHAT THESE ARE
--------------
- The "full V1" settings for a first serious real-data experiment on the current
  MVP/V1 dataset (IFS-only, temperature_2m_c, 28-day window, ~602k TRAIN rows).
- Deterministic (fixed seeds) and reproducible.

WHAT THESE ARE NOT
------------------
- NOT the smoke-test settings (those live in scripts/run_real_ml_smoke_test.py
  and are intentionally tiny).
- NOT Optuna / hyperparameter-search configurations. Each candidate has ONE
  justified configuration chosen from the implementation + smoke behaviour.
- NOT tied to the current dataset size: sizes are parameters, and the Kernel
  support set is configurable so larger post-V1 datasets scale without edits.

LEAKAGE / SCIENTIFIC RULES
--------------------------
- Preprocessing is fit on TRAIN only (each candidate fits its own preprocessor
  on the TRAIN samples it is given).
- Early stopping (XGBoost, MLP) uses VALIDATION only. TEST is never used for
  fitting, preprocessing, early stopping, or model selection.
- These configs contain NO TEST-derived information.

RESOURCE REASONING (see per-config notes and estimate_* helpers)
----------------------------------------------------------------
The feature matrix is 28 float32 columns. For N rows the dense matrix is
~ N * 28 * 4 bytes. For the full TRAIN (601,931 rows) that is ~ 67 MB per dense
copy. The in-memory list of TrainingSample objects dominates instead (~1 KB each
=> a few hundred MB for ~602k), which is why the smoke run peaked near 3.9 GB.
The runner should avoid holding multiple simultaneous full-size float matrices.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any


# Bytes per feature-matrix element (float32) and feature dimension (canonical).
_FLOAT_BYTES = 4
CANONICAL_FEATURE_DIM = 28  # standardized numerics + availability flags + one-hot


def estimate_feature_matrix_mb(n_rows: int, n_features: int = CANONICAL_FEATURE_DIM) -> float:
    """Approximate memory (MB) of one dense float32 feature matrix."""
    return (n_rows * n_features * _FLOAT_BYTES) / (1024.0 * 1024.0)


# ----------------------------------------------------------------------
# Kernel full-V1 configuration
# ----------------------------------------------------------------------
@dataclass
class KernelV1Config:
    """
    Full-V1 configuration for the optimized (per-model KDTree) Kernel candidate.

    Justification
    -------------
    - The Kernel candidate now builds ONE KDTree per model over that model's
      preprocessed rows and answers each query with a bounded k-NN search
      (O(k log N_model)). Full-TRAIN indexing is therefore computationally
      reasonable for V1.
    - support_set_limit=None => use the FULL TRAIN representation. For the V1
      IFS-only dataset that is ~602k rows in a single IFS tree. Estimated tree
      data memory ~ estimate_feature_matrix_mb(602k) ≈ 64 MB plus cKDTree
      overhead — safe on the current machine.
    - n_neighbors=100: a stable local neighbourhood for ~hundreds of thousands
      of rows; large enough to average out noise, small enough to stay local.
    - bandwidth=1.0: features are standardized (unit-scale) by the shared
      preprocessor, so a unit Gaussian bandwidth is a sensible default.
    - min_neighbors=10: require a minimally reliable neighbourhood before
      trusting a reliability estimate; otherwise fall back to conservative 1.0.

    Scalability / safety fallback
    -----------------------------
    If a future dataset makes full indexing unsafe (memory/runtime), set
    support_set_limit to a bounded integer. The runner MUST then use a
    DETERMINISTIC, chronologically-ordered prefix of TRAIN as the support set
    (earliest N; never random; never VALIDATION/TEST). This is a documented,
    explicit choice — never a silent dataset reduction.
    """
    n_neighbors: int = 100
    bandwidth: float = 1.0
    min_neighbors: int = 10

    # None => use the full TRAIN representation. An int => deterministic
    # chronological-prefix support set of that size (documented fallback).
    support_set_limit: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# XGBoost full-V1 configuration
# ----------------------------------------------------------------------
@dataclass
class XGBoostV1Config:
    """
    Full-V1 configuration for the XGBoost candidate.

    Justification
    -------------
    - n_estimators=400 with learning_rate=0.05: a conservative low-LR / more-
      trees pairing that learns meaningful structure without overfitting; early
      stopping trims to the effective count. (Smoke used 60 trees @ lr 0.1 and
      converged/early-stopped cleanly, so more capacity here is safe.)
    - max_depth=6: XGBoost's standard moderate depth; expressive but regularized.
    - subsample=0.8, colsample_bytree=0.8: row/column stochasticity for
      generalization; deterministic given random_state.
    - min_child_weight=5, reg_lambda=1.0: mild regularization for stability.
    - early_stopping_rounds=25 on VALIDATION only (never TEST).
    - random_state=42: reproducibility.

    Resource
    --------
    XGBoost stores a compact histogram model; memory is dominated by the input
    matrix (~67 MB for full TRAIN float32) plus histograms — comfortably bounded.
    """
    n_estimators: int = 400
    max_depth: int = 6
    learning_rate: float = 0.05
    min_child_weight: int = 5
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    gamma: float = 0.0
    reg_alpha: float = 0.0
    reg_lambda: float = 1.0
    early_stopping_rounds: int = 25
    random_state: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# MLP full-V1 configuration
# ----------------------------------------------------------------------
@dataclass
class MLPV1Config:
    """
    Full-V1 configuration for the MLP candidate.

    Justification
    -------------
    - hidden_layers=(128, 64, 32): a credible first architecture — clearly more
      capacity than the tiny smoke net (32,16) that underfit, but still small
      and CPU-friendly. No architecture search.
    - n_epochs=100 ceiling with early_stopping_patience=10 on VALIDATION only:
      lets training run to convergence while capping wall-clock; stops when the
      VALIDATION loss stops improving.
    - batch_size=512: efficient CPU throughput on ~602k rows while keeping
      per-batch tensors small (512 x 28 float32 ≈ 57 KB).
    - learning_rate=1e-3 (Adam), weight_decay=1e-4: standard, stable defaults.
    - device="cpu": the current implementation forces CPU for this phase; no
      GPU is assumed.
    - random_state=42 (torch + numpy seeded in the candidate) for reproducibility.

    Resource
    --------
    Tiny network (a few thousand params) + streaming DataLoader batches. Memory
    is dominated by the training feature tensor (~67 MB float32 for full TRAIN)
    plus one target column; well within budget.
    """
    hidden_layers: Tuple[int, ...] = (128, 64, 32)
    activation: str = "relu"
    dropout_rate: float = 0.1
    n_epochs: int = 100
    batch_size: int = 512
    learning_rate: float = 0.001
    weight_decay: float = 0.0001
    early_stopping_patience: int = 10
    device: str = "cuda"
    random_state: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Dataset / split configuration for the full-V1 fit
# ----------------------------------------------------------------------
@dataclass
class DatasetV1Config:
    """
    Dataset-build + chronological-split configuration for the full-V1 fit.

    Mirrors the leakage-safe DatasetBuilder defaults. Split is a deterministic
    function of issue_time (never random). TEST fraction is the remainder and is
    never used in this step.
    """
    variable: str = "temperature_2m_c"
    models: Tuple[str, ...] = ("gfs", "ifs", "icon")
    historical_window_days: int = 7
    min_history_samples: int = 1
    train_fraction: float = 0.6
    validation_fraction: float = 0.2  # remainder is TEST (untouched here)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FullV1TrainingConfig:
    """Bundle of all full-V1 configurations for the first TRAIN->VALIDATION fit."""
    dataset: DatasetV1Config = field(default_factory=DatasetV1Config)
    kernel: KernelV1Config = field(default_factory=KernelV1Config)
    xgboost: XGBoostV1Config = field(default_factory=XGBoostV1Config)
    mlp: MLPV1Config = field(default_factory=MLPV1Config)

    # Global reproducibility seed (candidates also carry their own).
    random_state: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset": self.dataset.to_dict(),
            "kernel": self.kernel.to_dict(),
            "xgboost": self.xgboost.to_dict(),
            "mlp": self.mlp.to_dict(),
            "random_state": self.random_state,
        }


def default_full_v1_config() -> FullV1TrainingConfig:
    """Return the canonical, documented full-V1 training configuration."""
    return FullV1TrainingConfig()
