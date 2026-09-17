# HELIOS MVP Configuration

## Approved NWP Sources for MVP Training

### Primary NWP Models
1. **GFS** (NOAA/NCEP)
   - Historical: 1979-present (excellent)
   - Access: NOMADS OpenDAP (public domain)
   - Resolution: 0.25° (~25 km)
   - Cycles: 4/day (00Z, 06Z, 12Z, 18Z)
   - Lead time: 0-384 hours
   - Estimated MVP size: ~12 GB

2. **ECMWF IFS** (via Copernicus CDS)
   - Historical: 2016-present (good via CDS)
   - Access: CDS API (requires free account)
   - Resolution: 9 km (HRES)
   - Cycles: 2/day (00Z, 12Z)
   - Lead time: 0-240+ hours
   - Estimated MVP size: ~18 GB
   - **USER ACTION REQUIRED**: Register for free CDS account

### Ground Truth / Verification
3. **ERA5-Land** (ECMWF/CDS)
   - Historical: 1950-present (excellent)
   - Access: CDS API (same account as ECMWF)
   - Resolution: 0.1° (~9 km)
   - Temporal: Hourly
   - Purpose: PRIMARY ground truth for forecast verification
   - Estimated MVP size: ~8 GB

### Auxiliary Data
4. **NASA POWER** (NASA LaRC)
   - Historical: 1981-present (excellent)
   - Access: REST API (no authentication)
   - Resolution: 0.5° × 0.625°
   - Purpose: Satellite-derived auxiliary features
   - Estimated MVP size: ~50-200 MB

## Secondary Models (Live Inference Only)
- **ICON** (DWD): ~2 months historical only → add for live inference after MVP training
- **GEM** (CMC): ~2 weeks historical only → add for live inference after MVP training

## Excluded from MVP
- **UK Met Office**: Commercial license required → skip for MVP

## MVP Geographic Domain
**Recommended**: India focus
- Bounding box: 6°N to 38°N, 68°E to 97°E
- Coverage: ~3,000 km × ~3,600 km
- Rationale: Well-defined region, diverse climate, reduced storage vs global

## MVP Temporal Coverage
**Recommended**: 2023 calendar year
- Period: January 1, 2023 - December 31, 2023
- Rationale: Complete year, all seasons, recent, stable model versions

## Temporal Resolution
**6-hourly outputs**
- Forecast cycles: 00Z, 06Z, 12Z, 18Z
- Lead times: 0-168 hours (7 days) in 6-hour intervals
- Rationale: Balances resolution vs storage (4× reduction vs hourly)

## Variables (Surface Only)
1. 2m temperature (primary target)
2. 2m dewpoint / relative humidity
3. 10m u-wind component
4. 10m v-wind component
5. Mean sea level pressure
6. Total precipitation

## Storage Estimate
- Raw downloads: ~38 GB
  - GFS: ~12 GB
  - ECMWF IFS: ~18 GB
  - ERA5-Land: ~8 GB
  - NASA POWER: ~0.1 GB
- Processed Parquet: ~18 GB
- **Peak usage: ~56 GB** (within 180 GB data cycle budget)
- Post-training cleanup: ~45 GB
- Model checkpoints: ~3-5 GB (permanent)

## Access Requirements
**BLOCKER**: User must complete before Phase 4:
1. Register for free Copernicus CDS account: https://cds.climate.copernicus.eu/user/register
2. Obtain CDS API key: https://cds.climate.copernicus.eu/how-to-api
3. Add credentials to `/home/agasthya/HELIOS/.env`:
   ```
   CDS_API_KEY=your-uid:your-api-key
   CDS_API_URL=https://cds.climate.copernicus.eu/api
   ```
