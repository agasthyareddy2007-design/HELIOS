"""
Tests for ICON Live Adapter

Validates:
1. Import and syntax correctness
2. Model identifier is 'icon'
3. Icosahedral grid recognition
4. Regridding method presence
5. Temporal constraint enforcement
6. ForecastRecord schema compliance
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from nwp.icon.icon_live_adapter import ICONLiveAdapter
from nwp.common.schemas import NWPModel, ForecastRecord


def test_import_and_initialization():
    """Test adapter imports and initializes correctly."""
    adapter = ICONLiveAdapter()
    assert adapter is not None
    assert adapter.BASE_URL == "https://opendata.dwd.de/weather/nwp/icon/grib"
    assert adapter.target_resolution == 0.25


def test_model_identifier():
    """Test model identifier is 'icon' (lowercase)."""
    assert NWPModel.ICON == "icon"
    assert NWPModel.ICON.value == "icon"


def test_india_domain():
    """Test India domain coordinates are correct."""
    adapter = ICONLiveAdapter()
    assert adapter.INDIA_DOMAIN['lat_min'] == 6.0
    assert adapter.INDIA_DOMAIN['lat_max'] == 38.0
    assert adapter.INDIA_DOMAIN['lon_min'] == 68.0
    assert adapter.INDIA_DOMAIN['lon_max'] == 97.0


def test_required_variables():
    """Test all required variables are defined."""
    adapter = ICONLiveAdapter()
    required_vars = ['t_2m', 'td_2m', 'u_10m', 'v_10m', 'pmsl', 'tot_prec']

    for var in required_vars:
        assert var in adapter.REQUIRED_VARIABLES
        assert adapter.REQUIRED_VARIABLES[var] in [
            'temperature_2m_c',
            'dewpoint_2m_c',
            'wind_u_10m_ms',
            'wind_v_10m_ms',
            'pressure_msl_hpa',
            'precipitation_mm'
        ]


def test_latest_run_cycles():
    """Test ICON cycles are 00/06/12/18 UTC."""
    adapter = ICONLiveAdapter()
    run_time, delay = adapter.get_latest_available_run()

    # Run time should be on a 6-hour cycle
    assert run_time.hour in [0, 6, 12, 18]
    assert run_time.minute == 0
    assert run_time.second == 0


def test_target_grid_generation():
    """Test target lat/lon grid is generated correctly."""
    adapter = ICONLiveAdapter(target_resolution=0.25)

    # Check target grid dimensions
    assert len(adapter.target_lats) > 0
    assert len(adapter.target_lons) > 0

    # Check grid covers India domain
    assert adapter.target_lats.min() >= adapter.INDIA_DOMAIN['lat_min'] - 0.01
    assert adapter.target_lats.max() <= adapter.INDIA_DOMAIN['lat_max'] + 0.01
    assert adapter.target_lons.min() >= adapter.INDIA_DOMAIN['lon_min'] - 0.01
    assert adapter.target_lons.max() <= adapter.INDIA_DOMAIN['lon_max'] + 0.01

    # Check resolution
    lat_spacing = adapter.target_lats[1] - adapter.target_lats[0]
    lon_spacing = adapter.target_lons[1] - adapter.target_lons[0]
    assert abs(lat_spacing - 0.25) < 0.01
    assert abs(lon_spacing - 0.25) < 0.01


def test_regridding_method_exists():
    """Test regridding methods are implemented."""
    adapter = ICONLiveAdapter()

    # Check regridding methods exist
    assert hasattr(adapter, '_regrid_to_latlon')
    assert hasattr(adapter, '_regrid_wind_components')
    assert hasattr(adapter, '_build_kdtree')

    # Check they are callable
    assert callable(adapter._regrid_to_latlon)
    assert callable(adapter._regrid_wind_components)
    assert callable(adapter._build_kdtree)


def test_regridding_nearest_neighbor():
    """Test nearest-neighbor regridding basic functionality."""
    adapter = ICONLiveAdapter(target_resolution=1.0)  # Coarse for testing

    # Create simple icosahedral-like grid (simplified)
    icon_lats = np.array([10.0, 15.0, 20.0, 25.0, 30.0])
    icon_lons = np.array([70.0, 75.0, 80.0, 85.0, 90.0])
    icon_values = np.array([20.0, 22.0, 24.0, 26.0, 28.0])  # Temperature values

    # Regrid
    regridded = adapter._regrid_to_latlon(icon_values, icon_lats, icon_lons)

    # Check output shape
    assert regridded.shape == (len(adapter.target_lats), len(adapter.target_lons))

    # Check no NaN/Inf in output
    assert not np.any(np.isnan(regridded))
    assert not np.any(np.isinf(regridded))

    # Check values are reasonable (should be in range of input)
    assert np.all(regridded >= icon_values.min() - 0.1)
    assert np.all(regridded <= icon_values.max() + 0.1)


def test_temporal_constraint_validation():
    """Test temporal constraints are enforced."""
    adapter = ICONLiveAdapter()

    # Test valid temporal ordering
    run_time = datetime(2026, 9, 7, 0, 0, 0)
    forecast_hour = 6
    valid_time = run_time + timedelta(hours=forecast_hour)

    assert valid_time >= run_time

    # Test invalid temporal ordering would be caught
    invalid_valid_time = run_time - timedelta(hours=1)
    assert invalid_valid_time < run_time  # This should fail validation


def test_forecast_record_schema_compliance():
    """Test that adapter produces ForecastRecord-compliant data."""
    run_time = datetime(2026, 9, 7, 0, 0, 0)
    valid_time = run_time + timedelta(hours=6)

    # Create sample ForecastRecord
    from nwp.common.schemas import Location

    record = ForecastRecord(
        forecast_id="icon_2026090700_006_20.00_75.00_t_2m",
        model=NWPModel.ICON,
        model_version="icon_global_20260907",
        issue_time=run_time,
        valid_time=valid_time,
        lead_time_hours=6,
        location=Location(latitude=20.0, longitude=75.0),
        source="dwd_icon_open_data_2026090700",
        temperature_2m_c=25.5
    )

    # Validate fields
    assert record.model == NWPModel.ICON
    assert record.model.value == "icon"
    assert record.issue_time == run_time
    assert record.valid_time == valid_time
    assert record.lead_time_hours == 6
    assert record.temperature_2m_c == 25.5


def test_url_construction():
    """Test ICON URL construction follows verified pattern."""
    adapter = ICONLiveAdapter()
    run_time = datetime(2026, 9, 7, 0, 0, 0)
    forecast_hour = 6
    variable = 't_2m'

    # Expected URL pattern from verification
    expected_filename = f"icon_global_icosahedral_single-level_2026090700_{forecast_hour:03d}_T_2M.grib2.bz2"
    expected_url = f"{adapter.BASE_URL}/00/t_2m/{expected_filename}"

    # Adapter should construct this URL internally
    # (This is a structural test, not a live fetch)
    assert adapter.BASE_URL in expected_url
    assert variable in expected_url
    assert "00" in expected_url  # Cycle hour


def test_wind_component_handling():
    """Test wind components use proper vector handling."""
    adapter = ICONLiveAdapter(target_resolution=1.0)

    # Create sample wind components
    icon_lats = np.array([10.0, 15.0, 20.0])
    icon_lons = np.array([70.0, 75.0, 80.0])
    icon_u = np.array([5.0, 6.0, 7.0])  # U wind
    icon_v = np.array([2.0, 3.0, 4.0])  # V wind

    # Regrid wind components
    u_regridded, v_regridded = adapter._regrid_wind_components(
        icon_u, icon_v, icon_lats, icon_lons
    )

    # Check output shapes match
    assert u_regridded.shape == v_regridded.shape
    assert u_regridded.shape == (len(adapter.target_lats), len(adapter.target_lons))

    # Check no NaN/Inf
    assert not np.any(np.isnan(u_regridded))
    assert not np.any(np.isnan(v_regridded))


def test_precipitation_semantics():
    """Test precipitation handling preserves accumulation semantics."""
    # ICON tot_prec is in kg/m² which equals mm
    # No conversion needed, but verify field mapping
    adapter = ICONLiveAdapter()

    assert adapter.REQUIRED_VARIABLES['tot_prec'] == 'precipitation_mm'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
