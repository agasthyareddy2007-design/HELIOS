# HELIOS Database Schema

## Overview

HELIOS uses PostgreSQL to store structured operational data, forecast metadata, verification records, and model performance statistics. The database does NOT store full weather grids (those live in Parquet/Zarr); it stores lightweight metadata and point-based records.

## Design Principles

1. **Lightweight metadata** - Store pointers to data files, not the data itself
2. **Time-series optimized** - Indexes on temporal columns for fast queries
3. **Strict temporal integrity** - Separate forecast and observation timestamps
4. **Normalization** - Avoid data redundancy, maintain referential integrity
5. **Audit trail** - Track data ingestion, training runs, model deployments

## Schema Diagram

```
locations
    ↓
forecasts ← observations (verification)
    ↓
verification_metrics
    ↓
model_performance
```

## Core Tables

### locations

Defines the geographic points where forecasts are generated and verified.

```sql
CREATE TABLE locations (
    location_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    latitude DECIMAL(8, 5) NOT NULL,
    longitude DECIMAL(8, 5) NOT NULL,
    elevation_m DECIMAL(6, 1),
    timezone VARCHAR(50) NOT NULL,
    country_code CHAR(2),
    region VARCHAR(100),
    location_type VARCHAR(50), -- 'city', 'station', 'grid_point'
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_coordinates UNIQUE (latitude, longitude)
);

CREATE INDEX idx_locations_coords ON locations USING GIST (
    ll_to_earth(latitude, longitude)
);
CREATE INDEX idx_locations_name ON locations (name);
```

### nwp_models

Registry of NWP model configurations and versions.

```sql
CREATE TABLE nwp_models (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(50) NOT NULL, -- 'gfs', 'ecmwf', 'icon', 'ukmo', 'gem'
    model_version VARCHAR(50) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    spatial_resolution VARCHAR(50),
    temporal_resolution VARCHAR(50),
    max_lead_time_hours INT,
    variables_available TEXT[],
    data_source_url VARCHAR(500),
    access_method VARCHAR(100), -- 'nomads', 'cds', 'opendata'
    active BOOLEAN DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_model_version UNIQUE (model_name, model_version)
);

CREATE INDEX idx_nwp_models_name ON nwp_models (model_name);
```

### forecasts

Individual NWP model forecasts at specific locations and times.

```sql
CREATE TABLE forecasts (
    forecast_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id UUID NOT NULL REFERENCES nwp_models(model_id),
    location_id UUID NOT NULL REFERENCES locations(location_id),
    
    -- Temporal
    initialization_time TIMESTAMP WITH TIME ZONE NOT NULL,
    valid_time TIMESTAMP WITH TIME ZONE NOT NULL,
    lead_time_hours INT NOT NULL,
    
    -- Forecast values
    temperature_2m DECIMAL(5, 2),
    dewpoint_2m DECIMAL(5, 2),
    wind_speed_10m DECIMAL(5, 2),
    wind_direction_10m DECIMAL(5, 2),
    pressure_msl DECIMAL(6, 2),
    precipitation_total DECIMAL(6, 2),
    cloud_cover DECIMAL(5, 2),
    
    -- Metadata
    ensemble_member INT, -- NULL for deterministic
    data_source VARCHAR(100),
    ingestion_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_forecast UNIQUE (
        model_id, location_id, initialization_time, valid_time, ensemble_member
    )
);

CREATE INDEX idx_forecasts_valid_time ON forecasts (valid_time);
CREATE INDEX idx_forecasts_init_time ON forecasts (initialization_time);
CREATE INDEX idx_forecasts_location ON forecasts (location_id);
CREATE INDEX idx_forecasts_model ON forecasts (model_id);
CREATE INDEX idx_forecasts_lead_time ON forecasts (lead_time_hours);
```

### observations

Actual observed weather conditions used for forecast verification.

```sql
CREATE TABLE observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID NOT NULL REFERENCES locations(location_id),
    
    -- Temporal
    observation_time TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Observed values
    temperature_2m DECIMAL(5, 2),
    dewpoint_2m DECIMAL(5, 2),
    wind_speed_10m DECIMAL(5, 2),
    wind_direction_10m DECIMAL(5, 2),
    pressure_msl DECIMAL(6, 2),
    precipitation_total DECIMAL(6, 2),
    cloud_cover DECIMAL(5, 2),
    
    -- Metadata
    data_source VARCHAR(100), -- 'era5', 'station', 'weather_api'
    quality_flag VARCHAR(50),
    ingestion_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_observation UNIQUE (location_id, observation_time, data_source)
);

CREATE INDEX idx_observations_time ON observations (observation_time);
CREATE INDEX idx_observations_location ON observations (location_id);
```

### helios_predictions

HELIOS blended forecast predictions.

```sql
CREATE TABLE helios_predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id UUID NOT NULL REFERENCES locations(location_id),
    model_version VARCHAR(50) NOT NULL, -- 'helios-0.1', 'helios-0.2'
    
    -- Temporal
    initialization_time TIMESTAMP WITH TIME ZONE NOT NULL,
    valid_time TIMESTAMP WITH TIME ZONE NOT NULL,
    lead_time_hours INT NOT NULL,
    
    -- Predictions
    temperature_2m DECIMAL(5, 2),
    dewpoint_2m DECIMAL(5, 2),
    wind_speed_10m DECIMAL(5, 2),
    wind_direction_10m DECIMAL(5, 2),
    pressure_msl DECIMAL(6, 2),
    precipitation_total DECIMAL(6, 2),
    
    -- Blending metadata
    model_weights JSONB, -- {"gfs": 0.3, "ecmwf": 0.4, ...}
    confidence_score DECIMAL(4, 3),
    ensemble_spread DECIMAL(5, 2),
    
    -- Metadata
    prediction_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_helios_prediction UNIQUE (
        model_version, location_id, initialization_time, valid_time
    )
);

CREATE INDEX idx_helios_valid_time ON helios_predictions (valid_time);
CREATE INDEX idx_helios_location ON helios_predictions (location_id);
CREATE INDEX idx_helios_version ON helios_predictions (model_version);
```

### verification_metrics

Forecast verification results comparing predictions to observations.

```sql
CREATE TABLE verification_metrics (
    verification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- What was verified
    forecast_id UUID REFERENCES forecasts(forecast_id),
    prediction_id UUID REFERENCES helios_predictions(prediction_id),
    observation_id UUID NOT NULL REFERENCES observations(observation_id),
    location_id UUID NOT NULL REFERENCES locations(location_id),
    
    -- Temporal
    valid_time TIMESTAMP WITH TIME ZONE NOT NULL,
    lead_time_hours INT NOT NULL,
    
    -- Error metrics
    variable VARCHAR(50) NOT NULL, -- 'temperature_2m', 'wind_speed_10m', etc.
    forecast_value DECIMAL(10, 4),
    observed_value DECIMAL(10, 4),
    absolute_error DECIMAL(10, 4),
    squared_error DECIMAL(10, 4),
    bias DECIMAL(10, 4),
    
    -- Metadata
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT check_forecast_or_prediction CHECK (
        (forecast_id IS NOT NULL AND prediction_id IS NULL) OR
        (forecast_id IS NULL AND prediction_id IS NOT NULL)
    )
);

CREATE INDEX idx_verification_time ON verification_metrics (valid_time);
CREATE INDEX idx_verification_lead_time ON verification_metrics (lead_time_hours);
CREATE INDEX idx_verification_variable ON verification_metrics (variable);
CREATE INDEX idx_verification_forecast ON verification_metrics (forecast_id);
CREATE INDEX idx_verification_prediction ON verification_metrics (prediction_id);
```

### model_performance

Aggregated model performance statistics over time windows.

```sql
CREATE TABLE model_performance (
    performance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Model identification
    model_id UUID REFERENCES nwp_models(model_id),
    helios_version VARCHAR(50), -- NULL for NWP models
    location_id UUID REFERENCES locations(location_id),
    
    -- Time window
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    lead_time_hours INT NOT NULL,
    
    -- Variable
    variable VARCHAR(50) NOT NULL,
    
    -- Statistics
    sample_count INT NOT NULL,
    mae DECIMAL(10, 4),
    rmse DECIMAL(10, 4),
    bias DECIMAL(10, 4),
    correlation DECIMAL(6, 4),
    
    -- Metadata
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT check_model_or_helios CHECK (
        (model_id IS NOT NULL AND helios_version IS NULL) OR
        (model_id IS NULL AND helios_version IS NOT NULL)
    )
);

CREATE INDEX idx_performance_period ON model_performance (period_start, period_end);
CREATE INDEX idx_performance_lead_time ON model_performance (lead_time_hours);
CREATE INDEX idx_performance_variable ON model_performance (variable);
CREATE INDEX idx_performance_model ON model_performance (model_id);
CREATE INDEX idx_performance_helios ON model_performance (helios_version);
```

## Operational Tables

### training_runs

Metadata for ML model training runs.

```sql
CREATE TABLE training_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Model identification
    model_type VARCHAR(50) NOT NULL, -- 'kernel', 'xgboost', 'mlp'
    model_version VARCHAR(50) NOT NULL, -- 'helios-0.2'
    
    -- Training configuration
    training_period_start DATE NOT NULL,
    training_period_end DATE NOT NULL,
    validation_period_start DATE NOT NULL,
    validation_period_end DATE NOT NULL,
    
    -- Data sources
    nwp_models_used TEXT[],
    features_used TEXT[],
    hyperparameters JSONB,
    
    -- Results
    training_mae DECIMAL(10, 4),
    training_rmse DECIMAL(10, 4),
    validation_mae DECIMAL(10, 4),
    validation_rmse DECIMAL(10, 4),
    
    -- Metadata
    git_commit VARCHAR(40),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50), -- 'running', 'completed', 'failed'
    checkpoint_path VARCHAR(500),
    
    created_by VARCHAR(100)
);

CREATE INDEX idx_training_version ON training_runs (model_version);
CREATE INDEX idx_training_status ON training_runs (status);
CREATE INDEX idx_training_started ON training_runs (started_at);
```

### model_deployments

Track which HELIOS model version is currently deployed.

```sql
CREATE TABLE model_deployments (
    deployment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    model_version VARCHAR(50) NOT NULL,
    run_id UUID REFERENCES training_runs(run_id),
    
    deployment_type VARCHAR(50) NOT NULL, -- 'champion', 'challenger', 'shadow'
    
    deployed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deployed_by VARCHAR(100),
    
    deactivated_at TIMESTAMP WITH TIME ZONE,
    deactivated_reason TEXT,
    
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_deployments_version ON model_deployments (model_version);
CREATE INDEX idx_deployments_active ON model_deployments (is_active);
```

### data_ingestion_log

Audit trail for data downloads and ingestion.

```sql
CREATE TABLE data_ingestion_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    data_type VARCHAR(50) NOT NULL, -- 'nwp_forecast', 'era5', 'observation'
    source VARCHAR(100) NOT NULL,
    
    -- Time range
    data_start_time TIMESTAMP WITH TIME ZONE,
    data_end_time TIMESTAMP WITH TIME ZONE,
    
    -- Status
    status VARCHAR(50) NOT NULL, -- 'started', 'completed', 'failed'
    records_ingested INT,
    error_message TEXT,
    
    -- Metadata
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    file_path VARCHAR(500),
    file_size_bytes BIGINT
);

CREATE INDEX idx_ingestion_type ON data_ingestion_log (data_type);
CREATE INDEX idx_ingestion_status ON data_ingestion_log (status);
CREATE INDEX idx_ingestion_started ON data_ingestion_log (started_at);
```

## Functions and Triggers

### Update timestamps

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_locations_updated_at
    BEFORE UPDATE ON locations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### Compute verification metrics

```sql
CREATE OR REPLACE FUNCTION compute_verification_metrics(
    p_forecast_id UUID,
    p_observation_id UUID,
    p_variable VARCHAR
) RETURNS VOID AS $$
DECLARE
    v_forecast_value DECIMAL;
    v_observed_value DECIMAL;
    v_location_id UUID;
    v_valid_time TIMESTAMP WITH TIME ZONE;
    v_lead_time INT;
BEGIN
    -- Get forecast and observation values
    SELECT 
        f.temperature_2m,
        f.location_id,
        f.valid_time,
        f.lead_time_hours
    INTO 
        v_forecast_value,
        v_location_id,
        v_valid_time,
        v_lead_time
    FROM forecasts f
    WHERE f.forecast_id = p_forecast_id;
    
    SELECT o.temperature_2m
    INTO v_observed_value
    FROM observations o
    WHERE o.observation_id = p_observation_id;
    
    -- Insert verification record
    INSERT INTO verification_metrics (
        forecast_id,
        observation_id,
        location_id,
        valid_time,
        lead_time_hours,
        variable,
        forecast_value,
        observed_value,
        absolute_error,
        squared_error,
        bias
    ) VALUES (
        p_forecast_id,
        p_observation_id,
        v_location_id,
        v_valid_time,
        v_lead_time,
        p_variable,
        v_forecast_value,
        v_observed_value,
        ABS(v_forecast_value - v_observed_value),
        POWER(v_forecast_value - v_observed_value, 2),
        v_forecast_value - v_observed_value
    );
END;
$$ LANGUAGE plpgsql;
```

## Views

### recent_model_performance

Current model performance over the last 30 days.

```sql
CREATE VIEW recent_model_performance AS
SELECT 
    m.model_name,
    mp.variable,
    mp.lead_time_hours,
    AVG(mp.mae) as avg_mae,
    AVG(mp.rmse) as avg_rmse,
    AVG(mp.bias) as avg_bias,
    SUM(mp.sample_count) as total_samples
FROM model_performance mp
JOIN nwp_models m ON mp.model_id = m.model_id
WHERE mp.period_end >= NOW() - INTERVAL '30 days'
GROUP BY m.model_name, mp.variable, mp.lead_time_hours;
```

### active_helios_model

Currently deployed HELIOS champion model.

```sql
CREATE VIEW active_helios_model AS
SELECT 
    d.model_version,
    d.deployed_at,
    d.deployed_by,
    tr.validation_mae,
    tr.validation_rmse,
    tr.checkpoint_path
FROM model_deployments d
JOIN training_runs tr ON d.run_id = tr.run_id
WHERE d.is_active = TRUE
  AND d.deployment_type = 'champion'
ORDER BY d.deployed_at DESC
LIMIT 1;
```

## Backup and Maintenance

### Daily backup

```bash
# Automated daily backup
pg_dump helios_db > /home/agasthya/HELIOS/database/backups/helios_$(date +%Y%m%d).sql
```

### Vacuum and analyze

```sql
-- Weekly maintenance
VACUUM ANALYZE forecasts;
VACUUM ANALYZE observations;
VACUUM ANALYZE verification_metrics;
```

### Archive old data

```sql
-- Archive forecasts older than 1 year
DELETE FROM forecasts
WHERE initialization_time < NOW() - INTERVAL '1 year'
  AND forecast_id NOT IN (
      SELECT forecast_id FROM verification_metrics
  );
```

## Migration Strategy

Alembic will manage schema migrations:

```
database/migrations/
├── versions/
│   ├── 001_initial_schema.py
│   ├── 002_add_helios_predictions.py
│   └── 003_add_performance_indices.py
└── env.py
```

## Access Patterns and Optimization

**Typical Queries**:

1. **Forecast retrieval**: Fast point queries by location + time
2. **Verification lookup**: Join forecasts with observations by valid_time
3. **Performance aggregation**: Time-series aggregation over lead times
4. **Model comparison**: Multi-model performance over date ranges

**Optimization**:
- Partition `forecasts` and `observations` by month
- Index on (location_id, valid_time) for fast lookups
- Materialized views for expensive aggregations
- Connection pooling via SQLAlchemy

---

**Status**: Schema designed
**Next**: Implement Alembic migrations and create initial tables
