"""
HELIOS V1 — Forecast repository (read-only DB access).

Fetches the per-NWP (GFS/IFS/ICON) 2m-temperature forecasts already stored in
the authoritative HELIOS database for a requested (issue_time, valid_time,
station), so the live V1 forecast endpoint can serve real data. Read-only; never
writes; never recomputes TEST; temperature-only.

Missing model => absent from the returned dict (the service treats missing as
unavailable, NOT zero).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "helios.db"
NWP_MODELS = ("gfs", "ifs", "icon")


def _connect():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def list_sample_requests(limit: int = 20) -> List[Dict[str, Any]]:
    """Return sample (issue, valid, lead, station) tuples that have >=1 NWP model,
    for demo/exploration. Read-only."""
    con = _connect(); c = con.cursor()
    rows = c.execute(
        "SELECT DISTINCT issue_time, valid_time, lead_time_hours, observation_station_ids "
        "FROM forecast_verification WHERE observation_station_ids IS NOT NULL "
        "ORDER BY issue_time, lead_time_hours LIMIT ?", (limit,)).fetchall()
    con.close()
    out = []
    for it, vt, lead, st in rows:
        out.append({"issue_time": it, "valid_time": vt, "lead_time_hours": lead, "station": st})
    return out


def get_nwp_forecasts(issue_time: str, lead_time_hours: int, station: str
                      ) -> Optional[Dict[str, Any]]:
    """
    Fetch available NWP temperatures for a (issue, lead, station).

    SPATIAL CONTRACT — must match the frozen protocol
    -------------------------------------------------
    The frozen V1 dataset was built with ``spatial_key="station"``: GFS, IFS and
    ICON sit on different native grids, so each model's rows are anchored to a
    shared NOAA station, and when several grid points of the SAME model map to one
    station the builder keeps the point NEAREST the station (tie-break: smaller
    verification_id). See ml/dataset_builder.py::_group_examples.

    This function therefore orders by ``observation_distance_km ASC,
    verification_id ASC`` so live serving selects exactly the same grid point the
    validated model was trained and evaluated on. (A bare ``LIMIT 1`` would pick
    an arbitrary one of up to ~41 candidate grid points.)

    Returns forecasts{model->degC (present only)} plus, for spatial disclosure,
    the per-model grid point actually used and its distance to the station.
    `latitude`/`longitude` are the grid coordinates of the reference model and are
    NOT the station's location — real station coordinates come from
    station_repository (NOAA ISD metadata).
    """
    con = _connect(); c = con.cursor()
    forecasts: Dict[str, float] = {}
    grid: Dict[str, Dict[str, Any]] = {}
    lat = lon = zone = valid = None
    for m in NWP_MODELS:
        r = c.execute(
            "SELECT forecast_value, latitude, longitude, location_zone, valid_time, "
            "       observation_distance_km "
            "FROM forecast_verification "
            "WHERE model=? AND issue_time=? AND lead_time_hours=? "
            "      AND observation_station_ids=? "
            "ORDER BY (observation_distance_km IS NULL), observation_distance_km ASC, "
            "         verification_id ASC "
            "LIMIT 1",
            (m, issue_time, lead_time_hours, station)).fetchone()
        if r is not None and r[0] is not None:
            forecasts[m] = float(r[0])
            grid[m] = {
                "latitude": r[1],
                "longitude": r[2],
                "distance_to_station_km": (round(float(r[5]), 3)
                                           if r[5] is not None else None),
            }
            lat, lon, zone, valid = r[1], r[2], r[3], r[4]
    con.close()
    if not forecasts:
        return None
    return {"forecasts": forecasts, "latitude": lat, "longitude": lon,
            "location_zone": zone, "valid_time": valid, "issue_time": issue_time,
            "lead_time_hours": lead_time_hours, "station": station,
            "grid_points": grid}


def list_lead_times() -> List[int]:
    """Distinct forecast lead times actually present in the DB (read-only)."""
    con = _connect(); c = con.cursor()
    rows = c.execute("SELECT DISTINCT lead_time_hours FROM forecast_verification "
                     "ORDER BY lead_time_hours").fetchall()
    con.close()
    return [int(r[0]) for r in rows if r[0] is not None]


def list_issue_times(station: str, lead_time_hours: int) -> List[str]:
    """Issue times available for a given station+lead (read-only)."""
    con = _connect(); c = con.cursor()
    rows = c.execute(
        "SELECT DISTINCT issue_time FROM forecast_verification "
        "WHERE observation_station_ids=? AND lead_time_hours=? "
        "ORDER BY issue_time", (station, lead_time_hours)).fetchall()
    con.close()
    return [r[0] for r in rows]


def parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(s)
