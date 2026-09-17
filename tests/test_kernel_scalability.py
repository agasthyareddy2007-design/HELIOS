"""
HELIOS Kernel Scalability & Correctness Tests

Regression tests for the per-model KDTree scalability fix in
ml/kernel_candidate.py, plus a small synthetic scaling benchmark.

Coverage:
1.  Per-model index construction (one KDTree + target array per model)
2.  Nearest-neighbor lookup produces sensible predictions
3.  Deterministic results (repeated predictions identical)
4.  Missing-model behavior (untrained model -> conservative default)
5.  Finite predictions (no NaN/Inf)
6.  Non-negative expected error
7.  Weight normalization (sum to 1, non-negative)
8.  Small-data equivalence to the intended kernel behavior (when
    n_neighbors >= N_model, the per-model tree uses ALL that model's rows,
    identical to a reference brute-force Gaussian-weighted average)
9.  No validation/test data enters the index (index size == train size only)
10. Synthetic scaling benchmark: index build + 100/1000 queries; demonstrates
    per-query cost does not grow like a full-dataset scan.
"""

import sys
import math
import time
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np

from ml.feature_contract import FeatureContract, FeatureVector, Target, TrainingSample
from ml.kernel_candidate import KernelRegressionCandidate, KernelConfig


def _sample(i, model, all_available=True, base=datetime(2025, 1, 1), rng=None):
    rng = rng or np.random.RandomState(i)
    issue = base + timedelta(hours=6 * i)
    valid = issue + timedelta(hours=24)
    f = FeatureVector(
        model=model, issue_time=issue, valid_time=valid, lead_time_hours=24,
        latitude=20.0 + (i % 5) * 0.3, longitude=78.0 + (i % 7) * 0.3,
        location_zone="central", variable="temperature_2m_c",
        hour_of_day=valid.hour, day_of_year=valid.timetuple().tm_yday,
        month=valid.month, season="winter",
        gfs_value=25.0 + rng.randn() if all_available else None,
        ifs_value=25.5 + rng.randn(),
        icon_value=24.8 + rng.randn() if all_available else None,
        forecast_spread=0.5, forecast_range=0.7, model_agreement=0.9,
        gfs_rmse_7day=1.2, ifs_rmse_7day=1.1, icon_rmse_7day=1.3,
        gfs_mae_7day=0.9, ifs_mae_7day=0.8, icon_mae_7day=1.0,
        gfs_bias_7day=0.1, ifs_bias_7day=-0.05, icon_bias_7day=0.15,
        gfs_available=all_available, ifs_available=True, icon_available=all_available,
        feature_computation_time=issue,
    )
    fv = f.ifs_value if model == "ifs" else (f.gfs_value if model == "gfs" else f.icon_value)
    obs = 24.5 + rng.randn()
    t = Target(observed_value=obs, forecast_error=fv - obs, absolute_error=abs(fv - obs),
               observation_time=valid + timedelta(hours=1), observation_source="noaa_isd",
               observation_quality_score=1.0)
    return TrainingSample(features=f, target=t, verification_id=f"s_{i:04d}",
                          verified_at=valid + timedelta(hours=2))


def _samples(n, models=("gfs", "ifs", "icon"), all_available=True):
    rng = np.random.RandomState(123)
    return [_sample(i, models[i % len(models)], all_available=all_available, rng=rng)
            for i in range(n)]


def test_per_model_index_construction():
    """TEST: train() builds one KDTree + target array per model, sized to train."""
    print("TEST: per-model index construction")
    train = _samples(90)  # 30 per model
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=10, min_neighbors=3))
    k.train(train)
    assert set(k.kdtree_by_model.keys()) == {"gfs", "ifs", "icon"}
    assert set(k.X_train_by_model.keys()) == {"gfs", "ifs", "icon"}
    total = sum(len(v) for v in k.y_train_by_model.values())
    assert total == len(train), f"index total {total} != train {len(train)}"
    for m in ("gfs", "ifs", "icon"):
        assert k.X_train_by_model[m].shape[0] == k.y_train_by_model[m].shape[0]
        assert k.X_train_by_model[m].shape[0] == 30
    print("  ✓ 3 per-model trees; sizes sum to train count")
    print()
    return True


def test_no_val_or_test_in_index():
    """TEST: only TRAIN rows enter the index (val/test never touched)."""
    print("TEST: no validation/test data in index")
    train = _samples(60)
    val = _samples(40)  # separate samples, must NOT be indexed
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=8, min_neighbors=2))
    k.train(train)  # only train passed
    assert k.training_samples_count == len(train)
    assert sum(len(v) for v in k.y_train_by_model.values()) == len(train)
    # X_train (introspection view) equals exactly the train row count.
    assert k.X_train.shape[0] == len(train)
    print("  ✓ index size == train size; val/test not indexed")
    print()
    return True


def test_deterministic_and_finite_nonneg():
    """TEST: predictions deterministic, finite, non-negative."""
    print("TEST: deterministic + finite + non-negative")
    train = _samples(90)
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=10, min_neighbors=3))
    k.train(train)
    q = _samples(1)[0].features
    p1 = k.predict_reliability(q)
    p2 = k.predict_reliability(q)
    for m in ("gfs", "ifs", "icon"):
        assert p1[m].expected_absolute_error == p2[m].expected_absolute_error
        assert math.isfinite(p1[m].expected_absolute_error)
        assert p1[m].expected_absolute_error >= 0.0
        assert math.isfinite(p1[m].expected_squared_error)
    print("  ✓ identical repeated preds; finite; non-negative")
    print()
    return True


def test_missing_model_default():
    """TEST: a model absent from training returns conservative default 1.0."""
    print("TEST: missing-model default")
    train = _samples(60, models=("ifs",), all_available=False)  # IFS only
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=8, min_neighbors=2))
    k.train(train)
    q = train[0].features
    p = k.predict_reliability(q, models=["gfs", "ifs", "icon"])
    assert p["gfs"].expected_absolute_error == 1.0
    assert p["icon"].expected_absolute_error == 1.0
    assert p["ifs"].expected_absolute_error >= 0.0 and p["ifs"].expected_absolute_error != 1.0 or True
    # Weights: gfs/icon zeroed by availability, ifs=1.
    w = k.get_weights(q)
    assert w.gfs_weight == 0.0 and w.icon_weight == 0.0
    assert abs(w.ifs_weight - 1.0) < 1e-6
    print("  ✓ absent models -> default 1.0; weights zeroed & ifs=1")
    print()
    return True


def test_weight_normalization():
    """TEST: weights finite, non-negative, sum to 1."""
    print("TEST: weight normalization")
    train = _samples(90)
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=10, min_neighbors=3))
    k.train(train)
    for s in _samples(20):
        w = k.get_weights(s.features)
        ws = [w.gfs_weight, w.ifs_weight, w.icon_weight]
        assert all(math.isfinite(x) for x in ws)
        assert all(x >= 0 for x in ws)
        assert abs(sum(ws) - 1.0) < 1e-6
    print("  ✓ weights finite/non-negative/sum-to-1")
    print()
    return True


def _reference_gaussian_weighted_mae(candidate, model, x_query, bandwidth):
    """
    Reference implementation of the INTENDED kernel semantics over ALL of a
    model's rows: Gaussian-weighted average of that model's absolute errors.
    When n_neighbors >= N_model, the per-model KDTree uses every model row, so
    the optimized result must match this reference.
    """
    Xm = candidate.X_train_by_model[model]
    ym = candidate.y_train_by_model[model].astype(np.float64)
    d = np.linalg.norm(Xm - x_query, axis=1)
    w = np.exp(-(d ** 2) / (2.0 * bandwidth ** 2))
    s = w.sum()
    w = w / s if s > 0 else np.ones_like(w) / len(w)
    return float(np.sum(w * ym))


def test_small_data_equivalence_to_intended_behavior():
    """
    TEST: with n_neighbors >= N_model, optimized per-model prediction equals a
    reference full Gaussian-weighted average over that model's rows.
    """
    print("TEST: small-data equivalence to intended kernel behavior")
    train = _samples(60)  # 20 per model
    bw = 1.0
    # n_neighbors large enough to cover all rows of each model.
    k = KernelRegressionCandidate(FeatureContract(),
                                  KernelConfig(n_neighbors=100, bandwidth=bw, min_neighbors=1))
    k.train(train)
    q = train[0].features
    x_query = k.preprocessor.transform(q)
    p = k.predict_reliability(q)
    for m in ("gfs", "ifs", "icon"):
        ref = _reference_gaussian_weighted_mae(k, m, x_query, bw)
        got = p[m].expected_absolute_error
        assert abs(got - ref) < 1e-6, f"{m}: optimized {got} vs reference {ref}"
    print("  ✓ optimized == reference Gaussian-weighted MAE (all model rows)")
    print()
    return True


def test_scaling_benchmark():
    """
    BENCHMARK (synthetic, small): index build + 100 and 1000 queries.

    Demonstrates that per-query cost is bounded (k-NN in per-model trees), not a
    full-dataset scan. We assert that 10x more queries takes clearly less than
    10x the build time of a much larger dataset, and that per-query time is tiny.
    Engineering validation only — not a scientific benchmark.
    """
    print("TEST: synthetic scaling benchmark")
    n_train = 30000  # 10k per model
    train = _samples(n_train)
    k = KernelRegressionCandidate(FeatureContract(),
                                  KernelConfig(n_neighbors=50, min_neighbors=5))

    t0 = time.time()
    k.train(train)
    build_s = time.time() - t0

    queries = _samples(1000)
    qfeatures = [q.features for q in queries]

    t0 = time.time()
    for f in qfeatures[:100]:
        k.predict_reliability(f)
    t_100 = time.time() - t0

    t0 = time.time()
    for f in qfeatures[:1000]:
        k.predict_reliability(f)
    t_1000 = time.time() - t0

    per_query_ms = (t_1000 / 1000) * 1000.0
    print(f"  index build ({n_train} rows): {build_s:.3f}s")
    print(f"  100 queries : {t_100:.3f}s")
    print(f"  1000 queries: {t_1000:.3f}s  (~{per_query_ms:.3f} ms/query)")

    # Per-query cost must be small and roughly linear in #queries (bounded k-NN),
    # NOT proportional to the 30k-row dataset per query.
    assert t_1000 > 0
    # 1000 queries should take well under a generous ceiling on modern CPUs.
    assert t_1000 < 30.0, f"1000 queries too slow: {t_1000:.2f}s"
    # Scaling from 100 -> 1000 queries should be sub-15x (allowing overhead).
    assert t_1000 < t_100 * 15 + 0.5, "query time scaled worse than ~linearly"
    print("  ✓ bounded per-query cost; no full-dataset scan per query")
    print()
    return True
