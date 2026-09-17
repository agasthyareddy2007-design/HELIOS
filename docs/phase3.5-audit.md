# HELIOS Phase 3.5 Scientific Validation Audit

**Date**: 2026-09-06 21:51 IST  
**Purpose**: Scientific and architectural validation gate before Phase 4 data acquisition  
**Status**: IN PROGRESS

---

## AUDIT 1: ERA5-Land vs Actual Observations

**Finding**: ⚠️ **TERMINOLOGY CHANGE REQUIRED**

**Current Phase 3 Description**: "ERA5-Land as PRIMARY ground truth"

**Scientific Issue**: ERA5-Land is a **reanalysis**, not direct observational ground truth. It combines NWP model output with observational data through data assimilation, but it remains a model-derived product.

**Correct Observation Hierarchy**:

1. **Primary Verification Reference** (where available):
   - Station observations (METAR, SYNOP, NOAA ISD)
   - High-quality, direct measurements
   - Sparse spatial coverage
   - Immediate availability for live verification

2. **Secondary Reference / Spatial Context**:
   - ERA5-Land reanalysis
   - Gridded, gap-filled reference
   - Consistent spatial coverage
   - Good for historical verification and spatial interpolation
   - NOT "ground truth" but best available gridded reference

3. **Auxiliary Features**:
   - NASA POWER (satellite-derived)
   - ERA5 (if ERA5-Land insufficient)

**Recommended Terminology**:
- Replace: "ERA5-Land as PRIMARY ground truth"
- With: "ERA5-Land as PRIMARY gridded verification reference"
- Add: "Station observations as PRIMARY direct verification where available"

**Architecture Implication**: 
- Schema already supports multiple observation sources ✓
- Should prioritize station obs over ERA5-Land when both available
- Use ERA5-Land for spatial gaps and historical consistency

**Decision**: **CHANGE REQUIRED** - Update terminology and verification hierarchy documentation

---

## AUDIT 2: Temporal Leakage Rules

**Finding**: ⚠️ **CRITICAL INSUFFICIENCY DETECTED**

**Current Schema Rule**: `observation_time >= forecast.valid_time`

**Test Results**:
```
Forecast: issue_time=2023-06-01 00Z, valid_time=2023-06-02 00Z

Observation Time          Features?  Verification?
2023-05-31 18Z (before)   ✓ YES      ✗ NO
2023-06-01 00Z (issue)    ✓ YES      ✗ NO
2023-06-01 06Z (between)  ✗ NO       ✗ NO  ← DEAD ZONE
2023-06-01 12Z (between)  ✗ NO       ✗ NO  ← DEAD ZONE
2023-06-01 18Z (between)  ✗ NO       ✗ NO  ← DEAD ZONE
2023-06-02 00Z (valid)    ✗ NO       ✓ YES
2023-06-02 06Z (after)    ✗ NO       ✗ NO
```

**Critical Finding**: Current rule prevents **verification leakage** but does NOT prevent **feature leakage**.

**Problem**: Observations between issue_time and valid_time:
- Should NOT be features (future relative to forecast generation)
- Should NOT be verification (past relative to forecast target)
- Current schema ONLY enforces the second constraint

**Required Changes**:

1. **Feature Cutoff Rule**:
   ```python
   feature_observation_time <= forecast.issue_time
   ```

2. **Verification Matching Rule**:
   ```python
   abs(observation_time - forecast.valid_time) <= tolerance  # e.g., ±3 hours
   ```

3. **Training Target Rule**:
   ```python
   target_observation_time >= forecast.valid_time
   AND target_observation_time <= forecast.valid_time + max_acceptable_lag
   ```

**Schema Changes Required**:
- Add separate validation for feature extraction vs verification pairing
- Create distinct classes or methods:
  - `FeatureContext` (obs_time <= issue_time)
  - `VerificationPair` (obs_time ~= valid_time)
  - `TrainingExample` (combines both with proper guards)

**Historical Performance Features**:
⚠️ **Additional Leakage Risk**: A model's recent MAE/bias statistics must use **only** forecasts issued **before** the current forecast's issue_time.

Example:
- Current forecast issue_time: 2023-06-15 00Z
- "GFS MAE last 7 days" feature must use:
  - Forecasts issued: 2023-06-08 00Z through 2023-06-14 18Z
  - Verified against observations available by those issue times
- Must NOT include any forecast issued on/after 2023-06-15 00Z

**Decision**: **CHANGE REQUIRED** - Implement separate feature and verification temporal rules

---

## AUDIT 3: Five NWP Models vs MVP Reality

**Finding**: ⚠️ **CONFIGURATION CHANGE RECOMMENDED**

**Original Concept**: GFS, ECMWF IFS, ICON, UKMO, GEM (5 models)

**Phase 3 Recommendation**: GFS + ECMWF IFS only (2 models)

**Detailed Model Assessment**:

| Model | Historical Archive | India Coverage | Access | Training Suitability | Recommendation |
|-------|-------------------|----------------|--------|---------------------|----------------|
| **GFS** | 1979-present (excellent) | ✓ Full | Public OpenDAP | ✓ Excellent | ✅ MVP Training |
| **ECMWF IFS** | 2016-present via CDS | ✓ Full | Free CDS account | ✓ Good | ✅ MVP Training |
| **ICON** | ~2 months rolling | ✓ Full | Public OpenData | ✗ Insufficient | ⏸️ Live only |
| **UK Met** | Requires license | ✓ Full | Commercial | ✗ Not accessible | ❌ Exclude |
| **GEM** | ~2 weeks rolling | ✓ Full | Public Datamart | ✗ Insufficient | ⏸️ Live only |

**Additional Model Candidates**:

**JMA GSM** (Japan Meteorological Agency Global Spectral Model):
- Historical: Limited public access
- Would add Asian regional center perspective
- Assessment: **Deferred** (access complexity)

**NCMRWF** (India's National Centre for Medium Range Weather Forecasting):
- Historical: Unknown public availability
- Advantage: India-focused, local expertise
- Assessment: **Investigate for post-MVP** (could be valuable for India domain)

**CMA GFS** (China Meteorological Administration):
- Historical: Limited public access
- Spatial coverage: Good for Asia
- Assessment: **Deferred** (access complexity)

**Recommended MVP Configuration**:

**Option C (RECOMMENDED)**: Staged architecture
- **MVP Training (historical)**: GFS + ECMWF IFS (2 models)
- **Live Inference (post-MVP)**: Add ICON + GEM (4 models total)
- **Future expansion**: Investigate NCMRWF, JMA, CMA

**Rationale**:
- 2 models is scientifically valid for initial MVP
- Both have excellent historical archives
- Both provide good spatial coverage of India
- Different model families (NOAA vs ECMWF) provide diversity
- ICON/GEM addition post-MVP adds ensemble diversity without training burden
- System architecture already supports 5+ models

**Alternative Consideration**:
If user strongly prefers ≥3 models for MVP training, only realistic option is to:
- Reduce temporal coverage (e.g., 2023 Q3-Q4 only) to capture ICON's ~2-month archive
- This trades temporal completeness for model diversity
- **NOT RECOMMENDED**: seasonal incompleteness worse than model count

**Decision**: **PASS WITH CLARIFICATION** - Two-model MVP is scientifically valid; staged architecture recommended

---

## AUDIT 4: 2023 One-Year Dataset

**Finding**: ✓ **PASS - Appropriate with documented limitations**

**Selected Period**: January 1, 2023 - December 31, 2023

**Assessment**:

**Strengths**:
- ✓ Complete calendar year (all 12 months)
- ✓ Full seasonal cycle for India:
  - Winter (Jan-Feb): Cool, dry
  - Pre-monsoon (Mar-May): Hot, dry
  - Southwest Monsoon (Jun-Sep): Wet season, critical for agriculture
  - Post-monsoon (Oct-Dec): Transition, northeast monsoon
- ✓ Recent data (model versions stable)
- ✓ All archives likely complete for 2023
- ✓ ~8760 hours of verification data per location
- ✓ Sufficient sample size for ML training

**Limitations** (documented, acceptable):
- One year may not capture all extreme events
- Inter-annual variability not represented
- Model regime changes across years not learned
- Long-term climate trends not captured

**Extreme Weather Coverage** (2023 India):
- Monsoon active/break cycles: Present
- Heat waves: Present (March-May typical)
- Cyclones: Variable (need to verify 2023 had representative events)
- Cold waves: Present (January-February)

**Storage vs Benefit Trade-off**:
- One year: ~92 GB raw (revised estimate)
- Two years: ~184 GB raw (exceeds 180 GB data cycle budget with processed)
- One year is maximum feasible within budget constraints

**Generalization Strategy**:
- Train on 2023 Jan-Oct (10 months)
- Validate on 2023 Nov-Dec (2 months)
- If budget allows future expansion: test on 2024 data
- Rolling annual updates to capture regime changes

**Decision**: **PASS** - 2023 calendar year is appropriate for MVP

---

## AUDIT 5: Temporal Sampling

**Finding**: ⚠️ **REFINEMENT RECOMMENDED**

**Phase 3 Proposal**:
- Forecast cycles: 00Z, 06Z, 12Z, 18Z (4/day)
- Valid times: 6-hourly
- Lead times: 0-168 hours in 6-hour increments

**Critical Distinction** (often confused):

1. **Forecast Initialization Frequency**: How often forecasts are issued
   - GFS: 00Z, 06Z, 12Z, 18Z (4/day)
   - ECMWF: 00Z, 12Z (2/day)

2. **Forecast Output Frequency**: Time resolution of each forecast run
   - GFS: Hourly 0-120h, 3-hourly 120-384h
   - ECMWF: Hourly 0-90h, 3-hourly 90-144h, 6-hourly 144-240h

3. **What We Sample**: Combination of above

**Current Proposal Analysis**:

**Initialization Sampling**: All 4 GFS cycles (00Z, 06Z, 12Z, 18Z) + 2 ECMWF cycles (00Z, 12Z)
- ✓ Captures all major forecast cycles
- ✓ Provides forecast updates every 6 hours
- ✓ Enables comparing same valid_time from multiple issue_times

**Valid Time Sampling**: 6-hourly increments
- ⚠️ **ISSUE**: Discards hourly forecast information available 0-120h from GFS
- ⚠️ **ISSUE**: Discards 3-hourly information available in various ranges
- Storage trade-off: Hourly would be 4× larger

**Recommended Refinement**:

**Option A (Storage-Conscious)**:
- Keep 6-hourly sampling as proposed
- Accept loss of sub-6h resolution
- Justification: 6-hourly captures diurnal cycle, storage savings substantial

**Option B (Stratified Resolution)**:
- 0-72h lead time: 3-hourly (short-range, more critical)
- 72-168h lead time: 6-hourly (medium-range)
- Compromise: +50% storage vs all 6-hourly, better short-range resolution

**Option C (Hourly Short-Range)**:
- 0-48h: hourly
- 48-168h: 6-hourly
- Best resolution where it matters most
- Storage: +100% short-range portion

**Storage Impact**:

Current (all 6-hourly):
- 29 lead times per forecast × 1460 GFS cycles × 730 ECMWF cycles
- Estimated: ~15 GB GFS + ~69 GB ECMWF = ~84 GB for forecasts

Option B (stratified):
- 0-72h: 25 time steps (3-hourly)
- 72-168h: 17 time steps (6-hourly)
- Total: 42 lead times (vs 29)
- Estimated: +45% → ~122 GB for forecasts
- **EXCEEDS revised storage estimate significantly**

Option C (hourly short):
- 0-48h: 49 time steps (hourly)
- 48-168h: 21 time steps (6-hourly)
- Total: 70 lead times (vs 29)
- Estimated: +140% → ~200 GB for forecasts alone
- **EXCEEDS budget**

**Decision**: **PASS - Keep 6-hourly as proposed** (Option A)
- Rationale: Storage constraints are binding
- 6-hourly preserves diurnal information
- Future: If budget expands, implement Option B

---

## AUDIT 6: Variables

**Finding**: ✓ **PASS - Well-chosen for MVP**

**Proposed Variables**:
1. 2m temperature (°C)
2. 2m dewpoint (°C) / relative humidity (%)
3. 10m u-wind component (m/s)
4. 10m v-wind component (m/s)
5. Mean sea-level pressure (hPa)
6. Total precipitation (mm)

**Assessment by End-User Domain**:

**Agriculture** (stated target):
- ✓ Temperature: Critical for crop development
- ✓ Dewpoint/humidity: Evapotranspiration, disease risk
- ✓ Wind: Pollination, spray applications
- ✓ Precipitation: Irrigation decisions
- ✓ Pressure: Storm/weather regime indicator
- **All 6 variables highly relevant**

**Aviation/Aerial Applications** (stated target):
- ✓ Temperature: Density altitude
- ✓ Dewpoint: Fog/icing risk
- ✓ Wind: Critical for operations
- ✓ Pressure: Altimetry
- ⚠️ Missing: Visibility, ceiling, cloud base
- ⚠️ Missing: Wind shear indicators
- **Core 6 are necessary but not sufficient**

**Additional Variables to Consider**:

**Phase 4+ Candidates** (NOT MVP):
1. **Cloud ceiling/base height**: Critical for aviation, moderate storage cost
2. **Visibility**: Critical for aviation, small storage cost
3. **10m wind gusts**: Aviation, agriculture (wind damage), moderate cost
4. **Soil moisture** (0-10cm): Agriculture, ERA5-Land provides this, small cost
5. **Solar radiation**: Agriculture (evapotranspiration), NASA POWER provides, negligible cost

**MVP Decision**:
- **KEEP proposed 6 variables** for MVP
- Document Phase 4+ expansion candidates
- Solar radiation is essentially free via NASA POWER → **ADD to MVP** (minimal cost)

**Revised MVP Variable List**:
1. 2m temperature ✓
2. 2m dewpoint ✓
3. 10m u-wind ✓
4. 10m v-wind ✓
5. Mean sea-level pressure ✓
6. Total precipitation ✓
7. **Surface solar radiation** (NEW - via NASA POWER, ~0 additional cost)

**Decision**: **PASS with minor addition** - Add solar radiation via NASA POWER

---

## AUDIT 7: Spatial Domain and Resolution

**Finding**: ✓ **PASS - Appropriate domain and resolution strategy**

**Proposed Domain**: India bounding box
- 6°N to 38°N (32° latitude)
- 68°E to 97°E (29° longitude)

**Assessment**:

**Geographic Coverage**:
- ✓ Covers all of India including:
  - Kashmir/Himalayan north (up to 38°N)
  - Southern peninsula (down to 6°N includes most of Tamil Nadu)
  - Eastern states (Arunachal Pradesh, Assam near 97°E)
  - Western coast (Gujarat, Maharashtra near 68°E)
- ✓ Includes partial ocean areas (Arabian Sea, Bay of Bengal) - beneficial for monsoon
- ✓ Captures major weather patterns affecting India

**Resolution Strategy**:
- Native model resolutions vary:
  - GFS: 0.25° (~25 km)
  - ECMWF: ~9 km (~0.08°)
  - ERA5-Land: 0.1° (~9-10 km)
- **No explicit target grid resolution specified in Phase 3**

**Critical Decision Needed**: Target grid resolution for HELIOS predictions

**Options**:

**A. 0.25° (GFS native)**:
- Matches coarsest input model
- Grid points: ~128 × 116 = ~15,000 locations
- Computational: Very feasible
- **Limitation**: Loses ECMWF/ERA5-Land finer detail

**B. 0.1° (ERA5-Land native)**:
- Matches verification reference resolution
- Grid points: ~320 × 290 = ~93,000 locations
- Computational: Moderate (6× more locations than 0.25°)
- **Advantage**: Preserves high-resolution information, matches verification

**C. City/Station-based** (as mentioned in mvp-recommendations.md):
- ~100-200 specific locations
- Computationally lightest
- **Advantage**: Matches real user needs (cities), easiest to verify
- **Limitation**: Not a full grid, requires spatial interpolation for new points

**Recommended Approach**:

**MVP**: **Option C - Station/City-Based** (~150 locations)
- Select major cities and agricultural regions
- One prediction per location
- Storage: Minimal compared to grid
- Verification: Can match station observations directly where available
- User value: Immediate applicability

**Post-MVP Expansion**: Option B (0.1° grid)
- Full gridded predictions
- Matches ERA5-Land for verification
- Enables spatial interpolation
- Requires more compute but feasible on RTX 5080

**Decision**: **NEEDS USER DECISION** - Target resolution (station-based vs 0.25° grid vs 0.1° grid)

**If user doesn't specify, recommend**: Station-based MVP, gridded post-MVP

---

## AUDIT 8: Storage Estimate

**Finding**: ⚠️ **SIGNIFICANT UNDERESTIMATE IDENTIFIED**

**Phase 3 Estimate**: ~38 GB raw, ~56 GB peak

**Revised Calculation**:

```
GFS (GRIB2):     ~14 GB  (14,848 grid points × 1460 cycles × 29 leads × 6 vars)
ECMWF (GRIB):    ~69 GB  (144,800 grid points × 730 cycles × 29 leads × 6 vars)
ERA5-Land (NC):  ~9 GB   (92,800 grid points × 8760 hours × 6 vars)
NASA POWER:      ~0.1 GB (coarse, daily)
───────────────────────
TOTAL RAW:       ~92 GB
Processed:       ~46 GB  (50% of raw)
───────────────────────
PEAK STORAGE:    ~138 GB
```

**Discrepancy Analysis**:
- Phase 3 estimate: 38 GB raw
- Revised estimate: 92 GB raw
- **Difference: +142% (2.4× larger)**

**Primary Causes**:
1. ECMWF higher resolution (9km vs assumed 0.25°) → 9.8× more grid points
2. Full native resolution retained (no aggressive spatial downsampling assumed)

**Budget Status**:
- Peak 138 GB vs 180 GB data cycle budget
- **Headroom: 42 GB (23%)**
- Status: **✓ STILL WITHIN BUDGET** but much tighter

**Risk Assessment**:
- ⚠️ Little room for unexpected overruns
- ⚠️ Leaves minimal space for additional variables/models
- ⚠️ Processed data compression may be worse than 50% assumed

**Mitigation Options**:

**Option 1**: Accept tighter budget (138 GB peak)
- Still within limits
- Proceed with caution
- Monitor actual sizes closely

**Option 2**: Reduce ECMWF resolution
- Resample ECMWF from 9km to 0.25° (matches GFS)
- Saves: ~55 GB raw → new total ~37 GB raw, ~55 GB peak
- **Loses high-resolution information from best NWP model**
- NOT RECOMMENDED unless necessary

**Option 3**: Station-based approach (Audit 7 recommendation)
- Dramatically reduces storage (extracts only ~150-200 points)
- GFS: ~15,000 → ~150 points (100× reduction)
- New estimate: <10 GB raw total
- **RECOMMENDED if user approves**

**Decision**: **CHANGE REQUIRED** - Revise storage estimate to ~92 GB raw, ~138 GB peak

**Storage estimate is reasonable IF**:
- User approves tighter budget
- OR spatial domain reduced (station-based)
- OR ECMWF downsampled (not recommended)

---

## AUDIT 9: NWP Forecast Storage Model

**Finding**: ✓ **PASS - Correctly designed**

**Schema Verification**:

Current `ForecastRecord` schema includes:
- ✓ `model: NWPModel`
- ✓ `issue_time: datetime` (initialization time)
- ✓ `valid_time: datetime` (target time)
- ✓ `lead_time_hours: int`
- ✓ `location: Location`
- ✓ `variables: Dict[...]`
- ✓ `ensemble_member: Optional[int]`
- ✓ `source: str` (run identifier)

**Multiple-Run Coexistence Test**:

Scenario: Three GFS runs predicting same valid_time
- GFS 2023-06-01 00Z run → 2023-06-02 12Z (36h lead)
- GFS 2023-06-01 06Z run → 2023-06-02 12Z (30h lead)
- GFS 2023-06-01 12Z run → 2023-06-02 12Z (24h lead)

Each stored as separate `ForecastRecord`:
```python
{model="gfs", issue_time="2023-06-01T00:00Z", valid_time="2023-06-02T12:00Z", lead_time_hours=36, ...}
{model="gfs", issue_time="2023-06-01T06:00Z", valid_time="2023-06-02T12:00Z", lead_time_hours=30, ...}
{model="gfs", issue_time="2023-06-01T12:00Z", valid_time="2023-06-02T12:00Z", lead_time_hours=24, ...}
```

Primary key in database (from schema.md):
```sql
UNIQUE (model_id, location_id, initialization_time, valid_time, ensemble_member)
```

**Verification**: ✓ Different initialization_time makes them unique
**Verification**: ✓ Schema does NOT collapse forecasts by valid_time alone
**Verification**: ✓ Lead time explicitly tracked and distinguishes forecasts

**Decision**: **PASS** - Storage model correctly preserves forecast provenance

---

## AUDIT 10: Verification Design

**Finding**: ✓ **PASS - Comprehensive and appropriate**

**Proposed Metrics**:
- ✓ MAE (Mean Absolute Error)
- ✓ RMSE (Root Mean Squared Error)
- ✓ Bias (Mean Error)

**Stratification**:
- ✓ By variable
- ✓ By lead time
- ✓ By location
- ✓ By season
- ✓ By model
- ✓ By forecast horizon

**Baseline Comparisons**:
- ✓ Individual NWP models
- ✓ Simple mean ensemble
- ✓ Persistence
- ✓ Climatology

**Additional Metrics to Consider** (Post-MVP):
- Continuous Ranked Probability Score (CRPS) - if ensemble
- Brier score - for probabilistic forecasts
- Calibration metrics - reliability diagrams
- Skill scores - relative to climatology

**Critical Verification Rule**:
- ✓ No generic "accuracy %" for continuous variables
- ✓ Continuous metrics (MAE/RMSE/bias) appropriate

**Decision**: **PASS** - Verification design is sound and comprehensive

---

## AUDIT 11: Model Training Data Design

**Finding**: ⚠️ **CRITICAL LEAKAGE RISK IN HISTORICAL PERFORMANCE FEATURES**

**Feature Categories** (Reviewed):
- ✓ NWP forecasts: No leakage (at issue_time)
- ✓ Model spread/disagreement: Computed from contemporaneous forecasts, no leakage
- ✓ Lead time: No leakage
- ✓ Temporal features (hour, day, season): No leakage
- ✓ Spatial features (lat, lon, elevation): No leakage
- ✓ Observation context: Requires observation_time <= issue_time ⚠️ (Audit 2)

**Historical Performance Features** ⚠️ **LEAKAGE RISK**:

Example feature: "GFS MAE over last 7 days"

**Leaky implementation**:
```python
# WRONG: Uses ALL forecasts from last 7 days
current_issue = datetime(2023, 6, 15, 0, 0)
window_start = current_issue - timedelta(days=7)
# Gets forecasts issued 2023-06-08 through 2023-06-15
# INCLUDES forecasts issued ON 2023-06-15 → LEAKAGE
mae_last_7d = calculate_mae(forecasts_in_window)
```

**Safe implementation**:
```python
# CORRECT: Uses only forecasts issued BEFORE current
current_issue = datetime(2023, 6, 15, 0, 0)
window_end = current_issue - timedelta(seconds=1)  # Strictly before
window_start = window_end - timedelta(days=7)
# Gets forecasts issued 2023-06-08 through 2023-06-14 23:59:59
mae_last_7d = calculate_mae(forecasts_before_current)
```

**Required Guards**:
1. Rolling window MUST end **strictly before** current forecast issue_time
2. Verification observations for window forecasts MUST be available by window_end
3. Expanding window safe: MAE from "all forecasts before current"
4. Cannot use same-day forecasts even if earlier hour (might introduce correlation)

**Additional Consideration**:
- Historical performance features computed per-location or globally?
- Global: Simpler, less leakage risk
- Per-location: More informative, but requires strict temporal discipline per location

**Recommendation**:
- Use **expanding window** (all history before current) rather than rolling window
- Simpler to implement without leakage
- Grows over time (reflects model learning)
- Computational: Pre-compute cumulative statistics, efficient update

**Decision**: **CHANGE REQUIRED** - Implement strict temporal guards for historical performance features

---

## AUDIT 12: Checkpoint and Data Lifecycle

**Finding**: ✓ **PASS - Well-designed resilient architecture**

**Proposed Lifecycle**:
```
download
→ validate
→ preprocess
→ feature generation
→ train
→ checkpoint
→ reload
→ sanity check
→ evaluate
→ mark valid
→ optional cleanup
```

**Resilience Assessment**:

**Power loss/Process termination**:
- ✓ Manifest system tracks download progress
- ✓ Resume support for partial downloads
- ✓ Checkpoints save model state periodically during training
- ✓ Can restart from last checkpoint

**Network failure**:
- ✓ Resume downloads from manifest
- ✓ Validate downloaded files before processing

**Partial downloads**:
- ✓ Manifest tracks completed files
- ✓ Missing files detectable before preprocessing

**Preprocessing failure**:
- ✓ Raw data retained until preprocessing verified
- ✓ Can retry preprocessing without re-download

**Training interruption**:
- ✓ Model checkpoints saved periodically
- ✓ Training can resume from checkpoint

**Data Deletion Safety**:
- ✓ Checkpoint created and saved
- ✓ Checkpoint reload tested
- ✓ Sanity check performed
- ✓ Evaluation metrics computed
- ✓ Manual approval before deletion (not automatic)

**Critical Safeguard**: "Never delete training data merely because training finished"
- ✓ Correctly stated
- ✓ Requires explicit validation before cleanup

**Missing Element** (Minor):
- Could add: Checksum verification for downloaded files
- Could add: Version control for preprocessing code (prevent silent changes)
- **Not critical for MVP, document for Phase 4+**

**Decision**: **PASS** - Lifecycle design is resilient and safe

---

## SUMMARY OF REQUIRED CHANGES BEFORE PHASE 4

### CRITICAL (Must Fix):
1. **Temporal Leakage** (Audit 2): Implement separate feature and verification temporal rules
2. **Storage Estimate** (Audit 8): Revise to ~92 GB raw, ~138 GB peak
3. **Terminology** (Audit 1): Change "ground truth" to "gridded verification reference" for ERA5-Land

### IMPORTANT (Should Fix):
4. **Historical Performance Features** (Audit 11): Implement strict temporal guards
5. **Variable Addition** (Audit 6): Add solar radiation via NASA POWER (minimal cost)

### DECISIONS NEEDED:
6. **Target Resolution** (Audit 7): User must choose station-based vs grid-based approach
7. **Storage Budget** (Audit 8): User must approve tighter budget (138 GB vs 180 GB)

### DOCUMENTATION:
8. **Model Strategy** (Audit 3): Document two-model MVP with staged expansion plan
9. **Temporal Coverage** (Audit 4): Document one-year limitations and expansion strategy
10. **Temporal Sampling** (Audit 5): Confirm 6-hourly resolution, document hourly as future enhancement

---

## PHASE 4 READINESS STATUS

**BLOCKED - CHANGES REQUIRED**

Cannot proceed to Phase 4 until:
1. ✅ User completes CDS account registration (existing blocker)
2. ⚠️ Temporal leakage rules fixed in schema (CRITICAL)
3. ⚠️ Storage estimate revised and approved
4. ⚠️ Target resolution decided (station-based vs grid)
5. ⚠️ Tighter budget approved or mitigation chosen

**Items that CAN wait until later** (post-Phase 4):
- Probabilistic verification metrics (CRPS, Brier)
- Additional NWP models (ICON, GEM, NCMRWF)
- Hourly temporal resolution
- Full 0.1° grid coverage
- Upper-air variables
- Advanced checkpoint versioning
