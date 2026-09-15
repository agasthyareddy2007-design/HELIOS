"""
HELIOS V1 — Station (spatial support) repository. READ-ONLY.

WHY THIS EXISTS
---------------
`forecast_verification.latitude/longitude` are the **NWP GRID POINT** coordinates
of a model, NOT the coordinates of a place. A single NOAA station is surrounded by
many grid points (up to ~41 in this dataset, because GFS 0.25°, ICON 0.5° and the
IFS reduced-Gaussian grid all differ), each stored as its own row with
`observation_distance_km` = distance from that grid point to the station.

Reading a station's location straight off a verification row therefore yields a
semi-arbitrary grid point tens of km away from the actual place. The real station
coordinates live in the NOAA ISD station history file, together with the station
NAME and elevation.

SPATIAL MODEL SERVED BY V1
--------------------------
A location is:
    latitude, longitude              <- REAL station coordinates (ISD metadata)
    station_id                       <- the support/anchor identifier
    name                             <- presentation metadata (e.g. "SRINAGAR")
    elevation_m
    evaluation_zone                  <- statistical stratification ONLY, not a location

V1 is **station-anchored**: forecasts exist only at these supported points. Any
arbitrary coordinate must be resolved to the nearest supported station, and the
resolution distance must be disclosed. Arbitrary-coordinate forecasting would
require spatial interpolation/regridding and is NOT claimed by V1.
"""

from __future__ import annotations

import sqlite3
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "helios.db"
ISD_HISTORY = PROJECT_ROOT / "data" / "metadata" / "isd-history.txt"
NWP_MODELS = ("gfs", "ifs", "icon")

# isd-history.txt fixed-width columns (same contract as observation/noaa_isd_reader.py)
_COL_USAF = (0, 6)
_COL_WBAN = (7, 12)
_COL_NAME = (13, 43)
_COL_CTRY = (43, 47)
_COL_LAT = (57, 64)
_COL_LON = (65, 73)
_COL_ELEV = (74, 81)


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (same formula as observation/noaa_isd_reader)."""
    import math

    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2.0) ** 2
    )
    return 2.0 * r * math.asin(math.sqrt(a))


def _title_case(name: str) -> str:
    """ISD names are upper-case; render them as readable place names."""
    small = {"of", "the", "and", "de", "da", "del"}
    parts = []
    for w in name.strip().split():
        lw = w.lower()
        parts.append(lw if lw in small and parts else lw.capitalize())
    return " ".join(parts)


@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def _isd_index() -> Dict[str, Dict[str, Any]]:
    """
    Parse ghcnh-station-list.csv into {station_id: {name, latitude, longitude, elevation_m}}.
    """
    out = {}
    GHCN_STATION_LIST = PROJECT_ROOT / "data" / "raw" / "ghcnh_2026" / "ghcnh-station-list.csv"
    if not GHCN_STATION_LIST.exists():
        return out
    import csv
    with open(GHCN_STATION_LIST, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            st = row.get("GHCN_ID")
            if not st:
                continue
            try:
                lat = float(row.get("LATITUDE", ""))
                lon = float(row.get("LONGITUDE", ""))
            except ValueError:
                continue
                
            elev = None
            if row.get("ELEVATION"):
                try:
                    elev = float(row.get("ELEVATION", ""))
                except ValueError:
                    pass
            
            out[st] = {
                "name": row.get("NAME", "").strip() or None,
                "latitude": lat,
                "longitude": lon,
                "elevation_m": elev,
                "country": row.get("ISO_CODE", "").strip() or None,
            }
    return out

    with open(ISD_HISTORY, "r", encoding="latin-1") as fh:
        for line in fh:
            if len(line) < 73:
                continue
            usaf = line[_COL_USAF[0]:_COL_USAF[1]].strip()
            wban = line[_COL_WBAN[0]:_COL_WBAN[1]].strip()
            if not usaf or not wban:
                continue
            lat_s = line[_COL_LAT[0]:_COL_LAT[1]].strip()
            lon_s = line[_COL_LON[0]:_COL_LON[1]].strip()
            try:
                lat = float(lat_s)
                lon = float(lon_s)
            except ValueError:
                continue
            # ISD uses 0/0 as a missing-coordinate sentinel.
            if lat == 0.0 and lon == 0.0:
                continue
            name = line[_COL_NAME[0]:_COL_NAME[1]].strip()
            elev_s = line[_COL_ELEV[0]:_COL_ELEV[1]].strip()
            try:
                elev = float(elev_s)
            except ValueError:
                elev = None
            out[f"{usaf}-{wban}"] = {
                "name": _title_case(name) if name else None,
                "raw_name": name or None,
                "country": line[_COL_CTRY[0]:_COL_CTRY[1]].strip() or None,
                "latitude": lat,
                "longitude": lon,
                "elevation_m": elev,
            }
    return out


@lru_cache(maxsize=1)
def list_supported_locations() -> tuple:
    """
    Every supported V1 forecast point, with REAL station coordinates.

    Returned as a tuple (hashable/cacheable). Each entry:
      station, name, latitude, longitude, elevation_m, country,
      evaluation_zone, models, nearest_grid_km {model: km}, n_rows,
      coordinate_source
    """
    con = _connect()
    c = con.cursor()

    # Per station+model: how close the NEAREST grid point of that model sits.
    # This mirrors the frozen protocol (spatial_key="station" keeps the grid point
    # nearest the station), so what the UI shows matches what the model consumed.
    per_model: Dict[str, Dict[str, float]] = {}
    for st, model, dmin in c.execute(
        "SELECT observation_station_ids, model, MIN(observation_distance_km) "
        "FROM forecast_verification "
        "WHERE observation_station_ids IS NOT NULL "
        "GROUP BY observation_station_ids, model"
    ):
        if st is None:
            continue
        per_model.setdefault(st, {})[model] = (
            round(float(dmin), 3) if dmin is not None else None
        )

    # Row counts + the dominant evaluation zone (stratification metadata only).
    meta: Dict[str, Dict[str, Any]] = {}
    for st, zone, n in c.execute(
        "SELECT observation_station_ids, location_zone, COUNT(*) "
        "FROM forecast_verification "
        "WHERE observation_station_ids IS NOT NULL "
        "GROUP BY observation_station_ids, location_zone"
    ):
        if st is None:
            continue
        m = meta.setdefault(st, {"n_rows": 0, "zones": {}})
        m["n_rows"] += int(n)
        if zone:
            m["zones"][zone] = m["zones"].get(zone, 0) + int(n)
    con.close()

    idx = _isd_index()
    out: List[Dict[str, Any]] = []
    for st, models in sorted(per_model.items()):
        info = idx.get(st)
        m = meta.get(st, {"n_rows": 0, "zones": {}})
        zone = max(m["zones"], key=m["zones"].get) if m["zones"] else None
        if info is None:
            # No ISD metadata: we will NOT guess a location from a grid point.
            # The station is reported without coordinates so the UI can exclude it
            # from the map rather than plotting something untrue.
            out.append({
                "station": st,
                "name": None,
                "latitude": None,
                "longitude": None,
                "elevation_m": None,
                "country": None,
                "evaluation_zone": zone,
                "models": sorted(models.keys()),
                "nearest_grid_km": models,
                "n_rows": m["n_rows"],
                "coordinate_source": None,
            })
            continue
        out.append({
            "station": st,
            "name": info["name"],
            "latitude": info["latitude"],
            "longitude": info["longitude"],
            "elevation_m": info["elevation_m"],
            "country": info["country"],
            "evaluation_zone": zone,
            "models": sorted(models.keys()),
            "nearest_grid_km": models,
            "n_rows": m["n_rows"],
            "coordinate_source": "noaa_isd_station_history",
        })
    return tuple(out)


def resolve_nearest(latitude: float, longitude: float,
                    require_models: int = 1) -> Optional[Dict[str, Any]]:
    """
    Resolve an ARBITRARY coordinate to the nearest supported V1 forecast point.

    V1 is station-anchored, so this is an honest resolution step — not
    interpolation. The caller is expected to disclose `distance_km` in the UI.

    `require_models` filters to stations having at least that many NWP models.
    Returns None if no station has coordinates (never fabricates a point).
    """
    best = None
    best_d = float("inf")
    for loc in list_supported_locations():
        if loc["latitude"] is None or loc["longitude"] is None:
            continue
        if len(loc["models"]) < require_models:
            continue
        d = haversine_km(latitude, longitude, loc["latitude"], loc["longitude"])
        if d < best_d:
            best_d = d
            best = loc
    if best is None:
        return None
    return {
        "requested": {"latitude": latitude, "longitude": longitude},
        "resolved": dict(best),
        "distance_km": round(best_d, 2),
        "resolution": "nearest_supported_station",
        "note": (
            "V1 is station-anchored. The forecast is produced for the supported "
            "station shown, not interpolated to the requested coordinate. "
            "Arbitrary-coordinate forecasting requires spatial interpolation and "
            "is not part of validated V1."
        ),
    }


def station_info(station: str) -> Optional[Dict[str, Any]]:
    """Real coordinates/name for one station, or None if unknown."""
    for loc in list_supported_locations():
        if loc["station"] == station:
            return dict(loc)
    return None
