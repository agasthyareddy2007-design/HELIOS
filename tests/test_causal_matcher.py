import pytest
from datetime import datetime, timedelta
from typing import Optional, List

from observation.observation_matcher import (
    ObservationMatcher, MatcherConfig, Observation
)

# Mock readers to provide distinct controlled inputs
class MockGHCNhReader:
    def __init__(self, obs_list):
        self.obs_list = obs_list
    def find_nearest_station(self, latitude, longitude, max_distance_km):
        return {"station_id": "MOCK", "distance_km": 1.0, "latitude": latitude, "longitude": longitude, "elevation_m": 0, "name": "Mock"}
    def get_observations(self, station_id, time_start, time_end, variables):
        ret = []
        for obs in self.obs_list:
            if time_start <= obs['observation_time'] <= time_end:
                obs_copy = obs.copy(); obs_copy.update({'latitude': 10.0, 'longitude': 70.0, 'elevation_m': 0.0}); ret.append(obs_copy)
        return ret


class MockERA5LandReader:
    def __init__(self, hourly_obs_dict):
        self.hourly_obs_dict = hourly_obs_dict
    def get_gridpoint(self, latitude, longitude, time, variables):
        if time in self.hourly_obs_dict:
            return self.hourly_obs_dict[time]
        return None

vt = datetime(2026, 6, 17, 12, 0, 0)
lat, lon = 10.0, 70.0

@pytest.fixture
def make_matcher():
    def _make(ghcnh_obs, era5_obs=None):
        ghcnh = MockGHCNhReader(ghcnh_obs)
        era5 = MockERA5LandReader(era5_obs or {})
        config = MatcherConfig(causal_matching=True, temporal_tolerance_hours=2.0)
        return ObservationMatcher(config, ghcnh_reader=ghcnh, era5_land_reader=era5)
    return _make

def test_case_1_exact_match(make_matcher):
    obs = [{'observation_time': vt, 'temperature_2m_c': 20.0}]
    matcher = make_matcher(obs)
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is not None
    assert res.observation_time == vt
    assert res.temperature_2m_c == 20.0

def test_case_2_within_tolerance(make_matcher):
    t_1130 = vt - timedelta(minutes=30)
    obs = [{'observation_time': t_1130, 'temperature_2m_c': 21.0}]
    matcher = make_matcher(obs)
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is not None
    assert res.observation_time == t_1130

def test_case_3_future_reject(make_matcher):
    t_1300 = vt + timedelta(hours=1)
    obs = [{'observation_time': t_1300, 'temperature_2m_c': 22.0}]
    matcher = make_matcher(obs)
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is None  # Era5 dict empty, GHCNh rejected

def test_case_4_past_over_future(make_matcher):
    t_1100 = vt - timedelta(hours=1)
    t_1300 = vt + timedelta(hours=1)
    obs = [
        {'observation_time': t_1100, 'temperature_2m_c': 23.0},
        {'observation_time': t_1300, 'temperature_2m_c': 24.0}
    ]
    matcher = make_matcher(obs)
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is not None
    assert res.observation_time == t_1100
    assert res.temperature_2m_c == 23.0

def test_case_5_no_valid(make_matcher):
    matcher = make_matcher([])
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is None

def test_case_6_tie_deterministic(make_matcher):
    # Two valid observations within the negative tolerance
    # Let's say one at 10:00 (distance 2h) and one at 11:30 (dist 0.5h).
    # Since closest to target_time is required, 11:30 should win.
    t_1 = vt - timedelta(hours=2)
    t_2 = vt - timedelta(minutes=30)
    obs = [
        {'observation_time': t_1, 'temperature_2m_c': 10.0},
        {'observation_time': t_2, 'temperature_2m_c': 15.0} # This one should be selected
    ]
    matcher = make_matcher(obs)
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is not None
    assert res.observation_time == t_2
    
def test_case_6b_tie_exact_distance(make_matcher):
    # Tie break mechanism (can only happen if two stations or same timestamp?
    # but we only have 1 station mock. We can inject two obs at same timestamp)
    t = vt - timedelta(hours=1)
    obs = [
        {'observation_time': t, 'temperature_2m_c': 99.0}, # first in list
        {'observation_time': t, 'temperature_2m_c': 88.0}
    ]
    matcher = make_matcher(obs)
    res = matcher.get_observation(lat, lon, vt, ["temperature_2m_c"])
    assert res is not None
    assert res.observation_time == t
    # Min function is stable, so first element wins
    assert res.temperature_2m_c == 99.0

def test_era5_land_causal():
    config = MatcherConfig(causal_matching=True, temporal_tolerance_hours=1.0)
    # ERA5 uses hourly exactly.
    # Target 12:30. Window: 11:30 -> 12:30
    # Available are 11:00, 12:00, 13:00.
    v_time = datetime(2026, 6, 17, 12, 30, 0)
    e_obs = {
        datetime(2026, 6, 17, 11, 0, 0): {'temperature_2m_c': 11.0},
        datetime(2026, 6, 17, 12, 0, 0): {'temperature_2m_c': 12.0},
        datetime(2026, 6, 17, 13, 0, 0): {'temperature_2m_c': 13.0},
    }
    ghcnh = MockGHCNhReader([])
    era5 = MockERA5LandReader(e_obs)
    matcher = ObservationMatcher(config, ghcnh_reader=ghcnh, era5_land_reader=era5)
    
    # 13:00 is technically closest to 12:30 (0.5 hr dist) but it's AFTER target_time, 
    # so it should be rejected. The causal bounds for tolerance=1h are [11:30, 12:30].
    # So 12:00 is the only valid hour.
    res = matcher.get_observation(lat, lon, v_time, ["temperature_2m_c"])
    assert res is not None
    assert res.observation_time == datetime(2026, 6, 17, 12, 0, 0)
    
