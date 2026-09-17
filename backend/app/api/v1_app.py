#!/usr/bin/env python3
"""
HELIOS V1 API — minimal stdlib HTTP app (no third-party web framework required).

Authentication:
  ONE server, MULTIPLE API keys. Protected endpoints require a valid API key
  supplied via the ``X-API-Key`` header (never a query parameter). Keys are read
  from the ``HELIOS_API_KEYS`` environment variable (``id:secret`` pairs or bare
  secrets). Missing/invalid key -> HTTP 401 JSON. Keys are never logged or
  returned by any endpoint. See backend/app/api/auth.py.

Endpoints:
  GET /v1/health                (PUBLIC)
  GET /v1/models                (protected)
  GET /v1/evaluation            (protected)
  GET /v1/model-arena           (protected; historical competition; forecasts require a request)
  GET /v1/samples               (protected; sample request keys for the demo)
  GET /v1/forecast?issue_time=..&lead_time_hours=..&station=..   (protected)
  GET /v1/live/status           (protected; which live model cycle is published)
  GET /v1/live/forecast         (protected; LIVE current-run future forecast)
  GET /v1/locations             (protected; supported points, REAL station coords)
  GET /v1/resolve?lat=&lon=     (protected; nearest supported point + distance)
  GET /v1/usage                 (protected; usage for the authenticated key_id)

The live forecast is produced by the frozen MLP strategy over the AVAILABLE NWP
models (temperature-only). Startup does NOT train or recompute TEST.

Run:  HELIOS_API_KEYS="demo:sk_demo_xxx" python -m backend.app.api.v1_app  [--port 8011]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.helios_v2_service import HeliosV2Service
from backend.app.repositories import forecast_repository as repo
from backend.app.repositories import station_repository as stations
from backend.app.services.live_forecast_service import LIVE_FORECAST
from backend.app.services.live_nwp_service import LiveNwpError, V1_LEADS
from backend.app.api.auth import (
    ApiKeyAuthenticator, API_KEY_HEADER, UNAUTHORIZED_BODY, FORBIDDEN_BODY, generate_key
)

_SERVICE = HeliosV2Service()  # loads frozen artifacts lazily; NO training
_AUTH = ApiKeyAuthenticator()

# Public endpoints require NO API key. Everything else is protected.
PUBLIC_PATHS = frozenset({"/v1/health"})


def build_forecast_response(issue_time: str, lead_time_hours: int, station: str,
                            include_arena: bool = True):
    data = repo.get_nwp_forecasts(issue_time, lead_time_hours, station)
    if data is None:
        return {"error": "not_found",
                "detail": "no NWP forecasts for the requested issue_time/lead/station"}, 404
    issue = repo.parse_dt(data["issue_time"])
    valid = repo.parse_dt(data["valid_time"])
    out = _SERVICE.forecast(
        issue_time=issue, valid_time=valid,
        latitude=data["latitude"], longitude=data["longitude"],
        location_zone=data["location_zone"], forecasts=data["forecasts"],
        include_arena=include_arena)
    out["station"] = station

    # ---- spatial disclosure -------------------------------------------------
    # `data["latitude"]/["longitude"]` are NWP GRID coordinates, not a place.
    # Replace the reported location with the REAL station coordinates and state
    # exactly which grid point each model contributed, plus its offset. This makes
    # the station-anchored nature of V1 explicit instead of implying that the
    # forecast is valid at an arbitrary coordinate.
    info = stations.station_info(station)
    if info is not None:
        out["location"] = {
            "latitude": info["latitude"],
            "longitude": info["longitude"],
            "name": info["name"],
            "elevation_m": info["elevation_m"],
            "station": station,
            "coordinate_source": info["coordinate_source"],
            # Evaluation stratification only — NOT the location itself.
            "evaluation_zone": info["evaluation_zone"],
        }
    out["spatial"] = {
        "support": "station_anchored",
        "anchor_station": station,
        # Which grid point of each model was used, and how far it is from the
        # station. Mirrors the frozen protocol (nearest grid point per model).
        "model_grid_points": data.get("grid_points", {}),
        "selection_rule": "nearest grid point to the anchor station per model",
        "interpolated": False,
        "note": ("Each NWP model is sampled at its own nearest grid point to the "
                 "station; no spatial interpolation is performed in V1."),
    }
    return out, 200


def _live_status_payload():
    """Live availability, plus whether the server-side cache is warm."""
    st = LIVE_FORECAST.status()
    from backend.app.services.live_nwp_service import LIVE_NWP
    st["cache_entries"] = len(LIVE_NWP.cached_keys())
    st["cache_warm"] = st["cache_entries"] >= len(st.get("selected_cycle_models", [])) * len(
        st.get("supported_leads", []) or [1])
    st["warming"] = _WARMING["active"]
    return st


_WARMING = {"active": False, "error": None}


def _warm_live_cache():
    """
    Pre-fetch the current cycle in the background.

    A cold cycle needs ~15 small byte-range downloads (~25 s total) and then
    serves EVERY station instantly. Doing this at startup means a browser request
    never triggers a large synchronous download.
    """
    def work():
        _WARMING["active"] = True
        try:
            # Prime the availability/status cache first (it is what the page loads
            # on mount), then the field cache for the current cycle.
            LIVE_FORECAST.status()
            locs = [l for l in stations.list_supported_locations()
                    if l["latitude"] is not None]
            if not locs:
                return
            LIVE_FORECAST.forecast(locs[0]["station"])
            print("  live cache warm: current cycle ready (status + fields)")
        except Exception as e:
            _WARMING["error"] = f"{type(e).__name__}: {e}"
            print(f"  live cache warm failed: {e}")
        finally:
            _WARMING["active"] = False

    t = threading.Thread(target=work, name="helios-live-warm", daemon=True)
    t.start()


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", f"{API_KEY_HEADER}, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # CORS preflight for browsers sending the X-API-Key custom header.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", f"{API_KEY_HEADER}, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):  # quiet
        pass

    def _authorize(self, require_admin=False):
        """Return (ok, key_id). On failure, send 401/403 JSON and return (False, None).

        Reads the API key ONLY from the X-API-Key header (never query params).
        Never logs the key. Does not reveal how close a supplied key is to valid.
        """
        presented = self.headers.get(API_KEY_HEADER)
        ok, key_id, err = _AUTH.authenticate(presented, require_admin=require_admin)
        if not ok:
            code = 401 if err == UNAUTHORIZED_BODY else 403
            self._send(dict(err), code)
            return False, None
        return True, key_id

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except:
            return {}

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if not u.path.startswith("/v1/admin/"):
                self._send({"error": "not_found"}, 404)
                return
            
            ok, key_id = self._authorize(require_admin=True)
            if not ok:
                return

            if u.path == "/v1/admin/api-keys":
                body = self._read_body()
                role = body.get("role", "user")
                name = body.get("name", "Unnamed Key")
                if role not in ("admin", "user"):
                    self._send({"error": "bad_request", "message": "role must be admin or user"}, 400)
                    return
                plaintext, info = generate_key(role, name)
                self._send({"status": "created", "key": info}, 201)
                return
            elif u.path.startswith("/v1/admin/api-keys/"):
                parts = u.path.split("/")
                if len(parts) == 6:  # /v1/admin/api-keys/{key_id}/{action}
                    target_key_id = parts[4]
                    action = parts[5]
                    from database.connection import get_db_manager
                    from database.schema.helios_schema import ApiKey
                    from datetime import datetime
                    
                    db = get_db_manager()
                    with db.get_session() as session:
                        key_record = session.query(ApiKey).filter_by(id=target_key_id).first()
                        if not key_record:
                            self._send({"error": "not_found", "message": "key not found"}, 404)
                            return
                        
                        if action == "revoke":
                            key_record.enabled = False
                            key_record.revoked_at = datetime.utcnow()
                            session.commit()
                            self._send({"status": "ok", "message": f"Key {target_key_id} revoked"}, 200)
                            return
                        elif action == "enable":
                            key_record.enabled = True
                            key_record.revoked_at = None
                            session.commit()
                            self._send({"status": "ok", "message": f"Key {target_key_id} enabled"}, 200)
                            return
                            
            self._send({"error": "not_found"}, 404)
        except Exception as e:
            self._send({"error": "internal", "detail": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            # PUBLIC endpoint: no key required.
            if u.path == "/v1/health":
                self._send(_SERVICE.health())
                return

            # Everything else is PROTECTED by the SAME authenticator (one server,
            # many keys). Missing/invalid key -> 401.
            if u.path == "/v1/admin/api-keys":
                ok, key_id = self._authorize(require_admin=True)
                if not ok:
                    return
                from database.connection import get_db_manager
                from database.schema.helios_schema import ApiKey
                db = get_db_manager()
                with db.get_session() as session:
                    keys = session.query(ApiKey).all()
                    out = []
                    for k in keys:
                        out.append({
                            "id": k.id,
                            "name": k.name,
                            "role": k.role,
                            "enabled": k.enabled,
                            "created_at": k.created_at.isoformat() + "Z" if k.created_at else None,
                            "last_used_at": k.last_used_at.isoformat() + "Z" if k.last_used_at else None,
                            "revoked_at": k.revoked_at.isoformat() + "Z" if k.revoked_at else None,
                            "key_prefix": k.key_prefix
                        })
                self._send({"api_keys": out})
                return

            ok, key_id = self._authorize()

            if u.path == "/v1/models":
                self._send(_SERVICE.models())
            elif u.path == "/v1/evaluation":
                self._send(_SERVICE.evaluation())
            elif u.path == "/v1/model-arena":
                self._send(_SERVICE.model_arena())
            elif u.path == "/v1/samples":
                self._send({"samples": repo.list_sample_requests(int(q.get("limit", ["20"])[0]))})
            elif u.path == "/v1/live/status":
                self._send(_live_status_payload())
            elif u.path == "/v1/live/forecast":
                if "station" not in q:
                    self._send({"error": "bad_request",
                                "detail": "require station"}, 400)
                    return
                leads = V1_LEADS
                if "leads" in q:
                    try:
                        want = tuple(int(x) for x in q["leads"][0].split(",") if x.strip())
                        leads = tuple(l for l in want if l in V1_LEADS) or V1_LEADS
                    except ValueError:
                        self._send({"error": "bad_request",
                                    "detail": "leads must be comma-separated integers"}, 400)
                        return
                try:
                    self._send(LIVE_FORECAST.forecast(q["station"][0], leads=leads))
                except LiveNwpError as e:
                    # Live failure NEVER falls back to the January 2025 dataset.
                    self._send({
                        "error": "live_unavailable",
                        "message": str(e),
                        "mode": "live",
                        "fallback_to_historical": False,
                        "detail": ("Historical V1 evaluation remains available via "
                                   "/v1/evaluation and /v1/forecast, which are "
                                   "explicitly historical endpoints."),
                    }, 503)
            elif u.path == "/v1/locations":
                # Supported V1 forecast points with REAL station coordinates
                # (NOAA ISD station history), not NWP grid points.
                locs = [dict(l) for l in stations.list_supported_locations()]
                self._send({
                    "locations": locs,
                    "count": len(locs),
                    "lead_time_hours": repo.list_lead_times(),
                    "spatial_support": "station_anchored",
                    "coordinate_source": "noaa_isd_station_history",
                    "spatial_note": (
                        "V1 serves forecasts only at these supported station points. "
                        "latitude/longitude are the real station coordinates. "
                        "nearest_grid_km reports how far each NWP model's nearest "
                        "grid point sits from the station. Arbitrary-coordinate "
                        "forecasting requires interpolation and is not part of V1."
                    ),
                })
            elif u.path == "/v1/resolve":
                # Resolve an arbitrary coordinate to the nearest supported point.
                if "lat" not in q or "lon" not in q:
                    self._send({"error": "bad_request",
                                "detail": "require lat, lon"}, 400)
                    return
                try:
                    rlat = float(q["lat"][0]); rlon = float(q["lon"][0])
                except ValueError:
                    self._send({"error": "bad_request",
                                "detail": "lat/lon must be numeric"}, 400)
                    return
                if not (-90 <= rlat <= 90) or not (-180 <= rlon <= 180):
                    self._send({"error": "bad_request",
                                "detail": "lat/lon out of range"}, 400)
                    return
                need = int(q.get("require_models", ["1"])[0])
                res = stations.resolve_nearest(rlat, rlon, require_models=need)
                if res is None:
                    self._send({"error": "not_found",
                                "detail": "no supported station available"}, 404)
                    return
                self._send(res)
            elif u.path == "/v1/issue-times":
                if "station" not in q or "lead_time_hours" not in q:
                    self._send({"error": "bad_request",
                                "detail": "require station, lead_time_hours"}, 400)
                    return
                self._send({"issue_times": repo.list_issue_times(
                    q["station"][0], int(q["lead_time_hours"][0]))})
            elif u.path == "/v1/usage":
                self._send({"key_id": key_id, "usage": "not_tracked"})
            elif u.path == "/v1/forecast":
                if "issue_time" not in q or "lead_time_hours" not in q or "station" not in q:
                    self._send({"error": "bad_request",
                                "detail": "require issue_time, lead_time_hours, station"}, 400)
                    return
                obj, code = build_forecast_response(
                    q["issue_time"][0], int(q["lead_time_hours"][0]), q["station"][0],
                    include_arena=(q.get("arena", ["1"])[0] not in ("0", "false")))
                self._send(obj, code)
            else:
                self._send({"error": "not_found", "detail": f"unknown path {u.path}"}, 404)
        except Exception as e:
            self._send({"error": "internal", "detail": f"{type(e).__name__}: {e}"}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8011)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-warm", action="store_true",
                    help="skip background live-cache warm-up on startup")
    args = ap.parse_args()
    ThreadingHTTPServer.allow_reuse_address = True
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    if not args.no_warm:
        _warm_live_cache()
    print(f"HELIOS V1 API on http://{args.host}:{args.port}/v1/  (Ctrl-C to stop)")
    
    def handle_sigterm(*args):
        print("Received SIGTERM, shutting down...", flush=True)
        # Run shutdown in a separate thread so it doesn't block the signal handler
        threading.Thread(target=srv.shutdown).start()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    finally:
        print("Server shutdown complete.", flush=True)


if __name__ == "__main__":
    main()
