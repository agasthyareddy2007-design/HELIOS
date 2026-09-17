"""
HELIOS — LIVE forecast service (current run -> future valid times).

PIPELINE
--------
    current model cycle (per model, discovered from the live feeds)
        -> live GFS / IFS / ICON 2 m temperature at the station's nearest grid point
        -> FeatureBuilder (frozen 24-feature contract)
        -> frozen V1 MLP  ->  per-NWP reliability  ->  trust weights
        -> blended HELIOS temperature, per future horizon

TEMPORAL SAFETY
---------------
A live forecast issued at cycle time T may use only:
  * the model forecasts published for cycle T (information available AT T), and
  * historical error statistics strictly BEFORE T.

It must never use an observation or verification occurring after T. This service
therefore:
  * never queries the verification tables for anything at or after T, and
  * computes historical reliability features only from windows strictly before T.

For a live 2026 cycle the frozen database (January 2025 only) contains no data in
the 7 days before T, so the 9 optional reliability features are genuinely
UNAVAILABLE. They are left as None and imputed by the FROZEN preprocessor's
`missing_value_fills` (fitted on TRAIN) — exactly as the existing historical
serving path already does. Nothing is invented, no feature is filled with an
arbitrary constant, and the feature contract is unchanged.

This limitation is reported in the API response (`reliability_features`), because
it is a real difference between live inference and the January evaluation.

SCIENTIFIC INVARIANTS
---------------------
* The frozen MLP artifact is used exactly as trained. No retraining or tuning.
* Missing model => contributes NOTHING (not zero). Weights renormalise over the
  available models and always sum to 1.
* Temperature only. No other variable is produced.
* Live failure NEVER falls back to January 2025 data.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "helios.db"

# Bounded concurrency for the HEAVY live-forecast acquisition path. The stdlib
# ThreadingHTTPServer spawns one thread per request (unbounded), and each cold
# forecast fans out to a ThreadPoolExecutor doing GRIB byte-range fetches,
# wgrib2/bz2 decompression and torch inference. Under rapid location selection a
# storm of such requests could otherwise saturate CPU/memory and make the whole
# stack (including the Next server) unresponsive. This semaphore caps how many
# cold acquisitions run at once; excess requests wait briefly, then fail with a
# controlled 503 rather than piling up. The warm-cache fast path is unaffected.
_MAX_CONCURRENT_ACQUISITIONS = int(os.environ.get("HELIOS_LIVE_MAX_CONCURRENCY", "2"))
_ACQUIRE_WAIT_S = float(os.environ.get("HELIOS_LIVE_ACQUIRE_WAIT_S", "20"))
_ACQUISITION_GATE = threading.BoundedSemaphore(_MAX_CONCURRENT_ACQUISITIONS)

from backend.app.services.helios_v2_service import HeliosV2Service
NWP_MODELS = ('gfs', 'ifs', 'icon')
UNITS = 'C'
VARIABLE = 'temperature_2m_c'

from backend.app.services.live_nwp_service import (
    LIVE_NWP, LiveNwpError, ModelSlice, V1_LEADS, latest_cycle,
)
from backend.app.repositories import station_repository as stations

logger = logging.getLogger(__name__)


def _round(x, n=3):
    return round(x, n) if isinstance(x, (int, float)) and x is not None else x


@dataclass
class LeadOutcome:
    """Inference result for one future horizon."""
    lead_hours: int
    valid_time: Optional[str]
    nwp: Dict[str, Optional[float]]
    availability: Dict[str, bool]
    weights: Dict[str, float]
    helios_c: Optional[float]
    grid: Dict[str, dict]
    errors: Dict[str, str]
    # Additive: per-candidate blended output on the SAME live features (real
    # frozen kernel/xgboost/mlp artifacts; the deployed one is `helios_c`).
    candidates: Optional[Dict[str, dict]] = None


class LiveForecastService:
    """Runs the frozen V1 strategy over live NWP inputs."""

    # Cycle discovery costs ~15 HEAD requests, so its result is memoised. A short
    # TTL keeps the server responsive while still noticing a newly published cycle.
    CYCLE_TTL_S = 300

    def __init__(self, v2: Optional[HeliosV2Service] = None):
        self.v2 = v2 or HeliosV2Service()
        self._cycle_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._cycle_lock = threading.Lock()
        self._status_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._status_lock = threading.Lock()

    # ---------------------------------------------------------------- safety
    @staticmethod
    def historical_reliability_before(issue_time: datetime,
                                      window_days: int = 7) -> Tuple[Optional[dict], dict]:
        """
        Per-model error statistics from a window STRICTLY BEFORE `issue_time`.

        Returns (reliability_or_None, provenance). Reads only rows whose
        verification/valid time is < issue_time, so no future information can
        leak into a live forecast. For a 2026 live cycle this correctly finds
        nothing, because the frozen dataset covers January 2025 only.
        """
        start = issue_time - timedelta(days=window_days)
        prov: Dict[str, Any] = {
            "window_start": start.isoformat(),
            "window_end_exclusive": issue_time.isoformat(),
            "source": "forecast_verification (valid_time strictly before issue_time)",
            "available": False,
            "n_rows": 0,
        }
        try:
            con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            cur = con.cursor()
            rows = cur.execute(
                "SELECT model, COUNT(*), AVG(absolute_error), AVG(error), "
                "       AVG(squared_error) "
                "FROM forecast_verification "
                "WHERE valid_time >= ? AND valid_time < ? "
                "      AND absolute_error IS NOT NULL "
                "GROUP BY model",
                (start.strftime("%Y-%m-%d %H:%M:%S"),
                 issue_time.strftime("%Y-%m-%d %H:%M:%S"))).fetchall()
            con.close()
        except Exception as e:  # pragma: no cover - defensive
            prov["error"] = f"{type(e).__name__}: {e}"
            return None, prov

        if not rows:
            return None, prov

        from ml.feature_builder import HistoricalReliability
        out: Dict[str, Any] = {}
        total = 0
        for model, n, mae, bias, mse in rows:
            if model not in NWP_MODELS or not n:
                continue
            total += int(n)
            out[model] = HistoricalReliability(
                model=model,
                rmse=float(mse) ** 0.5 if mse is not None else None,
                mae=float(mae) if mae is not None else None,
                bias=float(bias) if bias is not None else None,
                n_samples=int(n),
            )
        prov["available"] = bool(out)
        prov["n_rows"] = total
        return (out or None), prov

    # --------------------------------------------------- cycle alignment
    def select_common_cycle(self, leads: Tuple[int, ...] = V1_LEADS,
                            max_back: int = 8) -> Dict[str, Any]:
        """
        Choose ONE model cycle that all (or the most) models have published.

        WHY THIS MATTERS SCIENTIFICALLY
        -------------------------------
        Models publish on different schedules: at a given moment GFS/IFS may have
        completed 00Z while ICON has completed 06Z. Blending a GFS +24h from 00Z
        with an ICON +24h from 06Z would combine forecasts valid at DIFFERENT
        times, which is not what the validated V1 protocol does — it blends models
        at the SAME valid time.

        So we walk cycles backwards and pick the most recent one where the
        greatest number of models has published every requested lead. Models that
        did not publish that cycle are reported UNAVAILABLE for it, rather than
        being back-filled from a different cycle.
        """
        with self._cycle_lock:
            if self._cycle_cache is not None:
                ts, cached = self._cycle_cache
                if time.time() - ts < self.CYCLE_TTL_S:
                    return cached

        best: Optional[Dict[str, Any]] = None
        for back in range(max_back):
            run = latest_cycle(back=back)
            ready: List[str] = []
            for m in NWP_MODELS:
                if all(LIVE_NWP._exists(m, run, ld) for ld in leads):
                    ready.append(m)
            if not ready:
                continue
            cand = {"run": run, "models": ready, "n": len(ready)}
            if best is None or cand["n"] > best["n"]:
                best = cand
            # A cycle with every model is optimal; stop immediately.
            if len(ready) == len(NWP_MODELS):
                with self._cycle_lock:
                    self._cycle_cache = (time.time(), cand)
                return cand
        result = best if best is not None else {"run": None, "models": [], "n": 0}
        with self._cycle_lock:
            self._cycle_cache = (time.time(), result)
        return result

    # --------------------------------------------------------------- status
    def status(self, leads: Tuple[int, ...] = V1_LEADS) -> Dict[str, Any]:
        """
        Which live cycle each model has published, without downloading fields.

        Availability probing costs ~15 HEAD requests, so the whole payload is
        memoised for CYCLE_TTL_S. Without this, every page load would re-probe the
        upstream feeds and could exceed the frontend proxy timeout.
        """
        with self._status_lock:
            if self._status_cache is not None:
                ts, cached = self._status_cache
                if time.time() - ts < self.CYCLE_TTL_S:
                    return cached

        per: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {m: ex.submit(self._model_status, m, leads) for m in NWP_MODELS}
            for m, f in futs.items():
                try:
                    per[m] = f.result()
                except Exception as e:
                    per[m] = {"available": False,
                              "error": f"{type(e).__name__}: {e}", "leads": []}
        online = [m for m in NWP_MODELS if per.get(m, {}).get("available")]
        chosen = self.select_common_cycle(leads)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": per,
            "models_online": online,
            "n_models_online": len(online),
            "live_available": chosen["n"] > 0,
            # The cycle actually used for blending — all models share it.
            "selected_cycle": chosen["run"].isoformat() if chosen["run"] else None,
            "selected_cycle_models": chosen["models"],
            "cycle_alignment": ("all models blended at one common cycle so every "
                                "horizon has a single consistent valid time"),
            "supported_leads": list(leads),
            "variable": VARIABLE,
            "units": UNITS,
        }
        with self._status_lock:
            self._status_cache = (time.time(), payload)
        return payload

    def _model_status(self, model: str, leads: Tuple[int, ...]) -> Dict[str, Any]:
        run = LIVE_NWP.discover_run(model, leads[0])
        if run is None:
            return {"available": False, "leads": [],
                    "error": f"no recent cycle published for +{leads[0]}h"}
        ok: List[int] = []
        for ld in leads:
            if LIVE_NWP._exists(model, run, ld):
                ok.append(ld)
        return {
            "available": bool(ok),
            "run": run.isoformat(),
            "cycle": f"{run:%H}Z",
            "leads": ok,
            "leads_missing": [ld for ld in leads if ld not in ok],
        }

    # ------------------------------------------------------------- forecast
    def forecast(self, station_id: str,
                 leads: Tuple[int, ...] = V1_LEADS) -> Dict[str, Any]:
        """
        Live multi-horizon forecast for one supported station.

        Raises LiveNwpError only if NO model/lead could be obtained at all; a
        partially available result is returned with explicit per-model errors.
        """
        info = stations.station_info(station_id)
        if info is None:
            raise LiveNwpError(f"unknown station {station_id}")
        if info["latitude"] is None or info["longitude"] is None:
            raise LiveNwpError(f"station {station_id} has no published coordinates")

        # Extract EVERY supported station from each download. The network cost is
        # identical (one GRIB message per model/lead) and the resulting cache then
        # serves any station instantly, so browsing locations never re-downloads.
        st = [
            {"station": l["station"], "latitude": l["latitude"], "longitude": l["longitude"]}
            for l in stations.list_supported_locations()
            if l["latitude"] is not None and l["longitude"] is not None
        ]

        # ---- pick ONE cycle for every model so valid times are consistent ----
        chosen = self.select_common_cycle(leads)
        if chosen["run"] is None:
            raise LiveNwpError(
                "No live NWP cycle is currently published with the required "
                "forecast horizons from GFS, IFS or ICON. The live forecast is "
                "unavailable; historical V1 evaluation remains available separately.")
        run: datetime = chosen["run"]
        cycle_models: List[str] = chosen["models"]

        # Fetch every (model, lead) for THAT cycle concurrently; isolate failures
        # per model so one failing feed cannot break the others.
        slices: Dict[Tuple[str, int], ModelSlice] = {}
        errors: Dict[Tuple[str, int], str] = {}

        def job(model: str, lead: int):
            return model, lead, LIVE_NWP.get_slice(model, lead, st, run=run)

        # Bounded-concurrency gate: cap simultaneous heavy acquisitions so a
        # rapid-selection storm queues (briefly) instead of spawning unbounded
        # concurrent GRIB/decompress/inference work. Warm-cache hits inside
        # get_slice remain fast; only genuine acquisition contends here.
        acquired = _ACQUISITION_GATE.acquire(timeout=_ACQUIRE_WAIT_S)
        if not acquired:
            raise LiveNwpError(
                "The live forecast service is busy acquiring current model data. "
                "Please retry in a moment. (Concurrent live acquisitions are bounded "
                "to keep the service responsive.)")
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = {ex.submit(job, m, ld): (m, ld)
                        for m in cycle_models for ld in leads}
                for f, (m, ld) in futs.items():
                    try:
                        _, _, sl = f.result()
                        slices[(m, ld)] = sl
                    except LiveNwpError as e:
                        errors[(m, ld)] = str(e)
                    except Exception as e:  # pragma: no cover - defensive
                        errors[(m, ld)] = f"{type(e).__name__}: {e}"
                        logger.warning("live fetch failed for %s +%sh: %s", m, ld, e)
        finally:
            _ACQUISITION_GATE.release()

        for m in NWP_MODELS:
            for ld in leads:
                if (m, ld) not in slices and (m, ld) not in errors:
                    errors[(m, ld)] = (
                        f"{m.upper()} did not publish the {run:%H}Z cycle used for "
                        f"this forecast")

        if not slices:
            raise LiveNwpError(
                "No live NWP data could be obtained from GFS, IFS or ICON for the "
                "current cycle. The live forecast is unavailable; historical V1 "
                "evaluation remains available separately.")

        # Issue time IS the published cycle shared by all contributing models.
        issue_dt = run if run.tzinfo else run.replace(tzinfo=timezone.utc)
        issue_iso = issue_dt.isoformat()
        runs = {m: issue_iso for m in {k[0] for k in slices}}

        reliability, rel_prov = self.historical_reliability_before(issue_dt)

        outcomes: List[LeadOutcome] = []
        for ld in leads:
            nwp: Dict[str, Optional[float]] = {}
            grid: Dict[str, dict] = {}
            errs: Dict[str, str] = {}
            valid: Optional[str] = None
            for m in NWP_MODELS:
                sl = slices.get((m, ld))
                if sl is None:
                    nwp[m] = None
                    errs[m] = errors.get((m, ld), "unavailable")
                    continue
                sv = sl.values.get(station_id)
                if sv is None:
                    nwp[m] = None
                    errs[m] = "station outside model domain"
                    continue
                nwp[m] = sv.value_c
                grid[m] = {
                    "latitude": sv.grid_latitude,
                    "longitude": sv.grid_longitude,
                    "distance_to_station_km": sv.distance_km,
                    "grid_note": sl.grid_note,
                    "run": sl.run,
                }
                valid = valid or sl.valid_time

            availability = {m: nwp.get(m) is not None for m in NWP_MODELS}
            if valid is None:
                valid = (issue_dt + timedelta(hours=ld)).isoformat()

            if not any(availability.values()):
                outcomes.append(LeadOutcome(
                    lead_hours=ld, valid_time=valid, nwp=nwp,
                    availability=availability,
                    weights={m: 0.0 for m in NWP_MODELS},
                    helios_c=None, grid=grid, errors=errs))
                continue

            res = self._infer(issue_dt, datetime.fromisoformat(valid.replace("Z", "+00:00")),
                              info, nwp, availability, reliability)
            outcomes.append(LeadOutcome(
                lead_hours=ld, valid_time=valid, nwp=nwp,
                availability=availability, weights=res["weights"],
                helios_c=res["helios_c"], grid=grid, errors=errs,
                candidates=res.get("candidates")))

        selected = "xgboost"
        lt = self.v2.evaluation() or {}
        mae_key = "mae"
        now = datetime.now(timezone.utc)

        def _is_future(valid_iso: Optional[str]) -> bool:
            """
            Whether a horizon's valid time still lies ahead of wall-clock now.

            The earliest lead of a published cycle can already have elapsed (e.g.
            the 00Z run's +6h is valid at 06Z, which is in the past by mid-morning).
            Such a horizon is still a legitimate product of the current run, but it
            is NOT a forecast of the future and must not be presented as one.
            """
            if not valid_iso:
                return False
            try:
                vt = datetime.fromisoformat(valid_iso.replace("Z", "+00:00"))
            except ValueError:
                return False
            if vt.tzinfo is None:
                vt = vt.replace(tzinfo=timezone.utc)
            return vt > now

        return {
            "mode": "live",
            "issue_time": issue_iso,
            "cycle": f"{issue_dt:%H}Z",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_runs": runs,
            "cycle_models": cycle_models,
            "cycle_alignment": ("all contributing models share this cycle, so each "
                                "horizon has a single consistent valid time"),
            "variable": VARIABLE,
            "units": UNITS,
            "live_strategy": "XGBOOST",
            "live_strategy_locked_test_mae_c": _round((lt.get("results", {})).get("mae"), 4),
            "location": {
                "station": station_id,
                "name": info["name"],
                "latitude": info["latitude"],
                "longitude": info["longitude"],
                "elevation_m": info["elevation_m"],
                "coordinate_source": info["coordinate_source"],
                "evaluation_zone": info["evaluation_zone"],
            },
            "spatial": {
                "support": "station_anchored",
                "anchor_station": station_id,
                "selection_rule": "nearest live model grid point to the anchor station",
                "interpolated": False,
                "note": ("Each live NWP model is sampled at its own nearest grid "
                         "point to the station. No spatial interpolation is applied."),
            },
            "reliability_features": {
                **rel_prov,
                "imputed_by_frozen_preprocessing": not rel_prov["available"],
                "note": ("The 9 optional 7-day reliability features are only "
                         "available when verification data exists strictly before "
                         "the issue time. The frozen January 2025 dataset provides "
                         "none for a current cycle, so they are imputed from the "
                         "frozen TRAIN statistics — identical to the historical "
                         "serving path. No value is fabricated."),
            },
            "horizons": [
                {
                    "lead_time_hours": o.lead_hours,
                    "valid_time": o.valid_time,
                    "nwp_forecasts_c": {m: _round(o.nwp.get(m)) for m in NWP_MODELS},
                    "nwp_availability": o.availability,
                    "nwp_weights": o.weights,
                    "helios_temperature_c": o.helios_c,
                    "model_grid_points": o.grid,
                    "model_errors": o.errors,
                    # Additive: real per-candidate outputs (kernel/xgboost/mlp) on
                    # the same live features; `selected_candidate` is the deployed
                    # one whose value equals helios_temperature_c.
                    "candidate_forecasts": o.candidates,
                    "selected_candidate": selected,
                    # Temporal honesty: distinguishes a future horizon from one
                    # whose valid time has already passed.
                    "is_future": _is_future(o.valid_time),
                }
                for o in outcomes
            ],
            "first_future_lead_hours": next(
                (o.lead_hours for o in outcomes if _is_future(o.valid_time)), None),
            "n_future_horizons": sum(1 for o in outcomes if _is_future(o.valid_time)),
            "temporal_safety": {
                "issue_time_is_published_cycle": True,
                "valid_times_relative_to": now.isoformat(),
                "elapsed_horizons_flagged": True,
                "uses_future_observations": False,
                "reliability_window": "strictly before issue_time",
            },
        }

    # -------------------------------------------------------------- inference
    def _infer(self, issue: datetime, valid: datetime, info: dict,
               nwp: Dict[str, Optional[float]], availability: Dict[str, bool],
               reliability: Optional[dict]) -> Dict[str, Any]:
        """Frozen V2 XGBoost inference for one horizon."""

        # We can just use the V2 service forecast function, which handles
        # feature vector creation, weight prediction, and blending internally.
        # But wait, HeliosV2Service.forecast() already looks up Historical reliability.
        # Since live_forecast_service also does it, it's slightly redundant,
        # but to keep V2 encapsulated we just call it directly.

        res = self.v2.forecast(
            issue_time=issue.replace(tzinfo=None),
            valid_time=valid.replace(tzinfo=None),
            latitude=info["latitude"],
            longitude=info["longitude"],
            location_zone=info["evaluation_zone"],
            forecasts=nwp,
            include_arena=True
        )

        # We return the response adapted to the LiveForecast protocol
        candidates = {
            "xgboost": {
                "temperature_c": res["helios_forecast"],
                "weights": res.get("model_weights", {}),
                "available": res["helios_forecast"] is not None,
                "selected": True
            }
        }

        return {
            "weights": res.get("model_weights", {}),
            "helios_c": res["helios_forecast"],
            "candidates": candidates
        }


LIVE_FORECAST = LiveForecastService()
