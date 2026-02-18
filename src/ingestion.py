import os
import fnmatch
import os
import fnmatch
import json
import re
from pathlib import Path
import pandas as pd
from typing import Dict


class FitbitLoader:
    def __init__(self, root_path: str):
        self.root = Path(root_path)

    def _discover_files(self, pattern: str):
        if not self.root.exists():
            return
        for dirpath, _, files in os.walk(self.root):
            for fname in fnmatch.filter(files, pattern):
                yield Path(dirpath) / fname

    def _extract_date_from_filename(self, path: Path):
        m = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
        return m.group(1) if m else None

    def load_heart_rate(self) -> pd.DataFrame:
        rows = []
        for p in self._discover_files('heart_rate-*.json'):
            try:
                with p.open('r', encoding='utf-8') as fh:
                    data = json.load(fh)

                # data may be {'value': [...]} or a list
                entries = None
                if isinstance(data, dict) and 'value' in data:
                    entries = data['value']
                elif isinstance(data, list):
                    entries = data

                base_date = self._extract_date_from_filename(p) or ''
                if entries:
                    for v in entries:
                        # v may contain 'dateTime' or 'time'
                        dt = v.get('dateTime') or v.get('time')
                        bpm = None
                        conf = None
                        if isinstance(v.get('value'), dict):
                            bpm = v['value'].get('bpm')
                            conf = v['value'].get('confidence')
                        else:
                            # sometimes structure is flattened
                            bpm = v.get('bpm') or (v.get('value') if isinstance(v.get('value'), (int, float)) else None)
                            conf = v.get('confidence')

                        if dt and len(dt) <= 8 and base_date:
                            dt = f"{base_date}T{dt}"

                        rows.append({'dateTime': dt, 'bpm': bpm, 'confidence': conf})
            except Exception:
                continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.dropna(subset=['dateTime'])
        try:
            df['dateTime'] = pd.to_datetime(df['dateTime'], errors='coerce')
        except Exception:
            df['dateTime'] = pd.to_datetime(df['dateTime'], errors='coerce')
        df = df.dropna(subset=['dateTime'])
        df = df.set_index('dateTime').sort_index()
        if 'bpm' in df.columns:
            df['bpm'] = pd.to_numeric(df['bpm'], errors='coerce').astype('Int64')
        return df

    def load_steps(self) -> pd.DataFrame:
        rows = []
        for p in self._discover_files('steps-*.json'):
            try:
                with p.open('r', encoding='utf-8') as fh:
                    data = json.load(fh)
                entries = data.get('value') if isinstance(data, dict) else data
                base = self._extract_date_from_filename(p) or ''
                for v in entries or []:
                    dt = v.get('dateTime') or v.get('time')
                    val = v.get('value') or v.get('steps')
                    if dt and len(dt) <= 8 and base:
                        dt = f"{base}T{dt}"
                    rows.append({'dateTime': dt, 'steps': val})
            except Exception:
                continue
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df['dateTime'] = pd.to_datetime(df['dateTime'], errors='coerce')
        df = df.dropna(subset=['dateTime']).set_index('dateTime').sort_index()
        if 'steps' in df.columns:
            df['steps'] = pd.to_numeric(df['steps'], errors='coerce').fillna(0).astype(int)
        return df

    def load_sleep(self) -> pd.DataFrame:
        # Collect sleep sessions from sleep-*.json
        sessions = []
        for p in self._discover_files('sleep-*.json'):
            try:
                with p.open('r', encoding='utf-8') as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    # try to find 'levels' or 'sleep'
                    if 'levels' in data:
                        levels = data['levels']
                        # some exports use 'data' under levels
                        for rec in levels.get('data', []):
                            start = rec.get('dateTime') or rec.get('start')
                            duration = rec.get('seconds') or rec.get('duration')
                            sessions.append({'start': start, 'duration_s': duration, 'level': rec.get('level') or rec.get('stage')})
                    elif 'sleep' in data:
                        for s in data['sleep']:
                            sessions.append({'start': s.get('startTime'), 'duration_s': s.get('durationMillis', 0) / 1000, 'level': None})
            except Exception:
                continue
        if not sessions:
            return pd.DataFrame()
        df = pd.DataFrame(sessions)
        df['start'] = pd.to_datetime(df['start'], errors='coerce')
        df = df.dropna(subset=['start']).sort_values('start')
        return df

    def load_daily_summary(self) -> pd.DataFrame:
        # look for Daily Activity Summary.csv and Sleep Score.csv
        dfs = []
        for dirpath, _, files in os.walk(self.root):
            for fname in files:
                if fname.lower().endswith('.csv') and 'daily activity' in fname.lower():
                    try:
                        p = Path(dirpath) / fname
                        dfs.append(pd.read_csv(p))
                    except Exception:
                        continue
        if not dfs:
            return pd.DataFrame()
        df = pd.concat(dfs, ignore_index=True)
        # try to standardize date column
        for c in df.columns:
            if 'date' in c.lower():
                df[c] = pd.to_datetime(df[c], errors='coerce')
                df = df.set_index(c)
                break
        return df

    def process_all(self) -> Dict[str, pd.DataFrame]:
        hr = self.load_heart_rate()
        steps = self.load_steps()
        sleep = self.load_sleep()
        daily = self.load_daily_summary()

        # derive an IBI (ms) approximation from bpm if possible
        ibi_df = pd.DataFrame()
        try:
            if not hr.empty and 'bpm' in hr.columns:
                # Convert bpm to IBI in milliseconds (approx): ibi_ms = 60000 / bpm
                ibi = 60000.0 / hr['bpm'].replace({0: None})
                ibi = ibi.dropna()
                ibi_df = pd.DataFrame({'ibi': ibi.astype(float)})
                ibi_df.index = ibi.index
        except Exception:
            ibi_df = pd.DataFrame()

        return {
            'heart_rate': hr,
            'ibi': ibi_df,
            'steps': steps,
            'sleep': sleep,
            'daily': daily,
        }
