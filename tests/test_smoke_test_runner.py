"""
HELIOS Smoke-Test Infrastructure Tests

Synthetic-fixture tests for scripts/run_real_ml_smoke_test.py and a regression
test for the XGBoost early-stopping (XGBoost >= 2.0 API) fix. No real data is
used; an in-memory SQLite DB is seeded with controlled ForecastVerification rows
and synthetic TrainingSamples are built directly.

Coverage:
1.  deterministic_prefix: chronological, deterministic, no random, no future
2.  TRAIN-only preprocessing fit (fit uses only TRAIN feature statistics)
3.  TEST isolation (subsets contain no TEST ids; subsets within their split)
4.  bounded Kernel training representation (respects kernel_train_limit)
5.  finite predictions (no NaN/Inf; expected abs error >= 0)
6.  weight normalization (sum to 1, non-negative, finite)
7.  missing-model handling (IFS-only => gfs/icon weight 0; not manufactured)
8.  chronological ordering across splits in the smoke-test run
9.  XGBoost early-stopping regression (fit with VALIDATION eval_set works on
    XGBoost 3.x; best_iteration populated)
10. end-to-end run_smoke_test on a small synthetic DB (all candidates ok,
    leakage audit clean)
"""

import sys
import math
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np

from database.connection import DatabaseManager, DatabaseConfig
from database.schema.helios_schema import ForecastVerification
from ml.feature_contract import FeatureContract, FeatureVector, Target, TrainingSample
from ml.xgboost_candidate import XGBoostCandidate, XGBoostConfig
from scripts.run_real_ml_smoke_test import (
    SmokeTestConfig,
    deterministic_prefix,
    evaluate_reliability_on_validation,
    run_smoke_test,
    leakage_audit,
    load_split,
    run_kernel,
)


# ----------------------------------------------------------------------
# Synthetic helpers
# ----------------------------------------------------------------------
def _make_db() -> DatabaseManager:
    db = DatabaseManager(DatabaseConfig(database_url="sqlite:///:memory:"))
    db.initialize(create_tables=True)
    return db


def _verif(vid, model, issue, valid, lead, lat, lon, zone, fv, obs,
           variable="temperature_2m_c"):
    err = fv - obs
    return ForecastVerification(
        verification_id=vid, forecast_id=f"fc_{vid}", model=model,
        issue_time=issue, valid_time=valid, lead_time_hours=lead,
        latitude=lat, longitude=lon, location_zone=zone, variable=variable,
        forecast_value=fv, observed_value=obs, observation_source="noaa_isd",
        observation_quality_score=1.0, observation_time=valid,
        error=err, absolute_error=abs(err), squared_error=err * err,
        verification_time=valid + timedelta(hours=1),
    )


def _seed_synthetic_ifs_db(db, n_days=20, points_per_cycle=40):
    """Seed a synthetic IFS-only DB with multiple cycles and grid points."""
    rows = []
    base = datetime(2025, 1, 1, 0, 0, 0)
    rng = np.random.RandomState(0)  # only for synthetic values, not for splitting
    for d in range(n_days):
        issue = base + timedelta(days=d)
        for p in range(points_per_cycle):
            lat = 20.0 + (p % 8) * 0.5
            lon = 78.0 + (p // 8) * 0.5
            zone = ["central", "north_plains", "south_coastal",
                    "south_plateau", "north_himalaya"][p % 5]
            valid = issue + timedelta(hours=24)
            fv = 25.0 + rng.randn()
            obs = 24.0 + rng.randn()
            rows.append(_verif(f"ifs_{d:02d}_{p:03d}", "ifs", issue, valid, 24,
                               lat, lon, zone, fv, obs))
    with db.get_session() as session:
        for r in rows:
            session.add(r)
    return len(rows)


def _synth_samples(n=60, all_available=True, model_cycle=("gfs", "ifs", "icon")):
    """Build synthetic TrainingSamples directly (bypassing DB)."""
    samples = []
    base = datetime(2025, 1, 1, 0, 0, 0)
    rng = np.random.RandomState(1)
    for i in range(n):
        issue = base + timedelta(hours=6 * i)
        valid = issue + timedelta(hours=24)
        model = model_cycle[i % len(model_cycle)]
        f = FeatureVector(
            model=model, issue_time=issue, valid_time=valid, lead_time_hours=24,
            latitude=20.0, longitude=78.0, location_zone="central",
            variable="temperature_2m_c", hour_of_day=valid.hour,
            day_of_year=valid.timetuple().tm_yday, month=valid.month, season="winter",
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
        samples.append(TrainingSample(features=f, target=t, verification_id=f"s_{i:03d}",
                                      verified_at=valid + timedelta(hours=2)))
    return samples


def _small_config(db_path=":memory:"):
    return SmokeTestConfig(
        db_path=db_path,
        kernel_train_limit=200,
        tree_nn_train_limit=400,
        validation_limit=200,
        kernel_n_neighbors=10,
        kernel_min_neighbors=3,
        xgb_n_estimators=20,
        xgb_max_depth=3,
        xgb_early_stopping_rounds=5,
        mlp_hidden_layers=(16, 8),
        mlp_n_epochs=5,
        mlp_batch_size=64,
    )


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_deterministic_prefix():
    """TEST: deterministic_prefix is chronological, deterministic, bounded."""
    print("TEST: deterministic_prefix")
    samples = _synth_samples(30)
    sub = deterministic_prefix(samples, 10)
    assert len(sub) == 10
    # Same result on repeat.
    assert [s.verification_id for s in sub] == [s.verification_id for s in deterministic_prefix(samples, 10)]
    # Prefix (earliest), not a random selection.
    assert sub == samples[:10]
    # Temporal order preserved & earliest (no future rows beyond index 10).
    assert max(s.features.issue_time for s in sub) == samples[9].features.issue_time
    # limit >= len returns all.
    assert len(deterministic_prefix(samples, 999)) == len(samples)
    assert len(deterministic_prefix(samples, 0)) == len(samples)
    print("  ✓ chronological earliest-N, deterministic, not random")
    print()
    return True


def test_xgboost_early_stopping_regression():
    """
    REGRESSION TEST: XGBoost trains with a VALIDATION eval_set on XGBoost >= 2.0
    (early_stopping_rounds is a constructor arg, not a fit() kwarg).
    """
    print("TEST: XGBoost early-stopping regression (xgboost>=2.0 API)")
    samples = _synth_samples(90)
    train, val = samples[:60], samples[60:]
    c = XGBoostCandidate(FeatureContract(),
                         XGBoostConfig(n_estimators=30, max_depth=3, early_stopping_rounds=5))
    c.train(train, validation_samples=val)  # must NOT raise
    assert set(c.models.keys()) == {"gfs", "ifs", "icon"}
    # best_iteration should be populated when early stopping is active.
    for m, reg in c.models.items():
        bi = getattr(reg, "best_iteration", None)
        assert bi is not None and bi >= 0, f"{m} best_iteration missing"
    # predictions finite & positive
    pred = c.predict_reliability(val[0].features)
    assert math.isfinite(pred["ifs"].expected_absolute_error)
    assert pred["ifs"].expected_absolute_error >= 0
    print("  ✓ trains with VALIDATION eval_set; best_iteration populated; finite preds")
    print()
    return True


def test_train_only_preprocessing_fit():
    """TEST: preprocessing statistics come only from TRAIN, not VALIDATION."""
    print("TEST: TRAIN-only preprocessing fit")
    from ml.preprocessing import FeaturePreprocessor
    train = _synth_samples(40)
    # Fit on TRAIN only.
    pp = FeaturePreprocessor()
    pp.fit(train)
    train_mean = pp.stats.feature_means["ifs_value"]
    # Re-fit including different validation-like samples must change stats,
    # proving fit is data-dependent and NOT using val unless passed.
    val = _synth_samples(40)
    for s in val:  # shift val distribution
        s.features.ifs_value += 100.0
    pp2 = FeaturePreprocessor()
    pp2.fit(train + val)
    assert abs(pp2.stats.feature_means["ifs_value"] - train_mean) > 1.0
    # The candidate path passes ONLY train to fit(); verify via kernel candidate.
    from ml.kernel_candidate import KernelRegressionCandidate, KernelConfig
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=5, min_neighbors=2))
    k.train(train)  # only train passed
    assert abs(k.preprocessor.stats.feature_means["ifs_value"] - train_mean) < 1e-6
    print("  ✓ preprocessing fit reflects TRAIN only")
    print()
    return True


def test_finite_predictions_and_weight_normalization():
    """TEST: predictions finite/non-negative; weights sum to 1, non-negative."""
    print("TEST: finite predictions + weight normalization")
    from ml.kernel_candidate import KernelRegressionCandidate, KernelConfig
    samples = _synth_samples(60)
    train, val = samples[:40], samples[40:]
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=8, min_neighbors=2))
    k.train(train)
    m = evaluate_reliability_on_validation(k, val, ("gfs", "ifs", "icon"))
    assert m.n_nonfinite_predictions == 0
    assert m.n_negative_predictions == 0
    assert m.n_finite_predictions == m.n_val_samples
    # All weight checks pass.
    assert m.n_weights_sum_to_one == m.n_weight_checks
    assert m.n_weights_nonneg == m.n_weight_checks
    assert m.n_weights_finite == m.n_weight_checks
    assert m.n_manufactured_unavailable_forecast == 0
    print(f"  ✓ finite={m.n_finite_predictions}/{m.n_val_samples}; "
          f"weights sum-to-1={m.n_weights_sum_to_one}/{m.n_weight_checks}")
    print()
    return True


def test_missing_model_handling_ifs_only():
    """TEST: IFS-only samples => gfs/icon weight 0, ifs weight 1, none manufactured."""
    print("TEST: missing-model handling (IFS-only)")
    from ml.kernel_candidate import KernelRegressionCandidate, KernelConfig
    samples = _synth_samples(60, all_available=False, model_cycle=("ifs",))
    train, val = samples[:40], samples[40:]
    k = KernelRegressionCandidate(FeatureContract(), KernelConfig(n_neighbors=8, min_neighbors=2))
    k.train(train)
    for s in val:
        w = k.get_weights(s.features)
        assert w.gfs_weight == 0.0 and w.icon_weight == 0.0
        assert abs(w.ifs_weight - 1.0) < 1e-6
        assert not s.features.gfs_available and not s.features.icon_available
    m = evaluate_reliability_on_validation(k, val, ("gfs", "ifs", "icon"))
    assert m.n_manufactured_unavailable_forecast == 0
    print("  ✓ gfs/icon weight 0, ifs weight 1; no manufactured forecasts")
    print()
    return True


def test_bounded_kernel_training_and_test_isolation():
    """
    TEST: end-to-end small run — bounded kernel training, TEST isolation,
    chronological ordering, clean leakage audit.
    """
    print("TEST: bounded kernel training + TEST isolation + ordering (e2e)")
    db = _make_db()
    n = _seed_synthetic_ifs_db(db, n_days=20, points_per_cycle=40)
    assert n == 800
    db.close()

    # Build split from the same in-memory DB by re-seeding a fresh DB the runner
    # will open. Since :memory: is per-connection, seed a file DB in a temp path
    # inside HELIOS instead.
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(prefix="helios_smoke_", suffix=".db",
                                      dir=str(project_root / "data"), delete=False)
    tmp.close()
    try:
        fdb = DatabaseManager(DatabaseConfig(database_url=f"sqlite:///{tmp.name}"))
        fdb.initialize(create_tables=True)
        _seed_synthetic_ifs_db(fdb, n_days=20, points_per_cycle=40)
        fdb.close()

        config = _small_config(db_path=tmp.name)
        report = run_smoke_test(config)

        sanity = report["sanity"]
        assert sanity["train_rows"] > 0 and sanity["validation_rows"] > 0 and sanity["test_rows"] > 0
        # Bounded kernel training subset respected.
        assert sanity["kernel_train_subset"] <= config.kernel_train_limit
        assert sanity["kernel_train_subset"] <= sanity["train_rows"]

        # Leakage audit clean.
        audit = report["leakage_audit"]
        assert audit["split_leakage_violations"] == 0
        assert audit["train_max_lt_val_min"] is True
        assert audit["val_max_lt_test_min"] is True
        assert audit["no_test_ids_in_train"] is True
        assert audit["no_test_ids_in_val"] is True
        assert audit["train_subset_within_train"] is True
        assert audit["val_subset_within_val"] is True
        assert audit["kernel_train_subset_is_prefix"] is True

        # All candidates ran OK and produced finite predictions.
        by_name = {c["name"]: c for c in report["candidates"]}
        assert set(by_name.keys()) == {"kernel_regression", "xgboost", "mlp"}
        for name, c in by_name.items():
            assert c["ok"], f"{name} failed: {c.get('error')}"
            met = c["metrics"]
            assert met["n_nonfinite_predictions"] == 0, name
            assert met["n_negative_predictions"] == 0, name
            assert met["n_weights_sum_to_one"] == met["n_weight_checks"], name
            assert met["n_manufactured_unavailable_forecast"] == 0, name
        print(f"  ✓ e2e ok: train={sanity['train_rows']} val={sanity['validation_rows']} "
              f"test={sanity['test_rows']} kernel_subset={sanity['kernel_train_subset']}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    print()
    return True
