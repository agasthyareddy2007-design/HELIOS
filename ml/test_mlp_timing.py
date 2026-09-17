import sys, time, gc
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path('/home/agasthya/HELIOS')
sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_manager
from ml.dataset_builder import DatasetBuilder, BuildConfig
from ml.mlp_candidate import MLPCandidate, MLPConfig
from ml.feature_contract import FeatureContract

db = get_db_manager()
builder = DatasetBuilder(db)
config = BuildConfig(variable="temperature_2m_c", models=("gfs", "ifs", "icon"))

print("Fetching a couple chunks for MLP test...")
gen = builder.stream_training_samples(config, start_issue=datetime(2026, 3, 12), end_issue=datetime(2026, 3, 20), chunk_size=20000)

mlp_cand = MLPCandidate(feature_contract=FeatureContract(), config=MLPConfig(device="cuda"))
chunk = next(gen)
mlp_cand.preprocessor.fit(chunk)

print("Starting MLP streaming 10 chunks...")
t0 = time.time()
count = 0
for i, chunk in enumerate(gen):
    count += len(chunk)
    # mock stream_train loop body:
    # Just to trace what is actually happening in MLPCandidate.stream_train
    pass
print(f"Loop overhead {time.time()-t0:.1f}s")
