# HELIOS Live NWP Forecast Source Audit
**Forecast-Blending Architecture Without Historical NWP Training Data**  
**Date**: 2026-09-07  
**Status**: Architecture audit complete — no historical NWP archives acquired

---

## Executive Summary

**HELIOS remains a forecast-blending system.** Historical GFS/IFS/ICON archives are permanently deferred for the MVP due to bandwidth/cost constraints. The MVP will demonstrate the complete forecast-blending pipeline using **live operational forecasts** with **simple average blending** (no ML training required). Post-SIH selection, historical NWP archives (~150-300 GB) will enable **learned dynamic weighting** for optimized model-specific reliability.

**Key Finding**: HELIOS MVP can demonstrate the forecast-blending value proposition (ensemble > single model) using live GFS/IFS/ICON forecasts without requiring historical NWP training data.

---

## 1. Live Operational NWP Forecast Sources

### GFS (NOAA Global Forecast System)

**Source**: NOAA AWS Big Data Program  
**URL**: https://noaa-gfs-bdp-pds.s3.amazonaws.com  
**Update Cycles**: 00Z, 06Z, 12Z, 18Z (4× daily)  
**Resolution**: 0.25° (~28 km)  
**Forecast Horizon**: 0-384 hours (16 days)
- Hours 0-240: 3-hourly output
- Hours 240-384: 12-hourly output

**Variables Available**:
- TMP:2 m above ground (Temperature)
- DPT:2 m above ground (Dewpoint)
- UGRD:10 m above ground (U-wind component)
- VGRD:10 m above ground (V-wind component)
- PRMSL:mean sea level (Pressure)
- APCP:surface (Accumulated precipitation)
- RH:2 m above ground (Relative humidity)

**Format**: GRIB2  
**Latency**: ~3-4 hours after cycle time  
**Cost**: FREE (AWS Open Data Program)  
**India Subset**: Extract using `wgrib2 -small_grib` (6°N-38°N, 68°E-97°E)

---

### ECMWF IFS (Integrated Forecasting System)

**Source**: ECMWF Open Data  
**URL**: https://data.ecmwf.int/forecasts/  
**Update Cycles**: 00Z, 12Z (2× daily)  
**Resolution**: 0.25° (~28 km)  
**Forecast Horizon**: 0-240 hours (10 days)
- Hours 0-144: 3-hourly output
- Hours 150-240: 6-hourly output

**Variables Available** (open data subset):
- 2t (2m Temperature)
- 2d (2m Dewpoint)
- 10u (10m U-wind component)
- 10v (10m V-wind component)
- msl (Mean sea-level pressure)
- tp (Total precipitation)

**Format**: GRIB2  
**Latency**: ~6-8 hours after cycle time  
**Cost**: FREE (CC-BY-4.0 license)  
**Note**: AIFS (AI-Integrated Forecasting System) also available on same platform

---

### ECMWF AIFS (AI-Integrated Forecasting System)

**Source**: ECMWF Open Data (same as IFS)  
**URL**: https://data.ecmwf.int/forecasts/  
**Update Cycles**: 00Z, 12Z (2× daily)  
**Resolution**: 0.25° (~28 km)  
**Forecast Horizon**: 0-360 hours (15 days)  
**Output**: 6-hourly  
**Variables**: Same subset as IFS open data  
**Format**: GRIB2  
**Latency**: Similar to IFS (~6-8 hours)  
**Cost**: FREE (CC-BY-4.0)  
**Note**: ML-based model running alongside traditional IFS

---

### DWD ICON (German Weather Service)

**Source**: DWD Open Data Server  
**URL**: https://opendata.dwd.de/weather/nwp/icon/grib/  
**Update Cycles**: 00Z, 06Z, 12Z, 18Z (4× daily)  
**Resolution**: ~13 km (icosahedral grid)  
**Forecast Horizon**:
- ICON-Global: 0-180 hours (7.5 days)
- ICON-EU: 0-120 hours (5 days, 7 km resolution)

**Variables Available**:
- T_2M (2m Temperature)
- TD_2M (2m Dewpoint)
- U_10M / V_10M (10m wind components)
- PMSL (Mean sea-level pressure)
- TOT_PREC (Total precipitation)

**Format**: GRIB2  
**Latency**: ~4-5 hours after cycle time  
**Cost**: FREE  
**Note**: Icosahedral grid requires regridding to lat/lon for HELIOS schema

---

## 2. HELIOS Forecast Normalization Schema

All live forecasts normalize to the common `ForecastRecord` schema defined in `/home/agasthya/HELIOS/nwp/common/schemas.py`:

```python
class ForecastRecord(BaseModel):
    # Identification
    forecast_id: str
    model: NWPModel  # Enum(GFS, ECMWF, ICON)
    model_version: Optional[str]
    
    # Temporal (BOTH required for temporal leakage prevention)
    issue_time: datetime  # When forecast was generated
    valid_time: datetime  # When forecast is valid for
    lead_time_hours: int  # Explicitly tracked
    
    # Spatial
    location: Location  # (lat, lon, elevation)
    
    # Variables
    temperature_2m_c: Optional[float]
    dewpoint_2m_c: Optional[float]
    wind_u_10m_ms: Optional[float]
    wind_v_10m_ms: Optional[float]
    pressure_msl_hpa: Optional[float]
    precipitation_mm: Optional[float]
    
    # Metadata
    source: str
    ingestion_time: datetime
```

### Variable Mapping

**GFS → HELIOS**:
- TMP:2 m → `temperature_2m_c` (K → °C)
- DPT:2 m → `dewpoint_2m_c` (K → °C)
- UGRD:10 m → `wind_u_10m_ms`
- VGRD:10 m → `wind_v_10m_ms`
- PRMSL → `pressure_msl_hpa` (Pa → hPa)
- APCP → `precipitation_mm` (kg/m² → mm)

**IFS → HELIOS**:
- 2t → `temperature_2m_c` (K → °C)
- 2d → `dewpoint_2m_c` (K → °C)
- 10u → `wind_u_10m_ms`
- 10v → `wind_v_10m_ms`
- msl → `pressure_msl_hpa` (Pa → hPa)
- tp → `precipitation_mm` (m → mm, accumulated)

**ICON → HELIOS**:
- T_2M → `temperature_2m_c` (K → °C)
- TD_2M → `dewpoint_2m_c` (K → °C)
- U_10M → `wind_u_10m_ms`
- V_10M → `wind_v_10m_ms`
- PMSL → `pressure_msl_hpa` (Pa → hPa)
- TOT_PREC → `precipitation_mm` (kg/m² → mm)

---

## 3. Baseline Blending Without Historical NWP Training

### MVP Approach: Simple Average Blending (No ML Required)

**Step 1: Acquire Live Forecasts**
- Fetch latest GFS 00Z cycle from NOAA AWS
- Fetch latest ECMWF IFS 00Z cycle from ECMWF Open Data
- Fetch latest ICON 00Z cycle from DWD Open Data
- Normalize all to common `ForecastRecord` schema
- Extract India domain subset (6°N-38°N, 68°E-97°E)

**Step 2: Simple Average Blending**

For each `(location, valid_time)`:

```python
blended_temperature = (GFS_temp + IFS_temp + ICON_temp) / 3
blended_dewpoint = (GFS_dew + IFS_dew + ICON_dew) / 3
blended_wind_u = (GFS_u + IFS_u + ICON_u) / 3
blended_wind_v = (GFS_v + IFS_v + ICON_v) / 3
blended_mslp = (GFS_mslp + IFS_mslp + ICON_mslp) / 3
blended_precip = (GFS_precip + IFS_precip + ICON_precip) / 3
```

**Step 3: Verification Against Observations**
- Wait until `valid_time` passes (temporal leakage prevention)
- Fetch NOAA ISD-Lite observation at `valid_time`
- Calculate skill scores:
  - RMSE(blended vs observation)
  - RMSE(GFS vs observation)
  - RMSE(IFS vs observation)
  - RMSE(ICON vs observation)
  - MAE, bias per model and blended

**Expected Result**:
- Simple average should perform **better than worst model**
- Simple average should perform **similar to best model**
- Demonstrates forecast blending value proposition without ML training

---

## 4. Role of Historical Datasets in Live Blending

### ERA5-Land 2025 (AVAILABLE)

**Role**: Contextual features for live forecasts (NOT historical NWP training)

**Use Cases**:
- ✅ Terrain elevation for pressure adjustment
- ✅ Land-sea mask for coastal correction
- ✅ Recent climatology (day-of-year mean from 2025)
- ✅ Anomaly detection (forecast vs climatology)

**NOT Used For**: Historical NWP forecast training

---

### NASA POWER 2025 (AVAILABLE)

**Role**: Solar radiation features (NOT in ERA5-Land)

**Use Cases**:
- ✅ Solar zenith angle calculation
- ✅ Clear-sky radiation baseline
- ✅ Day/night transition modeling
- ✅ Diurnal temperature range estimation

**NOT Used For**: Historical NWP forecast training

---

### NOAA ISD-Lite + GHCN-Daily (AVAILABLE)

**Role**: Real-time verification observations

**Use Cases**:
- ✅ Live forecast verification (after `valid_time` passes)
- ✅ Station-based skill score calculation
- ✅ Regional performance metrics (North/South/East/West India)
- ✅ Model bias estimation (per-model, per-location)

**NOT Used For**: Historical NWP forecast training

---

## 5. Components Requiring Historical NWP Data

### Learned Dynamic Weighting (DEFERRED — Requires Historical NWP)

**Objective**: Learn model-specific reliability as a function of:
- Lead time (Is GFS better at short range? IFS at long range?)
- Weather regime (stable vs convective conditions)
- Location (coastal vs inland, elevation effects)
- Season (monsoon vs winter performance)

**Training Data Required**:
- Historical GFS forecasts (`issue_time`, `valid_time`, predictions)
- Historical IFS forecasts (`issue_time`, `valid_time`, predictions)
- Historical ICON forecasts (`issue_time`, `valid_time`, predictions)
- Verification observations (`observation_time`, actual values)

**Model Architecture** (XGBoost regressor):

**Input Features**:
- `lead_time_hours`
- `day_of_year`
- `hour_of_day`
- `location` (lat, lon, elevation)
- `forecast_spread` (std deviation across models)
- `recent_model_skill` (rolling window of past performance)

**Output**:
- `weight_GFS`, `weight_IFS`, `weight_ICON` (sum to 1)

**Training Process**:
1. Build training set from historical forecasts + observations
2. For each `(valid_time, location)`:
   - Compute per-model absolute error vs observation
   - Extract contextual features
3. Train XGBoost to predict optimal weights
4. At inference: predict weights for live forecast based on features

**Status**: **DEFERRED** until historical NWP archives acquired post-SIH selection

---

## 6. MVP Demonstration Without Historical NWP

### HELIOS MVP Capabilities (NO HISTORICAL NWP REQUIRED)

✅ **Live Forecast Acquisition**
- Fetch GFS, IFS, ICON from operational sources (4× daily for GFS/ICON, 2× daily for IFS)
- Normalize to common `ForecastRecord` schema
- Extract India domain subset
- Handle GRIB2 format and unit conversions

✅ **Simple Average Blending**
- Equal-weight ensemble mean across all models
- Compute blended forecast for all variables
- Output in HELIOS `ForecastRecord` format
- Store in database with temporal metadata

✅ **Real-Time Verification**
- Wait until `valid_time` passes (temporal leakage prevention)
- Fetch NOAA station observations at `valid_time`
- Calculate skill scores (RMSE, MAE, bias)
- Compare blended vs individual models

✅ **Baseline Performance Metrics**
- Track blended forecast skill over time
- Identify best-performing model per variable
- Demonstrate blending value (ensemble > single model)
- Regional aggregation (India subregions)

✅ **Verification Infrastructure**
- Station-to-grid mapping (inverse distance weighting, 4 nearest neighbors)
- Regional aggregation (North/South/East/West India)
- Temporal leakage prevention (built into `VerificationPair` schema)
- Skill score persistence and trending

❌ **Learned Dynamic Weighting**  
**REQUIRES**: Historical NWP forecast archives  
**CURRENT STATUS**: Deferred

---

## 7. Post-SIH Upgrade Path

### Phase 1: MVP Demonstration (Current — No Historical NWP)
- Simple average blending
- Live forecast acquisition pipeline
- Real-time verification
- Demonstrate blending framework and value proposition

### Phase 2: Historical NWP Acquisition (Post-Selection)

**Required Data**:
- GFS historical forecasts: 2024 + 2025 (~50-100 GB)
- ECMWF IFS historical forecasts: 2024 + 2025 (licensing considerations)
- ICON historical forecasts: 2024 + 2025 (~50-100 GB)

**Total Estimate**: ~150-300 GB (manageable post-selection with funding)

### Phase 3: Learned Blending Model Training
- Build training dataset from historical forecasts + observations
- Train XGBoost dynamic weighting model
- Evaluate on held-out 2025 data
- Deploy learned model to production blending pipeline

### Phase 4: Operational Deployment
- Live forecast ingestion pipeline (automated)
- Learned dynamic weighting at inference time
- Real-time verification and monitoring dashboard
- RESTful API for forecast delivery
- Continuous model retraining with recent data

---

## 8. Honest MVP Positioning

### What HELIOS MVP CAN Demonstrate

✅ **Complete forecast-blending pipeline architecture**  
✅ **Live operational forecast acquisition** (GFS/IFS/ICON)  
✅ **Common schema normalization** (temporal leakage prevention)  
✅ **Simple average blending** (baseline ensemble method)  
✅ **Real-time verification** against observations  
✅ **Skill score calculation and comparison**  
✅ **Forecast blending VALUE PROPOSITION** (ensemble > single model)

### What HELIOS MVP CANNOT Demonstrate

❌ **Learned dynamic weighting** (requires historical NWP)  
❌ **Lead-time-dependent model selection**  
❌ **Weather-regime-aware blending**  
❌ **Historical skill-based weighting**

### Honest Messaging

> "HELIOS MVP demonstrates the complete forecast-blending **framework** using live operational GFS/IFS/ICON forecasts with simple average blending. Post-SIH selection, historical NWP archives will enable learned dynamic weighting for optimized model-specific reliability based on lead time, weather regime, and location."

---

## 9. Recommended Implementation Sequence

### Phase 5a: Live Forecast Acquisition (IMMEDIATE)

1. **Build GFS live adapter** (`/home/agasthya/HELIOS/nwp/gfs/gfs_live_adapter.py`)
   - Fetch from NOAA AWS (latest cycle)
   - Extract India domain using `wgrib2 -small_grib`
   - Normalize to `ForecastRecord` schema
   - Store in database

2. **Build ECMWF IFS live adapter** (`/home/agasthya/HELIOS/nwp/ecmwf/ifs_live_adapter.py`)
   - Fetch from ECMWF Open Data API
   - Extract India domain
   - Normalize to `ForecastRecord` schema
   - Handle AIFS (AI model) alongside IFS

3. **Build ICON live adapter** (`/home/agasthya/HELIOS/nwp/icon/icon_live_adapter.py`)
   - Fetch from DWD Open Data Server
   - Regrid from icosahedral to lat/lon
   - Extract India domain
   - Normalize to `ForecastRecord` schema

4. **Test live forecast normalization**
   - Validate unit conversions
   - Verify temporal metadata (`issue_time`, `valid_time`, `lead_time_hours`)
   - Confirm India domain coverage

---

### Phase 5b: Simple Blending Pipeline (IMMEDIATE)

1. **Implement equal-weight ensemble mean**
   - Simple average across all available models
   - Handle missing models gracefully (if IFS not yet available, blend GFS+ICON)

2. **Build blended `ForecastRecord` generator**
   - Input: List of `ForecastRecord` (one per model)
   - Output: Single blended `ForecastRecord` with `model="blended"`

3. **Store blended forecasts in database**
   - Same schema as individual model forecasts
   - Tag with `model="blended"` and `model_version="simple_average_v1"`

---

### Phase 5c: Real-Time Verification (IMMEDIATE)

1. **Wait-until-valid-time scheduler**
   - Monitor database for forecasts where `valid_time` has passed
   - Trigger verification workflow

2. **Fetch NOAA observation at `valid_time`**
   - Query NOAA ISD-Lite for nearest station observation
   - Apply inverse-distance weighting for grid-cell verification

3. **Calculate verification metrics**
   - RMSE, MAE, bias per model (GFS, IFS, ICON, blended)
   - Store in `VerificationPair` records

4. **Store verification results**
   - Database persistence
   - Time-series tracking for skill score trends

---

### Phase 5d: MVP Demonstration (IMMEDIATE)

1. **Run live blending for 7-14 days**
   - Daily cycle: fetch GFS/IFS/ICON, blend, verify

2. **Collect verification statistics**
   - Aggregate skill scores per model
   - Track blending improvement over single models

3. **Generate comparison report**:
   - Blended RMSE vs GFS RMSE
   - Blended RMSE vs IFS RMSE
   - Blended RMSE vs ICON RMSE
   - Regional breakdowns (North/South/East/West India)

4. **Demonstrate blending value**
   - Quantify: "Blended forecast reduces RMSE by X% vs worst model"
   - Show: "Blended forecast matches or exceeds best model performance"

---

### Phase 6: Learned Blending (POST-SELECTION)

**Deferred** until historical NWP archives acquired

---

## 10. Critical Architecture Principles

### HELIOS Remains a Forecast-Blending System

❌ **NOT**: Standalone weather forecasting using only ERA5/NASA POWER  
✅ **YES**: NWP forecast blending (GFS + IFS + ICON → HELIOS → blended forecast)

### Historical Datasets Support, Not Replace, NWP Forecasts

- ERA5-Land: Contextual features (elevation, land mask, climatology)
- NASA POWER: Solar radiation (not in ERA5-Land)
- NOAA observations: Verification ground truth

**None of these replace historical GFS/IFS/ICON forecasts for training.**

### Temporal Leakage Prevention is Mandatory

- `ForecastRecord`: Both `issue_time` and `valid_time` explicitly tracked
- `VerificationPair`: Schema-level validation (`observation_time >= forecast.valid_time`)
- Training: Only use observations from **before** forecast `issue_time` as features
- Verification: Match observations to forecast `valid_time`, not `issue_time`

### MVP is Honest About Capabilities

- **CAN**: Demonstrate blending framework with live forecasts
- **CANNOT**: Demonstrate learned dynamic weighting (requires historical NWP)
- **POST-SELECTION**: Historical NWP enables full learned blending system

---

## 11. Storage and Bandwidth Considerations

### Current Storage Usage

- **Total**: 2.04 GB / 220 GB (0.9% used)
  - ERA5-Land 2025: 1.2 GB
  - NASA POWER 2025: 285 MB
  - ERA5 MSLP 2025: 43 MB
  - NOAA observations: ~300 MB

### Live Forecast Storage (Estimated)

**Daily acquisition** (4 cycles × 3 models):
- GFS: ~50-100 MB per cycle (India subset, 0-168h)
- IFS: ~50-100 MB per cycle (India subset, 0-240h)
- ICON: ~50-100 MB per cycle (India subset, 0-180h)

**Daily total**: ~600-1200 MB (~1 GB/day)  
**7-day rolling window**: ~7 GB  
**30-day archive**: ~30 GB

**Well within budget** (217.96 GB remaining)

### Historical NWP (Post-Selection)

- GFS 2024+2025: ~50-100 GB
- IFS 2024+2025: ~50-100 GB (licensing required)
- ICON 2024+2025: ~50-100 GB

**Total**: ~150-300 GB (requires external funding post-selection)

---

## Audit Complete

**Status**: Architecture audit complete  
**HELIOS Objective**: Forecast blending (GFS + IFS + ICON → blended forecast)  
**MVP Approach**: Live forecasts + simple average blending  
**Post-Selection**: Historical NWP → learned dynamic weighting  
**No Additional Downloads**: GFS historical acquisition remains deferred

**Next Steps**: Implement Phase 5a (live forecast acquisition adapters)
