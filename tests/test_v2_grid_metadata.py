"""Deterministic test for the canonical HELIOS V2 0.5deg grid metadata (data/v2/grid/).

Verifies the persisted coordinate arrays and grid_metadata.json match the canonical
definition and the actual V2 forecast array shapes. Read-only w.r.t. forecast data.
"""
import json
import os
import glob

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GDIR = os.path.join(ROOT, "data", "v2", "grid")


def _load():
    lat = np.load(os.path.join(GDIR, "lat.npy"))
    lon = np.load(os.path.join(GDIR, "lon.npy"))
    with open(os.path.join(GDIR, "grid_metadata.json")) as f:
        meta = json.load(f)
    return lat, lon, meta


def test_coordinate_arrays():
    lat, lon = _load()[:2]
    assert len(lat) == 65
    assert len(lon) == 59
    assert lat[0] == 6.0 and lat[-1] == 38.0
    assert lon[0] == 68.0 and lon[-1] == 97.0
    assert np.allclose(np.diff(lat), 0.5)
    assert np.allclose(np.diff(lon), 0.5)
    assert np.all(np.diff(lat) > 0)  # south -> north
    assert np.all(np.diff(lon) > 0)  # west -> east


def test_matches_arange_definition():
    """Coordinates must equal the exact arange expression used in acquisition."""
    lat, lon = _load()[:2]
    assert np.array_equal(lat, np.arange(6.0, 38.0 + 1e-9, 0.5))
    assert np.array_equal(lon, np.arange(68.0, 97.0 + 1e-9, 0.5))


def test_metadata_json():
    meta = _load()[2]
    assert meta["grid_id"] == "india_0p5deg_v2"
    assert meta["shape"] == [65, 59]
    assert meta["temperature_units"] == "K"
    assert meta["coordinate_system"] == "regular_latitude_longitude"
    assert meta["latitude"] == {"start": 6.0, "end": 38.0, "spacing": 0.5,
                                "count": 65, "ordering": "south_to_north"}
    assert meta["longitude"] == {"start": 68.0, "end": 97.0, "spacing": 0.5,
                                 "count": 59, "ordering": "west_to_east"}


def test_matches_forecast_shapes():
    lat, lon = _load()[:2]
    shape = (len(lat), len(lon))
    for model in ("gfs", "ifs", "icon"):
        files = glob.glob(os.path.join(ROOT, "data", "v2", "forecasts", model, "*.npy"))
        assert files, f"no {model} forecast files found"
        for p in files:
            a = np.load(p, mmap_mode="r")
            assert a.shape == shape, f"{p} shape {a.shape} != {shape}"
