# NASA POWER 2025 Pre-Acquisition Feasibility Audit
**HELIOS Phase 4 Data Acquisition**  
**Date**: 2026-09-07  
**Status**: ⚠️ AWAITING APPROVAL — DO NOT BEGIN DOWNLOAD

---

## Executive Summary

NASA POWER 2025 acquisition is **feasible** with a tiled API approach. The 10°×10° regional API constraint requires **12 tile requests per variable** to cover the India domain. Estimated total: **~930 MB download**, **72 API requests**, **~5 minutes acquisition time**.

**CRITICAL SCIENTIFIC ROLE**: NASA POWER must be tagged as **auxiliary/reference data** — NOT direct ground truth, NOT a replacement for NOAA observations, NOT a replacement for GFS NWP forecasts. Primary value: **solar radiation** (ALLSKY_SFC_SW_DWN), which ERA5-Land does not provide.

---

## 1. NASA POWER Product Specifications

### Product and Version
- **Product**: NASA POWER (Prediction Of Worldwide Energy Resources)
- **Data Source**: MERRA-2 (Modern-Era Retrospective analysis for Research and Applications, Version 2)
- **Temporal Coverage**: 1981/01/01 to Near Real-Time (2025 data available)
- **Community**: RE (Renewable Energy) — optimal for meteorological parameters
- **Temporal Resolution**: Daily averages, maxima, and/or minima
- **Time Standard**: Local Solar Time (LST) by default; UTC available via `time-standard=UTC`

### Spatial Resolution
- **Grid**: 0.5° × 0.5° (approximately 55 km at equator)
- **Comparison to HELIOS datasets**:
  - ERA5-Land: 0.1° (~9 km) — **higher resolution**
  - ERA5 MSLP: 0.25° (~28 km) — **higher resolution**
  - NASA POWER: 0.5° (~55 km) — **lowest resolution**

### India Domain Grid
- **HELIOS Domain**: 6°N–38°N, 68°E–97°E
- **Latitude points**: 65 (32° / 0.5° + 1)
- **Longitude points**: 59 (29° / 0.5° + 1)
- **Total grid points**: **3,835 points**

---

## 2. Selected Variables

### Priority Variables (6 total)

| Variable | Unit | Source | ERA5-Land Overlap | Scientific Value |
|----------|------|--------|-------------------|------------------|
| **ALLSKY_SFC_SW_DWN** | kW-hr/m²/day | SOURCE | ❌ **NOT in ERA5-Land** | ⭐ **HIGH** — Solar radiation (primary justification) |
| T2M | °C | SOURCE | ✅ Yes (2m_temperature) | LOW — Validation only |
| T2MDEW | °C | SOURCE | ✅ Yes (2m_dewpoint_temperature) | LOW — Validation only |
| PRECTOTCORR | mm/day | SOURCE | ✅ Yes (total_precipitation) | LOW — Validation only |
| WS10M | m/s | POWER (calculated) | ✅ Yes (u10, v10) | LOW — Derived from u/v |
| PS | kPa | SOURCE | ✅ Yes (surface_pressure) | LOW — Validation only |

### Variable Details

**ALLSKY_SFC_SW_DWN** — All Sky Insolation Incident on a Horizontal Surface
- **Type**: RADIATION
- **Source**: MERRA-2 SOURCE (not calculated)
- **Units**: kW-hr/m²/day
- **Definition**: Total solar radiation reaching Earth's surface under all sky conditions (clear + cloudy)
- **HELIOS Value**: ⭐ **CRITICAL** — ERA5-Land does not provide solar radiation variables. This is the **primary scientific justification** for adding NASA POWER.

**T2M, T2MDEW, PRECTOTCORR** — Overlaps ERA5-Land
- **HELIOS Value**: Validation only — cross-check ERA5-Land values, but adds no new information

**WS10M** — 10m Wind Speed
- **Type**: METEOROLOGY (calculated from u/v components)
- **Source**: POWER (not direct MERRA-2)
- **HELIOS Value**: Minimal — ERA5-Land provides u10/v10 directly

**PS** — Surface Pressure
- **HELIOS Value**: Validation only — ERA5-Land already provides surface_pressure

### Optional Variables NOT Selected
- RH2M (Relative Humidity) — POWER calculated, not SOURCE
- T2M_MAX, T2M_MIN — Useful for extremes, but increases download size
- ALLSKY_SFC_LW_DWN (longwave radiation) — Could be added if solar proves useful

---

## 3. API Specifications

### Endpoint
```
https://power.larc.nasa.gov/api/temporal/daily/regional
```

### Critical API Constraint
**Maximum bounding box**: 10° latitude × 10° longitude per request

**Impact**: India domain (32° lat × 29° lon) exceeds this limit and must be tiled.

### Tiling Strategy
- **Tiles required**: 12 (4 latitude strips × 3 longitude strips)
- **Tile grid**:
  - Latitude: 4 strips of 10° (last strip = 2°)
  - Longitude: 3 strips of 10° (last strip = 9°)

#### Tile Breakdown

| Tile | Latitude Range | Longitude Range | Size |
|------|----------------|-----------------|------|
| 1    | 6°N–16°N       | 68°E–78°E       | 10°×10° |
| 2    | 6°N–16°N       | 78°E–88°E       | 10°×10° |
| 3    | 6°N–16°N       | 88°E–97°E       | 10°×9° |
| 4    | 16°N–26°N      | 68°E–78°E       | 10°×10° |
| 5    | 16°N–26°N      | 78°E–88°E       | 10°×10° |
| 6    | 16°N–26°N      | 88°E–97°E       | 10°×9° |
| 7    | 26°N–36°N      | 68°E–78°E       | 10°×10° |
| 8    | 26°N–36°N      | 78°E–88°E       | 10°×10° |
| 9    | 26°N–36°N      | 88°E–97°E       | 10°×9° |
| 10   | 36°N–38°N      | 68°E–78°E       | 2°×10° |
| 11   | 36°N–38°N      | 78°E–88°E       | 2°×10° |
| 12   | 36°N–38°N      | 88°E–97°E       | 2°×9° |

### Example API Request (Tile 1, ALLSKY_SFC_SW_DWN, Jan 1-31, 2025)
```bash
curl "https://power.larc.nasa.gov/api/temporal/daily/regional?\
parameters=ALLSKY_SFC_SW_DWN&\
community=RE&\
longitude-min=68&longitude-max=78&\
latitude-min=6&latitude-max=16&\
start=20250101&end=20250131&\
format=JSON"
```

### Request Format
- **Parameters**: Comma-separated list (e.g., `parameters=T2M,PRECTOTCORR`)
- **Limitation**: Regional requests limited to **1 parameter per request** (NASA POWER API documentation)
- **Dates**: YYYYMMDD format (`start=20250101&end=20251231`)
- **Format**: JSON (preferred for programmatic processing)

---

## 4. Acquisition Estimates

### Total API Requests
- **Tiles**: 12
- **Variables**: 6
- **Total requests**: **72** (12 tiles × 6 variables)

**Optimization**: Submit full-year date range per request (start=20250101, end=20251231) rather than monthly batches.

### Download Size Estimation

**Basis**: Test request (10°×10° tile, 1 variable, 1 day) returned ~50 KB JSON
- Grid points per 10°×10° tile: 21×21 = 441 points
- Data density: ~0.113 KB per grid point per day per variable

**Calculation**:
- India domain: 3,835 grid points
- 2025 full year: 365 days
- 6 variables
- **Estimated total download**: **930 MB** (0.91 GB)
- **Per variable**: ~155 MB

### Expected Final Storage
- **Raw JSON**: ~930 MB (as downloaded)
- **Post-processing** (NetCDF/Parquet compression): ~400–600 MB estimated

### Estimated Acquisition Time
- **Per request**: ~3–5 seconds (conservative estimate: 4s)
- **Total sequential time**: 72 requests × 4s = **288 seconds (~5 minutes)**
- **Parallelization potential**: NASA POWER API has no documented rate limit (checked docs)
- **With 4-thread parallel**: ~75 seconds (~1.3 minutes)

### API Rate Limits and Considerations
- ✅ **No explicit rate limit documented** in NASA POWER API documentation
- ✅ **Publicly accessible** (no authentication required)
- ⚠️ **Best practice**: Implement exponential backoff for transient errors (429/503 responses)
- ⚠️ **Best practice**: Add 0.5–1 second delay between requests to be respectful

---

## 5. Data Quality and Scientific Context

### NASA POWER Data Source
NASA POWER is derived from **MERRA-2** (Modern-Era Retrospective analysis for Research and Applications, Version 2), a NASA atmospheric reanalysis product assimilating satellite and ground observations.

### Relationship to HELIOS Datasets

| Dataset | Type | Purpose | Resolution | Authority Level |
|---------|------|---------|------------|-----------------|
| **ERA5-Land** | ECMWF Reanalysis | Primary observations | 0.1° (~9 km) | ⭐⭐⭐ High |
| **ERA5 MSLP** | ECMWF Reanalysis | MSLP observations | 0.25° (~28 km) | ⭐⭐⭐ High |
| **NOAA ISD-Lite** | Station observations | Direct ground truth | Point-based | ⭐⭐⭐⭐ Highest |
| **NOAA GHCN-Daily** | Station observations | Direct ground truth | Point-based | ⭐⭐⭐⭐ Highest |
| **NASA POWER** | NASA MERRA-2 Reanalysis | Auxiliary/reference | 0.5° (~55 km) | ⭐⭐ Medium |
| **GFS** (FROZEN) | NOAA NWP Forecast | Training input | 0.25° (~28 km) | N/A (forecast) |

### NASA POWER Scientific Role in HELIOS

#### ✅ Appropriate Uses
1. **Solar radiation data** (ALLSKY_SFC_SW_DWN) — **PRIMARY JUSTIFICATION**
   - ERA5-Land does not provide solar/radiation variables
   - Critical for solar power applications, evapotranspiration models
   - Can be used as auxiliary feature in post-processing models

2. **Cross-validation of ERA5-Land**
   - Independent reanalysis product (NASA MERRA-2 vs ECMWF ERA5)
   - Useful for identifying ERA5-Land outliers or gaps

3. **Feature engineering**
   - Solar radiation as additional predictor variable
   - Ensemble diversity: combining ECMWF and NASA reanalyses

#### ❌ Inappropriate Uses
1. **NOT direct ground truth** — NASA POWER is a reanalysis product (model-based), not direct observations
2. **NOT a replacement for NOAA observations** — NOAA ISD/GHCN are direct measurements; NASA POWER is modeled
3. **NOT equivalent authority to ERA5-Land** — Lower spatial resolution (0.5° vs 0.1°)
4. **NOT a replacement for GFS** — NASA POWER is reanalysis (hindsight), not forecast (future prediction)

### Variable Overlap Analysis

**Complete overlap** (5 variables):
- T2M, T2MDEW, PRECTOTCORR, WS10M, PS — All available in ERA5-Land at higher resolution

**Unique to NASA POWER** (1 variable):
- ALLSKY_SFC_SW_DWN — **Solar radiation** (not in ERA5-Land)

**Conclusion**: The **sole scientific justification** for adding NASA POWER is **solar radiation data**. All other variables are validation/cross-checks only.

---

## 6. Implementation Plan

### Phase 1: Adapter Development
**File**: `/home/agasthya/HELIOS/nwp/power/power_adapter.py`

**Architecture**:
- Follow existing adapter pattern (ERA5LandAdapter, ERA5MSLPAdapter)
- Use AcquisitionManifest for resumable downloads
- Implement 12-tile regional tiling strategy
- One manifest record per variable (6 records total)
- Atomic validation: only mark successful after all 12 tiles validated

**Key Methods**:
```python
class POWERAdapter:
    def acquire_variable_2025(self, variable: str) -> ManifestRecord:
        """Acquire one variable for full 2025, all 12 tiles."""
        
    def _acquire_tile(self, variable: str, tile_config: dict) -> dict:
        """Download one tile (10°×10° region) for one variable."""
        
    def _validate_tile(self, tile_data: dict) -> bool:
        """Validate tile coverage and data quality."""
        
    def _merge_tiles(self, tiles: List[dict]) -> xr.Dataset:
        """Merge 12 tiles into single India domain dataset."""
```

### Phase 2: Post-Processing
**File**: `/home/agasthya/HELIOS/nwp/power/power_preprocessor.py`

**Tasks**:
1. Convert JSON to NetCDF (xarray)
2. Regrid from 0.5° to 0.1° (align with ERA5-Land) using bilinear interpolation
3. Validate spatial alignment with ERA5-Land grid
4. Tag all variables with `source="NASA_POWER_MERRA2"` and `resolution="0.5deg_regridded_to_0.1deg"`

### Phase 3: Database Integration
**File**: `/home/agasthya/HELIOS/nwp/common/schemas.py`

**Schema Updates**:
```python
class ObservationRecord(BaseModel):
    # ... existing fields ...
    
    # NASA POWER auxiliary fields
    solar_radiation_kwh_m2: Optional[float] = None  # ALLSKY_SFC_SW_DWN
    
    # Metadata
    source: ObservationSource  # Add: POWER_MERRA2
    source_resolution_deg: Optional[float] = None  # 0.5 (original)
    regridded_to_deg: Optional[float] = None  # 0.1 (aligned with ERA5-Land)
```

---

## 7. Manifest Structure

### Manifest Path
`/home/agasthya/HELIOS/data/manifests/power_acquisition.json`

### Record Structure
One record per variable (6 records total):

```json
{
  "power_2025_allsky_sfc_sw_dwn": {
    "record_id": "power_2025_allsky_sfc_sw_dwn",
    "source": "nasa_power",
    "dataset": "2025-allsky_sfc_sw_dwn",
    "file_path": "/home/agasthya/HELIOS/data/raw/power/power_2025_allsky_sfc_sw_dwn.nc",
    "file_size_bytes": 155000000,
    "checksum_sha256": "...",
    "status": "successful",
    "metadata": {
      "variable": "ALLSKY_SFC_SW_DWN",
      "year": 2025,
      "num_tiles": 12,
      "domain": "India (38N-6N, 68E-97E)",
      "spatial_resolution": "0.5°",
      "temporal_resolution": "daily",
      "time_standard": "LST",
      "tiles_acquired": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    }
  }
}
```

---

## 8. Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API downtime during acquisition | Low | Medium | Resumable manifest system |
| Tile boundary misalignment | Low | High | Validation checks on merge |
| 0.5° → 0.1° regridding artifacts | Medium | Medium | Validate against ERA5-Land overlap |
| JSON response size exceeds memory | Low | Medium | Stream-process large responses |

### Scientific Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Over-reliance on reanalysis vs observations | Medium | High | ⚠️ Tag as auxiliary, prioritize NOAA stations |
| Solar radiation accuracy for India domain | Medium | Medium | Cross-validate with station pyranometer data if available |
| Confusion between POWER and GFS forecasts | Low | High | Clear metadata: "POWER = reanalysis, GFS = forecast" |

---

## 9. Pre-Acquisition Checklist

### API Verification
- ✅ **Endpoint confirmed**: `https://power.larc.nasa.gov/api/temporal/daily/regional`
- ✅ **10°×10° constraint confirmed**: Test request validated
- ✅ **Parameters available**: All 6 variables confirmed in RE community
- ✅ **2025 data availability**: Test request returned 2025-01-01 data successfully
- ⚠️ **Rate limits**: No documented limit; will implement respectful delays

### Scientific Validation
- ✅ **Primary value identified**: ALLSKY_SFC_SW_DWN (solar radiation)
- ✅ **Overlap documented**: 5/6 variables redundant with ERA5-Land
- ✅ **Authority level defined**: Auxiliary/reference, NOT ground truth
- ✅ **Role clarified**: Solar radiation + validation only

### Implementation Readiness
- ✅ **Tiling strategy designed**: 12 tiles, validated boundaries
- ✅ **Manifest structure defined**: One record per variable
- ✅ **Adapter pattern confirmed**: Follows ERA5 adapter architecture
- ✅ **Storage estimate**: ~930 MB raw, ~400–600 MB post-processing

---

## 10. Approval Required

**Status**: ⚠️ **AWAITING EXPLICIT APPROVAL**

**DO NOT BEGIN DOWNLOAD** until user confirms:

1. ✅ Accept 930 MB download size?
2. ✅ Accept NASA POWER as **auxiliary/reference** data (NOT ground truth)?
3. ✅ Accept that 5/6 variables are redundant with ERA5-Land (validation only)?
4. ✅ Confirm solar radiation (ALLSKY_SFC_SW_DWN) justifies acquisition?
5. ✅ Approve tiled acquisition strategy (12 tiles × 6 variables = 72 requests)?

---

## Summary Table

| Specification | Value |
|---------------|-------|
| **Product** | NASA POWER (MERRA-2) |
| **Temporal Coverage** | 2025 full year (365 days) |
| **Spatial Resolution** | 0.5° × 0.5° (~55 km) |
| **Domain** | India (6°N–38°N, 68°E–97°E) |
| **Grid Points** | 3,835 |
| **Variables** | 6 (ALLSKY_SFC_SW_DWN + 5 validation) |
| **API Endpoint** | `https://power.larc.nasa.gov/api/temporal/daily/regional` |
| **API Requests** | 72 (12 tiles × 6 variables) |
| **Download Size** | ~930 MB |
| **Storage (processed)** | ~400–600 MB |
| **Acquisition Time** | ~5 minutes (sequential), ~1.3 minutes (4-thread parallel) |
| **Rate Limits** | None documented; implement respectful delays |
| **Primary Value** | ⭐ Solar radiation (ALLSKY_SFC_SW_DWN) |
| **Scientific Role** | Auxiliary/reference data, NOT ground truth |

---

**Next Step**: Await user approval to begin NASA POWER 2025 acquisition.
