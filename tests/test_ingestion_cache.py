import os
import shutil
from pathlib import Path
import pandas as pd
from src.ingestion import FitbitLoader
from tests.helpers import create_sample_takeout_zip


def test_incremental_zip_processing(tmp_path, monkeypatch):
    # setup workspace
    data_dir = tmp_path / 'takeout'
    data_dir.mkdir()

    # Patch Path.cwd() to return tmp_path so cache is isolated
    monkeypatch.setattr('pathlib.Path.cwd', lambda: tmp_path)

    # create two zips
    zip1 = create_sample_takeout_zip(data_dir, 'takeout1.zip', heart_records=2, step_records=2, include_daily_csv=True)
    zip2 = create_sample_takeout_zip(data_dir, 'takeout2.zip', heart_records=3, step_records=1, include_daily_csv=False)

    loader = FitbitLoader(str(data_dir))

    progress = []

    def cb(src, msg):
        progress.append((src, msg))

    res1 = loader.process_all(progress_callback=cb)

    # caches should exist
    hr_cache = loader._cache_file('heart_rate')
    steps_cache = loader._cache_file('steps')
    daily_cache = loader._cache_file('daily')

    assert hr_cache.exists()
    assert steps_cache.exists()
    assert daily_cache.exists()

    hr_df = pd.read_parquet(hr_cache)
    steps_df = pd.read_parquet(steps_cache)
    daily_df = pd.read_parquet(daily_cache)

    # expected counts: heart 2+3, steps 2+1
    assert len(hr_df) == 5
    assert len(steps_df) == 3
    assert len(daily_df) >= 1

    # processed metadata should include both zips
    meta = loader._load_processed_metadata()
    keys = [k for k in meta.keys() if 'takeout' in k]
    assert len(keys) >= 2

    # create a third zip with additional heart records
    zip3 = create_sample_takeout_zip(data_dir, 'takeout3.zip', heart_records=4, step_records=0, include_daily_csv=False)
    res2 = loader.process_all(progress_callback=cb)

    hr_df2 = pd.read_parquet(hr_cache)
    assert len(hr_df2) >= 9  # 5 + 4

    # progress log should contain entries
    plog = loader.get_progress_log()
    assert len(plog) > 0
