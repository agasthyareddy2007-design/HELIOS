from datetime import datetime
from observation.observation_matcher import ObservationMatcher, MatcherConfig
import logging

logging.basicConfig(level=logging.INFO)

def test():
    # Make sure we use ERA5 Land as fallback
    config = MatcherConfig(use_era5_land_fallback=True)
    matcher = ObservationMatcher(config=config)
    
    # Use spatial/temporal coordinates that exist in ERA5 but have no NOAA obs
    time = datetime(2026, 4, 1, 12, 0, 0)
    obs = matcher.get_observation(latitude=20.0, longitude=80.0, valid_time=time)
    
    assert obs is not None
    assert obs.source == "era5_land"
    assert obs.temperature_2m_c is not None
    print(f"Integration successfully retrieved obs: temp={obs.temperature_2m_c:.2f} C at {obs.observation_time}")

if __name__ == "__main__":
    test()
