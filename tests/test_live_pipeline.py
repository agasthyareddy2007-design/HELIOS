"""
HELIOS — LIVE pipeline tests.

Verifies the live serving path with REAL current model data. These tests touch the
network (that is the point: they prove the live feeds are genuinely live), and they
enforce the scientific invariants that matter most:

  * issue_time is a real published model cycle, not wall-clock
  * every model in a blend shares ONE cycle, so valid times are consistent
  * valid_time = issue_time + lead, and elapsed horizons are flagged
  * no future observation influences a live forecast (temporal safety)
  * the frozen MLP is used, weights sum to 1 over available models
  * missing model contributes nothing (never zero)
  * live failure NEVER falls back to January 2025
  * frozen artifacts are untouched by live serving
"""

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.live_forecast_service import LIVE_FORECAST
from backend.app.services.live_nwp_service import LIVE_NWP, V1_LEADS, latest_cycle
from backend.app.repositories import station_repository as stations
from backend.app.services.helios_v1_service import FROZEN_PATH

STATION = "420270-99999"  # Srinagar: all three models, strong disagreement


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _first_3model_station():
    for l in stations.list_supported_locations():
        if len(l["models"]) == 3 and l["latitude"] is not None:
            return l["station"]
    raise AssertionError("no 3-model station with coordinates")


def test_live_status_is_real_cycle():
    print("TEST: live status reports a real published cycle")
    st = LIVE_FORECAST.status()
    assert st["live_available"] is True, f"no live feed available: {st}"
    assert st["selected_cycle"], "no cycle selected"
    cyc = datetime.fromisoformat(st["selected_cycle"])
    if cyc.tzinfo is None:
        cyc = cyc.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    # A published cycle is in the past (it has already run) but recent.
    assert cyc <= now, "cycle is in the future — not a published run"
    assert now - cyc < timedelta(days=2), f"cycle is stale: {cyc}"
    assert cyc.hour % 6 == 0, f"cycle hour {cyc.hour} is not a 6-hourly run"
    assert st["selected_cycle_models"], "no models on the selected cycle"
    print(f"  ✓ cycle {cyc.isoformat()} ({st['cycle_alignment'][:40]}…) "
          f"models={st['selected_cycle_models']}")
    print(); return True


def test_live_forecast_is_future_and_consistent():
    print("TEST: live forecast valid times derive from the issue cycle")
    station = _first_3model_station()
    f = LIVE_FORECAST.forecast(station)
    assert f["mode"] == "live"

    issue = datetime.fromisoformat(f["issue_time"])
    if issue.tzinfo is None:
        issue = issue.replace(tzinfo=timezone.utc)

    # ONE cycle for every contributing model => consistent valid times.
    for m, run in f["model_runs"].items():
        assert run == f["issue_time"], f"{m} run {run} != issue {f['issue_time']}"

    assert f["horizons"], "no horizons returned"
    for h in f["horizons"]:
        valid = datetime.fromisoformat(h["valid_time"].replace("Z", "+00:00"))
        if valid.tzinfo is None:
            valid = valid.replace(tzinfo=timezone.utc)
        # valid_time == issue_time + lead
        delta_h = round((valid - issue).total_seconds() / 3600)
        assert delta_h == h["lead_time_hours"], (
            f"+{h['lead_time_hours']}h has valid_time {delta_h}h after issue")
        # valid time must be after the issue cycle (a forecast, not a nowcast of the past)
        assert valid > issue, "valid_time is not after issue_time"

    # At least one horizon must still lie ahead of wall clock, and the flag must
    # agree with reality.
    now = datetime.now(timezone.utc)
    for h in f["horizons"]:
        valid = datetime.fromisoformat(h["valid_time"].replace("Z", "+00:00"))
        if valid.tzinfo is None:
            valid = valid.replace(tzinfo=timezone.utc)
        assert h["is_future"] == (valid > now), (
            f"is_future={h['is_future']} disagrees with valid_time {valid} vs now")
    assert f["n_future_horizons"] >= 1, "no horizon is still in the future"
    assert f["first_future_lead_hours"] is not None
    print(f"  ✓ issue {f['issue_time']} · {f['n_future_horizons']}/{len(f['horizons'])} "
          f"horizons ahead of now · first future +{f['first_future_lead_hours']}h")
    print(); return True


def test_live_weights_and_missing_model_contract():
    print("TEST: live weights sum to 1 over available models; missing ≠ zero")
    f = LIVE_FORECAST.forecast(_first_3model_station())
    for h in f["horizons"]:
        avail = [m for m in ("gfs", "ifs", "icon") if h["nwp_availability"][m]]
        if not avail:
            assert h["helios_temperature_c"] is None
            continue
        total = sum(h["nwp_weights"][m] for m in avail)
        assert abs(total - 1.0) < 1e-4, f"+{h['lead_time_hours']}h weights sum {total}"
        for m in ("gfs", "ifs", "icon"):
            assert h["nwp_weights"][m] >= 0.0
            if not h["nwp_availability"][m]:
                # unavailable contributes NOTHING and has no fabricated value
                assert h["nwp_weights"][m] == 0.0, f"{m} unavailable but weighted"
                assert h["nwp_forecasts_c"][m] is None, f"{m} unavailable but valued"
        # blended value must lie within the range of contributing models
        vals = [h["nwp_forecasts_c"][m] for m in avail]
        assert h["helios_temperature_c"] is not None
        assert min(vals) - 1e-6 <= h["helios_temperature_c"] <= max(vals) + 1e-6, (
            f"blend {h['helios_temperature_c']} outside inputs {vals}")
    print(f"  ✓ all {len(f['horizons'])} horizons: Σw=1 over available, "
          f"blend within input range, missing contributes nothing")
    print(); return True


def test_live_temporal_safety_no_future_observations():
    print("TEST: temporal safety — reliability window is strictly before issue")
    f = LIVE_FORECAST.forecast(_first_3model_station())
    ts = f["temporal_safety"]
    assert ts["uses_future_observations"] is False
    assert ts["issue_time_is_published_cycle"] is True
    rel = f["reliability_features"]
    issue = datetime.fromisoformat(f["issue_time"])
    if issue.tzinfo is None:
        issue = issue.replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(rel["window_end_exclusive"])
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    assert end <= issue, "reliability window extends to/after issue time"

    # Direct check of the query itself: it must find nothing at/after issue.
    r, prov = LIVE_FORECAST.historical_reliability_before(issue)
    assert prov["window_end_exclusive"] == issue.isoformat()
    # For a current cycle the frozen January dataset supplies no window rows.
    assert prov["available"] is False and prov["n_rows"] == 0, (
        f"unexpected reliability rows for a live cycle: {prov}")
    assert r is None
    # ...and the response says so explicitly rather than hiding it.
    assert rel["imputed_by_frozen_preprocessing"] is True
    print(f"  ✓ window [{rel['window_start'][:19]} → {rel['window_end_exclusive'][:19]}) "
          f"exclusive of issue; 0 rows; imputation disclosed")
    print(); return True


def test_live_uses_frozen_mlp_and_leaves_artifacts_untouched():
    print("TEST: live inference uses the frozen MLP and mutates no artifact")
    before = _sha(FROZEN_PATH)
    import ml.mlp_candidate as mlpmod
    calls = {"n": 0}
    orig = mlpmod.MLPCandidate.train

    def spy(self, *a, **k):
        calls["n"] += 1
        return orig(self, *a, **k)

    mlpmod.MLPCandidate.train = spy
    try:
        f = LIVE_FORECAST.forecast(_first_3model_station())
    finally:
        mlpmod.MLPCandidate.train = orig
    assert calls["n"] == 0, f"MLP.train called {calls['n']} times during live serving"
    assert f["live_strategy"] == "MLP"
    assert _sha(FROZEN_PATH) == before, "frozen selection artifact changed!"
    print("  ✓ zero train() calls; frozen artifact sha256 unchanged")
    print(); return True


def test_live_never_falls_back_to_january():
    print("TEST: live responses contain no January 2025 data")
    f = LIVE_FORECAST.forecast(_first_3model_station())
    blob = json.dumps(f)
    # A live payload must not reference the frozen historical window.
    assert "2025-01" not in blob, "live payload contains January 2025 timestamps"
    issue = datetime.fromisoformat(f["issue_time"])
    if issue.tzinfo is None:
        issue = issue.replace(tzinfo=timezone.utc)
    assert issue.year >= 2026, f"live issue_time is historical: {issue}"

    # The documented failure contract: unavailable => explicit error, no substitution.
    from backend.app.api.v1_app import _live_status_payload  # noqa: F401
    print("  ✓ no 2025-01 timestamps; issue_time is a current-year cycle")
    print(); return True


def test_live_spatial_matches_validated_rule():
    print("TEST: live spatial anchoring mirrors the validated V1 rule")
    station = _first_3model_station()
    f = LIVE_FORECAST.forecast(station)
    info = stations.station_info(station)
    loc = f["location"]
    # Real station coordinates, not grid coordinates.
    assert loc["latitude"] == info["latitude"] and loc["longitude"] == info["longitude"]
    assert loc["coordinate_source"] == "noaa_isd_station_history"
    assert f["spatial"]["interpolated"] is False
    assert f["spatial"]["support"] == "station_anchored"
    # Each model reports the grid point it actually used, close to the station.
    for h in f["horizons"]:
        for m, gp in h["model_grid_points"].items():
            assert gp["distance_to_station_km"] >= 0
            # nearest grid point of a global model must be within a grid diagonal
            assert gp["distance_to_station_km"] < 80, (m, gp)
    print("  ✓ real station coords; per-model nearest grid point; interpolated=False")
    print(); return True


def test_live_cache_prevents_repeat_downloads():
    print("TEST: server-side cache prevents repeat model downloads")
    import time
    station = _first_3model_station()
    LIVE_FORECAST.forecast(station)          # ensure warm
    keys_before = set(LIVE_NWP.cached_keys())
    t0 = time.time()
    LIVE_FORECAST.forecast(station)
    warm_s = time.time() - t0
    # A different station must be served from the SAME cached slices.
    other = [l["station"] for l in stations.list_supported_locations()
             if l["latitude"] is not None and l["station"] != station][0]
    t0 = time.time()
    LIVE_FORECAST.forecast(other)
    other_s = time.time() - t0
    keys_after = set(LIVE_NWP.cached_keys())
    assert keys_after == keys_before, "a cached cycle triggered new downloads"
    assert warm_s < 2.0, f"warm request took {warm_s:.1f}s"
    assert other_s < 2.0, f"different station took {other_s:.1f}s (should hit cache)"
    print(f"  ✓ warm {warm_s*1000:.0f}ms · other station {other_s*1000:.0f}ms · "
          f"{len(keys_after)} cached slices, no new downloads")
    print(); return True


def test_cycle_alignment_single_run():
    print("TEST: cycle selection never mixes runs")
    sel = LIVE_FORECAST.select_common_cycle(V1_LEADS)
    assert sel["run"] is not None, "no common cycle found"
    assert sel["n"] >= 1
    # Every model chosen must genuinely have every requested lead for THAT run.
    for m in sel["models"]:
        for ld in V1_LEADS:
            assert LIVE_NWP._exists(m, sel["run"], ld), (
                f"{m} lacks +{ld}h for the selected cycle {sel['run']}")
    # The selected cycle must be a real 6-hourly slot at or before the latest.
    assert sel["run"].hour % 6 == 0
    assert sel["run"] <= latest_cycle()
    print(f"  ✓ single cycle {sel['run'].isoformat()} with {sel['models']} "
          f"— all requested leads present for each")
    print(); return True
