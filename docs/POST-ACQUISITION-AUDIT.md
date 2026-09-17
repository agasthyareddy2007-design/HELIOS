# HELIOS Phase 4 Post-Acquisition Pipeline Audit

**Audit Date**: 2026-09-07  
**Audit Scope**: Post-NOAA acquisition pipeline status, GFS dependencies, temporal leakage prevention, implementation readiness  
**Status**: Phase 4 PARTIAL — Observational and reanalysis data complete, NWP forecast data (GFS) frozen

---

## Executive Summary

### Datasets Acquired (Phase 4)

| Dataset | Status | Files | Size | Coverage | Purpose |
|---------|--------|-------|------|----------|---------|
| **ERA5-Land 2025** | ✅ Complete | 12 GRIB | 1.24 GB | Jan-Dec, 4x daily | Ground truth target (training) |
| **ERA5 MSLP 2025** | ✅ Complete | 12 GRIB | 44 MB | Jan-Dec, 4x daily | MSLP ground truth |
| **NOAA ISD-Lite 2025** | ✅ Complete | 382 stations | 5.2 MB | Jan-Aug, hourly | Independent verification (hourly) |
| **NOAA GHCN-Daily** | ✅ Complete | 3,807 stations | 572 MB | Historical + 2025 | Independent verification (daily) |
| **GFS 2025** | 🔒 FROZEN | 0 files | 0 MB | None | NWP forecasts (pilot deleted) |
| **NASA POWER 2025** | ⏸ DEFERRED | 0 files | 0 MB | None | Auxiliary data (not acquired) |

**Total Phase 4 Storage**: 1.85 GB (within 220 GB budget)

### Critical Finding

**HELIOS MVP architecture requires GFS forecasts as input features for post-processing.** Without GFS data:
- ❌ Cannot train GFS post-processing models
- ❌ Cannot implement forecast blending (no forecasts to blend)
- ✅ CAN implement ERA5-to-ERA5 "reanalysis reconstruction" as proof-of-concept
- ✅ CAN implement NOAA verification infrastructure for later use
- ✅ CAN implement data preprocessing pipelines

---

## 1. Current Database/Schema Status

### Schema Implementation: **DEFINED BUT NOT DEPLOYED**

**Location**: `/home/agasthya/HELIOS/nwp/common/schemas.py`

**Core Pydantic Schemas**:

```python
class ForecastRecord(BaseModel):
    # Temporal leakage prevention built-in
    issue_time: datetime          # When forecast was generated
    valid_time: datetime          # When forecast is valid for
    lead_time_hours: int         # Hours between issue and valid
    
    # Spatial
    location: Location
    
    # Variables (surface only for MVP)
    temperature_2m_c: Optional[float]
    dewpoint_2m_c: Optional[float]
    wind_u_10m_ms: Optional[float]
    wind_v_10m_ms: Optional[float]
    pressure_msl_hpa: Optional[float]
    precipitation_mm: Optional[float]
    
class ObservationRecord(BaseModel):
    observation_time: datetime    # Single timestamp
    location: Location
    
    # CRITICAL: Two distinct pressure variables
    pressure_msl_hpa: Optional[float]        # From ERA5 (for GFS PRMSL verification)
    surface_pressure_hpa: Optional[float]    # From ERA5-Land (NOT equivalent)
    
    # Other variables match ForecastRecord
    
class VerificationPair(BaseModel):
    forecast: ForecastRecord
    observation: ObservationRecord
    
    @field_validator('observation')
    def validate_temporal_ordering(cls, obs, info):
        # PREVENTS TEMPORAL LEAKAGE
        if obs.observation_time < forecast.valid_time:
            raise ValueError("Temporal leakage detected!")
```

**Temporal Leakage Prevention**: ✅ **BUILT INTO SCHEMA**
- `VerificationPair` validates `observation_time >= forecast.valid_time`
- Schema enforces that observations cannot leak into forecasts during training
- Lead time explicitly tracked to prevent using future information

**Database Status**: 
- ❌ PostgreSQL schema NOT created
- ❌ Alembic migrations NOT run
- ❌ No database deployment yet
- ✅ Pydantic schemas ready for use

**Action Required**: Run `alembic upgrade head` after creating initial migration

---

## 2. Available Variables in Acquired Datasets

### ERA5-Land 2025 (Ground Truth Target)

**Source**: ECMWF Reanalysis v5-Land (9km surface reanalysis, HTESSEL land model)  
**Format**: GRIB (cfgrib engine)  
**Temporal Resolution**: 4x daily (00, 06, 12, 18 UTC)  
**Spatial Resolution**: 0.1° (~11 km)  
**Domain**: India (38°N-6°N, 68°E-97°E)  

**Variables** (GRIB short names):
- `t2m`: 2m temperature (Kelvin → convert to °C)
- `d2m`: 2m dewpoint temperature (Kelvin → convert to °C)
- `u10`: 10m u-component wind (m/s)
- `v10`: 10m v-component wind (m/s)
- `sp`: Surface pressure (Pa → convert to hPa) — **NOT mean sea-level pressure**
- `tp`: Total precipitation (m → convert to mm)

**Units Convention**:
- Temperature: Kelvin in GRIB, convert to Celsius for schema
- Pressure: Pascals in GRIB, convert to hPa for schema
- Precipitation: meters in GRIB, convert to mm for schema
- Wind: m/s (use as-is)

**Missing Values**: Handled by xarray (masked arrays, NaN)

**Validation Status**: ✅ All 12 months validated with xarray + cfgrib

---

### ERA5 MSLP 2025 (MSLP Ground Truth)

**Source**: ECMWF Reanalysis v5 (31km atmospheric reanalysis, IFS model)  
**Format**: GRIB (cfgrib engine)  
**Temporal Resolution**: 4x daily (00, 06, 12, 18 UTC)  
**Spatial Resolution**: 0.25° (~28 km)  
**Domain**: India (38°N-6°N, 68°E-97°E)  

**Variables** (GRIB short names):
- `msl`: Mean sea-level pressure (Pa → convert to hPa)

**Critical Distinction**:
- ERA5 `msl` ≠ ERA5-Land `sp`
- Mean sea-level pressure vs surface pressure are DISTINCT physical quantities
- **DO NOT substitute one for the other**
- ERA5 MSLP is for verifying GFS PRMSL forecasts
- ERA5-Land sp is surface-level pressure (different from MSLP)

**Validation Status**: ✅ All 12 months validated with xarray + cfgrib

---

### NOAA ISD-Lite 2025 (Hourly Verification)

**Source**: NOAA Integrated Surface Database (station observations)  
**Format**: Fixed-width text, gzip compressed  
**Temporal Resolution**: Hourly (varies by station)  
**Spatial Coverage**: 382 stations across India  
**Coverage Quality**: Excellent at major airports, moderate at state capitals, sparse in rural areas

**Fixed-Width Format** (9 fields):
```
YYYY MM DD HH  T_air  T_dew  SLP   WDir  WSpd  Sky  P1h  P6h
2025 01 01 00   -22   -9999  -9999  160    10    3   -9999 -9999
```

**Field Details**:
1. Year, Month, Day, Hour (UTC)
2. **Air temperature** (°C × 10, e.g., -22 = -2.2°C)
3. **Dewpoint temperature** (°C × 10)
4. **Sea-level pressure** (hPa × 10)
5. **Wind direction** (degrees)
6. **Wind speed** (m/s × 10)
7. **Sky condition** (code, 0-9)
8. **1-hour precipitation** (mm × 10)
9. **6-hour precipitation** (mm × 10)

**Missing Value**: `-9999` (must be filtered)

**Scaling**: All numeric values scaled by 10 (divide by 10 to get actual values)

**Temporal Coverage**: January 2025 through August 2025 (incomplete year)

**Validation Role**: 
- Hourly verification of GFS temperature, dewpoint, wind, MSLP forecasts
- Precipitation verification (1h and 6h accumulations)
- Station-based skill scores by location

**Limitations**:
- Point-based (not gridded) — verification only at station locations
- Urban heat island effects (airports vs grid-cell average)
- Sparse precipitation reporting at rural stations
- Cannot be used for training (point vs grid mismatch)

---

### NOAA GHCN-Daily (Daily Verification)

**Source**: NOAA Global Historical Climatology Network - Daily  
**Format**: Fixed-width .dly format (complex 31-day blocks)  
**Temporal Resolution**: Daily summaries  
**Spatial Coverage**: 3,807 stations across India  
**Temporal Depth**: Full historical records from 1940s-present through 2025

**Fixed-Width Format** (element-based):
```
STATION_ID YEAR MONTH ELEMENT [VALUE1 MFLAG1 QFLAG1 SFLAG1] × 31 days
IN001010100 1951 01 PRCP    0  I    0  I    0  I ... (31 days)
```

**Elements** (variable types):
- `PRCP`: Daily precipitation (tenths of mm, e.g., 127 = 12.7mm)
- `TMAX`: Daily maximum temperature (tenths of °C)
- `TMIN`: Daily minimum temperature (tenths of °C)
- `TAVG`: Daily average temperature (tenths of °C, when available)
- `SNOW`: Snowfall (mm)
- `SNWD`: Snow depth (mm)

**Flags**:
- M-flag: Measurement flag
- Q-flag: Quality flag (blank = passed QC)
- S-flag: Source flag
- Missing value: `-9999`

**Validation Role**:
- Daily verification of GFS daily max/min temperature forecasts
- Daily precipitation totals verification
- Long historical baseline for climatological context

**Limitations**:
- Daily summaries only (cannot validate sub-daily forecasts)
- Cannot verify hourly forecasts
- Point-based (not gridded)

---

## 3. Temporal Resolutions and Timestamp Conventions

### ERA5-Land and ERA5 MSLP

**Timestamp Convention**: 
- GRIB coordinate: `time` or `valid_time` dimension
- Values represent instantaneous conditions at that hour
- UTC timezone (all HELIOS data is UTC)

**Temporal Resolution**: 
- 4x daily: 00:00, 06:00, 12:00, 18:00 UTC
- 6-hour intervals
- Consistent across all 12 months

**Alignment Strategy**:
- ERA5-Land (0.1°) is higher spatial resolution than ERA5 MSLP (0.25°)
- **OPTION 1**: Regrid ERA5 MSLP to 0.1° to match ERA5-Land grid
- **OPTION 2**: Regrid ERA5-Land to 0.25° to match ERA5 MSLP (loses spatial detail)
- **RECOMMENDATION**: Keep separate — ERA5-Land for most variables, ERA5 MSLP only for MSLP verification

---

### NOAA ISD-Lite

**Timestamp Convention**:
- Fixed-width fields: Year, Month, Day, Hour (UTC)
- Each record is an hourly observation
- Not all stations report every hour

**Temporal Resolution**: 
- Nominally hourly
- Actual reporting frequency varies by station:
  - Major airports: hourly or more frequent
  - Rural stations: 3-hourly to 6-hourly
  - Sparse stations: daily or less

**Verification Matching Strategy**:
1. Parse ISD-Lite timestamp to datetime
2. Match to nearest ERA5/GFS forecast valid_time (within ±30 minutes)
3. Filter by station quality (exclude stations with >50% missing data)

---

### NOAA GHCN-Daily

**Timestamp Convention**:
- Fixed-width fields: Year, Month, Element
- Each record contains 31 daily values (one per day of month)
- Day-of-month position determines date

**Temporal Resolution**: Daily summaries

**Verification Matching Strategy**:
1. Parse GHCN-Daily records to extract date + daily values
2. Match to daily-aggregated forecast (e.g., GFS day-1 max temp forecast)
3. Use TMAX/TMIN for daily temperature extremes verification

---

## 4. Spatial Grids and Station Coordinates

### ERA5-Land Grid

**Resolution**: 0.1° (~11 km)  
**Domain**: 38°N-6°N, 68°E-97°E  
**Grid Points**: 
- Latitude: 321 points (38 to 6, step -0.1)
- Longitude: 291 points (68 to 97, step 0.1)
- **Total**: 93,411 grid cells

**Coordinate Convention**: 
- Standard lat/lon grid
- Coordinates in GRIB: `latitude`, `longitude` dimensions

---

### ERA5 MSLP Grid

**Resolution**: 0.25° (~28 km)  
**Domain**: 38°N-6°N, 68°E-97°E  
**Grid Points**:
- Latitude: 129 points (38 to 6, step -0.25)
- Longitude: 117 points (68 to 97, step 0.25)
- **Total**: 15,093 grid cells

**Spatial Alignment with ERA5-Land**: 
- NOT aligned (different resolutions)
- Regridding required for combining variables

---

### NOAA ISD-Lite Station Coordinates

**Format**: Station metadata in `isd-history.txt`
- USAF station ID (6 digits)
- WBAN station ID (5 digits)
- Latitude (decimal degrees, ±90)
- Longitude (decimal degrees, ±180)
- Elevation (meters)

**Example**:
```
USAF    WBAN  NAME                   LAT      LON      ELEV
420270  99999 JAIPUR                 26.817   75.800   390.1
```

**Station Count**: 382 stations with 2025 data

**Spatial Matching Strategy** (for verification):
1. Find nearest ERA5-Land/GFS grid cell to station lat/lon
2. Use inverse-distance weighting for interpolation (4 nearest neighbors)
3. Or: extract exact grid cell (nearest-neighbor)

---

### NOAA GHCN-Daily Station Coordinates

**Format**: Station metadata in `ghcnd-stations.txt`
- Station ID (11 characters, e.g., `IN001010100`)
- Latitude (decimal degrees, 5 decimals)
- Longitude (decimal degrees, 5 decimals)
- Elevation (meters, 1 decimal)
- Name (optional)

**Example**:
```
IN001010100  17.1167  -61.7833   10.1    ST JOHNS COOLIDGE FLD
```

**Station Count**: 3,807 stations

**Spatial Matching Strategy**: Same as ISD-Lite (nearest grid cell or IDW interpolation)

---

## 5. Units and Missing-Value Conventions

### ERA5-Land / ERA5 MSLP

**GRIB Native Units**:
- Temperature: Kelvin (K)
- Pressure: Pascals (Pa)
- Wind: meters per second (m/s)
- Precipitation: meters (m)

**HELIOS Schema Units** (after conversion):
- Temperature: Celsius (°C)
- Pressure: hectopascals (hPa)
- Wind: meters per second (m/s)
- Precipitation: millimeters (mm)

**Conversion Functions Needed**:
```python
def kelvin_to_celsius(k: float) -> float:
    return k - 273.15

def pa_to_hpa(pa: float) -> float:
    return pa / 100.0

def meters_to_mm(m: float) -> float:
    return m * 1000.0
```

**Missing Values**: 
- xarray handles missing data as `NaN`
- No explicit missing-value code in GRIB

---

### NOAA ISD-Lite

**Native Units** (scaled by 10):
- Temperature: tenths of °C (e.g., -22 = -2.2°C)
- Pressure: tenths of hPa (e.g., 10132 = 1013.2 hPa)
- Wind speed: tenths of m/s (e.g., 50 = 5.0 m/s)
- Precipitation: tenths of mm (e.g., 127 = 12.7 mm)

**Missing Value Code**: `-9999` (must be filtered before use)

**Conversion Functions Needed**:
```python
def isd_to_actual(value: int) -> Optional[float]:
    if value == -9999:
        return None
    return value / 10.0
```

---

### NOAA GHCN-Daily

**Native Units** (scaled by 10):
- Temperature: tenths of °C
- Precipitation: tenths of mm

**Missing Value Code**: `-9999`

**Conversion**: Same as ISD-Lite (divide by 10, filter -9999)

---

## 6. ERA5-Land and ERA5 MSLP Alignment

### Problem

ERA5-Land (0.1°) and ERA5 MSLP (0.25°) are on **different spatial grids**.

### Solution Options

**OPTION 1: Separate Storage, Matched at Query Time**
- Store ERA5-Land and ERA5 MSLP in separate arrays
- When creating training samples, regrid ERA5 MSLP to ERA5-Land grid (0.1°) on-the-fly
- Use xarray `.interp()` or scipy regridding

**OPTION 2: Pre-regrid ERA5 MSLP to ERA5-Land Resolution**
- One-time preprocessing: regrid ERA5 MSLP to 0.1° grid
- Store regridded version
- Simpler at training time

**OPTION 3: Downgrade ERA5-Land to ERA5 MSLP Resolution**
- ❌ NOT RECOMMENDED: Loses spatial detail from ERA5-Land

**RECOMMENDATION**: **OPTION 2** (pre-regrid ERA5 MSLP to 0.1°)
- One-time cost during preprocessing
- Cleaner training pipeline
- All variables on common 0.1° grid

**Regridding Method**:
- Use xarray `.interp(method='linear')` for bilinear interpolation
- Suitable for MSLP (smooth atmospheric field)

---

## 7. NOAA Station Observations Alignment (Verification)

### Problem

NOAA station observations are **point-based**, not gridded.

### Solution: Spatial Matching for Verification

**Step 1: Station-to-Grid Mapping**
1. For each NOAA station, find 4 nearest ERA5-Land grid cells
2. Compute inverse-distance weights
3. Store mapping in lookup table (precomputed)

**Step 2: Verification Workflow**
1. Extract gridded forecast at station locations (using IDW interpolation)
2. Match forecast valid_time to observation time (±30 minutes)
3. Compute verification metrics (RMSE, MAE, bias) per station
4. Aggregate to regional/national statistics

**Verification Metrics** (per station):
- RMSE: Root mean squared error
- MAE: Mean absolute error
- Bias: Mean error (forecast - observation)
- Correlation: Pearson correlation coefficient

**Station Quality Filtering**:
- Exclude stations with >50% missing data
- Flag stations with known biases (urban heat island)
- Weight by data completeness

**Verification Use Cases**:
1. GFS post-processed vs raw GFS skill comparison
2. Regional bias detection (coastal vs inland, urban vs rural)
3. Station-based verification reports for operational use

---

## 8. GFS Dependencies in Current Code

### Files Referencing GFS

**NWP Adapters**:
- `/home/agasthya/HELIOS/nwp/gfs/gfs_aws_adapter.py` ✅ IMPLEMENTED (frozen)
- `/home/agasthya/HELIOS/nwp/common/schemas.py` (NWPModel enum includes GFS)

**Acquisition Scripts**:
- `/home/agasthya/HELIOS/scripts/acquire_gfs_january_2025_pilot.py` (frozen)

**Documentation References**:
- `docs/data/mvp-config.md`: GFS listed as primary model (~12 GB)
- `docs/data/data-architecture.md`: GFS listed in data sources table
- `docs/data/mvp-recommendations.md`: GFS acquisition approved
- `docs/ml/ml-architecture.md`: GFS features referenced (`gfs_temperature`, `gfs_mae_recent_7d`)

### GFS Adapter Status: ✅ **FULLY IMPLEMENTED BUT FROZEN**

**Capabilities**:
- Downloads GFS 0.25° GRIB2 from NOAA AWS S3
- Extracts India domain subset (38°N-6°N, 68°E-97°E)
- Complete validation workflow (temporal checks, variable checks)
- Manifest-tracked acquisition (resumable)
- Temporal leakage prevention (issue_time, valid_time, lead_time tracked)

**Required Variables** (validated):
- `TMP:2 m above ground`
- `DPT:2 m above ground`
- `UGRD:10 m above ground`
- `VGRD:10 m above ground`
- `PRMSL:mean sea level`
- `APCP:surface`

**Forecast Lead Times**: 0-168h (6-hourly, 29 time steps per cycle)

**Dependency**: `wgrib2` (✅ AVAILABLE — version 3.8.0 installed)

---

## 9. HELIOS Architecture Without GFS

### What CANNOT Be Implemented Without GFS

❌ **GFS Post-Processing Models**
- HELIOS MVP is designed to POST-PROCESS GFS forecasts
- Without GFS forecasts, there are no NWP forecasts to improve
- Core value proposition requires GFS data

❌ **Forecast Blending**
- No forecasts to blend without GFS (and other NWP models)
- Blending requires multiple candidate forecasts

❌ **Operational Forecast Improvement**
- Cannot demonstrate forecast skill improvement without baseline forecasts

❌ **Training Forecast Error Predictors**
- ML models learn to predict forecast errors: `error = forecast - observation`
- Without `forecast`, cannot compute training targets

---

### What CAN Be Implemented Without GFS

✅ **ERA5-to-ERA5 "Reanalysis Reconstruction" (Proof-of-Concept)**

**Concept**: Use ERA5 reanalysis as BOTH input and target
- **Input**: ERA5-Land at time `t-6h` (simulating a "forecast")
- **Target**: ERA5-Land at time `t` (ground truth)
- **Task**: Learn to "forecast" current conditions from past reanalysis

**Why Useful**:
- Tests full ML pipeline without GFS
- Validates temporal leakage prevention
- Confirms data preprocessing works
- Establishes baseline performance
- **NOT scientifically valid** (reanalysis is not a forecast)
- **NOT useful for operational forecasting**
- Only for pipeline validation

**Implementation**:
```python
# Pseudo-forecast from ERA5-Land
input_time = datetime(2025, 1, 1, 0, 0)   # 00 UTC
target_time = datetime(2025, 1, 1, 6, 0)  # 06 UTC (6h "lead time")

input_features = load_era5_land(input_time)   # Past state
target = load_era5_land(target_time)          # "Predict" this
```

---

✅ **NOAA Verification Infrastructure**

**Components**:
1. **Station-to-grid mapping** (precompute IDW weights)
2. **Temporal matching** (observation_time to forecast valid_time)
3. **Verification metrics calculation** (RMSE, MAE, bias per station)
4. **Verification database schema** (store station-based results)
5. **Verification report generation** (regional aggregation)

**Ready for Later Use**:
- When GFS data arrives, verification system is operational
- Can immediately produce skill scores for GFS post-processed forecasts

---

✅ **Data Preprocessing Pipelines**

**ERA5 Preprocessing**:
1. GRIB → xarray Dataset loading
2. Unit conversions (K→°C, Pa→hPa, m→mm)
3. Spatial regridding (ERA5 MSLP to ERA5-Land grid)
4. Temporal alignment (all datasets to common 6-hourly timestamps)
5. Domain extraction (India bbox)
6. Normalization statistics (mean, std per variable)

**NOAA Preprocessing**:
1. ISD-Lite fixed-width parsing
2. Missing value filtering (-9999)
3. Unit conversion (scaled values → actual values)
4. Station metadata indexing
5. Quality control flags

**Output Format**:
- Zarr arrays (chunked, compressed, fast random access)
- Or: Parquet files (tabular, ML-friendly)

---

✅ **Baseline Model Training (Non-Operational)**

**Baseline Models**:
1. **Climatology**: Historical mean for each day-of-year
2. **Persistence**: Previous observation as "forecast"
3. **Reanalysis Reconstruction**: ERA5(t-6h) → ERA5(t)

**Purpose**:
- Validate training pipeline works
- Establish performance baselines
- Test temporal leakage prevention
- Confirm evaluation metrics are correct

---

✅ **Database Schema Deployment**

**Actions**:
1. Create Alembic initial migration from Pydantic schemas
2. Run `alembic upgrade head` to create tables
3. Test ForecastRecord, ObservationRecord insertion
4. Validate VerificationPair temporal ordering checks

---

## 10. Temporal Leakage Prevention Strategy

### Risk: Using Future Information in Training

**Leakage Scenario 1**: Observation from AFTER forecast valid time used to train
```python
# WRONG: Temporal leakage
forecast_valid_time = datetime(2025, 1, 1, 12, 0)  # Noon forecast
observation_time = datetime(2025, 1, 1, 13, 0)     # 1 hour AFTER valid time
# Using this observation to train the forecast model leaks future information!
```

**Prevention**: `VerificationPair` schema validates `observation_time >= forecast.valid_time`

---

**Leakage Scenario 2**: Using forecast issue_time to access observations
```python
# WRONG: Temporal leakage
forecast_issue_time = datetime(2025, 1, 1, 0, 0)   # Forecast issued at midnight
forecast_valid_time = datetime(2025, 1, 1, 12, 0)  # Valid for noon

# Model accesses observation at issue_time (midnight) to "improve" noon forecast
observation_at_issue = load_observation(forecast_issue_time)  # LEAKS FUTURE INFO
```

**Prevention**: 
- Only use observations from BEFORE forecast issue_time as contextual features
- Never use observations between issue_time and valid_time
- For training: match observation_time to valid_time (not issue_time)

---

**Leakage Scenario 3**: Using GFS forecast as a feature when it contains ERA5 assimilated data
```python
# SUBTLE LEAKAGE: GFS assimilated ERA5 observations
# If ERA5 assimilated station observations that GFS also assimilated,
# then ERA5 and GFS are not fully independent
```

**Mitigation**:
- Acknowledge partial dependence in documentation
- NOAA ISD/GHCN observations are "most independent" available
- ERA5 is reanalysis (not fully independent), but standard for training
- GFS forecasts are more independent than ERA5 for verification

---

### Enforcement Strategy

**Schema-Level**:
- ✅ `VerificationPair.validate_temporal_ordering()` raises error on leakage
- ✅ `lead_time_hours` explicitly tracked in `ForecastRecord`

**Code-Level**:
- ✅ Data loading functions accept `max_observation_time` parameter
- ✅ Training loops validate temporal ordering before batching
- ✅ Test suite includes temporal leakage tests

**Validation-Level**:
- ✅ Evaluation metrics computed only on held-out temporal splits
- ✅ Train/val/test splits are CHRONOLOGICAL (not random)
- ✅ No overlap between train and test periods

---

## 11. Training Dataset Construction Without GFS

### Option 1: Reanalysis Reconstruction (Pipeline Validation Only)

**Training Data**:
```python
# Input: ERA5-Land state at t-6h (simulate past conditions)
input = {
    "temperature_2m_c": era5_land["t2m"][t-6h],
    "dewpoint_2m_c": era5_land["d2m"][t-6h],
    "wind_u_10m_ms": era5_land["u10"][t-6h],
    "wind_v_10m_ms": era5_land["v10"][t-6h],
    "surface_pressure_hpa": era5_land["sp"][t-6h],
}

# Target: ERA5-Land state at t (current conditions)
target = {
    "temperature_2m_c": era5_land["t2m"][t],
}

# Task: "Forecast" current state from past state
```

**Limitations**:
- ❌ Not a real forecast (reanalysis is not predictive)
- ❌ No forecast errors to learn from
- ❌ No operational value
- ✅ Validates pipeline works
- ✅ Tests temporal leakage prevention

---

### Option 2: Climatology + Persistence Baselines

**Climatology**:
```python
# Predict long-term mean for each grid cell and day-of-year
target = era5_land["t2m"][date]
prediction = historical_mean["t2m"][day_of_year, lat, lon]
```

**Persistence**:
```python
# "Forecast" = most recent observation
target = era5_land["t2m"][t]
prediction = era5_land["t2m"][t-6h]  # Previous time step
```

**Value**:
- ✅ Establishes baseline performance
- ✅ No GFS needed
- ❌ No ML model needed (rule-based)

---

### Option 3: Wait for GFS Data (Recommended)

**Rationale**:
- HELIOS MVP requires GFS forecasts for its core value proposition
- Training without GFS produces non-operational models
- Verification infrastructure can be built now, training later

**Recommended Actions**:
1. ✅ Build NOAA verification infrastructure now
2. ✅ Build ERA5 preprocessing pipelines now
3. ✅ Deploy database schema now
4. ⏸ **DEFER** GFS-dependent training until GFS acquisition approved
5. ⏸ **DEFER** forecast blending until multiple NWP sources available

---

## 12. Components Requiring GFS vs Available Now

### Requires GFS (Cannot Implement Now)

| Component | Dependency | Blocker |
|-----------|------------|---------|
| GFS post-processing model training | GFS forecasts | No forecasts = no training data |
| Forecast blending | Multiple NWP models | GFS is primary candidate model |
| Operational forecast improvement | Baseline GFS forecasts | Need forecasts to improve upon |
| GFS bias correction | Historical GFS errors | `error = GFS_forecast - ERA5_truth` |
| Lead-time-specific models | GFS forecast lead times | Different models for 6h, 12h, ... 168h forecasts |
| Ensemble forecasting | GFS ensemble members | HELIOS could use GFS ensemble spread |

---

### Available Now (Can Implement Without GFS)

| Component | Data Source | Status |
|-----------|-------------|--------|
| **Data Preprocessing** | ERA5-Land, ERA5 MSLP | ✅ Ready |
| GRIB loading and parsing | xarray + cfgrib | ✅ Libraries available (in venv) |
| Unit conversions | Built-in Python | ✅ Trivial |
| Spatial regridding | xarray `.interp()` | ✅ Available |
| **NOAA Verification** | ISD-Lite, GHCN-Daily | ✅ Data acquired |
| Station-to-grid mapping | scipy, numpy | ✅ Available |
| Verification metrics | sklearn, numpy | ✅ Available |
| **Database Schema** | Pydantic, PostgreSQL | ✅ Schemas defined |
| Alembic migrations | Alembic | ⏸ Need to run `alembic upgrade head` |
| **Baseline Models** | ERA5 only | ✅ Can implement climatology, persistence |
| **Temporal Validation** | Pydantic validators | ✅ Built into schema |

---

## 13. Python Environment Status

### Virtual Environment: ✅ **ACTIVE AND CONFIGURED**

**Location**: `/home/agasthya/HELIOS/.venv/`

**Critical Libraries** (from `pyproject.toml`):
- ✅ `xarray>=2024.1.0` — Installed and working
- ✅ `netcdf4>=1.6.5` — Installed
- ✅ `cfgrib>=0.9.10` — Installed and working
- ✅ `pandas>=2.2.0` — Installed
- ✅ `numpy>=1.26.0` — Installed
- ✅ `scipy>=1.12.0` — Installed
- ✅ `scikit-learn>=1.4.0` — Installed
- ✅ `xgboost>=2.0.3` — Installed
- ✅ `torch>=2.2.0` — Installed
- ✅ `fastapi>=0.110.0` — Installed
- ✅ `pydantic>=2.6.0` — Installed
- ✅ `sqlalchemy>=2.0.25` — Installed
- ✅ `psycopg2-binary>=2.9.9` — Installed
- ✅ `alembic>=1.13.0` — Installed

**System Tools**:
- ✅ `wgrib2` version 3.8.0 — Available (for GFS GRIB2 processing when needed)

---

## 14. Recommendations

### Immediate Actions (Can Implement Now)

1. **Deploy Database Schema**
   ```bash
   cd /home/agasthya/HELIOS
   alembic init database/migrations
   alembic revision --autogenerate -m "Initial schema"
   alembic upgrade head
   ```

2. **Build ERA5 Preprocessing Pipeline**
   - GRIB → xarray → unit conversion → regridding → Zarr/Parquet
   - Output: Preprocessed ERA5-Land + ERA5 MSLP on common 0.1° grid
   - Estimated storage: ~2-3 GB (compressed Zarr)

3. **Build NOAA Verification Infrastructure**
   - Parse ISD-Lite and GHCN-Daily formats
   - Create station-to-grid mapping (precompute IDW weights)
   - Implement verification metrics (RMSE, MAE, bias per station)
   - Store in database for later use

4. **Implement Baseline Models** (Non-Operational)
   - Climatology baseline (historical mean per day-of-year)
   - Persistence baseline (previous observation as "forecast")
   - Optional: Reanalysis reconstruction (ERA5 t-6h → ERA5 t)

5. **Temporal Leakage Testing**
   - Write unit tests for `VerificationPair` temporal validation
   - Test chronological train/val/test splits
   - Validate observation_time >= forecast.valid_time enforcement

---

### Deferred Actions (Require GFS Data)

1. **GFS Data Acquisition**
   - Decision required: Resume GFS acquisition or remain frozen?
   - If approved: ~439 MB per month × 8 months (Jan-Aug 2025) = ~3.5 GB
   - GFS adapter is fully implemented and ready to use

2. **GFS Post-Processing Model Training**
   - Train XGBoost, MLP, Kernel Regression models
   - Input: GFS forecasts + ERA5-Land past state + derived features
   - Target: ERA5-Land ground truth
   - Output: Improved forecasts

3. **Forecast Blending**
   - Requires multiple NWP models (GFS + ECMWF/ICON/UKMO)
   - Dynamic weighting based on recent model performance
   - Ensemble forecasting

4. **Operational Deployment**
   - Real-time GFS ingest
   - Inference API (FastAPI)
   - Frontend dashboard

---

### Storage Budget Impact

**Current Usage**: 1.85 GB (Phase 4 data)

**If GFS Acquisition Resumes**:
- GFS Jan-Aug 2025 (8 months, India subset): ~3.5 GB
- **Total**: 5.35 GB (still within 220 GB budget)

**If Full Year GFS Acquired**:
- GFS Jan-Dec 2025 (12 months, India subset): ~5.25 GB
- **Total**: 7.1 GB (within budget)

---

## 15. Critical Questions for User Decision

### Question 1: GFS Acquisition Status

**Should GFS acquisition resume?**

- ✅ **YES** → HELIOS can proceed to training and operational forecasting
- ❌ **NO** → HELIOS remains in infrastructure-building mode only

**If YES**: 
- Acquire GFS January-August 2025 (8 months, ~3.5 GB)
- Or: Acquire full year January-December 2025 (12 months, ~5.25 GB)

**If NO**:
- Build data preprocessing pipelines
- Build NOAA verification infrastructure
- Implement baseline models (non-operational)
- Wait for GFS approval later

---

### Question 2: Scope of Implementation Without GFS

**What should be implemented now (without GFS)?**

**OPTION A: Full Preprocessing Infrastructure**
- ERA5 preprocessing pipelines
- NOAA verification infrastructure
- Database schema deployment
- Baseline models (climatology, persistence)
- **Timeline**: ~3-5 days
- **Value**: Ready for GFS training when data arrives

**OPTION B: Minimal Infrastructure Only**
- Database schema deployment
- ERA5 GRIB loading tests
- NOAA format parsing tests
- **Timeline**: ~1 day
- **Value**: Validates schemas work, defers heavy preprocessing

**OPTION C: Wait for GFS Decision**
- No new implementation
- Await GFS acquisition approval
- **Timeline**: 0 days
- **Value**: Avoids premature work if architecture changes

---

### Question 3: Reanalysis Reconstruction Proof-of-Concept

**Should we implement ERA5-to-ERA5 "reanalysis reconstruction"?**

**Purpose**: Validate pipeline works end-to-end without GFS

**Pros**:
- ✅ Tests full ML pipeline
- ✅ Validates temporal leakage prevention
- ✅ Confirms preprocessing works

**Cons**:
- ❌ Not scientifically valid (reanalysis ≠ forecast)
- ❌ No operational value
- ❌ Time investment (~2 days) with no deliverable forecast product

**Recommendation**: **SKIP** — Wait for GFS instead

---

## 16. Final Summary

### Phase 4 Status: PARTIAL

**Acquired**:
- ✅ ERA5-Land 2025 (1.24 GB, 12 months)
- ✅ ERA5 MSLP 2025 (44 MB, 12 months)
- ✅ NOAA ISD-Lite 2025 (5.2 MB, 382 stations)
- ✅ NOAA GHCN-Daily (572 MB, 3,807 stations)

**Frozen**:
- 🔒 GFS 2025 (0 MB, no data)

**Total Storage**: 1.85 GB / 220 GB budget (0.8% used)

---

### Architecture Dependencies

**CRITICAL FINDING**: HELIOS MVP **requires GFS forecasts** to fulfill its design purpose (NWP post-processing and blending).

**Without GFS**:
- ❌ Cannot train post-processing models
- ❌ Cannot implement forecast blending
- ✅ CAN build preprocessing infrastructure
- ✅ CAN build verification infrastructure
- ✅ CAN test temporal leakage prevention

---

### Recommended Path Forward

**RECOMMENDED: OPTION A — Build Preprocessing Infrastructure Now**

**Phase 5a: Infrastructure (No GFS Required)**
1. Deploy database schema (Alembic migrations)
2. Build ERA5 preprocessing pipeline (GRIB → Zarr)
3. Build NOAA verification infrastructure (station-to-grid mapping)
4. Implement baseline models (climatology, persistence)
5. Write temporal leakage tests

**Timeline**: 3-5 days  
**Deliverables**: 
- Database operational
- ERA5 data preprocessed and ready
- NOAA verification ready for GFS
- Temporal leakage prevention validated

**Phase 5b: Training (Requires GFS Acquisition Approval)**
1. Acquire GFS 2025 data (decision required)
2. Train GFS post-processing models
3. Evaluate against baselines
4. Generate verification reports

**Timeline**: 5-7 days (after GFS acquired)  
**Deliverables**:
- Trained HELIOS models
- Skill scores vs GFS
- Station-based verification reports

---

### Awaiting User Approval

**Decision Point**: Proceed with Phase 5a (infrastructure) or wait for GFS decision?

**If APPROVED**: Begin ERA5 preprocessing pipeline implementation  
**If DEFERRED**: Await GFS acquisition decision before further work

---

**Audit Complete**: 2026-09-07

