from __future__ import annotations
import sys
import os
from pathlib import Path
import pickle
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_manager
from ml.dataset_builder import DatasetBuilder, BuildConfig, lead_time_group
from ml.feature_builder import FeatureBuilder
from ml.feature_contract import FeatureVector

class HeliosV2Service:
    def __init__(self):
        self.artifact_path = PROJECT_ROOT / "ml" / "artifacts" / "lockedtest_v2_20260915_184718" / "model_xgboost_v2.pkl"
        self.xgb_cand = None
        self.db = get_db_manager()
        self.builder = DatasetBuilder(self.db)
        self.feature_builder = FeatureBuilder()
        self.config = BuildConfig(variable="temperature_2m_c")

    def _load_model(self):
        if self.xgb_cand is None:
            if not self.artifact_path.exists():
                raise FileNotFoundError(f"Missing V2 artifact at {self.artifact_path}")
            with open(self.artifact_path, "rb") as f:
                self.xgb_cand = pickle.load(f)

    def force_load(self):
        """Forces the loading of the model to keep memory prepared."""
        self._load_model()

    def forecast(
        self,
        issue_time: datetime,
        valid_time: datetime,
        latitude: float,
        longitude: float,
        location_zone: str | None,
        forecasts: dict[str, float],
        include_arena: bool = False
    ) -> dict:
        self._load_model()
        
        # 1. Compute historical reliability features for this context
        lead_time_hours = int((valid_time - issue_time).total_seconds() / 3600)
        
        historical_dict = {}
        target_models = ['gfs', 'ifs', 'icon']
        for m in target_models:
            lead_group = lead_time_group(max(0, lead_time_hours))
            hr = self.builder._historical_reliability(
                model=m,
                variable="temperature_2m_c",
                issue_time=issue_time,
                lead_group=lead_group,
                zone=location_zone,
                config=self.config
            )
            if hr is not None:
                historical_dict[m] = hr
        
        # 2. Build feature vector (Canonical V2 Protocol)
        fv = self.feature_builder.build_feature_vector(
            target_model='blend',  
            issue_time=issue_time,
            valid_time=valid_time,
            location=(latitude, longitude),
            location_zone=location_zone,
            variable="temperature_2m_c",
            forecasts=forecasts,
            historical_reliability=historical_dict
        )
        
        # 3. Predict expected errors and compute inverse-error weights
        weights_pred = self.xgb_cand.get_weights(features=fv, models=list(forecasts.keys()))
        weights_dict = {"gfs": weights_pred.gfs_weight, "ifs": weights_pred.ifs_weight, "icon": weights_pred.icon_weight}
        
        # 4. Enforce V2 blending math: blend = sum(weight_i * forecast_i) (weights are already 0-1 and sum to 1 in get_weights)
        blended_value = 0.0
        active_models = 0
        for m, w in weights_dict.items():
            if m in forecasts and forecasts[m] is not None:
                blended_value += w * forecasts[m]
                active_models += 1
                
        if active_models == 0:
            # Fallback if no valid model data
            blended_value = None

        # Format output mirroring V1 API for frontend compatibility
        result = {
            "issue_time": issue_time.isoformat() + "Z",
            "valid_time": valid_time.isoformat() + "Z",
            "lead_time_hours": lead_time_hours,
            "variable": "temperature_2m_c",
            "helios_forecast": round(blended_value, 2) if blended_value is not None else None,
            "nwp_forecasts": {m: round(v, 2) for m, v in forecasts.items() if v is not None},
            "model_weights": {m: round(w, 4) for m, w in weights_dict.items() if w > 0.0},
            "reliability_metrics": {
                m: {
                    "expected_absolute_error": round(rp.expected_absolute_error, 3) 
                }
                for m, rp in {"gfs": weights_pred.gfs_reliability, "ifs": weights_pred.ifs_reliability, "icon": weights_pred.icon_reliability}.items()
            }
        }
        
        if include_arena:
            # Arena returns the unweighted raw variants to show convergence
            result["arena"] = {
                "gfs": round(forecasts.get('gfs'), 2) if forecasts.get('gfs') is not None else None,
                "ifs": round(forecasts.get('ifs'), 2) if forecasts.get('ifs') is not None else None,
                "icon": round(forecasts.get('icon'), 2) if forecasts.get('icon') is not None else None,
                "simple_average": round(sum(v for v in forecasts.values() if v is not None) / active_models, 2) if active_models > 0 else None,
            }
            
        return result

    def health(self) -> dict:
        self.force_load()
        return {
            "status": "ok",
            "strategy": "XGBoost",
            "generation": "v2",
            "models_loaded": ["gfs", "ifs", "icon"],
            "artifact": self.artifact_path.name
        }

    def models(self) -> dict:
        return {
            "strategy": "XGBoost",
            "generation": "v1->v2_migrated",
            "supported_variable": "temperature_2m_c"
        }

    def evaluation(self) -> dict:
        # V2 locked test report
        report_path = self.artifact_path.parent / "locked_test_report.json"
        if report_path.exists():
            import json
            with open(report_path, "r") as f:
                return json.load(f)
        return {"error": "Locked test report not found"}

    def model_arena(self) -> dict:
        # Historic evaluation endpoint mirroring V1 structure but passing V2 locked test logic
        rep = self.evaluation()
        res = rep.get("results", {})
        return {
            "winner": "HELIOS V2 (XGBoost)",
            "benchmark_period": rep.get("train_bounds", [None, ""])[1] or "2026-06-07T00:00:00",
            "competitors": {
                "helios_v2": {"mae": res.get("mae"), "rmse": res.get("rmse")},
                "stat_avg": {"mae": res.get("sa_mae"), "rmse": res.get("sa_rmse")},
                "ifs": {"mae": res.get("ifs_mae"), "rmse": res.get("ifs_rmse")},
                "icon": {"mae": res.get("icon_mae"), "rmse": res.get("icon_rmse")},
                "gfs": {"mae": res.get("gfs_mae"), "rmse": res.get("gfs_rmse")}
            }
        }
