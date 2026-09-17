import unittest
from datetime import datetime
from observation.era5_land_reader import ERA5LandReader

class TestERA5LandReader(unittest.TestCase):
    def setUp(self):
        # We assume the default path has the valid data we just downloaded
        self.reader = ERA5LandReader()
        
    def test_reader_initialization(self):
        self.assertIsNotNone(self.reader.ds)
        self.assertIn('t2m', self.reader.ds.data_vars)
        self.assertIn('d2m', self.reader.ds.data_vars)
        
    def test_first_timestamp(self):
        result = self.reader.get_gridpoint(
            latitude=20.0, 
            longitude=80.0, 
            time=datetime(2026, 3, 12, 0, 0), 
            variables=['temperature_2m_c', 'dewpoint_2m_c']
        )
        self.assertIsNotNone(result)
        self.assertIn('temperature_2m_c', result)
        self.assertIn('dewpoint_2m_c', result)
        # Should be reasonable Temps (Celsius)
        self.assertTrue(-50 < result['temperature_2m_c'] < 60)
        
    def test_missing_out_of_bounds_time(self):
        result = self.reader.get_gridpoint(
            latitude=20.0, 
            longitude=80.0, 
            time=datetime(2025, 3, 12, 0, 0), # 2025 is out of bounds
            variables=['temperature_2m_c']
        )
        self.assertIsNone(result)
        
    def test_missing_out_of_bounds_spatial(self):
        result = self.reader.get_gridpoint(
            latitude=50.0, # Box max lat is 38
            longitude=80.0, 
            time=datetime(2026, 5, 12, 12, 0), 
            variables=['temperature_2m_c']
        )
        self.assertIsNone(result)
        
    def test_nan_ocean_handing(self):
        # Coordinates in Arabian Sea (lat 15, lon 70) => should be NaN for ERA5-Land
        result = self.reader.get_gridpoint(
            latitude=15.0, 
            longitude=70.0, 
            time=datetime(2026, 4, 15, 10, 0), 
            variables=['temperature_2m_c']
        )
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
