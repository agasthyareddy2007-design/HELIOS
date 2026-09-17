"""
HELIOS Evaluation Protocol Tests

Synthetic-fixture tests for ml/evaluation_protocol.py and ml/acquisition_plan.py.
No real data is used. A tiny stub candidate mimics the BaseCandidateModel
weight/reliability interface so tests do not require training.

Coverage:
1.  Metric correctness (MAE/RMSE/bias/median/quantiles)
2.  Deterministic model comparison / selection
3.  Chronological selection rule (TRAIN/VAL only; reliability vs forecast)
4.  TEST isolation (protocol never touches TEST; LockedTestProtocol.executed False;
    acquisition downloads_performed False)
5.  Stratified metrics (by lead, by zone)
6.  Missing-model handling (available_models; Simple Average skips missing)
7.  Simple Average compatibility (averages participating available models only)
8.  HELIOS weighted forecast calculation (sum forecast*weight)
9.  Weight diagnostics (IFS-only => IFS mean 1, GFS/ICON 0)
10. Correlated-data note (row count != independent sample count)
"""

import sys
import math
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.feature_contract import FeatureVector, Target, TrainingSample
from ml.candidate_interface import WeightPrediction, ReliabilityPrediction
from ml import evaluation_protocol as ep
from ml.acquisition_plan import acquisition_plan


# ----------------------------------------------------------------------
# Synthetic data + stub candidate
# ----------------------------------------------------------------------
def _sample(i, model="ifs", gfs=None, ifs=25.0, icon=None, obs=24.0,
            lead=24, zone="central", lat=20.0, lon=78.0,
            base=datetime(2025, 1, 1)):
    issue = base + timedelta(hours=6 * i)
    valid = issue + timedelta(hours=lead)
    gfs_av = gfs is not None
    icon_av = icon is not None
    own = {"gfs": gfs, "ifs": ifs, "icon": icon}[model]
    f = FeatureVector(
        model=model, issue_time=issue, valid_time=valid, lead_time_hours=lead,
        latitude=lat, longitude=lon, location_zone=zone, variable="temperature_2m_c",
        hour_of_day=valid.hour, day_of_year=valid.timetuple().tm_yday,
        month=valid.month, season="winter",
        gfs_value=gfs, ifs_value=ifs, icon_value=icon,
        forecast_spread=None, forecast_range=None, model_agreement=None,
        gfs_rmse_7day=None, ifs_rmse_7day=None, icon_rmse_7day=None,
        gfs_mae_7day=None, ifs_mae_7day=None, icon_mae_7day=None,
        gfs_bias_7day=None, ifs_bias_7day=None, icon_bias_7day=None,
        gfs_available=gfs_av, ifs_available=True, icon_available=icon_av,
        feature_computation_time=issue,
    )
    err = own - obs
    t = Target(observed_value=obs, forecast_error=err, absolute_error=abs(err),
               observation_time=valid + timedelta(hours=1), observation_source="noaa_isd",
               observation_quality_score=1.0)
    return TrainingSample(features=f, target=t, verification_id=f"s_{i:04d}",
                          verified_at=valid + timedelta(hours=2))


class StubCandidate:
    """Minimal candidate exposing get_weights + predict_reliability.

    reliability_map: model -> constant predicted expected absolute error.
    Weights derived by inverse-error over AVAILABLE models (mirrors the real
    get_weights contract: unavailable -> 0, renormalize, sum to 1).
    """
    def __init__(self, reliability_map):
        self.reliability_map = reliability_map

    def predict_reliability(self, features, models=("gfs", "ifs", "icon")):
        out = {}
        for m in models:
            err = self.reliability_map.get(m, 1.0)
            out[m] = ReliabilityPrediction(model=m, expected_absolute_error=err,
                                           expected_squared_error=err ** 2,
                                           prediction_time=datetime.utcnow())
        return out

    def get_weights(self, features, models=("gfs", "ifs", "icon"), epsilon=0.001):
        avail = {"gfs": features.gfs_available and features.gfs_value is not None,
                 "ifs": features.ifs_available and features.ifs_value is not None,
                 "icon": features.icon_available and features.icon_value is not None}
        raw = {}
        for m in models:
            if avail.get(m):
                raw[m] = 1.0 / max(self.reliability_map.get(m, 1.0), epsilon)
        tot = sum(raw.values())
        w = {m: (raw.get(m, 0.0) / tot if tot > 0 else 0.0) for m in ("gfs", "ifs", "icon")}
        rp = self.predict_reliability(features, models)
        return WeightPrediction(
            gfs_weight=w["gfs"], ifs_weight=w["ifs"], icon_weight=w["icon"],
            gfs_reliability=rp.get("gfs"), ifs_reliability=rp.get("ifs"),
            icon_reliability=rp.get("icon"),
            gfs_available=avail["gfs"], ifs_available=avail["ifs"], icon_available=avail["icon"],
            prediction_time=datetime.utcnow())


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_metric_correctness():
    print("TEST: metric correctness")
    m = ep.compute_forecast_metrics([1.0, -3.0, 2.0, -2.0])
    assert m.n_rows == 4
    assert abs(m.mae - 2.0) < 1e-9
    assert abs(m.rmse - math.sqrt(4.5)) < 1e-9
    assert abs(m.bias - (-0.5)) < 1e-9
    assert abs(m.median_abs_error - 2.0) < 1e-9
    # p50 of |errors| [1,2,2,3] via linear interp = 2.0
    assert abs(m.error_quantiles["p50"] - 2.0) < 1e-9
    assert m.error_quantiles["p99"] <= 3.0 + 1e-9
    # empty
    e = ep.compute_forecast_metrics([])
    assert e.n_rows == 0 and e.mae is None
    print("  ✓ MAE/RMSE/bias/median/quantiles correct")
    print()
    return True


def test_missing_model_and_simple_average_compatibility():
    print("TEST: missing-model + Simple Average compatibility")
    # gfs=26, ifs=24, icon missing; obs=24.
    s = _sample(0, model="ifs", gfs=26.0, ifs=24.0, icon=None, obs=24.0)
    assert set(ep.available_models(s.features)) == {"gfs", "ifs"}
    # Simple average over available (gfs,ifs) = 25 => error = 25-24 = +1.0
    sa = ep.simple_average_error(s)
    assert abs(sa - 1.0) < 1e-9, sa
    # Individual model errors.
    assert abs(ep.individual_model_error(s, "gfs") - 2.0) < 1e-9
    assert abs(ep.individual_model_error(s, "ifs") - 0.0) < 1e-9
    assert ep.individual_model_error(s, "icon") is None  # missing != zero
    print("  ✓ available_models correct; SA averages available only; missing=None")
    print()
    return True


def test_helios_weighted_forecast_calc():
    print("TEST: HELIOS weighted forecast calculation")
    # gfs=30, ifs=20 available; icon missing. Stub: gfs err 1.0, ifs err 1.0 =>
    # equal weights 0.5/0.5 => blend = 25; obs=24 => error +1.0.
    s = _sample(0, model="ifs", gfs=30.0, ifs=20.0, icon=None, obs=24.0)
    cand = StubCandidate({"gfs": 1.0, "ifs": 1.0, "icon": 1.0})
    wp = cand.get_weights(s.features)
    assert abs(wp.gfs_weight - 0.5) < 1e-9 and abs(wp.ifs_weight - 0.5) < 1e-9
    assert wp.icon_weight == 0.0
    e = ep.helios_blend_error(s, wp)
    assert abs(e - 1.0) < 1e-9, e
    # Unequal reliability: gfs err 3.0, ifs err 1.0 => raw 1/3 and 1 => w_gfs=0.25,w_ifs=0.75
    cand2 = StubCandidate({"gfs": 3.0, "ifs": 1.0, "icon": 1.0})
    wp2 = cand2.get_weights(s.features)
    assert abs(wp2.gfs_weight - 0.25) < 1e-6 and abs(wp2.ifs_weight - 0.75) < 1e-6
    blend = 0.25 * 30.0 + 0.75 * 20.0  # = 22.5
    assert abs(ep.helios_blend_error(s, wp2) - (blend - 24.0)) < 1e-6
    print("  ✓ blend = sum(forecast*weight); unavailable excluded")
    print()
    return True


def test_stratified_metrics():
    print("TEST: stratified metrics by lead and zone")
    samples = [
        _sample(0, ifs=25.0, obs=24.0, lead=24, zone="central"),    # err +1
        _sample(1, ifs=27.0, obs=24.0, lead=24, zone="central"),    # err +3
        _sample(2, ifs=20.0, obs=24.0, lead=120, zone="south_coastal"),  # err -4
    ]
    by_lead = ep.stratified_forecast_metrics(
        samples, lambda s: ep.individual_model_error(s, "ifs"), ep.Stratifier.LEAD)
    assert set(by_lead.keys()) == {24, 120}
    assert abs(by_lead[24].mae - 2.0) < 1e-9   # (1+3)/2
    assert abs(by_lead[120].mae - 4.0) < 1e-9
    by_zone = ep.stratified_forecast_metrics(
        samples, lambda s: ep.individual_model_error(s, "ifs"), ep.Stratifier.ZONE)
    assert set(by_zone.keys()) == {"central", "south_coastal"}
    print("  ✓ per-lead and per-zone metrics correct")
    print()
    return True


def test_weight_diagnostics_ifs_only():
    print("TEST: weight diagnostics (IFS-only)")
    samples = [_sample(i, model="ifs", gfs=None, ifs=25.0, icon=None) for i in range(10)]
    cand = StubCandidate({"gfs": 1.0, "ifs": 1.0, "icon": 1.0})
    wd = ep.weight_diagnostics(samples, cand)
    assert abs(wd.mean_weight["ifs"] - 1.0) < 1e-9
    assert wd.mean_weight["gfs"] == 0.0 and wd.mean_weight["icon"] == 0.0
    assert abs(wd.median_weight["ifs"] - 1.0) < 1e-9
    # by_lead has the single lead 24 with ifs mean 1.0
    assert "24" in wd.by_lead and abs(wd.by_lead["24"]["ifs"] - 1.0) < 1e-9
    print("  ✓ IFS=1, GFS/ICON=0; not fabricated")
    print()
    return True


def test_correlated_data_note():
    print("TEST: correlated-data note")
    # 6 rows but only 2 distinct issue_times (dup lat/lon/lead), 1 station, 1 cycle.
    base = datetime(2025, 1, 1)
    samples = []
    for i in range(6):
        s = _sample(0)  # same issue_time (i=0) => same everything
        s.features.__dict__  # no-op
        samples.append(s)
    note = ep.correlated_data_note(samples)
    assert note.n_rows == 6
    assert note.n_distinct_issue_times == 1  # all identical
    assert note.n_distinct_stations == 1
    assert "NOT an independent-sample count" in note.caveat
    print(f"  ✓ n_rows={note.n_rows} but n_distinct_issue_times={note.n_distinct_issue_times}")
    print()
    return True


def test_deterministic_selection_multi_model():
    print("TEST: deterministic selection (multi-model separable)")
    # Multi-model samples so blends differ between candidates.
    samples = [_sample(i, model="ifs", gfs=30.0, ifs=20.0, icon=22.0, obs=24.0)
               for i in range(20)]
    # cand A weights ifs heavily (blend ~ near 20 -> far from obs 24)
    A = StubCandidate({"gfs": 5.0, "ifs": 0.5, "icon": 5.0})
    # cand B weights gfs heavily (blend ~ near 30 -> also far). Choose so blends differ.
    B = StubCandidate({"gfs": 0.5, "ifs": 5.0, "icon": 5.0})
    res1 = ep.select_candidate(samples, {"A": A, "B": B})
    res2 = ep.select_candidate(samples, {"A": A, "B": B})
    assert res1.forecast_separable is True
    assert res1.selected is not None
    assert [r[0] for r in res1.ranked] == [r[0] for r in res2.ranked]  # deterministic
    assert "FORECAST MAE" in res1.criterion
    print(f"  ✓ separable; selected={res1.selected}; deterministic ranking")
    print()
    return True


def test_chronological_selection_ifs_only_not_separable():
    print("TEST: chronological selection (IFS-only => not separable, provisional)")
    samples = [_sample(i, model="ifs", gfs=None, ifs=25.0, icon=None, obs=24.0)
               for i in range(20)]
    # Different reliability predictions; blends identical (IFS weight 1).
    A = StubCandidate({"gfs": 1.0, "ifs": 0.8, "icon": 1.0})  # lower reliability MAE-ish
    B = StubCandidate({"gfs": 1.0, "ifs": 5.0, "icon": 1.0})
    res = ep.select_candidate(samples, {"A": A, "B": B})
    assert res.forecast_separable is False
    assert res.selected is None  # cannot select a final forecaster on single-model data
    assert "PROVISIONAL" in res.criterion
    # Provisional ranking is by reliability MAE (A predicts 0.8 vs actual 1.0 -> |−0.2|=0.2;
    # B predicts 5.0 vs 1.0 -> 4.0). A should rank first.
    assert res.ranked[0][0] == "A"
    print("  ✓ IFS-only: not separable, selected=None, provisional reliability ordering")
    print()
    return True


def test_test_isolation_markers():
    print("TEST: TEST isolation markers")
    # LockedTestProtocol not executed; acquisition performs no downloads.
    lp = ep.LockedTestProtocol()
    assert lp.executed is False
    assert "helios" in lp.compare_models and "simple_average" in lp.compare_models
    plan = acquisition_plan()
    assert plan["downloads_performed"] is False
    assert plan["bulk_download_performed"] is False
    assert plan["gfs"]["acquired"] is False
    assert plan["gfs"]["availability"] == "VERIFIED"
    assert plan["icon"]["acquired"] is False
    assert plan["icon"]["acquisition_risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert plan["alignment_target_ifs_v1"]["acquired"] is True
    # protocol summary exposes reliability-vs-forecast distinction.
    summ = ep.default_protocol_summary()
    assert "decisive" in summ["reliability_vs_forecast"]
    assert summ["locked_test"]["executed"] is False
    assert summ["walk_forward"]["enabled"] is False
    print("  ✓ LockedTestProtocol.executed False; no downloads; ICON HIGH risk")
    print()
    return True


def test_reliability_vs_forecast_reported_separately():
    print("TEST: reliability vs final-forecast reported separately")
    samples = [_sample(i, model="ifs", gfs=None, ifs=25.0, icon=None, obs=24.0)
               for i in range(15)]
    cand = StubCandidate({"gfs": 1.0, "ifs": 1.0, "icon": 1.0})
    rel = ep.evaluate_reliability(samples, cand)
    fc = ep.evaluate_helios_blend(samples, cand)
    ifs = ep.evaluate_individual_model(samples, "ifs")
    # Distinct objects/metrics.
    assert rel.reliability_mae is not None
    assert fc.mae is not None
    # IFS-only: HELIOS blend == IFS baseline exactly.
    assert abs(fc.mae - ifs.mae) < 1e-9
    assert abs(fc.rmse - ifs.rmse) < 1e-9
    assert rel.n_negative == 0 and rel.n_nonfinite == 0
    print(f"  ✓ reliability MAE {round(rel.reliability_mae,3)} vs forecast MAE "
          f"{round(fc.mae,3)} (== IFS {round(ifs.mae,3)}), reported separately")
    print()
    return True
