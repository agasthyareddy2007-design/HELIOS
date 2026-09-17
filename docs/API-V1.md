# HELIOS V1 API

HELIOS V1 serves a **2 m temperature** forecast for India (January 2025 dataset,
GFS + IFS + ICON), produced by the **validated MLP** arbitration strategy, and
exposes the full **Model Arena** of candidate approaches for transparent
comparison.

V1 is **temperature-only**. The API never fabricates humidity, wind,
precipitation, feels-like temperature, confidence percentages, or weather
descriptions.

---

## Layers (kept deliberately separate)

### 1. NWP layer
`GFS`, `IFS`, `ICON` — the three input numerical weather prediction models.

### 2. HELIOS candidate layer (arbitration strategies)
`Kernel Regression`, `XGBoost`, `MLP` — alternative HELIOS reliability/arbitration
candidates. Each predicts the conditional reliability (expected error) of the NWP
models and converts it to blending weights.

### 3. Baseline
`Simple Average` — permanent baseline. Averages only the participating **available**
models (a missing model is not treated as zero).

### 4. V1 live strategy
`MLP` — the candidate selected by the frozen walk-forward + locked-test protocol.
The live V1 forecast is produced by this frozen MLP.

---

## Two levels (do not confuse them)

```
LEVEL 1 (live serving)
  GFS / IFS / ICON
      -> frozen MLP predicts per-NWP reliability
      -> inverse-error weights (sum to 1 over AVAILABLE models; missing ≠ 0)
      -> blended HELIOS temperature            <-- the live forecast

LEVEL 2 (Model Arena)
  Kernel / XGBoost / MLP
      -> alternative HELIOS arbitration CANDIDATES
      -> historical competition / evaluation (walk-forward + locked test)
```

**LEVEL 1** ("NWP trust") is the weights the live MLP places on GFS/IFS/ICON.
**LEVEL 2** ("Model Arena") is the competition among the three arbitration
candidates. These are different things and are presented separately in the UI.

---

## Why all three candidates are shown

HELIOS is designed as a **multi-candidate reliability/arbitration framework**. The
three candidates are retained for transparent comparison and reproducibility.
Kernel Regression and XGBoost are **validated candidates** (not "failed"); the MLP
is the **validated live strategy** because it was selected by the frozen protocol.

Correct language:

> "HELIOS evaluates multiple candidate arbitration strategies. The V1 live strategy
> is the validated MLP configuration."

Do **not** say "HELIOS dynamically chooses between Kernel, XGBoost and MLP" — that
second-level dynamic arbitration is **not implemented in V1**.

---

## What is NOT implemented in V1

- A **second-level dynamic arbitration** between Kernel / XGBoost / MLP. This is
  reserved for **V2** and would require a new evaluation before it could be
  claimed as an improvement. V1 uses the single validated MLP live strategy.
- Any variable other than 2 m temperature.

---

## Authentication (API keys)

Protected endpoints require an API key supplied in the **`X-API-Key`** request
header. Keys are **never** accepted in query parameters (that would leak them into
logs, browser history, and referrers).

```
X-API-Key: <key>
```

### Public vs protected

| Endpoint            | Auth        |
| ------------------- | ----------- |
| `GET /v1/health`    | **public**  |
| `GET /v1/models`    | protected   |
| `GET /v1/evaluation`| protected   |
| `GET /v1/model-arena`| protected  |
| `GET /v1/samples`   | protected   |
| `GET /v1/forecast`  | protected   |
| `GET /v1/locations` | protected   |
| `GET /v1/live/status`| protected  |
| `GET /v1/live/forecast`| protected |
| `GET /v1/resolve`   | protected   |
| `GET /v1/issue-times`| protected  |
| `GET /v1/usage`     | protected   |

- **Missing** key on a protected endpoint → **HTTP 401**.
- **Invalid** key → **HTTP 401** (the response never reveals whether a key was
  "close" to valid).
- **Valid** key → the request proceeds.

The 401 body is:

```json
{ "error": "unauthorized", "message": "Valid API key required" }
```

### One server, multiple keys

A **single** HELIOS API server (`backend/app/api/v1_app.py`) supports **multiple**
API keys against the **same** application code. There is no per-key server or
duplicated endpoint logic — every protected endpoint uses the same authenticator
(`backend/app/api/auth.py`).

```
HELIOS API (one server)
   ├── key A → allowed
   ├── key B → allowed
   ├── key C → allowed
   └── invalid / missing key → 401
```

### Configuration (keys come from the environment, never source)

Keys are supplied through the **`HELIOS_API_KEYS`** environment variable as
comma-separated entries. Each key has a stable, non-secret `key_id`:

```bash
# id:secret pairs (recommended)
export HELIOS_API_KEYS="demo:sk_demo_xxx,partner:sk_partner_yyy"
# or bare secrets (auto ids key1, key2, ...)
export HELIOS_API_KEYS="sk_xxx,sk_yyy"
python -m backend.app.api.v1_app --port 8011
```

If `HELIOS_API_KEYS` is unset/empty the API is **fail-closed**: no key is valid
and every protected endpoint returns 401.

### Security properties

- **Constant-time comparison** (`hmac.compare_digest`) over all configured keys —
  no timing side channel and no "closeness" disclosure.
- Keys are **never returned** by any endpoint (including `/v1/usage`).
- Keys are **never logged**. The startup banner prints only the key **count** and
  the non-secret **key ids** (e.g. `[demo, partner]`), never the secrets.

### Usage accounting — `GET /v1/usage`

Usage is tracked by `key_id`, never by the raw key. `/v1/usage` returns the count
for the **authenticated** caller:

```json
{ "key_id": "demo", "requests": 12 }
```

There is **no** billing, quota, rate-limiting, or user-account system in V1 — only
authentication and this basic per-key request count.

### Frontend

The frontend client (`frontend/lib/api.js`) sends the **same** key on **all**
protected endpoints (there are not separate keys for `/forecast`, `/models`,
`/evaluation`, `/model-arena`). The key is read from configuration and never
hard-coded:

```bash
export HELIOS_API_KEY="sk_demo_xxx"          # the single key used for all protected calls
export HELIOS_API_BASE="http://127.0.0.1:8011"  # optional API base URL
```

`GET /v1/health` remains callable without a key.

---

## Endpoints

Run: `HELIOS_API_KEYS="demo:sk_demo_xxx" python -m backend.app.api.v1_app --port 8011`
(stdlib HTTP server; no extra web-framework dependency). All responses are JSON.
The API loads frozen artifacts lazily and **does not train any model or recompute
the locked TEST at startup**.

### `GET /v1/health`  (public)
Liveness + flags (`trains_on_startup: false`, `recomputes_test: false`).

### `GET /v1/models`  (protected)
```json
{
  "nwp_models": ["GFS", "IFS", "ICON"],
  "helios_candidates": [
    {"name": "Kernel Regression", "key": "kernel", "type": "candidate", "status": "validated_candidate"},
    {"name": "XGBoost",           "key": "xgboost","type": "candidate", "status": "validated_candidate"},
    {"name": "MLP",               "key": "mlp",    "type": "candidate", "status": "validated_live_strategy"}
  ],
  "baseline": "Simple Average",
  "live_strategy": "MLP",
  "variables": ["temperature_2m_c"],
  "units": "degC"
}
```

### `GET /v1/evaluation`  (protected)
Read directly from the frozen artifacts (`frozen_selection_v1.json`,
`walkforward_*/walkforward_report.json`, `lockedtest_*/locked_test_report.json`).
**Never recomputed; the TEST set is never re-accessed** (`recomputed: false`,
`test_accessed_for_new_computation: false`).

- Walk-forward mean MAE (°C): Kernel 1.6827 (±0.0293, +3.87%), XGBoost 1.6471
  (±0.0286, +5.90%), MLP 1.6395 (±0.0250, +6.33%); Simple Average 1.7505. All
  three beat Simple Average in 8/8 folds.
- Locked TEST (n = 34,591, evaluated once): GFS 2.055, IFS 2.101, ICON 1.816,
  Simple Average 1.700, **HELIOS (MLP) 1.611** (RMSE 2.351, bias −0.686, median
  1.212, p90 3.205, p95 4.240, p99 9.270). HELIOS vs Simple Average **+5.24%**;
  vs best individual (ICON) **+11.30%**.

### `GET /v1/model-arena`  (protected)
Level-2 candidate competition (historical metrics from frozen artifacts). Live
candidate forecasts are populated only when a forecast request context is
provided (see `/v1/forecast?arena=1`); otherwise `forecast_available: false`.

### `GET /v1/forecast?issue_time=..&lead_time_hours=..&station=..`  (protected)
Live V1 forecast for one (issue_time, lead, station), served by the frozen MLP.
Returns the HELIOS temperature, per-NWP temperatures + availability, the
**MLP-derived NWP weights** (sum to 1 over available models), the lead/valid/issue
times, location, units, and (with `arena=1`) the Model Arena candidate forecasts
generated from the already-trained artifacts.

### `GET /v1/samples?limit=N`  (protected)
Sample `(issue_time, lead_time_hours, station)` request keys from the DB for demos.

### `GET /v1/locations`  (protected)
The supported V1 forecast points with their **real station coordinates**.

```json
{
  "locations": [
    {"station": "420270-99999", "name": "Srinagar",
     "latitude": 34.083, "longitude": 74.833, "elevation_m": 1587.0,
     "country": "IN", "evaluation_zone": "north_himalaya",
     "models": ["gfs","icon","ifs"],
     "nearest_grid_km": {"gfs": 11.986, "ifs": 5.27, "icon": 17.943},
     "n_rows": 5930, "coordinate_source": "noaa_isd_station_history"}
  ],
  "count": 354,
  "lead_time_hours": [6, 24, 48, 72, 120],
  "spatial_support": "station_anchored",
  "coordinate_source": "noaa_isd_station_history"
}
```

> **`latitude`/`longitude` are the real station coordinates**, sourced from the
> NOAA ISD station history file — **not** NWP grid coordinates. See the spatial
> model section below for why that distinction matters.

`nearest_grid_km` reports how far each NWP model's closest grid point sits from
the station. `evaluation_zone` is a statistical stratification region and is
**not** a location.

### `GET /v1/resolve?lat=..&lon=..[&require_models=N]`  (protected)
Resolves an **arbitrary coordinate** to the nearest supported forecast point.
V1 is station-anchored, so this is an explicit resolution step — never
interpolation.

```json
{
  "requested": {"latitude": 28.6139, "longitude": 77.209},
  "resolved":  {"station": "421820-99999", "name": "Safdarjung",
                "latitude": 28.585, "longitude": 77.206, "...": "..."},
  "distance_km": 3.23,
  "resolution": "nearest_supported_station",
  "note": "V1 is station-anchored. The forecast is produced for the supported station shown, not interpolated to the requested coordinate. …"
}
```

Clients must disclose `distance_km`. The UI grades it against the dataset's 50 km
verification matching radius: ≤ 25 km representative, 25–100 km caution, > 100 km
shown as *outside supported coverage*.

### `GET /v1/issue-times?station=..&lead_time_hours=..`  (protected)
The model cycles (00Z / 12Z issue times) actually available for a given station
and horizon. Lets the UI offer only selections the frozen dataset can serve.

### `GET /v1/usage`  (protected)
Per-key request accounting for the authenticated caller. Returns
`{"key_id": "<id>", "requests": <n>}`. Never returns the raw API key.

---

## Live serving (current run → future forecast)

V1 has **two strictly separate serving paths**:

| Path | Endpoints | Data |
| --- | --- | --- |
| **LIVE** | `/v1/live/status`, `/v1/live/forecast` | current operational GFS/IFS/ICON cycles, FUTURE valid times |
| **HISTORICAL** | `/v1/forecast`, `/v1/evaluation`, `/v1/model-arena` | frozen January 2025 evaluation dataset |

A live failure returns **503 `live_unavailable`** with `fallback_to_historical: false`.
Historical data is never substituted into a live response.

### Pipeline

```
current cycle (discovered from the live feeds; ONE cycle shared by all models)
   -> GFS  .idx  byte-range  (~500 KB)  -> wgrib2 India crop
   -> IFS  .index byte-range (~640 KB)
   -> ICON DWD bz2 (~3 MB) + cached CLAT/CLON KDTree (2,949,120 cells)
   -> value at each model's nearest grid point to the station anchor
   -> FeatureBuilder (frozen 24-feature contract)
   -> frozen V1 MLP -> per-model reliability -> trust weights
   -> blended HELIOS temperature per horizon (+6/+24/+48/+72/+120 h)
```

Full cycle files are never downloaded. One fetch per (model, lead) serves **all
354 stations**, and the extracted values are cached on disk, so browsing
locations never re-downloads. Cold cycle ≈ 25 s once; warm requests are
sub-millisecond. The server warms the cache in the background at startup
(`--no-warm` disables).

### Cycle alignment (important)

Models publish on different schedules — GFS/IFS may have finished 00Z while ICON
has finished 06Z. Blending a GFS +24h from 00Z with an ICON +24h from 06Z would
combine forecasts valid at **different times**. So `/v1/live/*` selects the most
recent cycle for which the greatest number of models has published every
requested lead, and reports models absent from that cycle as unavailable rather
than back-filling them from another run.

### Temporal safety

A live forecast issued at cycle time `T` may use only information available at
`T` plus history strictly **before** `T`.

* `issue_time` is always a real published cycle, never wall-clock.
* `valid_time = issue_time + lead`.
* The reliability window is `[T − 7 days, T)` — the query is exclusive of `T`, so
  no observation at or after the issue time can influence the forecast.
* Each horizon carries `is_future`. The earliest lead of a cycle can already have
  **elapsed** (a 00Z run's +6h is valid at 06Z); such a horizon is flagged and the
  UI defaults to the first horizon still ahead of now.

### Reliability features on a live cycle

The 9 optional `*_rmse/mae/bias_7day` features require verification data in the 7
days before `T`. The frozen dataset covers **January 2025 only**, so for a current
cycle there is none. They are therefore left `None` and imputed by the **frozen**
preprocessor's `missing_value_fills` (fitted on TRAIN) — exactly what the existing
historical serving path already does. The feature contract is unchanged, nothing
is filled with an arbitrary constant, and the response discloses this in
`reliability_features`.

The 8 **required** features are all computed from live data.

### `GET /v1/live/status`

Which cycle each model has published, the selected common cycle, and whether the
server cache is warm. Memoised (~5 min) so page loads never re-probe the feeds.

### `GET /v1/live/forecast?station=..[&leads=6,24,48]`

```json
{
  "mode": "live",
  "issue_time": "2026-09-09T00:00:00+00:00",
  "cycle": "00Z",
  "cycle_models": ["gfs", "ifs", "icon"],
  "location": {"station": "420270-99999", "name": "Srinagar",
               "latitude": 34.083, "longitude": 74.833, "elevation_m": 1587.0},
  "spatial": {"support": "station_anchored", "interpolated": false},
  "reliability_features": {"available": false,
                           "imputed_by_frozen_preprocessing": true},
  "first_future_lead_hours": 24,
  "n_future_horizons": 4,
  "horizons": [
    {"lead_time_hours": 24, "valid_time": "2026-09-10T00:00:00Z",
     "nwp_forecasts_c": {"gfs": 13.93, "ifs": 16.249, "icon": 17.318},
     "nwp_availability": {"gfs": true, "ifs": true, "icon": true},
     "nwp_weights": {"gfs": 0.585, "ifs": 0.236, "icon": 0.179},
     "helios_temperature_c": 15.083,
     "model_grid_points": {"...": "per-model grid point + offset km"},
     "is_future": true}
  ],
  "temporal_safety": {"uses_future_observations": false,
                      "reliability_window": "strictly before issue_time"}
}
```

Live data is **never written to the database** — the frozen January tables remain
byte-identical.

---

## Spatial model (important)

**Zone ≠ location.** `north_himalaya`, `north_plains`, `central`,
`south_plateau` and `south_coastal` are **evaluation stratification regions** used
for regional performance analysis. They must never be presented as a forecast
location.

**A location is a coordinate.** V1 represents a forecast point as:

```
latitude, longitude     real station coordinates (NOAA ISD station history)
station                 the support/anchor identifier, e.g. 420270-99999
name                    place name, presentation metadata, e.g. "Srinagar"
elevation_m
evaluation_zone         stratification metadata ONLY
```

### Why grid coordinates are not locations

`forecast_verification.latitude/longitude` hold the **NWP grid point**
coordinates of a row, not a place. One station is surrounded by many grid points
(up to ~41 here) because GFS (0.25°), ICON (0.5°) and IFS (reduced Gaussian) use
different native grids; each row stores `observation_distance_km`, the distance
from that grid point to the station. Reading a station's position off a
verification row therefore yields a semi-arbitrary point tens of km from the
actual place.

### Station anchoring and grid selection

V1 is **station-anchored**. The frozen dataset was built with
`spatial_key="station"` (see `ml/dataset_builder.py::_group_examples`): each model
contributes the grid point **nearest the station**, tie-broken by smaller
`verification_id`. Live serving applies the identical ordering, so the served
forecast uses exactly the grid points the validated model was trained and
evaluated on.

`GET /v1/forecast` therefore returns both the real location and full spatial
provenance:

```json
"location": {"latitude": 34.083, "longitude": 74.833, "name": "Srinagar",
             "elevation_m": 1587.0, "station": "420270-99999",
             "coordinate_source": "noaa_isd_station_history",
             "evaluation_zone": "north_himalaya"},
"spatial": {
  "support": "station_anchored",
  "anchor_station": "420270-99999",
  "model_grid_points": {
    "gfs":  {"latitude": 34.0,     "longitude": 74.75,    "distance_to_station_km": 11.986},
    "ifs":  {"latitude": 34.08824, "longitude": 74.77612, "distance_to_station_km": 5.27},
    "icon": {"latitude": 34.0,     "longitude": 75.0,     "distance_to_station_km": 17.943}
  },
  "selection_rule": "nearest grid point to the anchor station per model",
  "interpolated": false
}
```

### What V1 does NOT claim

- No arbitrary-coordinate ("hyperlocal") forecasting. Arbitrary coordinates are
  resolved to the nearest supported station and the distance is disclosed.
- No spatial interpolation or regridding (`interpolated: false`).

**V2** would add proper interpolation/regridding to serve arbitrary coordinates;
the API contracts above are shaped so that becomes an additive change (a future
response can report `interpolated: true` with its own method and uncertainty)
without breaking clients.

---

## Scientific integrity notes

- Evaluation numbers are read from frozen artifacts; the locked TEST is not rerun.
- Model Arena candidate forecasts use only already-trained artifacts
  (`model_kernel.pkl`, `model_xgboost.pkl`, `model_mlp.pt`); **nothing is trained**
  to populate the API.
- Missing NWP model ⇒ 0 weight, no contribution (never encoded as a zero forecast).
- HELIOS learns the **conditional reliability** of the NWP models; it does not
  learn atmospheric physics, and no superiority over other operational systems
  (e.g. NBM/AIFS) is claimed.
