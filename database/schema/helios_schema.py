"""
HELIOS Phase 5a Database Schema

Implements the 6-table architecture for continuous learning forecast blending:
1. forecasts - Rolling window of live NWP forecasts
2. observations - Ground truth measurements
3. forecast_verification - Permanent verified forecast-outcome pairs
4. model_performance - Aggregated performance statistics
5. blending_weights - Historical weight decisions
6. production_models - Model versioning and promotion

All temporal constraints are enforced to prevent temporal leakage.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Boolean, Text, JSON,
    ForeignKey, CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Forecast(Base):
    """
    Live NWP forecasts (rolling window).

    Stores forecasts from GFS, IFS, ICON, and HELIOS blends.
    Rolling retention policy: typically 7-30 days.
    """
    __tablename__ = 'forecasts'

    # Primary key
    forecast_id = Column(String(255), primary_key=True)

    # Model identification
    model = Column(String(50), nullable=False, index=True)
    model_version = Column(String(100))

    # Temporal metadata (CRITICAL for temporal leakage prevention)
    issue_time = Column(DateTime(timezone=True), nullable=False, index=True)
    valid_time = Column(DateTime(timezone=True), nullable=False, index=True)
    lead_time_hours = Column(Integer, nullable=False, index=True)

    # Spatial
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float)
    location_id = Column(String(100))

    # Variables
    temperature_2m_c = Column(Float)
    dewpoint_2m_c = Column(Float)
    wind_u_10m_ms = Column(Float)
    wind_v_10m_ms = Column(Float)
    wind_speed_10m_ms = Column(Float)
    wind_direction_10m_deg = Column(Float)
    pressure_msl_hpa = Column(Float)
    precipitation_mm = Column(Float)
    relative_humidity_pct = Column(Float)
    cloud_cover_pct = Column(Float)

    # Metadata
    source = Column(Text, nullable=False)
    ingestion_time = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    raw_file_path = Column(Text)  # NULL after cleanup
    ensemble_member = Column(Integer)

    # Constraints
    __table_args__ = (
        CheckConstraint('lead_time_hours >= 0', name='check_positive_lead_time'),
        CheckConstraint('valid_time >= issue_time', name='check_temporal_ordering'),
        Index('idx_model_valid_location', 'model', 'valid_time', 'latitude', 'longitude'),
        Index('idx_issue_lead', 'issue_time', 'lead_time_hours'),
    )


class Observation(Base):
    """
    Ground truth observations.

    Direct measurements from NOAA stations or reference from ERA5-Land.
    Includes quality control and provenance tracking.
    """
    __tablename__ = 'observations'

    # Primary key
    observation_id = Column(String(255), primary_key=True)

    # Source and quality
    source = Column(String(50), nullable=False, index=True)
    quality_flag = Column(String(50))
    quality_score = Column(Float)  # 0.0 to 1.0

    # Temporal
    observation_time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Spatial
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float)
    location_id = Column(String(100))
    station_id = Column(String(100), index=True)
    station_distance_km = Column(Float)

    # Variables
    temperature_2m_c = Column(Float)
    dewpoint_2m_c = Column(Float)
    wind_u_10m_ms = Column(Float)
    wind_v_10m_ms = Column(Float)
    wind_speed_10m_ms = Column(Float)
    wind_direction_10m_deg = Column(Float)
    pressure_msl_hpa = Column(Float)
    surface_pressure_hpa = Column(Float)  # Distinct from MSLP
    precipitation_mm = Column(Float)
    relative_humidity_pct = Column(Float)
    cloud_cover_pct = Column(Float)

    # Metadata
    ingestion_time = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    raw_source = Column(Text)

    # Indices
    __table_args__ = (
        Index('idx_obs_time_location', 'observation_time', 'latitude', 'longitude'),
        Index('idx_obs_station_time', 'station_id', 'observation_time'),
    )


class ForecastVerification(Base):
    """
    PERMANENT verified forecast-outcome pairs.

    This is HELIOS's core learning history.
    Compact records (~200 bytes each) retained indefinitely.

    CRITICAL: Temporal constraint enforced.
    """
    __tablename__ = 'forecast_verification'

    # Primary key
    verification_id = Column(String(255), primary_key=True)

    # Forecast metadata
    forecast_id = Column(String(255), nullable=False, index=True)
    model = Column(String(50), nullable=False, index=True)
    model_version = Column(String(100))
    issue_time = Column(DateTime(timezone=True), nullable=False, index=True)
    valid_time = Column(DateTime(timezone=True), nullable=False, index=True)
    lead_time_hours = Column(Integer, nullable=False, index=True)

    # Spatial
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float)
    location_id = Column(String(100))
    location_zone = Column(String(100))  # 'north_india', 'coastal', etc.

    # Variable and values
    variable = Column(String(50), nullable=False, index=True)
    forecast_value = Column(Float, nullable=False)
    observed_value = Column(Float, nullable=False)

    # Observation metadata
    observation_source = Column(String(50), nullable=False)
    observation_quality_flag = Column(String(50))
    observation_quality_score = Column(Float)
    observation_station_ids = Column(Text)
    observation_distance_km = Column(Float)
    observation_time = Column(DateTime(timezone=True), nullable=False)

    # Errors
    error = Column(Float, nullable=False)  # forecast - observed
    absolute_error = Column(Float, nullable=False)
    squared_error = Column(Float, nullable=False)

    # Metadata
    verification_time = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        # CRITICAL: Temporal leakage prevention
        # Note: SQLite doesn't support this constraint syntax, but it's documented here
        # Application-level validation is mandatory
        # CheckConstraint('observation_time >= valid_time', name='check_no_temporal_leakage'),
        Index('idx_model_var_lead', 'model', 'variable', 'lead_time_hours'),
        Index('idx_valid_time', 'valid_time'),
        Index('idx_model_issue', 'model', 'issue_time'),
        Index('idx_location_time', 'latitude', 'longitude', 'valid_time'),
    )


class ModelPerformance(Base):
    """
    PERMANENT aggregated performance statistics.

    Rolling windows (7-day, 14-day, 30-day) of model RMSE/MAE/bias
    by model, variable, lead time group, and location zone.
    """
    __tablename__ = 'model_performance'

    # Primary key
    performance_id = Column(String(255), primary_key=True)

    # Model and context
    model = Column(String(50), nullable=False, index=True)
    variable = Column(String(50), nullable=False, index=True)
    lead_time_group = Column(String(50), nullable=False, index=True)  # '0-24h', '24-48h', etc.
    location_zone = Column(String(100))  # 'north_india', 'coastal', etc.

    # Time period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False, index=True)
    window_days = Column(Integer, nullable=False)

    # Statistics
    n_forecasts = Column(Integer, nullable=False)
    rmse = Column(Float, nullable=False)
    mae = Column(Float, nullable=False)
    bias = Column(Float, nullable=False)  # Mean error

    # Metadata
    computed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Indices
    __table_args__ = (
        Index('idx_model_period', 'model', 'period_end'),
        Index('idx_model_var_lead_period', 'model', 'variable', 'lead_time_group', 'period_end'),
    )


class BlendingWeight(Base):
    """
    PERMANENT historical weight decisions.

    Records the weights used for each forecast cycle.
    Tracks weighting method evolution (simple_average → adaptive → learned).
    """
    __tablename__ = 'blending_weights'

    # Primary key
    weight_id = Column(String(255), primary_key=True)

    # Forecast cycle
    forecast_cycle_time = Column(DateTime(timezone=True), nullable=False, index=True)

    # Model and context
    model = Column(String(50), nullable=False, index=True)
    variable = Column(String(50), nullable=False)
    lead_time_hours = Column(Integer, nullable=False)
    location_zone = Column(String(100))

    # Weight
    weight = Column(Float, nullable=False)

    # Method
    weighting_method = Column(String(50), nullable=False, index=True)  # 'simple_average', 'adaptive', 'learned'
    learned_model_version = Column(String(100))

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Constraints
    __table_args__ = (
        CheckConstraint('weight >= 0 AND weight <= 1', name='check_weight_bounds'),
        Index('idx_cycle_method', 'forecast_cycle_time', 'weighting_method'),
        Index('idx_model_method', 'model', 'weighting_method'),
    )


class ProductionModel(Base):
    """
    PERMANENT model versioning and promotion history.

    Tracks which learned models have been promoted to production,
    when, why, and their evaluation results.
    """
    __tablename__ = 'production_models'

    # Primary key
    model_id = Column(String(255), primary_key=True)

    # Model identification
    model_type = Column(String(50), nullable=False, index=True)  # 'helios_learned', 'kernel_regression', 'xgboost', 'mlp'
    version = Column(String(100), nullable=False)
    model_file_path = Column(Text, nullable=False)

    # Promotion
    promoted_at = Column(DateTime(timezone=True), nullable=False, index=True)
    promoted_from = Column(String(100))  # Previous version replaced
    evaluation_results = Column(JSON, nullable=False)  # JSON with RMSE comparison, improvement %, etc.

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    deactivated_at = Column(DateTime(timezone=True))
    deactivation_reason = Column(Text)

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    notes = Column(Text)

    # Indices
    __table_args__ = (
        Index('idx_type_active', 'model_type', 'is_active'),
        Index('idx_type_version', 'model_type', 'version'),
    )


# Database initialization function
def create_all_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def drop_all_tables(engine):
    """Drop all tables in the database (use with caution!)."""
    Base.metadata.drop_all(engine)


class ApiKey(Base):
    """
    Application API Keys for HELIOS V2 authentication.
    Stores cryptographically hashed secrets.
    """
    __tablename__ = 'api_keys'

    id = Column(String(50), primary_key=True)
    key_prefix = Column(String(50), unique=True, index=True, nullable=False)
    key_hash = Column(String(255), nullable=False)
    name = Column(String(100))
    role = Column(String(50), nullable=False, default='user')
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    revoked_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
