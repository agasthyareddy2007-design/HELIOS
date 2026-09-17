import sys, time, gc
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path('/home/agasthya/HELIOS')
sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_db_manager
from ml.dataset_builder import DatasetBuilder, BuildConfig

def time_stream():
    db = get_db_manager()
    builder = DatasetBuilder(db)
    config = BuildConfig(variable="temperature_2m_c", models=("gfs", "ifs", "icon"))
    
    start = datetime(2026, 3, 12, 0)
    end = datetime(2026, 5, 28, 12)
    
    t0 = time.time()
    count = 0
    gen = builder.stream_training_samples(config, start_issue=start, end_issue=end, chunk_size=20000)
    
    try:
        for i, chunk in enumerate(gen):
            count += len(chunk)
            if i % 5 == 0:
                print(f"Chunk {i}, accumulated {count} samples in {time.time()-t0:.1f}s")
            if i >= 10:
                break
    except KeyboardInterrupt:
        pass
        
    print(f"Read {count} samples in {time.time()-t0:.1f}s")

if __name__ == "__main__":
    time_stream()
