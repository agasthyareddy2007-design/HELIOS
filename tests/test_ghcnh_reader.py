import unittest
from datetime import datetime, timezone
import pandas as pd
from observation.ghcnh_reader import GHCNhReader
from pathlib import Path

class TestGHCNhReader(unittest.TestCase):
    def setUp(self):
        # We rely on the existing downloaded file for the test:
        # /home/agasthya/HELIOS/data/raw/ghcnh_2026/GHCNh_INI0000VABB_2026.psv
        self.reader = GHCNhReader(year=2026)

    def test_station_list_parsing(self):
        self.assertGreater(self.reader.n_stations, 0)
        # Should contain Mumbai airport
        self.assertIn("INI0000VABB", self.reader._stations)

    def test_station_lookup(self):
        # Coordinates near Mumbai
        st = self.reader.find_nearest_station(19.0887, 72.8679,  50.0)
        self.assertIsNotNone(st)
        self.assertEqual(st["station_id"], "INI0000VABB")
        self.assertLess(st["distance_km"], 50.0)

    def test_psv_parsing_and_temporal_filtering(self):
        # The V2 window
        start = datetime(2026, 3, 12, 0, 0)
        end = datetime(2026, 6, 17, 23, 59)
        obs = self.reader.get_observations(
            "INI0000VABB", 
            start, 
            end, 
            variables=["temperature_2m_c", "dewpoint_2m_c", "wind_speed", "wind_u_10m_ms", "pressure_msl_hpa"]
        )
        self.assertGreater(len(obs), 4000)
        
        # Test basic conversion and units extracted correctly natively
        for o in obs:
            self.assertIn("temperature_2m_c", o)
            self.assertIn("observation_time", o)
            self.assertTrue(10.0 < o["temperature_2m_c"] < 50.0) # Reasonable Mumbai temp

            if o.get("wind_u_10m_ms") is not None:
                # Wind u should be derived correctly
                self.assertTrue(-100 < o["wind_u_10m_ms"] < 100)
            break

    def test_missing_values(self):
        # Time with likely empty observations or file not downloaded for this station
        obs = self.reader.get_observations(
            "INI_FAKE_ID", 
            datetime(2026,1,1), 
            datetime(2026,1,2), 
            ["temperature_2m_c"]
        )
        self.assertEqual(len(obs), 0)

if __name__ == '__main__':
    unittest.main()
