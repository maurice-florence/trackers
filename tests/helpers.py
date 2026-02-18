import json
import zipfile
from pathlib import Path
import io
import pandas as pd


def create_sample_takeout_zip(target_path: Path, name: str, heart_records=2, step_records=2, include_daily_csv=False):
    """Create a small Takeout-like zip at `target_path/name`.

    heart_records: number of heart JSON points (dateTime and bpm)
    step_records: number of steps points
    """
    target_path.mkdir(parents=True, exist_ok=True)
    zip_path = target_path / name
    hr_list = []
    steps_list = []
    # simple incremental datetimes
    base_date = '2023-01-01'
    for i in range(heart_records):
        hr_list.append({'dateTime': f"{base_date}T0{i}:00:00", 'bpm': 60 + i})
    for i in range(step_records):
        steps_list.append({'dateTime': f"{base_date}T0{i}:00:00", 'value': 100 + i})

    with zipfile.ZipFile(zip_path, 'w') as zf:
        # write heart_rate-1.json
        hr_bytes = json.dumps(hr_list).encode('utf-8')
        zf.writestr('heart_rate-2023-01-01.json', hr_bytes)
        st_bytes = json.dumps(steps_list).encode('utf-8')
        zf.writestr('steps-2023-01-01.json', st_bytes)
        if include_daily_csv:
            df = pd.DataFrame([{'date': base_date, 'steps': sum([s['value'] for s in steps_list])}])
            csv_bytes = df.to_csv(index=False).encode('utf-8')
            zf.writestr('Daily Activity.csv', csv_bytes)
    return zip_path
