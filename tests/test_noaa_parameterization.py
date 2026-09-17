import unittest
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.acquire_noaa_observational_data import NOAAObservationalAcquisition
from observation.noaa_isd_reader import NOAAISDLiteReader

class TestNOAAParameterization(unittest.TestCase):
    def test_acquire_init_2025(self):
        acq = NOAAObservationalAcquisition("/tmp", year=2025)
        self.assertEqual(acq.isd_base_url, "https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/2025")
        self.assertEqual(acq.isd_dir.name, "noaa_isd_2025")

    def test_acquire_init_2026(self):
        acq = NOAAObservationalAcquisition("/tmp", year=2026)
        self.assertEqual(acq.isd_base_url, "https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/2026")
        self.assertEqual(acq.isd_dir.name, "noaa_isd_2026")

    def test_reader_init_2025(self):
        reader = NOAAISDLiteReader(year=2025)
        self.assertEqual(reader.isd_dir.name, "noaa_isd_2025")

    def test_reader_init_2026(self):
        reader = NOAAISDLiteReader(year=2026)
        self.assertEqual(reader.isd_dir.name, "noaa_isd_2026")
        
    def test_existing_2025_reader(self):
        # We know 2025 data is already downloaded! 
        # Verify reader can actually see the stations without breaking.
        reader = NOAAISDLiteReader(year=2025)
        self.assertTrue(reader.n_stations > 0)

if __name__ == "__main__":
    unittest.main()
