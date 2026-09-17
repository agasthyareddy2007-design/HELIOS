# NWP Source Access Summary

## Data Sources Verified

### Primary Training Sources (MVP Approved)

#### 1. NOAA GFS
- **Provider**: NOAA/NCEP
- **Historical Access**: Excellent (1979-present)
- **Access Method**: NOMADS OpenDAP (https://nomads.ncep.noaa.gov/)
- **Authentication**: None required (public domain)
- **Format**: GRIB2
- **Resolution**: 0.25° (~25 km)
- **Forecast Cycles**: 4/day (00Z, 06Z, 12Z, 18Z)
- **Maximum Lead Time**: 384 hours (16 days)
- **Variables Available**: All surface variables
- **MVP Estimated Size**: ~12 GB (2023, India domain, 6-hourly, surface only)
- **Automation**: Excellent (scriptable via OpenDAP)
- **Status**: ✅ READY FOR MVP

#### 2. ECMWF IFS
- **Provider**: ECMWF
- **Historical Access**: Good (2016-present via CDS)
- **Access Method**: Copernicus Climate Data Store (CDS) API
- **Authentication**: FREE CDS account required
- **Format**: GRIB
- **Resolution**: 9 km (HRES operational)
- **Forecast Cycles**: 2/day (00Z, 12Z operational)
- **Maximum Lead Time**: 240+ hours (10+ days)
- **Variables Available**: Comprehensive surface variables
- **MVP Estimated Size**: ~18 GB (2023, India domain, 6-hourly, surface only)
- **Automation**: Good (Python cdsapi library)
- **Status**: ⚠️ BLOCKED - User must register for CDS account
- **Action Required**: 
  1. Register at https://cds.climate.copernicus.eu/user/register
  2. Obtain API key from https://cds.climate.copernicus.eu/how-to-api
  3. Add to .env: `CDS_API_KEY=<uid>:<api-key>`

#### 3. ERA5-Land (Ground Truth)
- **Provider**: ECMWF via Copernicus
- **Historical Access**: Excellent (1950-present)
- **Access Method**: Same CDS API as ECMWF IFS
- **Authentication**: Same FREE CDS account
- **Format**: NetCDF
- **Resolution**: 0.1° (~9 km) - highest quality land reanalysis
- **Temporal Resolution**: Hourly
- **Purpose**: PRIMARY ground truth for forecast verification
- **Variables Available**: All surface variables
- **MVP Estimated Size**: ~8 GB (2023, India domain, hourly surface data)
- **Automation**: Good (same cdsapi library)
- **Status**: ⚠️ BLOCKED - Same CDS account requirement as ECMWF IFS

#### 4. NASA POWER
- **Provider**: NASA Langley Research Center
- **Historical Access**: Excellent (1981-present)
- **Access Method**: REST API (https://power.larc.nasa.gov/api/)
- **Authentication**: None required
- **Format**: JSON
- **Resolution**: 0.5° × 0.625° (~50 km)
- **Temporal Resolution**: Daily
- **Purpose**: Satellite-derived auxiliary features (especially solar radiation)
- **Variables**: Temperature, precipitation, solar radiation, humidity, wind
- **MVP Estimated Size**: ~50-200 MB (very lightweight)
- **Automation**: Excellent (simple REST API)
- **Status**: ✅ READY FOR MVP

### Secondary Sources (Live Inference Only - Not MVP Training)

#### 5. DWD ICON
- **Provider**: Deutscher Wetterdienst (DWD)
- **Live Access**: Excellent via DWD OpenData
- **Historical Access**: LIMITED (~2 months rolling archive only)
- **Recommendation**: Add for live inference AFTER MVP training
- **Reason**: Insufficient historical data for training
- **MVP Status**: ⏸️ DEFERRED to post-MVP

#### 6. CMC GEM
- **Provider**: Environment and Climate Change Canada
- **Live Access**: Good via MSC Datamart
- **Historical Access**: LIMITED (~2 weeks rolling archive only)
- **Recommendation**: Add for live inference AFTER MVP training
- **Reason**: Insufficient historical data for training
- **MVP Status**: ⏸️ DEFERRED to post-MVP

### Excluded Sources

#### 7. UK Met Office
- **Access**: Requires commercial license
- **Cost**: Not freely available
- **Recommendation**: EXCLUDE from MVP
- **MVP Status**: ❌ EXCLUDED

## MVP Configuration Summary

### Geographic Domain
- **Region**: India
- **Bounding Box**: 6°N to 38°N, 68°E to 97°E
- **Coverage**: ~3,000 km × ~3,600 km
- **Rationale**: Well-defined region, diverse climate, reduced storage

### Temporal Coverage
- **Period**: 2023 calendar year (January 1 - December 31, 2023)
- **Rationale**: Complete year, all seasons, recent, stable model versions

### Temporal Resolution
- **Forecast Cycles**: 00Z, 06Z, 12Z, 18Z (4 cycles/day)
- **Lead Times**: 0-168 hours (7 days) in 6-hour intervals
- **Rationale**: Balances resolution vs storage (4× reduction vs hourly)

### Variables (Surface Only)
1. 2m temperature (primary target)
2. 2m dewpoint / relative humidity
3. 10m u-wind component
4. 10m v-wind component
5. Mean sea level pressure
6. Total precipitation

### Storage Estimate
- **Raw Downloads**: ~38 GB
  - GFS: ~12 GB
  - ECMWF IFS: ~18 GB
  - ERA5-Land: ~8 GB
  - NASA POWER: ~0.1 GB
- **Processed Parquet**: ~18 GB
- **Peak Usage**: ~56 GB
- **Post-Training**: ~45 GB (after raw data cleanup)
- **Model Checkpoints**: ~3-5 GB (permanent)
- **Status**: ✅ Well within 180 GB data cycle budget

## Critical Blocker for Phase 4

**USER ACTION REQUIRED** before Phase 4 (Data Download) can begin:

1. Register for free Copernicus CDS account
2. Obtain CDS API key
3. Add credentials to HELIOS .env file

Without CDS access, HELIOS cannot download:
- ECMWF IFS forecasts (primary NWP model)
- ERA5-Land observations (ground truth)

This blocks 50% of the MVP training data.
