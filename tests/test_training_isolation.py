"""
HELIOS Training TEST-Isolation Tests

Synthetic-fixture tests proving the full-V1 training runner never uses the TEST
split for fitting, preprocessing, early stopping, or model/config selection, and
that the training configuration contains no TEST-derived information.

Coverage:
1.  TEST verification_ids never passed to any candidate.train()
2.  TEST verification_ids never passed to preprocessing.fit()
3.  Early stopping receives VALIDATION only (never TEST) for XGBoost/MLP
4.  Training configuration contains no TEST-specific information
5.  Runner report exposes TEST as counts only (no TEST-derived metrics)
6.  DatasetBuilder chronological split behavior unchanged (train<val<test)
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np

from database.connection import DatabaseManager, DatabaseConfig
from database.schema.helios_schema import ForecastVerification
from ml.feature_contract import FeatureContract
from ml.preprocessing import FeaturePreprocessor
from ml.training_config import default_full_v1_config, FullV1TrainingConfig
from ml.dataset_builder import DatasetBuilder, BuildConfig, DatasetSplitConfig
import scripts.run_v1_training as runner


def _verif(vid, model, issue, valid, lead, lat, lon, zone, fv, obs):
    err = fv - obs
    return ForecastVerification(
        verification_id=vid, forecast_id=f"fc_{vid}", model=model,
        issue_time=issue, valid_time=valid, lead_time_hours=lead,
        latitude=lat, longitude=lon, location_zone=zone, variable="temperature_2m_c",
        forecast_value=fv, observed_value=obs, observation_source="noaa_isd",
        observation_quality_score=1.0, observation_time=valid,
        error=err, absolute_error=abs(err), squared_error=err * err,
        verification_time=valid + timedelta(hours=1),
    )


def _seed_file_db():
    """Seed a small IFS-only file DB inside HELIOS; return path."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(prefix="helios_iso_", suffix=".db",
                                      dir=str(project_root / "data"), delete=False)
    tmp.close()
    db = DatabaseManager(DatabaseConfig(database_url=f"sqlite:///{tmp.name}"))
    db.initialize(create_tables=True)
    rows = []
    base = datetime(2025, 1, 1)
    rng = np.random.RandomState(0)
    for d in range(20):            # 20 cycles => chronological split has all 3 parts
        issue = base + timedelta(days=d)
        for p in range(30):
            valid = issue + timedelta(hours=24)
            rows.append(_verif(f"ifs_{d:02d}_{p:03d}", "ifs", issue, valid, 24,
                               20 + (p % 6) * 0.5, 78 + (p // 6) * 0.5,
                               ["central", "north_plains", "south_coastal",
                                "south_plateau", "north_himalaya"][p % 5],
                               25 + rng.randn(), 24 + rng.randn()))
    with db.get_session() as s:
        for r in rows:
            s.add(r)
    db.close()
    return tmp.name


def _get_split(db_path):
    config = default_full_v1_config()
    db, split = runner.load_split(config, db_path)
    db.close()
    return config, split


def test_config_has_no_test_information():
    """TEST: full-V1 config contains no TEST-specific fields/values."""
    print("TEST: training config has no TEST information")
    cfg = default_full_v1_config().to_dict()
    flat = str(cfg).lower()
    # No 'test' key/field anywhere in the config bundle.
    assert "test" not in flat, f"unexpected 'test' reference in config: {cfg}"
    # Only train/validation fractions present.
    assert "train_fraction" in cfg["dataset"] and "validation_fraction" in cfg["dataset"]
    assert "test_fraction" not in cfg["dataset"]
    print("  ✓ no TEST-specific info in config")
    print()
    return True


def test_dataset_builder_split_unchanged():
    """TEST: DatasetBuilder still yields chronological train<val<test."""
    print("TEST: DatasetBuilder chronological split unchanged")
    path = _seed_file_db()
    try:
        _, split = _get_split(path)
        assert len(split.train) > 0 and len(split.validation) > 0 and len(split.test) > 0
        tr = [s.features.issue_time for s in split.train]
        va = [s.features.issue_time for s in split.validation]
        te = [s.features.issue_time for s in split.test]
        assert max(tr) < min(va) < max(va) < min(te)
        assert split.statistics.leakage_violations == 0
    finally:
        import os
        os.unlink(path)
    print("  ✓ train<val<test; no leakage violations")
    print()
    return True


def test_test_never_reaches_fit_or_preprocessing_or_early_stopping():
    """
    TEST: instrument candidate.train and preprocessing.fit to capture every
    verification_id they receive; assert NO TEST id ever appears (fit, early
    stopping eval_set, etc.).
    """
    print("TEST: TEST never reaches fit / preprocessing.fit / early stopping")
    path = _seed_file_db()
    try:
        config, split = _get_split(path)
        test_ids = {s.verification_id for s in split.test}
        assert test_ids, "expected a non-empty TEST split"

        seen_train_ids = set()
        seen_val_ids = set()
        seen_fit_ids = set()

        # Instrument preprocessing.fit to record which sample ids it sees.
        orig_fit = FeaturePreprocessor.fit
        def spy_fit(self, samples):
            for s in samples:
                seen_fit_ids.add(s.verification_id)
            return orig_fit(self, samples)
        FeaturePreprocessor.fit = spy_fit

        # Instrument each candidate's train() to record train + validation ids.
        from ml.kernel_candidate import KernelRegressionCandidate
        from ml.xgboost_candidate import XGBoostCandidate
        from ml.mlp_candidate import MLPCandidate

        originals = {}
        for cls in (KernelRegressionCandidate, XGBoostCandidate, MLPCandidate):
            originals[cls] = cls.train
            def make_spy(orig):
                def spy_train(self, training_samples, validation_samples=None):
                    for s in training_samples:
                        seen_train_ids.add(s.verification_id)
                    if validation_samples:
                        for s in validation_samples:
                            seen_val_ids.add(s.verification_id)
                    return orig(self, training_samples, validation_samples)
                return spy_train
            cls.train = make_spy(originals[cls])

        try:
            # Tiny runner-validation fit (bounded); still must never touch TEST.
            report = runner.run(mode="runner-validation", db_path=path,
                                config=config, runner_validation_limit=200)
        finally:
            FeaturePreprocessor.fit = orig_fit
            for cls, fn in originals.items():
                cls.train = fn

        # No TEST ids anywhere in fit / train / validation streams.
        assert seen_fit_ids.isdisjoint(test_ids), "TEST id reached preprocessing.fit!"
        assert seen_train_ids.isdisjoint(test_ids), "TEST id reached candidate.train!"
        assert seen_val_ids.isdisjoint(test_ids), "TEST id reached early-stopping validation!"
        # fit ids are a subset of train ids (preprocessing fit on TRAIN only).
        assert seen_fit_ids.issubset(seen_train_ids), "preprocessing saw non-train ids"
        # Sanity: we actually exercised training.
        assert seen_train_ids and seen_val_ids
        # All candidates ran ok.
        for c in report["training"]["candidates"]:
            assert c["ok"], f"{c['name']} failed: {c.get('error')}"
    finally:
        import os
        os.unlink(path)
    print("  ✓ no TEST id in fit/train/validation; preprocessing fit ⊆ train")
    print()
    return True


def test_runner_report_exposes_test_as_counts_only():
    """TEST: runner report gives TEST as a count only (no TEST-derived metrics)."""
    print("TEST: runner exposes TEST as counts only")
    path = _seed_file_db()
    try:
        config, _ = _get_split(path)
        report = runner.run(mode="runner-validation", db_path=path,
                            config=config, runner_validation_limit=200)
        plan = report["plan"]
        assert "test" in plan["row_counts"] and plan["row_counts"]["test"] > 0
        # Training block reports train/validation only; no 'test' metric keys.
        tr = report["training"]
        assert "test" not in {k.lower() for k in tr.keys()}
        for c in tr["candidates"]:
            met = c.get("metrics", {})
            assert not any("test" in k.lower() for k in met.keys()), \
                f"TEST-derived metric found in {c['name']}"
        assert "counts only" in plan["test_usage"].lower()
    finally:
        import os
        os.unlink(path)
    print("  ✓ TEST appears only as a count; no TEST-derived metrics")
    print()
    return True
