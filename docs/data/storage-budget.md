# HELIOS Storage Budget

## Total Allocation

**Maximum HELIOS Storage**: ~220 GB

This is the total footprint limit for the entire HELIOS project, including code, models, data, and temporary files.

## Current Usage Breakdown

### Permanent Storage (40 GB Reserved)

```
Component                Size        Notes
─────────────────────────────────────────────────────────────
System overhead         20 GB        Reserved for safety margin
Model checkpoints       10 GB        5-10 versions × 1-2 GB each
Database                 5 GB        PostgreSQL + indices
Application code         3 GB        Backend + venv + dependencies
Logs/temporary           2 GB        Application logs, temp files
─────────────────────────────────────────────────────────────
Total Permanent         40 GB
```

### Data Cycle Budget (180 GB Available)

```
Phase                   Size        Description
─────────────────────────────────────────────────────────────
Raw NWP downloads      60-80 GB     1 year, 5 models, key variables
ERA5/NASA POWER        20-30 GB     1 year, reference data
Processed Parquet      30-40 GB     Feature-engineered datasets
Training workspace     20-30 GB     Temporary files, validation sets
─────────────────────────────────────────────────────────────
Peak Usage            130-180 GB    During training cycle
Post-cleanup           ~40 GB       After data deletion
```

## Detailed Component Breakdown

### 1. Model Checkpoints (10 GB)

```
models/checkpoints/
├── helios-0.1/          ~1.5 GB    Initial MVP
├── helios-0.2/          ~1.8 GB    Expanded dataset
├── helios-0.3/          ~2.0 GB    Production release
├── helios-0.4/          ~1.7 GB    Performance tuning
└── helios-1.0/          ~2.2 GB    Major release

Total: ~9.2 GB
```

**Per-checkpoint breakdown**:
- XGBoost model: 200-400 MB
- MLP model: 50-150 MB
- Kernel regression: 500-800 MB (stores training data)
- Preprocessing pipelines: 50-100 MB
- Metrics and plots: 20-50 MB
- Metadata and config: <10 MB

### 2. Database (5 GB)

```
PostgreSQL Database
├── Tables              ~2 GB       Forecasts, observations, verification
├── Indices             ~1.5 GB     Time-series and spatial indices
├── WAL/Temp            ~500 MB     Write-ahead logs
└── Backups             ~1 GB       Rolling 7-day backups

Total: ~5 GB
```

**Table size estimates** (1 year of data):

```
Table                   Rows            Size        Notes
─────────────────────────────────────────────────────────────────
forecasts              50M             1.2 GB       5 models × 10M forecasts
observations           10M             200 MB       Hourly observations
helios_predictions     10M             250 MB       HELIOS forecasts
verification_metrics   50M             800 MB       Error metrics
model_performance      50K             10 MB        Aggregated statistics
training_runs          100             5 MB         Training metadata
─────────────────────────────────────────────────────────────────
Total                                  ~2.5 GB
```

### 3. Application Code (3 GB)

```
HELIOS/
├── venv/               ~1.5 GB      Python virtual environment
├── backend/            ~50 MB       FastAPI application
├── ai/                 ~100 MB      ML training code
├── nwp/                ~80 MB       Data adapters
├── database/           ~20 MB       Schema and migrations
├── scripts/            ~50 MB       Utility scripts
├── config/             ~10 MB       Configuration files
├── docs/               ~30 MB       Documentation
├── frontend/           ~800 MB      Node modules (future)
└── .git/               ~400 MB      Git repository
─────────────────────────────────────────────────────────────────
Total:                  ~3 GB
```

### 4. Raw NWP Data (60-80 GB per year)

```
data/raw/
├── gfs/                15-20 GB     0.25° resolution, 4 cycles/day
├── ecmwf/              20-25 GB     Higher resolution, 2 cycles/day
├── icon/               10-15 GB     13km global
├── ukmo/               8-10 GB      Variable resolution
└── gem/                8-10 GB      15km resolution
─────────────────────────────────────────────────────────────────
Total:                  61-80 GB
```

**Per-model calculation** (GFS example):

```
Variables: 10 (temp, dewpoint, wind_u, wind_v, pressure, etc.)
Spatial: 0.25° global = 1440 × 721 = 1,038,240 points
Temporal: 4 cycles/day × 365 days = 1,460 files
Lead times: 0-168h in 3h steps = 57 time steps per file
Size per variable per time: ~2 MB (GRIB2 compressed)

Total: 10 variables × 1,460 files × 57 steps × 2 MB / 1024 ≈ 16 GB
```

### 5. ERA5-Land (20-30 GB per year)

```
data/raw/era5/
└── 2024/
    ├── temperature_2m.nc      8 GB
    ├── dewpoint_2m.nc         8 GB
    ├── wind_speed_10m.nc      5 GB
    ├── pressure_msl.nc        5 GB
    └── precipitation.nc       4 GB
─────────────────────────────────────────────────────────────────
Total:                        30 GB
```

**ERA5-Land characteristics**:
- Resolution: 0.1° (~9 km)
- Temporal: Hourly
- Format: NetCDF with compression
- Coverage: Global land surface

### 6. Processed Parquet (30-40 GB)

```
data/processed/
├── features/
│   ├── train.parquet         15 GB
│   ├── val.parquet            6 GB
│   └── test.parquet           6 GB
├── targets/
│   ├── train_targets.parquet  2 GB
│   ├── val_targets.parquet    1 GB
│   └── test_targets.parquet   1 GB
└── metadata/
    └── feature_index.parquet  500 MB
─────────────────────────────────────────────────────────────────
Total:                        ~32 GB
```

**Parquet compression**: Achieves ~50% reduction from raw data through:
- Columnar compression (Snappy)
- Dictionary encoding for categorical features
- Run-length encoding for repeated values

## Storage Lifecycle

### Phase 1: Download (60-80 GB)

```
Start:  40 GB (permanent)
NWP:   +70 GB
ERA5:  +25 GB
NASA:  +5 GB
─────────────
Total: 140 GB
```

### Phase 2: Preprocessing (130-180 GB)

```
Existing:     140 GB
Processed:    +35 GB
Workspace:    +15 GB
─────────────
Peak:         190 GB ⚠️ Near limit
```

**Risk mitigation**:
- Delete raw files as soon as processed
- Process in batches (quarterly instead of yearly)
- Stream preprocessing where possible

### Phase 3: Training (100-150 GB)

```
Existing:     140 GB (raw + processed)
Model cache:  +10 GB
Validation:   +5 GB
─────────────
Total:        155 GB
```

### Phase 4: Cleanup (40 GB)

```
Delete raw:       -95 GB
Delete processed: -35 GB
Keep checkpoint:  +2 GB
─────────────────
Final:            42 GB ✓ Back to baseline
```

## Progressive Dataset Expansion

### Year 1: MVP (1 year of data)

```
Peak Usage:    180 GB
Post-Cleanup:   42 GB
Status:        ✓ Fits comfortably
```

### Year 2: Expansion (2 years of data)

**Challenge**: 2 years would require ~360 GB peak (exceeds limit)

**Solution**: Incremental training
- Keep existing checkpoint
- Download only 2nd year of data
- Train incrementally
- Delete 2nd year after checkpoint

```
Permanent:      42 GB (includes year 1 checkpoint)
Year 2 data:  +140 GB
Peak:          182 GB ✓ Still fits
Post-cleanup:   44 GB
```

### Year 3-5: Production (3+ years)

**Strategy**: Temporal subsampling
- Sample every 2nd or 3rd day instead of daily
- OR: Focus on recent years, sample older data
- Use incremental learning to add data progressively

```
3 years (full):     ~540 GB ✗ Does not fit
3 years (sampled):  ~180 GB ✓ Fits with sampling
```

## Monitoring and Alerts

### Disk Usage Monitoring

```bash
#!/bin/bash
# Monitor HELIOS storage

HELIOS_ROOT="/home/agasthya/HELIOS"
MAX_GB=220
WARN_GB=200

USAGE_GB=$(du -sb $HELIOS_ROOT | awk '{print int($1/1024/1024/1024)}')

if [ $USAGE_GB -gt $MAX_GB ]; then
    echo "ERROR: HELIOS using ${USAGE_GB}GB (limit: ${MAX_GB}GB)"
    exit 1
elif [ $USAGE_GB -gt $WARN_GB ]; then
    echo "WARNING: HELIOS using ${USAGE_GB}GB (approaching limit: ${MAX_GB}GB)"
    exit 0
else
    echo "OK: HELIOS using ${USAGE_GB}GB / ${MAX_GB}GB"
    exit 0
fi
```

### Storage Alerts

```python
# Python monitoring
import psutil

def check_helios_storage():
    helios_path = "/home/agasthya/HELIOS"
    
    # Total HELIOS usage
    total_bytes = sum(
        f.stat().st_size 
        for f in Path(helios_path).rglob('*') 
        if f.is_file()
    )
    total_gb = total_bytes / 1e9
    
    # Breakdown by component
    breakdown = {
        'data/raw': get_dir_size(f"{helios_path}/data/raw"),
        'data/processed': get_dir_size(f"{helios_path}/data/processed"),
        'models/checkpoints': get_dir_size(f"{helios_path}/models/checkpoints"),
        'database': get_db_size(),
    }
    
    # Alert if approaching limit
    if total_gb > 200:
        send_alert(f"HELIOS storage at {total_gb:.1f} GB")
    
    return total_gb, breakdown
```

## Optimization Strategies

### 1. Data Compression

**GRIB2 compression**: Already compressed by provider
**Parquet compression**: Use Snappy (fast) or Zstd (high compression)
**Model checkpoints**: Use pickle protocol 5 for efficient serialization

### 2. Selective Variable Download

Don't download variables HELIOS doesn't use:

```python
# Download only required variables
required_vars = [
    'temperature_2m',
    'dewpoint_2m', 
    'wind_speed_10m',
    'wind_direction_10m',
    'pressure_msl'
]

# Skip: geopotential height, cloud layers, etc.
```

**Savings**: ~40% reduction in NWP data size

### 3. Spatial Subsetting

Focus on regions of interest instead of global grids:

```python
# Geographic bounding box
bbox = {
    'lat_min': -60,
    'lat_max': 60,
    'lon_min': -180,
    'lon_max': 180
}
```

**Savings**: Up to 50% for regional focus

### 4. Temporal Thinning

After initial training, use temporal subsampling:

```python
# Sample every 2nd day
data = data[::2]

# Or: stratified sampling (ensure seasonal balance)
data = stratified_temporal_sample(data, target_size=0.5)
```

**Savings**: 50% for every-other-day sampling

## Emergency Procedures

### If Storage Exceeds Limit

**Priority 1: Delete raw data**
```bash
rm -rf /home/agasthya/HELIOS/data/raw/*
```
Recovers: 60-80 GB

**Priority 2: Delete processed data**
```bash
rm -rf /home/agasthya/HELIOS/data/processed/*
```
Recovers: 30-40 GB

**Priority 3: Archive old checkpoints**
```bash
tar -czf helios-old-checkpoints.tar.gz models/checkpoints/helios-0.{1,2,3}
rm -rf models/checkpoints/helios-0.{1,2,3}
```
Recovers: 5-7 GB

**Last Resort: External storage**
- Move old checkpoints to external HDD
- Archive training data to cloud storage

## Capacity Planning

### Current Headroom

```
Total allocation:    220 GB
Permanent baseline:   40 GB
Available for data:  180 GB
Typical peak:        150 GB
Safety margin:        30 GB ✓ Comfortable
```

### Growth Projection

```
Year    Data         Peak      Feasibility
────────────────────────────────────────────
1       1 year      180 GB    ✓ Fits
2       2 years     360 GB    ✗ Use incremental training
3       3 years     540 GB    ✗ Use sampling
5       5 years     900 GB    ✗ Require cloud/external storage
```

**Conclusion**: HELIOS can comfortably handle 1 year of data, requires careful management for 2+ years.

## Next Steps

1. Implement storage monitoring scripts
2. Set up automated cleanup after training
3. Create checkpoint compression utilities
4. Build incremental training pipeline
5. Establish alert thresholds
6. Document emergency procedures
7. Test data sampling strategies
8. Evaluate external storage options

---

**Status**: Storage budget documented
**Next**: Implement monitoring and cleanup automation
