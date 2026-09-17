"""
HELIOS MVP Data Source Recommendations

Based on Phase 2 investigation, this document provides concrete recommendations
for the 1-year MVP implementation.

APPROVED SOURCES FOR MVP
========================

PRIMARY NWP MODELS (Training + Inference)
-----------------------------------------
1. ✓ NOAA GFS - APPROVED
   - Excellent historical archive availability
   - Public domain, no restrictions
   - OpenDAP enables efficient subsetting
   - Estimated size: 15-20 GB (1 year, surface variables, regional)
   
2. ✓ ECMWF IFS (via CDS) - APPROVED WITH SETUP
   - Gold standard NWP model
   - Requires free CDS account registration
   - Historical via Copernicus Climate Data Store
   - Estimated size: 20-30 GB (1 year, surface variables)
   - Action required: User must register for CDS API key

SECONDARY NWP MODELS (Inference only initially)
-----------------------------------------------
3. ⚠ DWD ICON - PARTIAL (Live forecasts only)
   - Excellent live forecast access
   - Very limited historical archive (~2 months)
   - Recommendation: Add for live inference after MVP training
   - Historical training: SKIP for initial MVP

4. ⚠ CMC GEM - PARTIAL (Live forecasts only)
   - Good real-time access via MSC Datamart
   - Limited historical archive
   - Recommendation: Add for live inference after MVP training
   - Historical training: SKIP for initial MVP

5. ✗ UK Met Office - SKIP FOR MVP
   - Requires commercial license
   - Not freely available
   - Recommendation: Do not include in MVP

GROUND TRUTH / VERIFICATION
---------------------------
6. ✓ ERA5-Land - APPROVED (PRIMARY VERIFICATION SOURCE)
   - Highest quality reanalysis dataset
   - 0.1° resolution (~9 km)
   - Hourly temporal resolution
   - Perfect for forecast verification
   - Requires free CDS account (same as ECMWF)
   - Estimated size: 8-12 GB (1 year, surface variables, regional)
   - This is the PRIMARY ground truth for HELIOS

AUXILIARY DATA
-------------
7. ✓ NASA POWER - APPROVED
   - Completely free, no authentication
   - Satellite-derived meteorological data
   - Excellent for auxiliary features
   - Very lightweight (~50-200 MB)

8. ✓ Open-Meteo - APPROVED (Current conditions API)
   - Free API for current weather
   - Easy integration
   - No authentication required
   - Use for live inference verification

MVP IMPLEMENTATION PLAN
=======================

PHASE 2A: Account Setup (User Action Required)
----------------------------------------------
[ ] User registers for free Copernicus CDS account:
    https://cds.climate.copernicus.eu/user/register
    
[ ] User obtains CDS API key:
    https://cds.climate.copernicus.eu/how-to-api
    
[ ] User adds API key to HELIOS .env file:
    CDS_API_KEY=your-key-here
    CDS_API_URL=https://cds.climate.copernicus.eu/api

PHASE 2B: Adapter Implementation
--------------------------------
Priority 1 (Training dataset):
[x] GFS adapter (NOMADS OpenDAP)
[x] ECMWF adapter (CDS API)
[x] ERA5-Land adapter (CDS API) - GROUND TRUTH
[x] NASA POWER adapter (REST API)

Priority 2 (Live inference):
[ ] ICON adapter (DWD OpenData) - implement later
[ ] GEM adapter (MSC Datamart) - implement later
[ ] Open-Meteo adapter (REST API) - implement later

PHASE 2C: Data Schema & Pipeline
--------------------------------
[x] Common data model (ForecastRecord, ObservationRecord)
[x] Temporal leakage prevention in schema
[x] Verification pair matching
[x] Storage budget tracking
[ ] Resumable download framework
[ ] Data manifest system
[ ] Checksum verification

MVP GEOGRAPHIC DOMAIN
====================

Recommendation: Start with India or another well-defined region

Option 1: India Focus
- Bounding box: 6°N to 38°N, 68°E to 97°E
- Rationale: Well-defined region, diverse climate zones, agricultural importance
- Spatial coverage: ~3000km × ~3600km
- Reduced data size vs global

Option 2: Global Grid Sample
- Sample every Nth grid point globally
- Enables worldwide testing
- More data but scientifically valid

RECOMMENDED: Option 1 (India focus) for MVP

MVP TEMPORAL COVERAGE
====================

Recommendation: 2023 calendar year (January 1 - December 31, 2023)

Rationale:
- Recent data (model versions stable)
- Complete year (all seasons)
- Far enough in past that all archives are complete
- Not too old (model configurations haven't changed significantly)

Alternative: 2024 if 2023 not fully archived yet

MVP VARIABLES
=============

Surface variables only (NO upper-air data for MVP):

Required:
- 2m temperature (primary target)
- 2m dewpoint / relative humidity
- 10m u-wind component
- 10m v-wind component
- Mean sea level pressure
- Total precipitation

These 6 variables provide comprehensive surface conditions while
minimizing storage requirements.

MVP TEMPORAL RESOLUTION
======================

Recommendation: 6-hourly outputs

Forecast cycles:
- GFS: 00Z, 06Z, 12Z, 18Z (all 4 cycles)
- ECMWF: 00Z, 12Z (both available cycles)
- ERA5-Land: Hourly available (aggregate to 6-hourly for matching)

Lead times:
- 0-168 hours (0-7 days)
- 6-hour intervals
- 29 time steps per forecast

Rationale:
- Balances temporal resolution vs data size
- Captures diurnal cycle
- Standard meteorological intervals
- Reduces storage by 4× vs hourly

MVP STORAGE ESTIMATE
===================

TRAINING DATASET (1 year, 2023, India domain, 6-hourly):

Raw Downloads:
- GFS (GRIB2): ~12 GB
- ECMWF (GRIB): ~18 GB  
- ERA5-Land (NetCDF): ~8 GB
- NASA POWER (JSON): ~0.1 GB
---------------------------------
Total Raw: ~38 GB

Processed Parquet:
- Feature dataset: ~15 GB
- Target dataset: ~3 GB
---------------------------------
Total Processed: ~18 GB

Peak Storage (Raw + Processed):
~56 GB

Post-Training (Checkpoints only):
~3-5 GB

SAFETY MARGIN: Well within 180 GB data cycle budget ✓

MVP DOWNLOAD TIMELINE ESTIMATE
==============================

Based on typical CDS/NOMADS performance:

GFS (OpenDAP): ~2-4 hours (parallelizable)
ECMWF (CDS queue): ~6-12 hours (queue dependent)
ERA5-Land (CDS): ~4-8 hours
NASA POWER (API): ~30 minutes

TOTAL: ~12-24 hours for complete download
(Assuming sequential, no rate limit issues)

Implementation note: Support resume for all downloads

API RATE LIMITS
===============

GFS/NOMADS: No strict limits, fair use
ECMWF/CDS: Request queue, ~20 concurrent requests
ERA5 CDS: Same as ECMWF
NASA POWER: No documented limits, ~10 req/sec reasonable
Open-Meteo: 10,000 calls/day free tier

MVP TRAINING LOCATIONS
=====================

Recommendation: 100-200 point locations across India

Approach 1: Regular grid
- Every 1° lat/lon (~100 km spacing)
- ~150 locations for India domain

Approach 2: Major cities + grid
- 50 major cities/airports
- 100 grid points for coverage
- Ensures important locations included

Approach 3: Station-based
- Match existing weather station locations
- Realistic verification points

RECOMMENDED: Approach 2 (cities + grid)

VERIFICATION STRATEGY
====================

Ground truth: ERA5-Land reanalysis

Matching approach:
1. Spatial: Nearest neighbor or bilinear interpolation
2. Temporal: 
   - Forecast valid_time must match observation time
   - ERA5-Land hourly → aggregate to 6-hourly
   - Allow ±3 hour matching window
3. Quality control:
   - Flag missing values
   - Flag outliers (>5 sigma)
   - Minimum data completeness threshold

Baseline comparisons:
- Individual models (GFS, ECMWF)
- Simple arithmetic mean
- Persistence (T+6h = T+0h)
- Climatology (historical average)

HELIOS must beat all baselines to be valid.

NEXT ACTIONS
============

FOR USER:
[ ] Register for Copernicus CDS account
[ ] Obtain CDS API key
[ ] Confirm geographic domain (India or alternative)
[ ] Confirm temporal period (2023 or 2024)
[ ] Review storage estimates
[ ] Approve MVP plan

FOR IMPLEMENTATION (PHASE 3):
[ ] Complete NWP adapter implementations
[ ] Implement resumable download system
[ ] Create data manifest tracking
[ ] Build preprocessing pipeline
[ ] Implement spatial interpolation
[ ] Implement temporal alignment
[ ] Create verification matching system
[ ] Build feature engineering pipeline
[ ] Implement storage monitoring
[ ] Create data quality checks

RISK MITIGATION
===============

Risk 1: CDS download queue delays
- Mitigation: Start downloads early, support resume

Risk 2: Storage overflow
- Mitigation: Pre-compute sizes, monitor continuously, fail-safe stops

Risk 3: Data quality issues
- Mitigation: Comprehensive QC checks, validation suite

Risk 4: API rate limits
- Mitigation: Exponential backoff, queue management, respect limits

Risk 5: Incomplete archives
- Mitigation: Check data availability before bulk download

SUCCESS CRITERIA FOR MVP
========================

Data acquisition:
✓ 1 year of GFS data downloaded and verified
✓ 1 year of ECMWF data downloaded and verified  
✓ 1 year of ERA5-Land data downloaded and verified
✓ All checksums verified
✓ <10% missing data

Processing:
✓ All sources normalized to common schema
✓ Spatial interpolation to common grid complete
✓ Temporal alignment verified
✓ Quality control flags applied
✓ Feature dataset generated

Storage:
✓ Peak usage < 180 GB
✓ Post-cleanup < 50 GB
✓ Checkpoint verified before data deletion

Training readiness:
✓ Train/val/test split created
✓ No temporal leakage verified
✓ Baseline metrics computed
✓ Ready for model training

TIMELINE ESTIMATE
================

Phase 2 (Research & Design): 2 days ← WE ARE HERE
Phase 3 (Implementation): 5-7 days
Phase 4 (Data Download): 1-2 days
Phase 5 (Preprocessing): 2-3 days
Phase 6 (Training MVP): 3-5 days
Phase 7 (Evaluation): 2-3 days

TOTAL MVP: ~15-20 days

Note: Assumes no major blockers, CDS API working normally

===============================================================
RECOMMENDATION: PROCEED WITH MVP IMPLEMENTATION
===============================================================

The MVP is feasible, well-scoped, and within storage constraints.

Primary models: GFS + ECMWF
Ground truth: ERA5-Land
Geographic: India domain
Temporal: 2023 calendar year
Resolution: 6-hourly
Storage: ~56 GB peak (well within 180 GB budget)

APPROVED FOR PHASE 3 IMPLEMENTATION
"""