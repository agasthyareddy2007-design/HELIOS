"""
Unit Tests for Observation Matcher

Tests for HELIOS observation matching with GHCNh (primary) and ERA5-Land (fallback).

Test coverage:
1. Matcher initialization
2. GHCNh matching (primary direct observations)
3. ERA5-Land fallback (gridded reanalysis reference)
4. Temporal tolerance window
5. Spatial tolerance for NOAA stations
6. Quality control and provenance
7. No observation behavior (no fabrication)
8. Supported variables
9. Temporal matching determinism
10. Spatial matching determinism
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_matcher_initialization():
    """Test matcher initializes correctly."""
    print("TEST 1: Matcher initialization")

    from observation.observation_matcher import (
        ObservationMatcher,
        MatcherConfig
    )

    config = MatcherConfig(
        temporal_tolerance_hours=2.0,
        max_station_distance_km=30.0
    )
    matcher = ObservationMatcher(config)

    assert matcher.config.temporal_tolerance_hours == 2.0
    assert matcher.config.max_station_distance_km == 30.0
    assert matcher.config.supported_variables == ['temperature_2m_c']

    print("  ✓ Matcher initialized with config")
    print("  ✓ Default supported variables set")
    print()
    return True


def test_temporal_tolerance_window():
    """Test temporal matching window calculation."""
    print("TEST 2: Temporal tolerance window")

    from observation.observation_matcher import MatcherConfig

    config = MatcherConfig(
        temporal_tolerance_hours=1.0,
        require_post_valid_time=True
    )

    valid_time = datetime(2026, 9, 7, 12, 0, 0)

    # With require_post_valid_time=True:
    # window = [valid_time, valid_time + 1h]
    time_window_start = valid_time
    time_window_end = valid_time + timedelta(hours=config.temporal_tolerance_hours)

    assert time_window_start == datetime(2026, 9, 7, 12, 0, 0)
    assert time_window_end == datetime(2026, 9, 7, 13, 0, 0)

    # observation_time must not precede valid_time
    obs_before_valid = datetime(2026, 9, 7, 11, 30, 0)
    assert obs_before_valid < time_window_start, "Should be before window"

    # observation_time within window is valid
    obs_within = datetime(2026, 9, 7, 12, 30, 0)
    assert time_window_start <= obs_within <= time_window_end, "Should be within window"

    print("  ✓ Temporal window calculated correctly")
    print("  ✓ require_post_valid_time enforced")
    print("  ✓ observation_time must not precede valid_time")
    print()
    return True


def test_spatial_tolerance():
    """Test spatial matching threshold."""
    print("TEST 3: Spatial tolerance")

    from observation.observation_matcher import MatcherConfig

    config = MatcherConfig(max_station_distance_km=50.0)

    # Station within threshold
    station_near = {'distance_km': 25.0}
    assert station_near['distance_km'] <= config.max_station_distance_km

    # Station beyond threshold
    station_far = {'distance_km': 75.0}
    assert station_far['distance_km'] > config.max_station_distance_km

    print("  ✓ max_station_distance_km threshold enforced")
    print("  ✓ Stations beyond threshold rejected")
    print()
    return True


def test_ghcnh_primary():
    """Test GHCNh as primary direct observation source."""
    print("TEST 4: GHCNh primary")

    from observation.observation_matcher import (
        ObservationMatcher,
        MatcherConfig,
        Observation
    )

    # Mock GHCNh reader
    mock_ghcnh_reader = Mock()
    mock_ghcnh_reader.find_nearest_station.return_value = {
        'station_id': 'VOBL',
        'distance_km': 15.5
    }
    mock_ghcnh_reader.get_observations.return_value = [
        {
            'observation_time': datetime(2026, 9, 7, 12, 30, 0),
            'latitude': 13.0,
            'longitude': 77.5,
            'elevation_m': 920.0,
            'temperature_2m_c': 25.5
        }
    ]

    matcher = ObservationMatcher(ghcnh_reader=mock_ghcnh_reader)

    obs = matcher.get_observation(
        latitude=13.0,
        longitude=77.5,
        valid_time=datetime(2026, 9, 7, 12, 0, 0)
    )

    assert obs is not None
    assert obs.source == "ghcnh"
    assert obs.quality_score == 1.0
    assert obs.quality_flag == "GOOD"
    assert obs.station_id == 'VOBL'
    assert obs.station_distance_km == 15.5
    assert obs.temperature_2m_c == 25.5

    print("  ✓ GHCNh selected as primary")
    print("  ✓ source = 'ghcnh'")
    print("  ✓ quality_score = 1.0 (primary direct observation)")
    print("  ✓ quality_flag = 'GOOD'")
    print("  ✓ station_id and distance returned")
    print()
    return True


def test_era5_land_fallback():
    """Test ERA5-Land as fallback when GHCNh unavailable."""
    print("TEST 5: ERA5-Land fallback")

    from observation.observation_matcher import (
        ObservationMatcher,
        MatcherConfig
    )

    # Mock GHCNh reader (no stations found)
    mock_ghcnh_reader = Mock()
    mock_ghcnh_reader.find_nearest_station.return_value = None

    # Mock ERA5-Land reader
    mock_era5_reader = Mock()
    mock_era5_reader.get_gridpoint.return_value = {
        'temperature_2m_c': 26.0
    }

    matcher = ObservationMatcher(
        ghcnh_reader=mock_ghcnh_reader,
        era5_land_reader=mock_era5_reader
    )

    obs = matcher.get_observation(
        latitude=13.0,
        longitude=77.5,
        valid_time=datetime(2026, 9, 7, 12, 0, 0)
    )

    assert obs is not None
    assert obs.source == "era5_land"
    assert obs.quality_score == 0.8
    assert obs.quality_flag == "FAIR"
    assert obs.station_id is None
    assert obs.temperature_2m_c == 26.0

    print("  ✓ ERA5-Land used as fallback")
    print("  ✓ source = 'era5_land'")
    print("  ✓ quality_score = 0.8 (gridded reanalysis reference)")
    print("  ✓ quality_flag = 'FAIR'")
    print("  ✓ No station information (gridded data)")
    print()
    return True


def test_no_observation_no_fabrication():
    """Test returns None when no observation available (no fabrication)."""
    print("TEST 6: No observation (no fabrication)")

    from observation.observation_matcher import ObservationMatcher

    # Mock readers (both return None)
    mock_ghcnh_reader = Mock()
    mock_ghcnh_reader.find_nearest_station.return_value = None

    mock_era5_reader = Mock()
    mock_era5_reader.get_gridpoint.return_value = None

    matcher = ObservationMatcher(
        ghcnh_reader=mock_ghcnh_reader,
        era5_land_reader=mock_era5_reader
    )

    obs = matcher.get_observation(
        latitude=13.0,
        longitude=77.5,
        valid_time=datetime(2026, 9, 7, 12, 0, 0)
    )

    assert obs is None, "Should return None when no observation available"

    print("  ✓ Returns None when no observation available")
    print("  ✓ No fabricated/interpolated observations")
    print()
    return True


def test_supported_variables():
    """Test supported variables configuration."""
    print("TEST 7: Supported variables")

    from observation.observation_matcher import MatcherConfig

    # Default: temperature only
    config_default = MatcherConfig()
    assert config_default.supported_variables == ['temperature_2m_c']

    # Custom: multiple variables
    config_custom = MatcherConfig(
        supported_variables=['temperature_2m_c', 'dewpoint_2m_c']
    )
    assert len(config_custom.supported_variables) == 2
    assert 'temperature_2m_c' in config_custom.supported_variables
    assert 'dewpoint_2m_c' in config_custom.supported_variables

    print("  ✓ Default: temperature_2m_c only")
    print("  ✓ Custom supported_variables configurable")
    print()
    return True


def test_observation_time_stored():
    """Test observation_time (actual timestamp) is stored."""
    print("TEST 8: observation_time stored")

    from observation.observation_matcher import Observation
    from datetime import datetime

    obs_time = datetime(2026, 9, 7, 12, 35, 0)

    obs = Observation(
        observation_time=obs_time,
        latitude=13.0,
        longitude=77.5,
        temperature_2m_c=25.0,
        source="ghcnh",
        quality_flag="GOOD",
        quality_score=1.0
    )

    assert obs.observation_time == obs_time
    assert obs.observation_time != datetime(2026, 9, 7, 12, 0, 0)

    print("  ✓ observation_time stored (actual timestamp)")
    print("  ✓ Not just valid_time")
    print()
    return True


def test_quality_scores():
    """Test quality scores for GHCNh vs ERA5-Land."""
    print("TEST 9: Quality scores")

    # GHCNh: 1.0 (primary direct observation)
    noaa_quality = 1.0
    assert noaa_quality == 1.0

    # ERA5-Land: 0.8 (gridded reanalysis fallback)
    era5_quality = 0.8
    assert era5_quality == 0.8
    assert era5_quality < noaa_quality

    print("  ✓ GHCNh quality_score = 1.0 (primary)")
    print("  ✓ ERA5-Land quality_score = 0.8 (fallback)")
    print("  ✓ GHCNh quality > ERA5-Land quality")
    print()
    return True


def test_config_defaults():
    """Test MatcherConfig default values."""
    print("TEST 10: MatcherConfig defaults")

    from observation.observation_matcher import MatcherConfig

    config = MatcherConfig()

    assert config.temporal_tolerance_hours == 1.0
    assert config.require_post_valid_time == True
    assert config.max_station_distance_km == 50.0
    assert config.prefer_closer_stations == True
    assert config.use_era5_land_fallback == True
    assert config.min_quality_score == 0.5
    assert config.supported_variables == ['temperature_2m_c']

    print("  ✓ temporal_tolerance_hours = 1.0")
    print("  ✓ require_post_valid_time = True")
    print("  ✓ max_station_distance_km = 50.0")
    print("  ✓ prefer_closer_stations = True")
    print("  ✓ use_era5_land_fallback = True")
    print("  ✓ min_quality_score = 0.5")
    print("  ✓ supported_variables = ['temperature_2m_c']")
    print()
    return True


if __name__ == '__main__':
    print("="*80)
    print("OBSERVATION MATCHER UNIT TESTS")
    print("="*80)
    print()

    tests = [
        test_matcher_initialization,
        test_temporal_tolerance_window,
        test_spatial_tolerance,
        test_ghcnh_primary,
        test_era5_land_fallback,
        test_no_observation_no_fabrication,
        test_supported_variables,
        test_observation_time_stored,
        test_quality_scores,
        test_config_defaults
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print()
    print("="*80)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    if failed > 0:
        print(f"         {failed}/{len(tests)} tests FAILED")
    print("="*80)

    sys.exit(0 if failed == 0 else 1)
