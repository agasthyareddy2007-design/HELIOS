"""
HELIOS — LIVE NWP acquisition (current model runs, future valid times).

WHAT THIS DOES
--------------
Fetches the CURRENT operational 2 m temperature forecast from GFS, IFS and ICON
and extracts the value at each supported HELIOS station. It never reads the
January 2025 historical tables — live and historical are strictly separate paths.

EFFICIENCY (this is what makes live serving viable)
--------------------------------------------------
A full GFS cycle file is ~500 MB. We never download one. Instead:

  GFS  : fetch `.idx`, locate the `TMP:2 m above ground` message, HTTP Range
         request only those bytes (~500 KB), crop to India with wgrib2.
  IFS  : fetch `.index` (JSONL), locate the `2t` sfc record, Range request only
         that message (~640 KB).
  ICON : DWD publishes one small file per variable+step (~3 MB bz2) on the native
         icosahedral grid. Cell coordinates come from the time-invariant
         CLAT/CLON files, fetched once and cached permanently (the grid does not
         change), then a KDTree maps stations to cells.

One download therefore serves ALL stations for that (model, run, lead), and the
extracted station values (a few hundred floats) are cached on disk. Repeated
browser requests never re-download anything.

SPATIAL CONSISTENCY WITH VALIDATED V1
-------------------------------------
V1's validated rule is "value at the model grid point nearest the station
anchor". This module applies exactly that rule per model, and reports the grid
point used plus its distance, so live spatial provenance is as explicit as the
historical path.

Note that the live ICON product is the native ~13 km icosahedral grid, whereas
the frozen historical ICON rows came from the coarser TIGGE 0.5° archive. That is
a real difference between the live feed and the evaluation dataset and is
reported in the API response rather than hidden.
"""

from __future__ import annotations

import bz2
import json
import logging
import math
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = PROJECT_ROOT / "data" / "temporary" / "live_cache"
GRID_DIR = PROJECT_ROOT / "data" / "metadata" / "live_grids"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
GRID_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

GFS_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
IFS_BASE = "https://data.ecmwf.int/forecasts"
ICON_BASE = "https://opendata.dwd.de/weather/nwp/icon/grib"

# India domain used to crop GFS (keeps the parsed array tiny).
INDIA = {"lon_min": 68.0, "lon_max": 98.0, "lat_min": 6.0, "lat_max": 36.0}

# The forecast horizons HELIOS V1 serves.
V1_LEADS: Tuple[int, ...] = (6, 24, 48, 72, 120)

# Model cycle cadence (hours) for run discovery.
CYCLE_HOURS = 6

# How long a cached (model, run, lead) extraction stays valid. The content is
# immutable once published, so this is effectively a housekeeping bound.
CACHE_TTL_S = 12 * 3600

NETWORK_TIMEOUT_S = 120


# ----------------------------------------------------------------- utilities
def _run(cmd: List[str], timeout: int = NETWORK_TIMEOUT_S) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _head_ok(url: str, timeout: int = 30) -> bool:
    try:
        r = _run(["curl", "-sfI", "-o", "/dev/null", "-w", "%{http_code}", url], timeout)
        return r.stdout.strip() == "200"
    except Exception:
        return False


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def latest_cycle(now: Optional[datetime] = None, back: int = 0) -> datetime:
    """The nominal model cycle `back` cycles before now (UTC, 6-hourly)."""
    n = (now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    n = n - timedelta(hours=CYCLE_HOURS * back)
    return n.replace(hour=(n.hour // CYCLE_HOURS) * CYCLE_HOURS)


@dataclass
class StationValue:
    """A live forecast value at one station, with its grid provenance."""
    station: str
    value_c: float
    grid_latitude: float
    grid_longitude: float
    distance_km: float


@dataclass
class ModelSlice:
    """One (model, run, lead) extraction across all requested stations."""
    model: str
    run: str            # ISO issue/cycle time
    lead_hours: int
    valid_time: str     # ISO
    values: Dict[str, StationValue]
    source: str
    grid_note: str
    fetched_at: str

    def to_json(self) -> dict:
        d = asdict(self)
        d["values"] = {k: asdict(v) for k, v in self.values.items()}
        return d

    @staticmethod
    def from_json(d: dict) -> "ModelSlice":
        vals = {k: StationValue(**v) for k, v in d["values"].items()}
        return ModelSlice(
            model=d["model"], run=d["run"], lead_hours=d["lead_hours"],
            valid_time=d["valid_time"], values=vals, source=d["source"],
            grid_note=d["grid_note"], fetched_at=d["fetched_at"])


class LiveNwpError(RuntimeError):
    """Raised when a live model slice genuinely cannot be produced."""


# ------------------------------------------------------------------ service
class LiveNwpService:
    """
    Acquires live NWP station values with aggressive caching.

    Thread-safe. All network work is guarded by a per-key lock so concurrent
    browser requests coalesce into a single download.
    """

    def __init__(self) -> None:
        self._mem: Dict[str, ModelSlice] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global = threading.Lock()
        self._icon_grid: Optional[Tuple[Any, Any, Any]] = None  # (tree, lat, lon)
        self._icon_lock = threading.Lock()

    # ---- cache plumbing -------------------------------------------------
    @staticmethod
    def _key(model: str, run: datetime, lead: int) -> str:
        return f"{model}_{run:%Y%m%d%H}_{lead:03d}"

    def _lock_for(self, key: str) -> threading.Lock:
        with self._global:
            return self._locks.setdefault(key, threading.Lock())

    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / f"{key}.json"

    def _load_cache(self, key: str) -> Optional[ModelSlice]:
        if key in self._mem:
            return self._mem[key]
        p = self._cache_path(key)
        if not p.exists():
            return None
        if time.time() - p.stat().st_mtime > CACHE_TTL_S:
            return None
        try:
            sl = ModelSlice.from_json(json.loads(p.read_text()))
            self._mem[key] = sl
            return sl
        except Exception:
            return None

    def _save_cache(self, key: str, sl: ModelSlice) -> None:
        self._mem[key] = sl
        tmp = self._cache_path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(sl.to_json()))
        os.replace(tmp, self._cache_path(key))

    def cached_keys(self) -> List[str]:
        return sorted(p.stem for p in CACHE_DIR.glob("*.json"))

    # ---- run discovery --------------------------------------------------
    def discover_run(self, model: str, lead: int, max_back: int = 6) -> Optional[datetime]:
        """
        Most recent published cycle for (model, lead).

        Publication lags the nominal cycle time by hours, so we walk backwards
        until the artifact for this lead actually exists.
        """
        for back in range(max_back):
            run = latest_cycle(back=back)
            if self._exists(model, run, lead):
                return run
        return None

    def _exists(self, model: str, run: datetime, lead: int) -> bool:
        if model == "gfs":
            return _head_ok(f"{GFS_BASE}/{self._gfs_key(run, lead)}.idx")
        if model == "ifs":
            return _head_ok(self._ifs_index_url(run, lead))
        if model == "icon":
            return _head_ok(self._icon_url(run, lead))
        raise LiveNwpError(f"unknown model {model}")

    # ---- URL builders ---------------------------------------------------
    @staticmethod
    def _gfs_key(run: datetime, lead: int) -> str:
        return (f"gfs.{run:%Y%m%d}/{run:%H}/atmos/"
                f"gfs.t{run:%H}z.pgrb2.0p25.f{lead:03d}")

    @staticmethod
    def _ifs_grib_url(run: datetime, lead: int) -> str:
        return (f"{IFS_BASE}/{run:%Y%m%d}/{run:%H}z/ifs/0p25/oper/"
                f"{run:%Y%m%d%H}0000-{lead}h-oper-fc.grib2")

    @classmethod
    def _ifs_index_url(cls, run: datetime, lead: int) -> str:
        return cls._ifs_grib_url(run, lead).replace(".grib2", ".index")

    @staticmethod
    def _icon_url(run: datetime, lead: int) -> str:
        name = (f"icon_global_icosahedral_single-level_{run:%Y%m%d%H}_"
                f"{lead:03d}_T_2M.grib2.bz2")
        return f"{ICON_BASE}/{run:%H}/t_2m/{name}"

    # ---- public entry ---------------------------------------------------
    def get_slice(self, model: str, lead: int, stations: List[dict],
                  run: Optional[datetime] = None) -> ModelSlice:
        """
        Live values for one model/lead at the given stations.

        `stations` items need: station, latitude, longitude.
        Raises LiveNwpError if the slice cannot be produced (never fabricates).
        """
        if run is None:
            run = self.discover_run(model, lead)
            if run is None:
                raise LiveNwpError(
                    f"{model.upper()} has not published lead +{lead}h for any recent cycle")
        key = self._key(model, run, lead)
        cached = self._load_cache(key)
        if cached is not None and all(s["station"] in cached.values for s in stations):
            return cached

        with self._lock_for(key):
            cached = self._load_cache(key)
            if cached is not None and all(s["station"] in cached.values for s in stations):
                return cached
            if model == "gfs":
                sl = self._fetch_gfs(run, lead, stations)
            elif model == "ifs":
                sl = self._fetch_ifs(run, lead, stations)
            elif model == "icon":
                sl = self._fetch_icon(run, lead, stations)
            else:
                raise LiveNwpError(f"unknown model {model}")
            self._save_cache(key, sl)
            return sl

    # ---- GFS ------------------------------------------------------------
    def _fetch_gfs(self, run: datetime, lead: int, stations: List[dict]) -> ModelSlice:
        key = self._gfs_key(run, lead)
        idx = _run(["curl", "-sf", f"{GFS_BASE}/{key}.idx"])
        if idx.returncode != 0:
            raise LiveNwpError(f"GFS idx unavailable for {run:%Y-%m-%d %HZ} +{lead}h")
        lines = idx.stdout.splitlines()
        rng = None
        for i, ln in enumerate(lines):
            p = ln.split(":")
            if len(p) >= 5 and p[3] == "TMP" and p[4] == "2 m above ground":
                start = int(p[1])
                end = str(int(lines[i + 1].split(":")[1]) - 1) if i + 1 < len(lines) else ""
                rng = f"{start}-{end}"
                break
        if rng is None:
            raise LiveNwpError("GFS idx has no 'TMP:2 m above ground' record")

        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "gfs.grib2"
            r = _run(["curl", "-sf", "-H", f"Range: bytes={rng}", "-o", str(raw),
                      f"{GFS_BASE}/{key}"])
            if r.returncode != 0 or not raw.exists():
                raise LiveNwpError("GFS byte-range download failed")
            crop = Path(td) / "india.grib2"
            c = None
            try:
                c = _run(["wgrib2", str(raw), "-small_grib",
                          f"{INDIA['lon_min']}:{INDIA['lon_max']}",
                          f"{INDIA['lat_min']}:{INDIA['lat_max']}", str(crop)])
            except FileNotFoundError:
                pass
            use = crop if (c is not None and c.returncode == 0 and crop.exists()) else raw
            vals, valid = self._extract_latlon(use, stations)

        return ModelSlice(
            model="gfs", run=run.isoformat(), lead_hours=lead, valid_time=valid,
            values=vals, source=f"{GFS_BASE} (0.25 deg, .idx byte-range)",
            grid_note="GFS 0.25 deg regular lat-lon; nearest grid point to station",
            fetched_at=datetime.now(timezone.utc).isoformat())

    # ---- IFS ------------------------------------------------------------
    def _fetch_ifs(self, run: datetime, lead: int, stations: List[dict]) -> ModelSlice:
        url = self._ifs_grib_url(run, lead)
        idx = _run(["curl", "-sf", self._ifs_index_url(run, lead)])
        if idx.returncode != 0:
            raise LiveNwpError(f"IFS index unavailable for {run:%Y-%m-%d %HZ} +{lead}h")
        rng = None
        for ln in idx.stdout.splitlines():
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if rec.get("param") in ("2t", "t2m") and rec.get("levtype") == "sfc":
                rng = f"{rec['_offset']}-{rec['_offset'] + rec['_length'] - 1}"
                break
        if rng is None:
            raise LiveNwpError("IFS index has no 2t/sfc record")

        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "ifs.grib2"
            r = _run(["curl", "-sf", "-H", f"Range: bytes={rng}", "-o", str(raw), url])
            if r.returncode != 0 or not raw.exists():
                raise LiveNwpError("IFS byte-range download failed")
            vals, valid = self._extract_latlon(raw, stations)

        return ModelSlice(
            model="ifs", run=run.isoformat(), lead_hours=lead, valid_time=valid,
            values=vals, source=f"{IFS_BASE} (IFS 0.25 deg oper, .index byte-range)",
            grid_note="IFS 0.25 deg regular lat-lon; nearest grid point to station",
            fetched_at=datetime.now(timezone.utc).isoformat())

    # ---- ICON -----------------------------------------------------------
    def _icon_grid_files(self, run: datetime) -> Tuple[Any, Any, Any]:
        """
        Load (KDTree, clat, clon) for the ICON icosahedral grid.

        The grid is time-invariant, so it is fetched once and cached on disk
        permanently. Building the tree over 2.9M cells takes a few seconds and is
        then held in memory.
        """
        import numpy as np
        from scipy.spatial import cKDTree

        with self._icon_lock:
            if self._icon_grid is not None:
                return self._icon_grid

            npz = GRID_DIR / "icon_global_cells.npz"
            if npz.exists():
                z = np.load(npz)
                clat, clon = z["clat"], z["clon"]
            else:
                import xarray as xr
                arrs = {}
                for v in ("clat", "clon"):
                    got = None
                    for back in range(8):
                        r0 = latest_cycle(back=back)
                        name = (f"icon_global_icosahedral_time-invariant_"
                                f"{r0:%Y%m%d%H}_{v.upper()}.grib2.bz2")
                        url = f"{ICON_BASE}/{r0:%H}/{v}/{name}"
                        if not _head_ok(url):
                            continue
                        with tempfile.TemporaryDirectory() as td:
                            bzp = Path(td) / name
                            rr = _run(["curl", "-sf", "-o", str(bzp), url], 300)
                            if rr.returncode != 0:
                                continue
                            gp = Path(td) / name.replace(".bz2", "")
                            with bz2.open(bzp, "rb") as fi, open(gp, "wb") as fo:
                                fo.write(fi.read())
                            ds = xr.open_dataset(gp, engine="cfgrib",
                                                 backend_kwargs={"indexpath": ""})
                            got = np.asarray(ds[list(ds.data_vars)[0]].values, dtype="float64")
                            ds.close()
                        break
                    if got is None:
                        raise LiveNwpError(f"ICON grid file {v.upper()} unavailable")
                    arrs[v] = got
                clat, clon = arrs["clat"], arrs["clon"]
                np.savez_compressed(npz, clat=clat, clon=clon)

            la, lo = np.radians(clat), np.radians(clon)
            xyz = np.column_stack([np.cos(la) * np.cos(lo),
                                   np.cos(la) * np.sin(lo),
                                   np.sin(la)])
            tree = cKDTree(xyz)
            self._icon_grid = (tree, clat, clon)
            return self._icon_grid

    def _fetch_icon(self, run: datetime, lead: int, stations: List[dict]) -> ModelSlice:
        import numpy as np
        import xarray as xr

        tree, clat, clon = self._icon_grid_files(run)
        url = self._icon_url(run, lead)
        with tempfile.TemporaryDirectory() as td:
            bzp = Path(td) / "icon.grib2.bz2"
            r = _run(["curl", "-sf", "-o", str(bzp), url], 300)
            if r.returncode != 0 or not bzp.exists():
                raise LiveNwpError(f"ICON download failed for {run:%Y-%m-%d %HZ} +{lead}h")
            gp = Path(td) / "icon.grib2"
            with bz2.open(bzp, "rb") as fi, open(gp, "wb") as fo:
                fo.write(fi.read())
            ds = xr.open_dataset(gp, engine="cfgrib", backend_kwargs={"indexpath": ""})
            var = list(ds.data_vars)[0]
            field = np.asarray(ds[var].values, dtype="float64").ravel()
            valid = str(np.datetime_as_string(ds.valid_time.values, unit="s"))
            ds.close()

        if field.size != clat.size:
            raise LiveNwpError(
                f"ICON field size {field.size} does not match grid {clat.size}")

        vals: Dict[str, StationValue] = {}
        for s in stations:
            lat, lon = s["latitude"], s["longitude"]
            if lat is None or lon is None:
                continue
            a, b = math.radians(lat), math.radians(lon)
            _, i = tree.query([math.cos(a) * math.cos(b),
                               math.cos(a) * math.sin(b),
                               math.sin(a)])
            k = float(field[int(i)]) - 273.15
            glat, glon = float(clat[int(i)]), float(clon[int(i)])
            vals[s["station"]] = StationValue(
                station=s["station"], value_c=round(k, 3),
                grid_latitude=round(glat, 5), grid_longitude=round(glon, 5),
                distance_km=round(haversine_km(lat, lon, glat, glon), 3))

        return ModelSlice(
            model="icon", run=run.isoformat(), lead_hours=lead,
            valid_time=_iso_utc(valid), values=vals,
            source=f"{ICON_BASE} (DWD ICON global, native icosahedral)",
            grid_note=("ICON native icosahedral ~13 km; nearest cell to station. "
                       "NOTE: finer than the 0.5 deg TIGGE ICON used in the frozen "
                       "January 2025 evaluation dataset."),
            fetched_at=datetime.now(timezone.utc).isoformat())

    # ---- shared lat/lon extraction --------------------------------------
    @staticmethod
    def _extract_latlon(grib: Path, stations: List[dict]) -> Tuple[Dict[str, StationValue], str]:
        """Nearest-grid-point extraction from a regular lat/lon GRIB message."""
        import numpy as np
        import xarray as xr

        ds = xr.open_dataset(grib, engine="cfgrib", backend_kwargs={"indexpath": ""})
        var = list(ds.data_vars)[0]
        da = ds[var]
        lats = np.asarray(da["latitude"].values, dtype="float64")
        lons = np.asarray(da["longitude"].values, dtype="float64")
        field = np.asarray(da.values, dtype="float64")
        valid = str(np.datetime_as_string(ds.valid_time.values, unit="s"))
        ds.close()

        # Normalise longitudes to [-180, 180] for consistent nearest search.
        lon_norm = ((lons + 180.0) % 360.0) - 180.0

        out: Dict[str, StationValue] = {}
        for s in stations:
            lat, lon = s["latitude"], s["longitude"]
            if lat is None or lon is None:
                continue
            i = int(np.argmin(np.abs(lats - lat)))
            j = int(np.argmin(np.abs(lon_norm - (((lon + 180.0) % 360.0) - 180.0))))
            v = float(field[i, j]) - 273.15
            glat, glon = float(lats[i]), float(lon_norm[j])
            out[s["station"]] = StationValue(
                station=s["station"], value_c=round(v, 3),
                grid_latitude=round(glat, 5), grid_longitude=round(glon, 5),
                distance_km=round(haversine_km(lat, lon, glat, glon), 3))
        return out, _iso_utc(valid)


def _iso_utc(s: str) -> str:
    """Normalise a numpy datetime string to an explicit UTC ISO timestamp."""
    s = s.replace(" ", "T")
    if not s.endswith("Z") and "+" not in s:
        s = s + "Z"
    return s


# Module-level singleton: one cache/grid per server process.
LIVE_NWP = LiveNwpService()
