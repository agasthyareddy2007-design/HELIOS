import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.helios_v2_service import HeliosV2Service

def test_helios_v2_model_loading():
    svc = HeliosV2Service()
    svc.force_load()
    assert svc.artifact_path.name == "helios.pkl"
    assert svc.artifact_path.exists()
    health = svc.health()
    assert health["status"] == "ok"
    assert health["strategy"] == "XGBoost"
    assert health["artifact"] == "helios.pkl"
    assert health["generation"] == "v2"
