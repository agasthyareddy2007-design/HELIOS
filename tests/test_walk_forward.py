"""
HELIOS Walk-Forward Tests (synthetic fixtures; no real data).

Coverage:
1.  fold chronological boundaries (train issue_time strictly < window_start;
    val in [window_start, window_end))
2.  no future-feature leakage (train_max_issue < window_start for every fold)
3.  preprocessing fit only on fold training data (candidate preprocessor means
    reflect the fold-train subset, not the whole pool)
4.  fold isolation (candidates rebuilt per fold; no state carried over)
5.  TEST remains untouched (samples at/after TEST_BOUNDARY never enter any fold)
6.  reproducibility (identical folds + identical metrics on repeat)
7.  missing-model handling (Simple Average / blend use available models only)
8.  metric aggregation (aggregate_stability math is correct)
"""

import sys
import math
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np

from ml.feature_contract import FeatureVector, Target, TrainingSample
from ml.candidate_interface import WeightPrediction, ReliabilityPrediction
from ml import walk_forward as wf
from ml import evaluation_protocol as ep


def _sample(i, issue, model="ifs", gfs=25.0, ifs=25.5, icon=24.8, obs=24.0,
            lead=24, zone="central", lat=20.0, lon=78.0):
    valid = issue + timedelta(hours=lead)
    own = {"gfs": gfs, "ifs": ifs, "icon": icon}[model]
    f = FeatureVector(
        model=model, issue_time=issue, valid_time=valid, lead_time_hours=lead,
        latitude=lat, longitude=lon, location_zone=zone, variable="temperature_2m_c",
        hour_of_day=valid.hour, day_of_year=valid.timetuple().tm_yday, month=valid.month,
        season="winter", gfs_value=gfs, ifs_value=ifs, icon_value=icon,
        forecast_spread=0.5, forecast_range=0.7, model_agreement=0.9,
        gfs_rmse_7day=1.2, ifs_rmse_7day=1.1, icon_rmse_7day=1.3,
        gfs_mae_7day=0.9, ifs_mae_7day=0.8, icon_mae_7day=1.0,
        gfs_bias_7day=0.1, ifs_bias_7day=-0.05, icon_bias_7day=0.15,
        gfs_available=gfs is not None, ifs_available=ifs is not None,
        icon_available=icon is not None, feature_computation_time=issue)
    e = own - obs
    t = Target(observed_value=obs, forecast_error=e, absolute_error=abs(e),
               observation_time=valid + timedelta(hours=1), observation_source="noaa_isd",
               observation_quality_score=1.0)
    return TrainingSample(features=f, target=t, verification_id=f"s_{i:05d}",
                          verified_at=valid + timedelta(hours=2))


def _pool(days=12, per_day=30, start=datetime(2025, 1, 1)):
    samples = []
    i = 0
    rng = np.random.RandomState(0)
    for d in range(days):
        issue = start + timedelta(days=d)
        for p in range(per_day):
            m = ("gfs", "ifs", "icon")[p % 3]
            samples.append(_sample(i, issue, model=m,
                                   gfs=25 + rng.randn(), ifs=25.5 + rng.randn(),
                                   icon=24.8 + rng.randn(), obs=24 + rng.randn(),
                                   lat=20 + (p % 5) * 0.3))
            i += 1
    return samples


class StubCandidate:
    """Records the training set it received; predicts constant reliability."""
    def __init__(self, rel=1.0):
        self.rel = rel
        self.seen_ids = None
        from ml.preprocessing import FeaturePreprocessor
        self.preprocessor = FeaturePreprocessor()

    def train(self, training_samples, validation_samples=None):
        self.seen_ids = [s.verification_id for s in training_samples]
        self.preprocessor.fit(training_samples)  # fold-train only
        return None

    def predict_reliability(self, features, models=("gfs", "ifs", "icon")):
        return {m: ReliabilityPrediction(model=m, expected_absolute_error=self.rel,
                                         expected_squared_error=self.rel ** 2,
                                         prediction_time=datetime.utcnow()) for m in models}

    def get_weights(self, features, models=("gfs", "ifs", "icon"), epsilon=0.001):
        avail = {"gfs": features.gfs_available and features.gfs_value is not None,
                 "ifs": features.ifs_available and features.ifs_value is not None,
                 "icon": features.icon_available and features.icon_value is not None}
        raw = {m: (1.0 / max(self.rel, epsilon)) for m in models if avail.get(m)}
        tot = sum(raw.values())
        w = {m: (raw.get(m, 0.0) / tot if tot else 0.0) for m in ("gfs", "ifs", "icon")}
        rp = self.predict_reliability(features, models)
        return WeightPrediction(gfs_weight=w["gfs"], ifs_weight=w["ifs"], icon_weight=w["icon"],
                                gfs_reliability=rp["gfs"], ifs_reliability=rp["ifs"],
                                icon_reliability=rp["icon"], gfs_available=avail["gfs"],
                                ifs_available=avail["ifs"], icon_available=avail["icon"],
                                prediction_time=datetime.utcnow())


def test_fold_boundaries_and_no_future_leakage():
    print("TEST: fold boundaries + no future-feature leakage")
    pool = _pool(12)
    starts = sorted({s.features.issue_time for s in pool})[-5:]
    folds = wf.make_walkforward_folds(pool, starts, window_hours=24, min_train=1)
    assert len(folds) >= 3
    for f in folds:
        # every train issue_time strictly before window_start
        assert all(s.features.issue_time < f.window_start for s in f.train)
        # every val issue_time within [window_start, window_end)
        assert all(f.window_start <= s.features.issue_time < f.window_end for s in f.val)
        assert f.train_max_issue() < f.window_start
    print(f"  ✓ {len(folds)} folds; train strictly precedes each val window")
    print()
    return True


def test_test_boundary_never_in_fold():
    print("TEST: TEST region never enters any fold")
    # pool spanning across TEST_BOUNDARY
    pool = []
    i = 0
    for d in range(6):
        issue = wf.TEST_BOUNDARY - timedelta(days=3) + timedelta(days=d)  # crosses boundary
        for p in range(9):
            pool.append(_sample(i, issue, model=("gfs", "ifs", "icon")[p % 3])); i += 1
    starts = sorted({s.features.issue_time for s in pool})
    folds = wf.make_walkforward_folds(pool, starts, window_hours=24, min_train=1)
    for f in folds:
        assert all(s.features.issue_time < wf.TEST_BOUNDARY for s in f.train + f.val)
        assert f.window_start < wf.TEST_BOUNDARY
    # no val window should include a post-boundary issue_time
    all_val_it = [s.features.issue_time for f in folds for s in f.val]
    assert all(it < wf.TEST_BOUNDARY for it in all_val_it)
    print("  ✓ no sample at/after TEST_BOUNDARY appears in any fold")
    print()
    return True


def test_fold_preprocessing_isolation_and_fold_isolation():
    print("TEST: preprocessing fit only on fold-train + fold isolation")
    pool = _pool(10)
    starts = sorted({s.features.issue_time for s in pool})[-4:]
    folds = wf.make_walkforward_folds(pool, starts, window_hours=24, min_train=1)

    built = []
    def factory():
        c = {"kernel": StubCandidate(1.0), "xgboost": StubCandidate(1.0), "mlp": StubCandidate(1.0)}
        built.append(c)
        return c
    for f in folds:
        wf.evaluate_fold(f, factory, kernel_support_limit=100000, models=("gfs", "ifs", "icon"))
    # A fresh candidate dict built per fold (fold isolation).
    assert len(built) == len(folds)
    # The xgboost stub's training ids for a fold must equal that fold's train ids
    # (preprocessing/fit only on fold-train, no pool leakage).
    for f, c in zip(folds, built):
        seen = set(c["xgboost"].seen_ids)
        assert seen == {s.verification_id for s in f.train}
    print(f"  ✓ per-fold candidates; fit only on fold-train ({len(folds)} folds)")
    print()
    return True


def test_missing_model_handling():
    print("TEST: missing-model handling in fold evaluation")
    # icon missing for all
    pool = []
    i = 0
    for d in range(8):
        issue = datetime(2025, 1, 1) + timedelta(days=d)
        for p in range(9):
            pool.append(_sample(i, issue, model="ifs", icon=None)); i += 1
    starts = sorted({s.features.issue_time for s in pool})[-3:]
    folds = wf.make_walkforward_folds(pool, starts, window_hours=24, min_train=1)
    def factory():
        return {"kernel": StubCandidate(1.0), "xgboost": StubCandidate(1.0), "mlp": StubCandidate(1.0)}
    fr = wf.evaluate_fold(folds[0], factory, kernel_support_limit=100000, models=("gfs", "ifs", "icon"))
    # icon individual has 0 rows (all missing); simple average from gfs+ifs only
    assert fr.metrics["icon"]["n_rows"] == 0
    assert fr.metrics["simple_average"]["n_rows"] == fr.n_val
    print("  ✓ missing icon -> 0 icon rows; SA over available (gfs,ifs)")
    print()
    return True


def test_reproducibility():
    print("TEST: reproducible folds + metrics")
    pool = _pool(10)
    starts = sorted({s.features.issue_time for s in pool})[-4:]
    f1 = wf.make_walkforward_folds(pool, starts, window_hours=24, min_train=1)
    f2 = wf.make_walkforward_folds(pool, starts, window_hours=24, min_train=1)
    assert [ (f.window_start, len(f.train), len(f.val)) for f in f1] == \
           [ (f.window_start, len(f.train), len(f.val)) for f in f2]
    def factory():
        return {"kernel": StubCandidate(1.0), "xgboost": StubCandidate(1.0), "mlp": StubCandidate(1.0)}
    r1 = wf.evaluate_fold(f1[0], factory, 100000, ("gfs", "ifs", "icon"))
    r2 = wf.evaluate_fold(f1[0], factory, 100000, ("gfs", "ifs", "icon"))
    assert r1.metrics["simple_average"]["mae"] == r2.metrics["simple_average"]["mae"]
    assert r1.metrics["gfs"]["mae"] == r2.metrics["gfs"]["mae"]
    print("  ✓ identical folds + identical metrics on repeat")
    print()
    return True


def test_metric_aggregation():
    print("TEST: metric aggregation math")
    # Build 3 synthetic FoldResults with known MAEs.
    def mkfr(idx, sa, xg):
        fr = wf.FoldResult(index=idx, window_start="w", window_end="e", n_train=10, n_val=5,
                           n_val_issue_times=1, n_val_stations=1, train_max_issue=None,
                           val_min_issue=None, val_max_issue=None,
                           train_strictly_before_val=True, no_test_in_fold=True)
        fr.metrics = {"simple_average": {"mae": sa}, "xgboost": {"mae": xg}}
        return fr
    frs = [mkfr(0, 2.0, 1.0), mkfr(1, 2.0, 1.5), mkfr(2, 2.0, 3.0)]
    agg = wf.aggregate_stability(frs, ["simple_average", "xgboost"])
    x = agg["per_candidate"]["xgboost"]
    assert abs(x["mean_fold_mae"] - (1.0 + 1.5 + 3.0) / 3) < 1e-9
    assert abs(x["median_fold_mae"] - 1.5) < 1e-9
    assert x["worst_fold_mae"] == 3.0 and x["best_fold_mae"] == 1.0
    assert x["folds_beating_sa"] == 2  # 1.0 and 1.5 beat 2.0, 3.0 does not
    # mean improvement vs SA: ((2-1)/2 + (2-1.5)/2 + (2-3)/2)/3 = (0.5+0.25-0.5)/3
    exp = ((0.5) + (0.25) + (-0.5)) / 3 * 100
    assert abs(x["mean_improvement_vs_sa_pct"] - exp) < 1e-6
    print("  ✓ mean/median/worst/best/beats/improvement correct")
    print()
    return True
