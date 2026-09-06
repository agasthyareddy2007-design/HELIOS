# HELIOS Data Architecture

## Overview

HELIOS is designed with a **storage-aware architecture** that acknowledges the 220 GB constraint while enabling progressive dataset expansion through a download-train-delete cycle.

## Data Sources

### NWP Model Data

| Model | Provider | Resolution | Cycles/Day | Lead Time | Access Method |
|-------|----------|------------|------------|-----------|---------------|
| **GFS** | NOAA/NCEP | 0.25° | 4 (00Z, 06Z, 12Z, 18Z) | 384h | NOMADS OpenDAP/GRIB2 |
| **ECMWF IFS** | ECMWF | Variable | 2 | 240h+ | MARS API / Commercial |
| **ICON** | DWD | 13km global | 4 | 180h | DWD OpenData |
| **UK Met Office** | UKMO | Variable | Variable | 144h+ | API access required |
| **GEM** | CMC | 15km | 2 | 240h | ECCC Datamart |

### Reference & Auxiliary Data

**ERA5-Land**
- Provider: ECMWF Copernicus
- Resolution: 0.1° (~9 km)
- Temporal: Hourly
- Coverage: 1950-present
- Purpose: Historical weather conditions, forecast verification
- Access: CDS API
- Format: NetCDF

**NASA POWER**
- Provider: NASA GES DISC
- Resolution: 0.5°
- Temporal: Daily
- Coverage: 1983-present
- Purpose: Satellite-derived meteorological data, auxiliary features
- Access: REST API
- Format: JSON

**Observational Data**
- Station observations (METAR, SYNOP)
- Weather API services (WeatherAPI, OpenWeatherMap, etc.)
- Purpose: Real-time verification, recent weather context

## Data Abstraction Layer

Each NWP source is normalized through an adapter pattern:

```
Raw NWP Data (GRIB/NetCDF/API)
           ↓
    Source Adapter
           ↓
  Common HELIOS Format
           ↓
    PostgreSQL Metadata
```

### Common Format Fields

```python
{
    "forecast_id": "uuid",
    "model": "gfs|ecmwf|icon|ukmo|gem",
    "initialization_time": "2026-09-05T00:00:00Z",
    "valid_time": "2026-09-06T12:00:00Z",
    "lead_time_hours": 36,
    "location": {
        "latitude": 17.385,
        "longitude": 78.487
    },
    "variables": {
        "temperature_2m": 28.5,
        "dewpoint_2m": 22.3,
        "wind_speed_10m": 4.2,
        "wind_direction_10m": 135,
        "pressure_msl": 1010.5,
        "precipitation_total": 0.0
    },
    "ensemble_member": null,  # or integer for ensemble models
    "model_version": "16.3.0",
    "data_source": "nomads",
    "ingestion_timestamp": "2026-09-05T00:15:23Z"
}
```

## Storage Formats

### Raw Data (Temporary)

**Purpose**: Downloaded NWP data before preprocessing

**Formats**:
- GRIB2 (GFS, ECMWF, ICON)
- NetCDF (ERA5, some NWP models)
- JSON (NASA POWER, weather APIs)

**Location**: `data/raw/<source>/`

**Retention**: Delete after preprocessing and verification

### Processed Data (Temporary)

**Purpose**: Preprocessed datasets ready for ML training

**Format**: Apache Parquet
- Columnar format optimized for analytics
- Excellent compression
- Fast I/O for ML frameworks

**Location**: `data/processed/<dataset>/`

**Retention**: Delete after training and checkpoint verification

### Archived Data (Optional, Temporary)

**Purpose**: Long-term efficient storage for potential retraining

**Format**: Zarr
- Chunked, compressed N-dimensional arrays
- Cloud-optimized
- Supports parallel I/O

**Location**: `data/processed/archives/`

**Retention**: Delete when storage pressure requires it

### Model Checkpoints (Permanent)

**Purpose**: Trained model artifacts

**Formats**:
- PyTorch: `.pt` / `.pth` (MLP)
- XGBoost: `.json` / `.ubj` (gradient boosting)
- Pickle: `.pkl` (kernel regression, preprocessing pipelines)

**Location**: `models/checkpoints/<version>/`

**Retention**: Keep indefinitely for rollback capability

### Application Data (Permanent)

**Purpose**: Structured operational data

**Format**: PostgreSQL database tables

**Content**:
- Location metadata
- NWP model configurations
- Forecast records (lightweight metadata, not full grids)
- Observation records
- Verification metrics
- Model performance statistics
- Training run metadata

## Storage Budget

**Total Allocation**: ~220 GB

**Breakdown**:

```
System overhead               20 GB   (Reserved)
Model checkpoints            10 GB   (5-10 versions × ~1-2 GB each)
Database                      5 GB   (PostgreSQL + indices)
Application code/venv         3 GB
Logs/temporary files          2 GB
───────────────────────────────────
Reserved/permanent           40 GB

Available for data cycles   180 GB
```

**Data Cycle Budget** (~180 GB available):

During one training cycle:

```
Raw NWP downloads          60-80 GB  (1 year, 5 models, key variables)
ERA5/NASA POWER            20-30 GB  (1 year, reference data)
Processed Parquet          30-40 GB  (Feature-engineered datasets)
Training workspace         20-30 GB  (Temporary files, validation sets)
────────────────────────────────────
Peak usage                130-180 GB
```

After checkpoint verification: Delete raw + processed → **Back to ~40 GB**

## Progressive Dataset Expansion

### Phase 1: MVP (1 year)

**Period**: 2025-01-01 to 2025-12-31
**Purpose**: Establish baseline, validate pipeline
**Storage**: ~150 GB peak, ~40 GB after cleanup

### Phase 2: Expansion (2 years)

**Period**: 2024-01-01 to 2025-12-31
**Purpose**: Improve model performance
**Storage**: Reuse freed space, incremental training

### Phase 3: Production (3+ years)

**Period**: 2022-01-01 onwards
**Purpose**: Production-ready model
**Strategy**: Incremental training, selective historical sampling

## Data Pipeline

### Download Phase

```python
# Pseudocode
for year in training_years:
    for model in nwp_models:
        adapter = get_adapter(model)
        data = adapter.download(year, variables)
        save_to_raw(data)
        
    # Download reference data
    era5_data = download_era5(year)
    nasa_data = download_nasa_power(year)
```

### Preprocessing Phase

```python
# Pseudocode
for raw_file in raw_files:
    # Spatial interpolation to common grid
    gridded_data = regrid_to_common(raw_file)
    
    # Temporal alignment
    aligned_data = align_timestamps(gridded_data)
    
    # Quality control
    clean_data = apply_qc(aligned_data)
    
    # Save to Parquet
    save_parquet(clean_data, processed_dir)
```

### Feature Engineering Phase

```python
# Pseudocode
processed_data = load_parquet(processed_dir)

features = engineer_features(
    nwp_data=processed_data,
    era5_data=era5_data,
    nasa_data=nasa_data,
    observations=obs_data
)

# Features include:
# - NWP model outputs (all 5 models)
# - Ensemble spread/disagreement
# - Temporal features (hour, day, season)
# - Spatial features (lat, lon, topography)
# - Historical model performance
# - Recent weather context
# - ERA5 climatology
# - NASA POWER auxiliary variables

save_features(features, data_dir)
```

### Training Phase

```python
# Pseudocode
train_data, val_data, test_data = load_and_split(features)

# Train each ML competitor
kernel_model = train_kernel_regression(train_data, val_data)
xgboost_model = train_xgboost(train_data, val_data)
mlp_model = train_mlp(train_data, val_data)

# Evaluate
metrics = evaluate_models([kernel_model, xgboost_model, mlp_model], test_data)

# Save best model
save_checkpoint(best_model, version, metrics)
```

### Cleanup Phase

```python
# Pseudocode
if checkpoint_verified:
    delete_raw_data(year)
    delete_processed_data(year)
    # Keep only checkpoint + metadata
```

## Data Governance

### Temporal Leakage Prevention

**Rule**: Never use future data to predict the past

**Implementation**:
- Strict train/val/test splits by time
- Features computed only from data available at forecast issue time
- Verification observations matched by valid time only
- Historical model performance computed from past forecasts only

**Example**:

```
Forecast issued: 2026-09-05 00:00 UTC
Valid time:      2026-09-06 12:00 UTC

Feature cutoff:  2026-09-05 00:00 UTC (no future data)
Observation:     Available at/after 2026-09-06 12:00 UTC
Verification:    Computed after observation available
```

### Data Versioning

Each dataset is versioned:

```
dataset/
├── v1.0/
│   ├── metadata.json      # Sources, dates, versions
│   ├── train.parquet
│   ├── val.parquet
│   └── test.parquet
├── v1.1/
│   └── ...
└── v2.0/
    └── ...
```

Metadata includes:
- NWP model versions
- Data source URLs
- Download dates
- Processing pipeline version
- Quality flags
- Known issues

## Access Patterns

### Training Access

**Pattern**: Sequential, full-scan
**Format**: Parquet (optimized for batch ML)
**Parallelism**: Multi-process data loading

### Inference Access

**Pattern**: Random, point queries
**Format**: PostgreSQL (fast lookups) + cached recent NWP
**Latency**: <100ms for single forecast

### Verification Access

**Pattern**: Time-based queries
**Format**: PostgreSQL with time indices
**Purpose**: Model performance monitoring

## Monitoring

### Storage Monitoring

```bash
# Check total HELIOS usage
du -sh /home/agasthya/HELIOS

# Check by directory
du -sh /home/agasthya/HELIOS/data/*
du -sh /home/agasthya/HELIOS/models/*

# Check available space
df -h /home
```

### Data Quality Monitoring

- Missing data percentage
- Out-of-range values
- Temporal gaps
- Spatial coverage
- Model availability

### Pipeline Health

- Download success rate
- Preprocessing completion
- Feature engineering validation
- Training convergence
- Verification completeness

## Future Considerations

### Cloud Storage Option

If local storage becomes limiting:

- **Option 1**: Cloud archival (AWS S3 Glacier, Google Cloud Storage Archive)
- **Option 2**: External HDD/SSD for historical data
- **Option 3**: Streaming training (cloud-to-local on-demand)

### Data Pruning Strategies

If dataset grows beyond capacity:

- **Temporal sampling**: Every N days instead of daily
- **Spatial sampling**: Subset of locations
- **Variable reduction**: Only essential variables
- **Ensemble thinning**: Fewer ensemble members

## Best Practices

1. **Always verify checksums** after downloads
2. **Log all data operations** for reproducibility
3. **Test preprocessing pipeline** on small subset first
4. **Validate checkpoint** before deleting training data
5. **Keep manifests** of deleted data for reference
6. **Monitor storage daily** during data operations
7. **Document data issues** in metadata

## References

- NOAA NOMADS: https://nomads.ncep.noaa.gov/
- ECMWF CDS: https://cds.climate.copernicus.eu/
- NASA POWER: https://power.larc.nasa.gov/
- DWD OpenData: https://opendata.dwd.de/
- ECCC Datamart: https://dd.weather.gc.ca/

---

**Status**: Foundation complete
**Next**: Implement data adapters for each NWP source
