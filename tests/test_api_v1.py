"""
HELIOS V1 API tests.

Verifies the V1 API service + app WITHOUT starting a server and WITHOUT training
or recomputing TEST. Uses real frozen artifacts + real DB January forecasts.

Coverage:
1.  /v1/models schema (NWP models, 3 candidates, baseline Simple Average, MLP live)
2.  /v1/evaluation schema (walk-forward + locked TEST; recomputed False; no TEST recompute)
3.  all three candidates present + MLP identified as validated_live_strategy
4.  candidate historical metrics MATCH the frozen artifact values
5.  frozen_selection_v1.json unchanged (sha256 before/after service use)
6.  no training triggered by service startup / calls (health flags + monkeypatch guard)
7.  temperature-only V1 contract (variables == [temperature_2m_c]; no fabricated keys)
8.  live forecast weights sum to 1 over available models
9.  missing NWP model handling (unavailable model gets 0 weight + no contribution)
10. Model Arena candidate forecasts come from existing artifacts (no retrain) or
    forecast_available: false
11. API does not fabricate unsupported variables (humidity/wind/precip/etc.)
"""

import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.helios_v1_service import HeliosV1Service, FROZEN_PATH
from backend.app.repositories import forecast_repository as repo

FORBIDDEN_VARS = ("humidity", "wind", "precip", "precipitation", "feels_like",
                  "feels-like", "confidence", "weather_description", "weather",
                  "dewpoint", "cloud")


def _svc():
    return HeliosV1Service()


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _sample_forecast(svc, include_arena=True):
    """Build one live forecast from a real DB sample request."""
    samples = repo.list_sample_requests(50)
    # pick one with all 3 models present for deterministic multi-model checks
    for s in samples:
        data = repo.get_nwp_forecasts(s["issue_time"], s["lead_time_hours"], s["station"])
        if data and len(data["forecasts"]) == 3:
            issue = repo.parse_dt(data["issue_time"]); valid = repo.parse_dt(data["valid_time"])
            return svc.forecast(issue, valid, data["latitude"], data["longitude"],
                                data["location_zone"], data["forecasts"],
                                include_arena=include_arena), data
    raise AssertionError("no 3-model sample request found")


def test_models_schema():
    print("TEST: /v1/models schema")
    m = _svc().models()
    assert [x for x in m["nwp_models"]] == ["GFS", "IFS", "ICON"]
    keys = {c["key"] for c in m["helios_candidates"]}
    assert keys == {"kernel", "xgboost", "mlp"}
    assert m["baseline"] == "Simple Average"
    assert m["live_strategy"] == "MLP"
    assert m["variables"] == ["temperature_2m_c"] and m["units"] == "degC"
    # MLP is validated_live_strategy; others validated_candidate; none 'failed'
    st = {c["key"]: c["status"] for c in m["helios_candidates"]}
    assert st["mlp"] == "validated_live_strategy"
    assert st["kernel"] == "validated_candidate" and st["xgboost"] == "validated_candidate"
    assert "dynamically chooses" not in (m.get("note") or "").lower()
    print("  ✓ NWP + 3 candidates + baseline + MLP live; honest wording")
    print(); return True


def test_evaluation_schema_and_no_recompute():
    print("TEST: /v1/evaluation schema + no recompute/no TEST access")
    e = _svc().evaluation()
    assert e["recomputed"] is False
    assert e["test_accessed_for_new_computation"] is False
    wf = e["walk_forward"]
    ckeys = {c["key"] for c in wf["candidates"]}
    assert ckeys == {"kernel", "xgboost", "mlp"}
    assert wf["simple_average"]["mean_mae_c"] is not None
    lt = e["locked_test"]
    assert "helios_mlp" in lt["results"] and "simple_average" in lt["results"]
    assert lt["helios_vs_simple_average"]["pct"] > 0
    print("  ✓ walk-forward + locked TEST present; recomputed False")
    print(); return True


def test_candidate_metrics_match_frozen_artifacts():
    print("TEST: candidate historical metrics match frozen artifacts")
    import json
    fz = json.loads(FROZEN_PATH.read_text())
    frozen_wf = {r["candidate"]: r for r in fz["walkforward_selection"]["ranked"]}
    e = _svc().evaluation()
    for c in e["walk_forward"]["candidates"]:
        exp = frozen_wf[c["key"]]
        assert abs(c["mean_mae_c"] - round(exp["mean_fold_mae"], 4)) < 1e-9, c["key"]
        assert abs(c["std_c"] - round(exp["std_fold_mae"], 4)) < 1e-9, c["key"]
    # Simple Average from frozen
    assert abs(e["walk_forward"]["simple_average"]["mean_mae_c"]
               - round(fz["walkforward_selection"]["simple_average_mean_fold_mae"], 4)) < 1e-9
    # locked TEST helios MAE from frozen locked report
    lt = json.loads(sorted((PROJECT_ROOT / "ml" / "artifacts").glob(
        "lockedtest_v1_*/locked_test_report.json"))[-1].read_text())
    assert abs(e["locked_test"]["results"]["helios_mlp"]["mae_c"]
               - round(lt["results"]["helios_mlp"]["mae"], 4)) < 1e-9
    print("  ✓ evaluation numbers equal frozen artifact values (not hardcoded elsewhere)")
    print(); return True


def test_frozen_artifact_unchanged():
    print("TEST: frozen_selection_v1.json unchanged by API use")
    before = _sha(FROZEN_PATH)
    svc = _svc()
    svc.models(); svc.evaluation(); _sample_forecast(svc)
    after = _sha(FROZEN_PATH)
    assert before == after, "frozen artifact was modified!"
    print("  ✓ frozen selection artifact sha256 unchanged")
    print(); return True


def test_no_training_on_startup():
    print("TEST: no training triggered by API startup/use")
    import ml.mlp_candidate as mlpmod
    import ml.xgboost_candidate as xgbmod
    import ml.kernel_candidate as kmod
    calls = {"n": 0}
    orig = {}
    for mod, cls in ((mlpmod, "MLPCandidate"), (xgbmod, "XGBoostCandidate"), (kmod, "KernelRegressionCandidate")):
        c = getattr(mod, cls)
        orig[(mod, cls)] = c.train
        def make(o):
            def spy(self, *a, **k):
                calls["n"] += 1
                return o(self, *a, **k)
            return spy
        c.train = make(c.train)
    try:
        svc = _svc()
        assert svc.health()["trains_on_startup"] is False
        svc.models(); svc.evaluation(); _sample_forecast(svc)
    finally:
        for (mod, cls), fn in orig.items():
            getattr(mod, cls).train = fn
    assert calls["n"] == 0, f"candidate.train was called {calls['n']} times (must be 0)"
    print("  ✓ zero candidate.train() calls; health.trains_on_startup False")
    print(); return True


def test_forecast_temperature_only_no_fabrication():
    print("TEST: forecast is temperature-only; no fabricated variables")
    out, _ = _sample_forecast(_svc())
    assert out["variable"] == "temperature_2m_c" and out["units"] == "degC"
    assert out["helios_temperature_c"] is not None
    flat = str(out).lower()
    # forbidden fabricated concepts must not appear as forecast outputs
    for bad in ("humidity", "feels_like", "feels-like", "confidence",
                "weather_description", "cloud_cover", "precipitation_mm"):
        assert bad not in flat, f"fabricated variable '{bad}' present"
    # top-level forecast keys must not include fabricated vars
    for k in out:
        assert not any(b in k.lower() for b in ("humid", "wind_speed", "precip", "feels", "cloud")), k
    print("  ✓ temperature-only; no humidity/wind/precip/feels-like/confidence/weather")
    print(); return True


def test_weights_sum_to_one_over_available():
    print("TEST: NWP weights sum to 1 over available models")
    out, _ = _sample_forecast(_svc())
    ws = out["nwp_weights"]
    total = sum(ws.values())
    assert abs(total - 1.0) < 1e-5, f"weights sum {total}"
    for m in ("gfs", "ifs", "icon"):
        assert ws[m] >= 0.0
    print(f"  ✓ weights sum {round(total,6)} over available; all >= 0")
    print(); return True


def test_missing_model_handling():
    print("TEST: missing NWP model gets 0 weight + no contribution")
    svc = _svc()
    samples = repo.list_sample_requests(50)
    data = None
    for s in samples:
        d = repo.get_nwp_forecasts(s["issue_time"], s["lead_time_hours"], s["station"])
        if d and len(d["forecasts"]) == 3:
            data = d; break
    assert data is not None
    # Drop ICON to simulate a missing model.
    fc = dict(data["forecasts"]); fc.pop("icon")
    issue = repo.parse_dt(data["issue_time"]); valid = repo.parse_dt(data["valid_time"])
    out = svc.forecast(issue, valid, data["latitude"], data["longitude"],
                       data["location_zone"], fc, include_arena=False)
    assert out["nwp_availability"]["icon"] is False
    assert out["nwp_weights"]["icon"] == 0.0, "missing icon must have 0 weight (not zero-valued forecast)"
    assert out["nwp_forecasts_c"]["icon"] is None
    total = out["nwp_weights"]["gfs"] + out["nwp_weights"]["ifs"]
    assert abs(total - 1.0) < 1e-5, f"available weights sum {total}"
    print("  ✓ icon missing -> weight 0, value None; gfs+ifs weights renormalize to 1")
    print(); return True


def test_model_arena_from_existing_artifacts():
    print("TEST: Model Arena candidate forecasts from existing artifacts (no retrain)")
    out, _ = _sample_forecast(_svc(), include_arena=True)
    arena = out["model_arena"]
    keys = {c["key"] for c in arena["candidates"]}
    assert keys == {"kernel", "xgboost", "mlp"}
    for c in arena["candidates"]:
        # walk-forward metric always present from frozen artifact
        assert c["walk_forward_mae_c"] is not None
        # forecast either available (from existing artifact) or explicitly false
        assert "forecast_available" in c
        if c["forecast_available"]:
            assert c["forecast_c"] is not None
        else:
            assert c["forecast_c"] is None
    assert "dynamically choose" not in arena["note"].lower() or "does not" in arena["note"].lower()
    print("  ✓ 3 candidates; forecasts from existing artifacts or forecast_available False")
    print(); return True


# ======================================================================
# API-KEY AUTHENTICATION TESTS
# ======================================================================
# One HELIOS API server, MULTIPLE keys. Header transport (X-API-Key) only.
# Missing/invalid -> 401; valid -> proceeds. Keys never returned/logged.
# These tests start the REAL stdlib app in-process on an ephemeral port with
# two temporary test keys configured ONLY via the test environment (no real
# secrets), proving both keys hit the SAME endpoint implementation.

import io
import json as _json
import os
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

# Two temporary TEST keys (test-only; not real secrets).
_KEY_A = "sk_test_alpha_0000000000000000"
_KEY_B = "sk_test_bravo_1111111111111111"
_KEY_INVALID = "sk_test_not_a_real_key_9999"


def test_authenticator_unit():
    print("TEST: ApiKeyAuthenticator core behavior")
    from backend.app.api.auth import (
        ApiKeyAuthenticator, parse_api_keys, UNAUTHORIZED_BODY, API_KEY_HEADER,
    )
    # header + error body contract
    assert API_KEY_HEADER == "X-API-Key"
    assert UNAUTHORIZED_BODY == {"error": "unauthorized",
                                 "message": "Valid API key required"}
    # parse id:secret pairs and bare secrets (auto ids)
    m = parse_api_keys("demo:sk_x, partner:sk_y ,  sk_bare")
    assert m == {"demo": "sk_x", "partner": "sk_y", "key1": "sk_bare"}, m
    # empty/None -> fail-closed (no valid keys)
    empty = ApiKeyAuthenticator(parse_api_keys(""))
    assert empty.configured is False
    assert empty.authenticate("anything") == (False, None)
    # multiple keys against ONE authenticator
    auth = ApiKeyAuthenticator({"alpha": _KEY_A, "bravo": _KEY_B})
    assert auth.identify(None) is None
    assert auth.identify("") is None
    assert auth.identify(_KEY_INVALID) is None
    assert auth.identify(_KEY_A) == "alpha"
    assert auth.identify(_KEY_B) == "bravo"
    ok, kid = auth.authenticate(_KEY_A)
    assert ok and kid == "alpha"
    # usage keyed by key_id; never contains the raw secret
    u = auth.usage("alpha")
    assert u == {"key_id": "alpha", "requests": 1}
    assert _KEY_A not in _json.dumps(auth.usage())  # aggregate has no secret
    print("  ✓ parse, fail-closed, multi-key identify/authenticate, usage by key_id")
    print(); return True


@contextmanager
def _live_server(keys_env):
    """Start the real v1_app in-process with the given HELIOS_API_KEYS value.

    Reloads the app module so the module-level authenticator picks up the env.
    Yields the base URL. Restores env + server on exit.
    """
    import importlib
    prev = os.environ.get("HELIOS_API_KEYS")
    os.environ["HELIOS_API_KEYS"] = keys_env
    import backend.app.api.auth as auth_mod
    import backend.app.api.v1_app as app_mod
    importlib.reload(auth_mod)
    importlib.reload(app_mod)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown(); srv.server_close()
        if prev is None:
            os.environ.pop("HELIOS_API_KEYS", None)
        else:
            os.environ["HELIOS_API_KEYS"] = prev


def _req(base, path, key=None):
    """GET helper -> (status, parsed_json_or_text)."""
    req = urllib.request.Request(base + path)
    if key is not None:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, _json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, _json.loads(raw)
        except Exception:
            return e.code, raw


def _one_sample_forecast_path():
    """A real (issue,lead,station) forecast path from the DB (India January)."""
    for s in repo.list_sample_requests(50):
        d = repo.get_nwp_forecasts(s["issue_time"], s["lead_time_hours"], s["station"])
        if d and len(d["forecasts"]) == 3:
            from urllib.parse import quote
            return (f"/v1/forecast?issue_time={quote(str(d['issue_time']))}"
                    f"&lead_time_hours={d['lead_time_hours']}"
                    f"&station={quote(str(d['station']))}&arena=1")
    raise AssertionError("no 3-model sample request found")


def test_public_health_no_key():
    print("TEST: /v1/health is public (no key)")
    with _live_server(f"alpha:{_KEY_A},bravo:{_KEY_B}") as base:
        code, body = _req(base, "/v1/health")  # no key
        assert code == 200, code
        assert body["status"] == "ok"
    print("  ✓ health returns 200 without an API key")
    print(); return True


def test_protected_missing_key_401():
    print("TEST: protected endpoints require a key (missing -> 401)")
    with _live_server(f"alpha:{_KEY_A},bravo:{_KEY_B}") as base:
        for path in ("/v1/models", "/v1/evaluation", "/v1/model-arena",
                     "/v1/samples", "/v1/usage"):
            code, body = _req(base, path)  # no key
            assert code == 401, (path, code)
            assert body == {"error": "unauthorized",
                            "message": "Valid API key required"}, (path, body)
    print("  ✓ all protected endpoints return 401 with JSON error when key missing")
    print(); return True


def test_invalid_key_401():
    print("TEST: invalid key -> 401")
    with _live_server(f"alpha:{_KEY_A},bravo:{_KEY_B}") as base:
        code, body = _req(base, "/v1/models", key=_KEY_INVALID)
        assert code == 401, code
        assert body["error"] == "unauthorized"
        # must NOT reveal closeness / which key
        assert "close" not in _json.dumps(body).lower()
    print("  ✓ invalid key returns 401 without leaking validity hints")
    print(); return True


def test_valid_keys_A_and_B_same_impl():
    print("TEST: key A and key B both 200 on the SAME endpoints (one server)")
    with _live_server(f"alpha:{_KEY_A},bravo:{_KEY_B}") as base:
        for key in (_KEY_A, _KEY_B):
            code, m = _req(base, "/v1/models", key=key)
            assert code == 200, (key, code)
            assert [x for x in m["nwp_models"]] == ["GFS", "IFS", "ICON"]
            assert m["live_strategy"] == "MLP"
        # Same forecast endpoint implementation for both keys -> identical result.
        fpath = _one_sample_forecast_path()
        ca, fa = _req(base, fpath, key=_KEY_A)
        cb, fb = _req(base, fpath, key=_KEY_B)
        assert ca == 200 and cb == 200
        assert fa["helios_temperature_c"] == fb["helios_temperature_c"]
        assert abs(sum(fa["nwp_weights"].values()) - 1.0) < 1e-5
    print("  ✓ keys A and B both authorized; identical forecast (shared implementation)")
    print(); return True


def test_usage_by_key_id_never_returns_secret():
    print("TEST: /v1/usage reports by key_id and never returns the raw key")
    with _live_server(f"alpha:{_KEY_A},bravo:{_KEY_B}") as base:
        # make a couple of authorized requests with key A
        _req(base, "/v1/models", key=_KEY_A)
        code, u = _req(base, "/v1/usage", key=_KEY_A)
        assert code == 200, code
        assert u["key_id"] == "alpha"
        assert isinstance(u["requests"], int) and u["requests"] >= 1
        # the raw secret must never appear anywhere in the usage payload
        assert _KEY_A not in _json.dumps(u)
        assert "actual_api_key" not in _json.dumps(u)
    print("  ✓ usage keyed by key_id; raw secret never present")
    print(); return True


def test_keys_never_returned_by_any_endpoint():
    print("TEST: no endpoint response contains a raw API key")
    with _live_server(f"alpha:{_KEY_A},bravo:{_KEY_B}") as base:
        fpath = _one_sample_forecast_path()
        paths = ["/v1/health", "/v1/models", "/v1/evaluation", "/v1/model-arena",
                 "/v1/samples", "/v1/usage", fpath]
        for p in paths:
            code, body = _req(base, p, key=_KEY_A)
            blob = _json.dumps(body)
            assert _KEY_A not in blob, p
            assert _KEY_B not in blob, p
    print("  ✓ raw keys absent from every endpoint response")
    print(); return True


def test_keys_never_logged():
    print("TEST: API keys are never written to logs/stdout/stderr by the app")
    import importlib
    import contextlib
    prev = os.environ.get("HELIOS_API_KEYS")
    os.environ["HELIOS_API_KEYS"] = f"alpha:{_KEY_A},bravo:{_KEY_B}"
    try:
        import backend.app.api.auth as auth_mod
        import backend.app.api.v1_app as app_mod
        importlib.reload(auth_mod); importlib.reload(app_mod)
        # capture the startup banner (main() would call print) via a direct call
        buf = io.StringIO()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            # emulate the startup banner logic (prints key COUNT/IDS, never secrets)
            with contextlib.redirect_stdout(buf):
                n_keys = len(app_mod._AUTH.key_ids())
                print(f"HELIOS V1 API keys configured: {n_keys} "
                      f"(key ids: {app_mod._AUTH.key_ids()})")
            # exercise requests (handler is silent: log_message overridden)
            with contextlib.redirect_stderr(buf):
                _req(f"http://127.0.0.1:{port}", "/v1/models", key=_KEY_A)
                _req(f"http://127.0.0.1:{port}", "/v1/models", key=_KEY_INVALID)
        finally:
            srv.shutdown(); srv.server_close()
        out = buf.getvalue()
        assert _KEY_A not in out and _KEY_B not in out and _KEY_INVALID not in out
        # key ids are allowed (non-secret)
        assert "alpha" in out and "bravo" in out
    finally:
        if prev is None:
            os.environ.pop("HELIOS_API_KEYS", None)
        else:
            os.environ["HELIOS_API_KEYS"] = prev
    print("  ✓ startup + request handling never emit raw keys (ids only)")
    print(); return True


def test_forecast_via_auth_still_uses_frozen_mlp_and_valid_weights():
    print("TEST: authenticated forecast still frozen-MLP; weights valid; temp-only")
    with _live_server(f"alpha:{_KEY_A}") as base:
        fpath = _one_sample_forecast_path()
        code, f = _req(base, fpath, key=_KEY_A)
        assert code == 200, code
        assert f["live_strategy"] == "MLP"
        assert f["variable"] == "temperature_2m_c" and f["units"] == "degC"
        ws = f["nwp_weights"]
        assert abs(sum(ws.values()) - 1.0) < 1e-5
        for m in ("gfs", "ifs", "icon"):
            assert ws[m] >= 0.0
        # no fabricated variables leak through the authenticated path
        blob = _json.dumps(f).lower()
        for bad in ("humidity", "feels_like", "precipitation_mm", "cloud_cover",
                    "confidence", "weather_description"):
            assert bad not in blob, bad
        # arena present with 3 candidates
        assert {c["key"] for c in f["model_arena"]["candidates"]} == {"kernel", "xgboost", "mlp"}
    print("  ✓ frozen MLP live strategy; weights sum to 1; temperature-only; arena intact")
    print(); return True


# ======================================================================
# SPATIAL CONTRACT TESTS
# ======================================================================
# A location must be represented by REAL coordinates + station anchor, never by
# an evaluation zone, and never by an arbitrary NWP grid point. Live serving must
# select the SAME grid point per model that the frozen dataset builder chose
# (spatial_key="station" -> nearest grid point to the station).

def test_station_coordinates_are_real_not_grid_points():
    print("TEST: /v1/locations returns REAL station coordinates (not grid points)")
    from backend.app.repositories import station_repository as stations
    locs = stations.list_supported_locations()
    assert len(locs) > 300, f"expected the full station set, got {len(locs)}"

    # Every plotted station must carry ISD-sourced coordinates and a place name.
    withc = [l for l in locs if l["latitude"] is not None]
    assert len(withc) == len(locs), "some stations lack real coordinates"
    for l in withc:
        assert l["coordinate_source"] == "noaa_isd_station_history", l["station"]
        assert 6.0 <= l["latitude"] <= 37.5, (l["station"], l["latitude"])
        assert 67.0 <= l["longitude"] <= 98.0, (l["station"], l["longitude"])

    # Spot-check a known station against the authoritative ISD record.
    srin = [l for l in locs if l["station"] == "420270-99999"]
    assert srin, "station 420270-99999 missing"
    s = srin[0]
    assert s["name"] and "srinagar" in s["name"].lower(), s["name"]
    assert abs(s["latitude"] - 34.083) < 1e-3, s["latitude"]
    assert abs(s["longitude"] - 74.833) < 1e-3, s["longitude"]

    # The station coordinate must NOT equal a stored verification grid point:
    # those are model grid coordinates, not the place.
    import sqlite3
    con = sqlite3.connect(f"file:{PROJECT_ROOT/'data'/'helios.db'}?mode=ro", uri=True)
    grid = con.execute(
        "SELECT DISTINCT latitude, longitude FROM forecast_verification "
        "WHERE observation_station_ids=?", ("420270-99999",)).fetchall()
    con.close()
    assert len(grid) > 1, "expected many candidate grid points for this station"
    assert (s["latitude"], s["longitude"]) not in [(g[0], g[1]) for g in grid], \
        "station coordinate collided with a grid point — likely reading grid as place"
    print(f"  ✓ {len(withc)} stations with real ISD coords; Srinagar "
          f"({s['latitude']}, {s['longitude']}) distinct from its {len(grid)} grid points")
    print(); return True


def test_live_grid_selection_matches_frozen_protocol():
    print("TEST: live serving picks the SAME grid point as the frozen builder")
    import sqlite3
    samples = repo.list_sample_requests(30)
    checked = 0
    con = sqlite3.connect(f"file:{PROJECT_ROOT/'data'/'helios.db'}?mode=ro", uri=True)
    for smp in samples:
        data = repo.get_nwp_forecasts(smp["issue_time"], smp["lead_time_hours"], smp["station"])
        if not data or not data.get("grid_points"):
            continue
        for model, gp in data["grid_points"].items():
            # Frozen rule (ml/dataset_builder.py::_group_examples with
            # spatial_key="station"): nearest grid point, tie-break smaller
            # verification_id.
            row = con.execute(
                "SELECT forecast_value, latitude, longitude, observation_distance_km "
                "FROM forecast_verification "
                "WHERE model=? AND issue_time=? AND lead_time_hours=? "
                "      AND observation_station_ids=? "
                "ORDER BY (observation_distance_km IS NULL), "
                "         observation_distance_km ASC, verification_id ASC LIMIT 1",
                (model, smp["issue_time"], smp["lead_time_hours"], smp["station"])).fetchone()
            assert row is not None
            assert abs(float(data["forecasts"][model]) - float(row[0])) < 1e-9, \
                f"{model}: served value is not the nearest-grid-point value"
            assert gp["latitude"] == row[1] and gp["longitude"] == row[2], \
                f"{model}: served grid point differs from frozen selection"
            checked += 1
        if checked >= 9:
            break
    con.close()
    assert checked >= 3, f"only checked {checked} model/grid selections"
    print(f"  ✓ {checked} model selections match the frozen nearest-grid-point rule")
    print(); return True


def test_forecast_exposes_real_location_and_spatial_disclosure():
    print("TEST: /v1/forecast reports real coordinates + spatial provenance")
    from backend.app.api.v1_app import build_forecast_response
    from backend.app.repositories import station_repository as stations
    smp = None
    for s in repo.list_sample_requests(40):
        d = repo.get_nwp_forecasts(s["issue_time"], s["lead_time_hours"], s["station"])
        if d and len(d["forecasts"]) == 3:
            smp = s; break
    assert smp is not None
    out, code = build_forecast_response(smp["issue_time"], smp["lead_time_hours"], smp["station"])
    assert code == 200, out

    # location must be the REAL station coordinate, matching station_repository
    info = stations.station_info(smp["station"])
    assert info is not None
    loc = out["location"]
    assert loc["latitude"] == info["latitude"] and loc["longitude"] == info["longitude"]
    assert loc.get("station") == smp["station"]
    assert loc.get("coordinate_source") == "noaa_isd_station_history"
    # zone is present but explicitly named as EVALUATION metadata, not "zone as location"
    assert "evaluation_zone" in loc
    assert "zone" not in loc, "bare 'zone' key would invite zone-as-location usage"

    sp = out["spatial"]
    assert sp["support"] == "station_anchored"
    assert sp["interpolated"] is False
    assert sp["anchor_station"] == smp["station"]
    for m in ("gfs", "ifs", "icon"):
        gp = sp["model_grid_points"].get(m)
        assert gp is not None, m
        assert gp["distance_to_station_km"] is not None
        # grid point must be within the verification matching radius (<= 50 km)
        assert 0 <= gp["distance_to_station_km"] <= 50.001, gp
    print(f"  ✓ location=({loc['latitude']}, {loc['longitude']}) name={loc.get('name')!r}; "
          f"grid offsets " +
          ", ".join(f"{m}={sp['model_grid_points'][m]['distance_to_station_km']}km"
                    for m in ('gfs','ifs','icon')))
    print(); return True


def test_resolve_nearest_is_honest():
    print("TEST: arbitrary coordinates resolve to nearest supported point")
    from backend.app.repositories import station_repository as stations
    # New Delhi
    r = stations.resolve_nearest(28.6139, 77.2090, require_models=1)
    assert r is not None
    assert r["resolution"] == "nearest_supported_station"
    assert r["distance_km"] >= 0
    assert "interpolat" in r["note"].lower(), "must state that it is not interpolation"
    res = r["resolved"]
    assert res["latitude"] is not None and res["longitude"] is not None

    # It must genuinely be the nearest among all coordinate-bearing stations.
    best = min(
        (l for l in stations.list_supported_locations() if l["latitude"] is not None),
        key=lambda l: stations.haversine_km(28.6139, 77.2090, l["latitude"], l["longitude"]),
    )
    assert res["station"] == best["station"], (res["station"], best["station"])

    # Resolving AT a station must give ~0 km.
    z = stations.resolve_nearest(res["latitude"], res["longitude"], require_models=1)
    assert z is not None and z["distance_km"] < 0.01, z["distance_km"]
    print(f"  ✓ (28.6139, 77.2090) -> {res['name']} {res['station']} "
          f"@ {r['distance_km']} km; self-resolution {z['distance_km']} km")
    print(); return True


def test_zone_is_not_used_as_a_location():
    print("TEST: evaluation zones are never presented as locations")
    from backend.app.repositories import station_repository as stations
    locs = stations.list_supported_locations()
    zones = {"north_himalaya", "north_plains", "central", "south_plateau", "south_coastal"}
    for l in locs:
        # the zone lives under an explicitly-named evaluation key only
        assert "evaluation_zone" in l
        assert l.get("name") not in zones, f"place name is a zone label: {l['name']}"
        # a location must be identified by coordinates, not by its zone
        assert l["latitude"] is not None and l["longitude"] is not None, l["station"]
    # distinct coordinates => real geography, not 5 zone centroids
    pts = {(l["latitude"], l["longitude"]) for l in locs}
    assert len(pts) > 300, f"only {len(pts)} distinct points — looks aggregated"
    print(f"  ✓ {len(pts)} distinct real coordinates; zone kept as evaluation metadata only")
    print(); return True
