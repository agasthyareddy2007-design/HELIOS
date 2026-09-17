"""
HELIOS Model Evaluation & Selection Protocol

A reusable, scientifically-defensible protocol for evaluating and selecting
HELIOS forecast-blending candidates (Kernel / XGBoost / MLP) and for comparing
HELIOS against individual NWP models and a Simple Average baseline.

WHY THIS MODULE EXISTS
----------------------
scripts/run_v1_training.py already computes ad-hoc VALIDATION metrics for the
training runner. This module is the CANONICAL, reusable home for evaluation:
metric definitions, stratified breakdowns, missing-model-aware baselines, the
HELIOS blended-forecast evaluation, weight diagnostics, the correlated-data
caveat, the chronological model-selection rule, the locked one-shot TEST
protocol specification, and the future walk-forward design. It does not modify
the working runner.

TWO DISTINCT QUANTITIES (do NOT conflate)
-----------------------------------------
A. RELIABILITY-PREDICTION accuracy: how well a candidate predicts a model's
   absolute forecast error (the training target). Metric: predicted expected
   |error| vs actual |error|.
B. FINAL FORECAST accuracy: how good the actual blended forecast is, i.e.
   HELIOS_forecast = sum(model_forecast * learned_weight), compared to the
   observation. THIS is the decisive metric for HELIOS.

The candidate with the best reliability-prediction MAE is NOT automatically the
best final-forecast candidate. Final selection must ultimately use (B), which
only becomes meaningful once multiple NWP models are available. With the current
IFS-only data every candidate's blend equals the IFS forecast (IFS weight = 1),
so (B) cannot separate candidates yet and NO forecast improvement can be claimed.

ERROR CONVENTION (consistent project-wide)
------------------------------------------
    error = forecast - observation
    MAE   = mean(|error|)
    RMSE  = sqrt(mean(error^2))
    bias  = mean(error)

CORRELATED DATA
---------------
The ~991k rows are NOT independent weather cases: nearby stations/grid points,
overlapping forecast cycles, and multiple leads from the same issue are strongly
correlated. Row counts are reported as `n_rows` (NOT "independent samples"), and
grouped-by-issue-date / station / cycle counts are provided so the effective
sample size can be judged honestly. No significance testing is claimed.

LEAKAGE / TEST RULES
--------------------
- Model selection uses TRAIN and VALIDATION only.
- TEST must never influence candidate/hyperparameter/threshold/blend/feature
  selection. TEST is used EXACTLY ONCE, after everything is frozen
  (LockedTestProtocol), and is NOT executed here.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import TrainingSample, FeatureVector, Target  # noqa: E402


CANONICAL_MODELS: Tuple[str, ...] = ("gfs", "ifs", "icon")
DEFAULT_LEADS: Tuple[int, ...] = (6, 24, 48, 72, 120)
DEFAULT_QUANTILES: Tuple[float, ...] = (0.5, 0.9, 0.95, 0.99)


# =====================================================================
# Metrics
# =====================================================================
@dataclass
class ForecastMetrics:
    """
    Continuous-temperature forecast error metrics.

    error = forecast - observation (degrees C).
    """
    n_rows: int
    mae: Optional[float]
    rmse: Optional[float]
    bias: Optional[float]
    median_abs_error: Optional[float] = None
    error_quantiles: Dict[str, float] = field(default_factory=dict)  # of |error|

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_forecast_metrics(
    errors: Sequence[float],
    quantiles: Sequence[float] = DEFAULT_QUANTILES,
) -> ForecastMetrics:
    """
    Compute MAE/RMSE/bias (+ median abs error and abs-error quantiles) from a
    sequence of signed errors (forecast - observation).
    """
    e = [x for x in errors if x is not None and math.isfinite(x)]
    n = len(e)
    if n == 0:
        return ForecastMetrics(n_rows=0, mae=None, rmse=None, bias=None,
                               median_abs_error=None, error_quantiles={})
    abs_e = [abs(x) for x in e]
    mae = sum(abs_e) / n
    rmse = math.sqrt(sum(x * x for x in e) / n)
    bias = sum(e) / n
    med = statistics.median(abs_e)
    q: Dict[str, float] = {}
    if n >= 2:
        srt = sorted(abs_e)
        for qq in quantiles:
            # linear-interpolation quantile of |error|
            pos = qq * (n - 1)
            lo = int(math.floor(pos))
            hi = int(math.ceil(pos))
            frac = pos - lo
            q[f"p{int(round(qq * 100))}"] = srt[lo] + (srt[hi] - srt[lo]) * frac
    return ForecastMetrics(n_rows=n, mae=mae, rmse=rmse, bias=bias,
                           median_abs_error=med, error_quantiles=q)


@dataclass
class ReliabilityMetrics:
    """
    Quality of a candidate's RELIABILITY prediction (predicted expected absolute
    error vs actual absolute error). Distinct from forecast accuracy.
    """
    n_rows: int
    reliability_mae: Optional[float]   # mean|predicted_abs_err - actual_abs_err|
    reliability_rmse: Optional[float]
    reliability_bias: Optional[float]  # mean(predicted - actual)
    n_finite: int = 0
    n_nonfinite: int = 0
    n_negative: int = 0
    pred_min: Optional[float] = None
    pred_max: Optional[float] = None
    pred_mean: Optional[float] = None
    all_predictions_identical: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =====================================================================
# Correlated-data metadata
# =====================================================================
@dataclass
class CorrelatedDataNote:
    """
    Honest metadata about non-independence of rows. Row count != independent
    sample count. Grouped counts give a sense of effective sample size.
    """
    n_rows: int
    n_distinct_issue_dates: int
    n_distinct_stations: int
    n_distinct_cycles: int          # distinct issue_time hour cycles (e.g. 00Z/12Z)
    n_distinct_issue_times: int
    caveat: str = (
        "Row count is NOT an independent-sample count. Nearby stations/grid "
        "points, overlapping forecast cycles, and multiple lead times from the "
        "same issue_time are strongly correlated in space/time/lead. Interpret "
        "aggregate metrics with this correlation in mind; no significance test "
        "is claimed."
    )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _station_key(f: FeatureVector) -> str:
    return f"{round(f.latitude, 4)},{round(f.longitude, 4)}"


def _cycle_key(f: FeatureVector) -> str:
    return f"{f.issue_time.hour:02d}Z"


def correlated_data_note(samples: Sequence[TrainingSample]) -> CorrelatedDataNote:
    issue_dates = set()
    stations = set()
    cycles = set()
    issue_times = set()
    for s in samples:
        f = s.features
        issue_dates.add(f.issue_time.date())
        stations.add(_station_key(f))
        cycles.add(_cycle_key(f))
        issue_times.add(f.issue_time)
    return CorrelatedDataNote(
        n_rows=len(samples),
        n_distinct_issue_dates=len(issue_dates),
        n_distinct_stations=len(stations),
        n_distinct_cycles=len(cycles),
        n_distinct_issue_times=len(issue_times),
    )


# =====================================================================
# Forecast extraction helpers (missing-model aware)
# =====================================================================
def available_models(f: FeatureVector) -> List[str]:
    """Models with a present forecast for this example (availability + value)."""
    out = []
    if f.gfs_available and f.gfs_value is not None:
        out.append("gfs")
    if f.ifs_available and f.ifs_value is not None:
        out.append("ifs")
    if f.icon_available and f.icon_value is not None:
        out.append("icon")
    return out


def model_value(f: FeatureVector, model: str) -> Optional[float]:
    return {"gfs": f.gfs_value, "ifs": f.ifs_value, "icon": f.icon_value}.get(model)


def individual_model_error(s: TrainingSample, model: str) -> Optional[float]:
    """
    Signed error (forecast - observation) of a single NWP model for a sample.

    If `model` is the sample's own target model, uses the leakage-safe
    Target.forecast_error directly. Otherwise derives it from the model's value
    and the observed value (same-valid-time observation; no TEST/future data).
    Returns None if the model is unavailable.
    """
    f = s.features
    v = model_value(f, model)
    avail = {"gfs": f.gfs_available, "ifs": f.ifs_available, "icon": f.icon_available}[model]
    if not avail or v is None:
        return None
    if model == f.model:
        return s.target.forecast_error
    return v - s.target.observed_value


# =====================================================================
# Baseline / forecast evaluators (missing-model aware)
# =====================================================================
def evaluate_individual_model(samples: Sequence[TrainingSample], model: str,
                              quantiles: Sequence[float] = DEFAULT_QUANTILES) -> ForecastMetrics:
    """Raw individual NWP model forecast vs observation (available rows only)."""
    errs = []
    for s in samples:
        e = individual_model_error(s, model)
        if e is not None:
            errs.append(e)
    return compute_forecast_metrics(errs, quantiles)


def simple_average_error(s: TrainingSample,
                         models: Sequence[str] = CANONICAL_MODELS) -> Optional[float]:
    """
    Simple Average over PARTICIPATING COMPATIBLE models only.

    Compatibility (temperature, this task): same variable/units/valid_time and
    compatible spatial representation are guaranteed by the FeatureContract
    (all model slots are 2 m temperature in degC at the same identity). A model
    that is unavailable does NOT contribute (missing != zero). If no model is
    available, returns None.
    """
    f = s.features
    vals = [model_value(f, m) for m in models
            if m in available_models(f)]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    blend = sum(vals) / len(vals)
    return blend - s.target.observed_value


def evaluate_simple_average(samples: Sequence[TrainingSample],
                            models: Sequence[str] = CANONICAL_MODELS,
                            quantiles: Sequence[float] = DEFAULT_QUANTILES) -> ForecastMetrics:
    errs = []
    for s in samples:
        e = simple_average_error(s, models)
        if e is not None:
            errs.append(e)
    return compute_forecast_metrics(errs, quantiles)


def helios_blend_error(s: TrainingSample, weight_prediction,
                       models: Sequence[str] = CANONICAL_MODELS) -> Optional[float]:
    """
    HELIOS final forecast error for one sample:
        HELIOS_forecast = sum(model_forecast * learned_weight)   (available only)
        error = HELIOS_forecast - observation

    `weight_prediction` is a WeightPrediction (gfs/ifs/icon_weight + availability).
    Unavailable models contribute nothing (their weight is 0 by construction).
    """
    f = s.features
    w = {"gfs": weight_prediction.gfs_weight,
         "ifs": weight_prediction.ifs_weight,
         "icon": weight_prediction.icon_weight}
    avail = set(available_models(f))
    blend = 0.0
    used = False
    for m in models:
        if m in avail:
            v = model_value(f, m)
            if v is not None:
                blend += w.get(m, 0.0) * v
                used = True
    if not used:
        return None
    return blend - s.target.observed_value


def evaluate_helios_blend(samples: Sequence[TrainingSample], candidate,
                          models: Sequence[str] = CANONICAL_MODELS,
                          quantiles: Sequence[float] = DEFAULT_QUANTILES) -> ForecastMetrics:
    """
    FINAL FORECAST accuracy of the HELIOS blend produced by `candidate`
    (a trained BaseCandidateModel). Uses candidate.get_weights per sample.

    NOTE: with IFS-only data this equals the IFS individual-model metrics
    because IFS weight == 1; that is expected and is not an improvement.
    """
    errs = []
    for s in samples:
        wp = candidate.get_weights(s.features, models=list(models))
        e = helios_blend_error(s, wp, models)
        if e is not None:
            errs.append(e)
    return compute_forecast_metrics(errs, quantiles)


def evaluate_reliability(samples: Sequence[TrainingSample], candidate,
                         models: Sequence[str] = CANONICAL_MODELS) -> ReliabilityMetrics:
    """
    RELIABILITY-prediction quality: candidate's predicted expected absolute
    error for each sample's OWN model vs the actual absolute error.
    """
    preds: List[float] = []
    diffs: List[float] = []
    n_finite = n_nonfinite = n_negative = 0
    for s in samples:
        f = s.features
        rel = candidate.predict_reliability(f, models=list(models))
        own = rel.get(f.model)
        pred = own.expected_absolute_error if own is not None else float("nan")
        if math.isfinite(pred):
            n_finite += 1
            preds.append(pred)
            diffs.append(pred - s.target.absolute_error)
            if pred < 0:
                n_negative += 1
        else:
            n_nonfinite += 1
    if not preds:
        return ReliabilityMetrics(n_rows=len(samples), reliability_mae=None,
                                  reliability_rmse=None, reliability_bias=None,
                                  n_finite=0, n_nonfinite=n_nonfinite, n_negative=0)
    n = len(preds)
    rel_mae = sum(abs(d) for d in diffs) / n
    rel_rmse = math.sqrt(sum(d * d for d in diffs) / n)
    rel_bias = sum(diffs) / n
    return ReliabilityMetrics(
        n_rows=len(samples),
        reliability_mae=rel_mae, reliability_rmse=rel_rmse, reliability_bias=rel_bias,
        n_finite=n_finite, n_nonfinite=n_nonfinite, n_negative=n_negative,
        pred_min=min(preds), pred_max=max(preds), pred_mean=sum(preds) / n,
        all_predictions_identical=all(abs(p - preds[0]) < 1e-9 for p in preds),
    )


# =====================================================================
# Stratified evaluation
# =====================================================================
class Stratifier(str, Enum):
    LEAD = "lead_time_hours"
    ZONE = "location_zone"
    STATION = "station"
    ISSUE_DATE = "issue_date"
    CYCLE = "cycle"


def _stratum_key(f: FeatureVector, by: Stratifier):
    if by is Stratifier.LEAD:
        return f.lead_time_hours
    if by is Stratifier.ZONE:
        return f.location_zone or "unknown"
    if by is Stratifier.STATION:
        return _station_key(f)
    if by is Stratifier.ISSUE_DATE:
        return f.issue_time.date().isoformat()
    if by is Stratifier.CYCLE:
        return _cycle_key(f)
    raise ValueError(f"Unknown stratifier: {by}")


def stratified_forecast_metrics(
    samples: Sequence[TrainingSample],
    error_fn: Callable[[TrainingSample], Optional[float]],
    by: Stratifier,
    quantiles: Sequence[float] = DEFAULT_QUANTILES,
) -> Dict[Any, ForecastMetrics]:
    """
    Group samples by a stratifier and compute forecast metrics per stratum.
    `error_fn(sample) -> signed error or None`. Deterministic key ordering.
    """
    buckets: Dict[Any, List[float]] = {}
    for s in samples:
        e = error_fn(s)
        if e is None:
            continue
        buckets.setdefault(_stratum_key(s.features, by), []).append(e)
    return {k: compute_forecast_metrics(buckets[k], quantiles)
            for k in sorted(buckets.keys(), key=lambda x: (str(type(x)), x))}


# =====================================================================
# Weight diagnostics (multi-model ready; honest for IFS-only)
# =====================================================================
@dataclass
class WeightDiagnostics:
    n_rows: int
    mean_weight: Dict[str, float]
    median_weight: Dict[str, float]
    weight_min: Dict[str, float]
    weight_max: Dict[str, float]
    by_lead: Dict[str, Dict[str, float]] = field(default_factory=dict)   # lead -> {model: mean}
    by_zone: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_period: Dict[str, Dict[str, float]] = field(default_factory=dict)  # issue_date -> {model: mean}
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def weight_diagnostics(samples: Sequence[TrainingSample], candidate,
                       models: Sequence[str] = CANONICAL_MODELS) -> WeightDiagnostics:
    """
    Aggregate learned model weights (mean/median/min/max, and by lead/zone/
    period). For IFS-only data this correctly reports IFS≈1, GFS=0, ICON=0.
    Ready for GFS+IFS+ICON once available; nothing is fabricated.
    """
    per_model: Dict[str, List[float]] = {m: [] for m in CANONICAL_MODELS}
    by_lead: Dict[str, Dict[str, List[float]]] = {}
    by_zone: Dict[str, Dict[str, List[float]]] = {}
    by_period: Dict[str, Dict[str, List[float]]] = {}

    for s in samples:
        f = s.features
        wp = candidate.get_weights(f, models=list(models))
        w = {"gfs": wp.gfs_weight, "ifs": wp.ifs_weight, "icon": wp.icon_weight}
        for m in CANONICAL_MODELS:
            per_model[m].append(w[m])
        lk = str(f.lead_time_hours)
        zk = f.location_zone or "unknown"
        pk = f.issue_time.date().isoformat()
        for store, key in ((by_lead, lk), (by_zone, zk), (by_period, pk)):
            d = store.setdefault(key, {m: [] for m in CANONICAL_MODELS})
            for m in CANONICAL_MODELS:
                d[m].append(w[m])

    def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
    def _median(xs): return statistics.median(xs) if xs else 0.0

    def _agg_group(store):
        return {k: {m: _mean(store[k][m]) for m in CANONICAL_MODELS}
                for k in sorted(store.keys())}

    return WeightDiagnostics(
        n_rows=len(samples),
        mean_weight={m: _mean(per_model[m]) for m in CANONICAL_MODELS},
        median_weight={m: _median(per_model[m]) for m in CANONICAL_MODELS},
        weight_min={m: (min(per_model[m]) if per_model[m] else 0.0) for m in CANONICAL_MODELS},
        weight_max={m: (max(per_model[m]) if per_model[m] else 0.0) for m in CANONICAL_MODELS},
        by_lead=_agg_group(by_lead),
        by_zone=_agg_group(by_zone),
        by_period=_agg_group(by_period),
        note=("Weight diagnostics reflect available models only. With IFS-only "
              "data, IFS≈1 and GFS/ICON=0 by construction; not a multi-model "
              "result."),
    )


# =====================================================================
# Model-selection protocol (TRAIN + VALIDATION only; never TEST)
# =====================================================================
@dataclass
class SelectionResult:
    ranked: List[Tuple[str, Dict[str, Any]]]   # (candidate_name, criteria) best-first
    selected: Optional[str]
    criterion: str
    rationale: str
    forecast_separable: bool  # whether final-forecast metric can separate candidates yet

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def select_candidate(
    validation_samples: Sequence[TrainingSample],
    candidates: Dict[str, Any],
    models: Sequence[str] = CANONICAL_MODELS,
) -> SelectionResult:
    """
    Deterministic candidate selection using VALIDATION only.

    PRIMARY criterion (once multiple NWP models are available): final blended
    FORECAST MAE on VALIDATION. SECONDARY: forecast RMSE, then |bias|, then
    robustness (max degradation across leads/zones). TERTIARY tie-break:
    reliability-prediction MAE, then candidate name (deterministic).

    CRITICAL: when only one NWP model is available (current V1: IFS only) every
    candidate's blend equals that model's forecast, so forecast metrics are
    IDENTICAL and cannot separate candidates. In that case `forecast_separable`
    is False and selection falls back to reliability-prediction MAE ONLY as a
    provisional ordering — explicitly NOT a claim that the top candidate is the
    best FINAL forecaster. Final selection must wait for multi-model data.
    """
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for name in sorted(candidates.keys()):
        cand = candidates[name]
        fm = evaluate_helios_blend(validation_samples, cand, models)
        rm = evaluate_reliability(validation_samples, cand, models)
        rows.append((name, {
            "forecast_mae": fm.mae, "forecast_rmse": fm.rmse, "forecast_bias": fm.bias,
            "reliability_mae": rm.reliability_mae, "reliability_rmse": rm.reliability_rmse,
        }))

    # Determine whether forecast metrics separate candidates.
    maes = [c["forecast_mae"] for _, c in rows if c["forecast_mae"] is not None]
    separable = len(set(round(m, 9) for m in maes)) > 1 if maes else False

    if separable:
        def key(item):
            _, c = item
            return (c["forecast_mae"], c["forecast_rmse"], abs(c["forecast_bias"] or 0.0),
                    c["reliability_mae"] if c["reliability_mae"] is not None else float("inf"))
        criterion = "validation blended-FORECAST MAE (primary), RMSE, |bias|, reliability MAE"
        rationale = ("Multiple NWP models available: candidates produce different "
                     "blended forecasts, so final-forecast MAE is the decisive, "
                     "separating criterion.")
    else:
        def key(item):
            name, c = item
            return (c["reliability_mae"] if c["reliability_mae"] is not None else float("inf"),
                    c["reliability_rmse"] if c["reliability_rmse"] is not None else float("inf"),
                    name)
        criterion = ("PROVISIONAL: reliability-prediction MAE (final-forecast metric "
                     "cannot separate candidates on single-model data)")
        rationale = ("Only one NWP model available (IFS-only V1): every candidate's "
                     "blend equals the IFS forecast, so forecast metrics are identical "
                     "and CANNOT select a final forecaster. Ranking by reliability-"
                     "prediction MAE is provisional only; final selection must wait "
                     "for GFS+IFS+ICON data and use final-forecast MAE.")

    ranked = sorted(rows, key=key)
    selected = ranked[0][0] if (ranked and separable) else None
    return SelectionResult(ranked=ranked, selected=selected, criterion=criterion,
                           rationale=rationale, forecast_separable=separable)


# =====================================================================
# Locked one-shot TEST protocol (SPEC ONLY — not executed here)
# =====================================================================
@dataclass
class LockedTestProtocol:
    """
    Specification of the single, final, locked TEST evaluation.

    TEST is evaluated EXACTLY ONCE, after ALL of the following are FROZEN using
    TRAIN/VALIDATION only:
      - candidate/model selection
      - hyperparameters
      - blend configuration
      - thresholds
      - preprocessing decisions / feature set
    The locked candidate is NOT retrained on TEST and NOTHING is tuned from TEST
    results. TEST is the final unseen evaluation of generalization.
    """
    executed: bool = False
    compare_models: Tuple[str, ...] = ("gfs", "ifs", "icon", "simple_average", "helios")
    metrics: Tuple[str, ...] = ("mae", "rmse", "bias", "median_abs_error", "quantiles")
    stratifications: Tuple[str, ...] = ("lead_time_hours", "location_zone")
    rules: Tuple[str, ...] = (
        "TEST used exactly once, after all decisions frozen on TRAIN/VALIDATION.",
        "No retraining on TEST; no tuning/selection from TEST results.",
        "HELIOS uses the locked candidate + locked preprocessing + locked weights.",
        "Simple Average averages only participating compatible available models.",
        "Report correlated-data caveat and grouped counts alongside TEST metrics.",
    )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =====================================================================
# Multi-model comparison design (temperature)
# =====================================================================
@dataclass
class MultiModelComparisonDesign:
    """
    Design of the eventual GFS+IFS+ICON comparison. Not executed here.
    """
    entrants: Tuple[str, ...] = ("gfs", "ifs", "icon", "simple_average", "helios")
    variable: str = "temperature_2m_c"
    compatibility_requirements: Tuple[str, ...] = (
        "same variable", "same units (degC)", "same valid_time",
        "compatible spatial representation (station-anchored / regridded to grid)",
        "compatible forecast semantics (instantaneous 2 m temperature)",
    )
    rules: Tuple[str, ...] = (
        "Missing model != zero; unavailable models excluded from Simple Average.",
        "Simple Average uses only participating compatible available models.",
        "HELIOS forecast = sum(model_forecast * learned_weight) over available models.",
        "Precipitation (accumulation semantics) is OUT OF SCOPE for this "
        "temperature-only protocol and must be handled separately when added.",
    )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =====================================================================
# Walk-forward design (future; not executed here)
# =====================================================================
@dataclass
class WalkForwardDesign:
    """
    Future chronological rolling / walk-forward evaluation design.

    Structure (documented; not executed now):
      - Partition the timeline into ordered folds by issue_time.
      - For each fold k: TRAIN on all issue_times < t_k, VALIDATE on
        [t_k, t_{k+1}); the model at fold k may only use information available
        before each example's issue_time.
      - Historical reliability features must use strictly-prior outcomes
        (period_end < issue_time), exactly as DatasetBuilder already enforces.
      - Future observations never enter features; folds never look ahead.
      - The final locked TEST remains the last, latest, untouched block and is
        evaluated once at the very end.
    This mirrors HELIOS's intended continuous learning from forecast errors and
    scales to much larger post-V1 datasets (more folds, longer history).
    """
    enabled: bool = False
    fold_boundary_basis: str = "issue_time"
    min_train_folds_before_validation: int = 1
    historical_reliability_cutoff: str = "period_end < issue_time (strict)"
    look_ahead_allowed: bool = False
    notes: Tuple[str, ...] = (
        "Rolling origin: expand TRAIN as time advances; validate on the next block.",
        "Never random; folds strictly ordered by issue_time.",
        "Reuses DatasetBuilder leakage-safe historical reliability computation.",
        "Final TEST block evaluated exactly once at the end (LockedTestProtocol).",
    )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_protocol_summary() -> Dict[str, Any]:
    """Machine-readable summary of the full evaluation protocol design."""
    return {
        "error_convention": "error = forecast - observation; MAE=mean|e|, RMSE=sqrt(mean e^2), bias=mean e",
        "metrics": ["mae", "rmse", "bias", "sample_count", "median_abs_error", "abs_error_quantiles"],
        "stratifications": [s.value for s in Stratifier],
        "default_leads": list(DEFAULT_LEADS),
        "reliability_vs_forecast": (
            "Reliability-prediction accuracy (predicted |error| vs actual |error|) is "
            "reported SEPARATELY from final-forecast accuracy (blend vs observation). "
            "Final-forecast accuracy is decisive and needs multiple NWP models."
        ),
        "selection": "TRAIN+VALIDATION only; primary=validation forecast MAE; TEST never used for selection.",
        "locked_test": LockedTestProtocol().as_dict(),
        "multi_model": MultiModelComparisonDesign().as_dict(),
        "walk_forward": WalkForwardDesign().as_dict(),
        "correlated_data_caveat": CorrelatedDataNote(0, 0, 0, 0, 0).caveat,
    }
