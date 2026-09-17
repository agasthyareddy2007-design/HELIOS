"""
HELIOS Walk-Forward Validation (reusable, deterministic, leakage-safe)

Expanding-origin, issue-time walk-forward over TRAIN+VALIDATION only. The locked
TEST region (issue_time >= TEST_BOUNDARY) is NEVER included in any fold.

Design (temporal causality guaranteed):
  - Folds are defined by chronological VALIDATION windows over issue_time.
  - Fold k trains ONLY on examples with issue_time STRICTLY earlier than the
    fold's validation-window start, and validates on
    [window_start, window_end).
  - Historical-reliability features are computed by DatasetBuilder as-of each
    example's OWN issue_time (period_end < issue_time), independent of fold
    assignment, so building the dataset once and partitioning by issue_time is
    leakage-safe.
  - Each candidate fits its OWN preprocessing on the fold's TRAIN subset only.
  - Observations from the validation window are used ONLY to score predictions
    after they are generated.

This module is data-source agnostic: it operates on lists of TrainingSample, so
it is drivable with synthetic samples in tests and with the real DatasetBuilder
output in the experiment runner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import FeatureContract, TrainingSample  # noqa: E402
from ml import evaluation_protocol as ep  # noqa: E402

# Locked TEST boundary for HELIOS V1. Nothing at/after this issue_time may enter
# any walk-forward fold. Enforced in fold generation.
TEST_BOUNDARY = datetime(2025, 1, 23, 12, 0, 0)

MODELS: Tuple[str, ...] = ("gfs", "ifs", "icon")
LEARNED: Tuple[str, ...] = ("kernel", "xgboost", "mlp")
BASELINES: Tuple[str, ...] = ("gfs", "ifs", "icon", "simple_average")



@dataclass
class StreamingFold:
    index: int
    window_start: datetime
    window_end: datetime
    train_bounds: Tuple[Optional[datetime], Optional[datetime]]
    val_bounds: Tuple[Optional[datetime], Optional[datetime]]
    
    # We maintain these methods for compatibility logging if needed
    def train_max_issue_approx(self):
        return self.train_bounds[1]

@dataclass
class Fold:
    index: int
    window_start: datetime
    window_end: datetime
    train: List[TrainingSample]
    val: List[TrainingSample]

    def train_max_issue(self) -> Optional[datetime]:
        return max((s.features.issue_time for s in self.train), default=None)

    def val_issue_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        its = [s.features.issue_time for s in self.val]
        return (min(its), max(its)) if its else (None, None)


def make_walkforward_folds(
    samples: Sequence[TrainingSample],
    window_starts: Sequence[datetime],
    window_hours: int = 24,
    min_train: int = 1,
    test_boundary: datetime = TEST_BOUNDARY,
) -> List[Fold]:
    """
    Build expanding-origin folds.

    For each window_start w (sorted, deterministic):
      train = samples with issue_time < w  (and issue_time < test_boundary)
      val   = samples with w <= issue_time < w+window_hours (and < test_boundary)

    Any sample with issue_time >= test_boundary is EXCLUDED from every fold
    (locked TEST protection). Folds with empty val or train < min_train are
    dropped and reported by the caller.
    """
    # Hard exclusion of the locked TEST region.
    pool = [s for s in samples if s.features.issue_time < test_boundary]
    folds: List[Fold] = []
    for i, w in enumerate(sorted(set(window_starts))):
        if w >= test_boundary:
            continue  # never validate into the locked TEST region
        w_end = w + timedelta(hours=window_hours)
        w_end = min(w_end, test_boundary)
        train = [s for s in pool if s.features.issue_time < w]
        val = [s for s in pool if w <= s.features.issue_time < w_end]
        if not val or len(train) < min_train:
            continue
        folds.append(Fold(index=len(folds), window_start=w, window_end=w_end,
                          train=train, val=val))
    return folds



def make_walkforward_folds_streaming(
    window_starts: Sequence[datetime],
    window_hours: int = 24,
    test_boundary: datetime = TEST_BOUNDARY,
) -> List[StreamingFold]:
    folds: List[StreamingFold] = []
    for i, w in enumerate(sorted(set(window_starts))):
        if w >= test_boundary:
            continue
        w_end = w + timedelta(hours=window_hours)
        w_end = min(w_end, test_boundary)
        
        folds.append(StreamingFold(
            index=len(folds),
            window_start=w,
            window_end=w_end,
            train_bounds=(None, w),
            val_bounds=(w, w_end)
        ))
    return folds

def _deterministic_prefix_by_time(samples: List[TrainingSample], limit: Optional[int]) -> List[TrainingSample]:
    """Chronologically-latest `limit` train samples as kernel support (nearest in
    time to the validation window; deterministic). Not random; no future data
    because all are strictly earlier than the window by fold construction."""
    if limit is None or limit <= 0 or limit >= len(samples):
        return list(samples)
    ordered = sorted(samples, key=lambda s: (s.features.issue_time, s.verification_id))
    return ordered[-limit:]


@dataclass
class FoldResult:
    index: int
    window_start: str
    window_end: str
    n_train: int
    n_val: int
    n_val_issue_times: int
    n_val_stations: int
    train_max_issue: Optional[str]
    val_min_issue: Optional[str]
    val_max_issue: Optional[str]
    train_strictly_before_val: bool
    no_test_in_fold: bool
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # candidate -> forecast metrics
    reliability: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)



def evaluate_fold_streaming(
    fold: StreamingFold,
    build_candidates: Callable[[], Dict[str, Any]],
    dataset_builder,
    config,
    kernel_support_limit: Optional[int] = 20000,
    models: Tuple[str, ...] = MODELS,
) -> FoldResult:
    # 1. Gather val samples exactly as before, since val is small (1 day).
    val = []
    for chunk in dataset_builder.stream_training_samples(config, start_issue=fold.val_bounds[0], end_issue=fold.val_bounds[1]):
        val.extend(chunk)
        
    fr = FoldResult(
        index=fold.index,
        window_start=fold.window_start.isoformat(),
        window_end=fold.window_end.isoformat(),
        n_train=0, # we will evaluate it during streaming
        n_val=len(val),
        n_val_issue_times=len({s.features.issue_time for s in val}),
        n_val_stations=len({(round(s.features.latitude, 4), round(s.features.longitude, 4)) for s in val}),
        train_max_issue=fold.train_bounds[1].isoformat() if fold.train_bounds[1] else None,
        val_min_issue=(min(s.features.issue_time for s in val).isoformat() if val else None),
        val_max_issue=(max(s.features.issue_time for s in val).isoformat() if val else None),
        train_strictly_before_val=True,
        no_test_in_fold=True,
    )

    # Baselines (individual + Simple Average) on the SAME val examples.
    for m in models:
        fr.metrics[m] = _fmt(ep.evaluate_individual_model(val, m))
    fr.metrics["simple_average"] = _fmt(ep.evaluate_simple_average(val, models))

    # Learned candidates.
    cands = build_candidates()
    for name in ("kernel", "xgboost", "mlp"):
        cand = cands.get(name)
        if cand is None:
            continue
        try:
            print(f"[Fold {fold.index}/19] [Candidate: {name.upper()}] Starting streaming train...")
            # We call stream_train which must be supported by the new candidates
            n_train_samples = cand.stream_train(
                dataset_builder=dataset_builder,
                config=config,
                train_bounds=fold.train_bounds,
                validation_samples=val,
                kernel_support_limit=kernel_support_limit if name=="kernel" else None
            )
            # Update n_train
            if fr.n_train == 0 and n_train_samples is not None:
                fr.n_train = n_train_samples.training_samples_count if hasattr(n_train_samples, "training_samples_count") else 0
                
            fr.metrics[name] = _fmt(ep.evaluate_helios_blend(val, cand, models))
            rm = ep.evaluate_reliability(val, cand, models)
            fr.reliability[name] = {
                "reliability_mae": rm.reliability_mae,
                "reliability_bias": rm.reliability_bias,
                "n_finite": rm.n_finite, "n_nonfinite": rm.n_nonfinite,
                "n_negative": rm.n_negative,
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            fr.metrics[name] = {"error": f"{type(e).__name__}: {e}", "mae": None,
                                "rmse": None, "bias": None, "n_rows": 0}
            
        import gc
        if hasattr(cand, "models"):
            cand.models.clear()
        del cand
        gc.collect()
    
    del val
    gc.collect()
    return fr

def _fmt(m: ep.ForecastMetrics) -> Dict[str, Any]:
    return {"n_rows": m.n_rows, "mae": m.mae, "rmse": m.rmse, "bias": m.bias,
            "median_abs_error": m.median_abs_error, "quantiles": m.error_quantiles}


def evaluate_fold(
    fold: Fold,
    build_candidates: Callable[[], Dict[str, Any]],
    kernel_support_limit: Optional[int] = 20000,
    models: Tuple[str, ...] = MODELS,
) -> FoldResult:
    """
    Train learned candidates on fold.train and evaluate all methods on fold.val.

    `build_candidates()` returns a fresh dict {name: candidate} each call, so no
    state leaks across folds. Kernel is trained on a bounded, deterministic,
    chronologically-latest support subset of fold.train (never random, never
    future — all strictly earlier than the window).
    """
    val = fold.val
    fr = FoldResult(
        index=fold.index,
        window_start=fold.window_start.isoformat(),
        window_end=fold.window_end.isoformat(),
        n_train=len(fold.train), n_val=len(val),
        n_val_issue_times=len({s.features.issue_time for s in val}),
        n_val_stations=len({(round(s.features.latitude, 4), round(s.features.longitude, 4)) for s in val}),
        train_max_issue=(fold.train_max_issue().isoformat() if fold.train else None),
        val_min_issue=(fold.val_issue_range()[0].isoformat() if val else None),
        val_max_issue=(fold.val_issue_range()[1].isoformat() if val else None),
        train_strictly_before_val=(
            (fold.train_max_issue() < fold.window_start) if fold.train else True),
        no_test_in_fold=all(s.features.issue_time < TEST_BOUNDARY for s in fold.train + val),
    )

    # Baselines (individual + Simple Average) on the SAME val examples.
    for m in models:
        fr.metrics[m] = _fmt(ep.evaluate_individual_model(val, m))
    fr.metrics["simple_average"] = _fmt(ep.evaluate_simple_average(val, models))

    # Learned candidates.
    cands = build_candidates()
    for name in ("kernel", "xgboost", "mlp"):
        cand = cands.get(name)
        if cand is None:
            continue
        try:
            if name == "kernel":
                cand.train(_deterministic_prefix_by_time(fold.train, kernel_support_limit))
            else:
                # XGBoost/MLP early stopping uses the fold's own val window only.
                cand.train(fold.train, validation_samples=val)
            fr.metrics[name] = _fmt(ep.evaluate_helios_blend(val, cand, models))
            rm = ep.evaluate_reliability(val, cand, models)
            fr.reliability[name] = {
                "reliability_mae": rm.reliability_mae,
                "reliability_bias": rm.reliability_bias,
                "n_finite": rm.n_finite, "n_nonfinite": rm.n_nonfinite,
                "n_negative": rm.n_negative,
            }
        except Exception as e:
            fr.metrics[name] = {"error": f"{type(e).__name__}: {e}", "mae": None,
                                "rmse": None, "bias": None, "n_rows": 0}
            
        import gc
        if hasattr(cand, "models"):
            cand.models.clear()
        del cand
        gc.collect()
    return fr


# ----------------------------------------------------------------------
# Stability aggregation
# ----------------------------------------------------------------------
def _mean(xs): return sum(xs) / len(xs) if xs else None
def _median(xs):
    if not xs: return None
    s = sorted(xs); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
def _std(xs):
    if len(xs) < 2: return 0.0 if xs else None
    mu = _mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def aggregate_stability(fold_results: List[FoldResult],
                        candidates: Sequence[str]) -> Dict[str, Any]:
    """
    Per-candidate fold-MAE stability + improvement vs Simple Average.
    """
    # Collect per-fold MAE per candidate.
    per_cand_mae: Dict[str, List[float]] = {c: [] for c in candidates}
    sa_mae_per_fold: List[float] = []
    beats_sa: Dict[str, int] = {c: 0 for c in candidates}
    n_folds_valid = 0

    for fr in fold_results:
        sa = fr.metrics.get("simple_average", {}).get("mae")
        if sa is None:
            continue
        n_folds_valid += 1
        sa_mae_per_fold.append(sa)
        for c in candidates:
            mae = fr.metrics.get(c, {}).get("mae")
            if mae is not None:
                per_cand_mae[c].append(mae)
                if mae < sa:
                    beats_sa[c] += 1

    out: Dict[str, Any] = {"n_folds": len(fold_results), "n_folds_scored": n_folds_valid,
                           "simple_average_mean_fold_mae": _mean(sa_mae_per_fold)}
    per = {}
    for c in candidates:
        maes = per_cand_mae[c]
        # per-fold improvement vs SA (aligned by fold order among scored folds)
        improvements = []
        for fr in fold_results:
            sa = fr.metrics.get("simple_average", {}).get("mae")
            mc = fr.metrics.get(c, {}).get("mae")
            if sa is not None and mc is not None and sa > 0:
                improvements.append((sa - mc) / sa)
        per[c] = {
            "mean_fold_mae": _mean(maes), "median_fold_mae": _median(maes),
            "std_fold_mae": _std(maes), "worst_fold_mae": (max(maes) if maes else None),
            "best_fold_mae": (min(maes) if maes else None),
            "mean_improvement_vs_sa_pct": (_mean(improvements) * 100 if improvements else None),
            "folds_beating_sa": beats_sa[c], "folds_scored": len(maes),
        }
    out["per_candidate"] = per
    return out
