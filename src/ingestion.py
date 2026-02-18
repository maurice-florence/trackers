import os
import fnmatch
import json
import re
import io
import zipfile
import time
import hashlib
from datetime import datetime
from pathlib import Path
import pandas as pd
from typing import Dict, Iterator, Tuple


class FitbitLoader:
    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self._exists = self.root.exists()
        self._is_dir = self.root.is_dir()
        self._is_zip = self.root.is_file() and self.root.suffix.lower() == '.zip'

    def _iter_matching_file_contents(self, pattern: str) -> Iterator[Tuple[str, bytes]]:
        """Yield tuples of (source_name, bytes_content) for files matching pattern.

        Supports: plain files under directories, zip files (single zip or directory of zips).
        """
        if not self._exists:
            return

        # 1) Files on disk that match directly
        if self._is_dir:
            for dirpath, _, files in os.walk(self.root):
                for fname in fnmatch.filter(files, pattern):
                    p = Path(dirpath) / fname
                    try:
                        yield (str(p), p.read_bytes())
                    except Exception:
                        continue

            # Also scan zip files inside the directory
            for dirpath, _, files in os.walk(self.root):
                for zname in fnmatch.filter(files, '*.zip'):
                    zpath = Path(dirpath) / zname
                    try:
                        with zipfile.ZipFile(zpath) as zf:
                            for member in zf.namelist():
                                if fnmatch.fnmatch(Path(member).name, pattern):
                                    try:
                                        yield (f"{zpath}!{member}", zf.read(member))
                                    except Exception:
                                        continue
                    except Exception:
                        continue

        # 2) Single zip file as root
        if self._is_zip:
            try:
                with zipfile.ZipFile(self.root) as zf:
                    for member in zf.namelist():
                        if fnmatch.fnmatch(Path(member).name, pattern):
                            try:
                                yield (f"{self.root}!{member}", zf.read(member))
                            except Exception:
                                continue
            except Exception:
                return

    # --- Parquet cache helpers ---
    def _cache_dir(self) -> Path:
        d = Path.cwd() / '.fitbit_cache'
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _cache_file(self, kind: str) -> Path:
        return self._cache_dir() / f"{kind}.parquet"

    def _latest_source_mtime(self, patterns) -> float:
        """Return latest modification time (epoch) among matching sources and zip members."""
        latest = 0.0
        # directory files and zips
        if self._is_dir:
            for dirpath, _, files in os.walk(self.root):
                for fname in files:
                    fpath = Path(dirpath) / fname
                    try:
                        if any(fnmatch.fnmatch(fname, p) for p in patterns):
                            latest = max(latest, fpath.stat().st_mtime)
                    except Exception:
                        continue
                # check zip members
                for zname in fnmatch.filter(files, '*.zip'):
                    zpath = Path(dirpath) / zname
                    try:
                        with zipfile.ZipFile(zpath) as zf:
                            for member in zf.infolist():
                                if any(fnmatch.fnmatch(Path(member.filename).name, p) for p in patterns):
                                    # zinfo.date_time -> tuple (Y,M,D,H,M,S)
                                    try:
                                        dt = datetime(*member.date_time)
                                        latest = max(latest, dt.timestamp())
                                    except Exception:
                                        pass
                    except Exception:
                        continue

        if self._is_zip:
            try:
                with zipfile.ZipFile(self.root) as zf:
                    for member in zf.infolist():
                        if any(fnmatch.fnmatch(Path(member.filename).name, p) for p in patterns):
                            try:
                                dt = datetime(*member.date_time)
                                latest = max(latest, dt.timestamp())
                            except Exception:
                                pass
            except Exception:
                pass

        return latest

    def get_cache_status(self) -> Dict[str, Dict]:
        """Return cache info for supported kinds.

        Returns a dict keyed by kind with values: {'exists', 'size', 'mtime', 'src_mtime', 'fresh'}
        """
        kinds = {
            'heart_rate': ['heart_rate-*.json'],
            'steps': ['steps-*.json'],
            'sleep': ['sleep-*.json'],
            'daily': ['*daily*.csv', '*Daily Activity*.csv']
        }
        info = {}
        for k, patterns in kinds.items():
            p = self._cache_file(k)
            exists = p.exists()
            size = p.stat().st_size if exists else 0
            mtime = p.stat().st_mtime if exists else None
            src_mtime = self._latest_source_mtime(patterns)
            fresh = exists and (mtime is not None and mtime >= src_mtime)
            info[k] = {'exists': exists, 'size': size, 'mtime': mtime, 'src_mtime': src_mtime, 'fresh': fresh, 'cache_path': str(p)}
        return info

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
        # use parquet cache when available and fresh
        cache_path = self._cache_file('heart_rate')
        src_mtime = self._latest_source_mtime(['heart_rate-*.json'])
        if cache_path.exists() and cache_path.stat().st_mtime >= src_mtime and cache_path.stat().st_size > 0:
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                pass

        rows = []
        for src, content in self._iter_matching_file_contents('heart_rate-*.json'):
            try:
                text = content.decode('utf-8')
                data = json.loads(text)
            except Exception:
                continue

            # data may be {'value': [...]} or a list
            entries = None
            if isinstance(data, dict) and 'value' in data:
                entries = data['value']
            elif isinstance(data, list):
                entries = data

            base_date = self._extract_date_from_filename(Path(src)) or ''
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
                        bpm = v.get('bpm') or (v.get('value') if isinstance(v.get('value'), (int, float)) else None)
                        conf = v.get('confidence')

                    if dt and len(str(dt)) <= 8 and base_date:
                        dt = f"{base_date}T{dt}"

                    rows.append({'dateTime': dt, 'bpm': bpm, 'confidence': conf})

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.dropna(subset=['dateTime'])

        # fast path: try a few common formats first to avoid slow dateutil fallback
        df['dateTime'] = self._parse_datetime_series(df['dateTime'])

        df = df.dropna(subset=['dateTime'])
        df = df.set_index('dateTime').sort_index()
        if 'bpm' in df.columns:
            df['bpm'] = pd.to_numeric(df['bpm'], errors='coerce')
        # write parquet cache
        try:
            df.to_parquet(cache_path, index=True)
        except Exception:
            pass
        return df

    def load_steps(self) -> pd.DataFrame:
        cache_path = self._cache_file('steps')
        src_mtime = self._latest_source_mtime(['steps-*.json'])
        if cache_path.exists() and cache_path.stat().st_mtime >= src_mtime and cache_path.stat().st_size > 0:
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                pass

        rows = []
        for src, content in self._iter_matching_file_contents('steps-*.json'):
            try:
                data = json.loads(content.decode('utf-8'))
            except Exception:
                continue
            entries = data.get('value') if isinstance(data, dict) else data
            base = self._extract_date_from_filename(Path(src)) or ''
            for v in entries or []:
                dt = v.get('dateTime') or v.get('time')
                val = v.get('value') or v.get('steps')
                if dt and len(str(dt)) <= 8 and base:
                    dt = f"{base}T{dt}"
                rows.append({'dateTime': dt, 'steps': val})

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df['dateTime'] = pd.to_datetime(df['dateTime'], errors='coerce')
        df = df.dropna(subset=['dateTime']).set_index('dateTime').sort_index()
        if 'steps' in df.columns:
            df['steps'] = pd.to_numeric(df['steps'], errors='coerce').fillna(0).astype(int)
        try:
            df.to_parquet(cache_path, index=True)
        except Exception:
            pass
        return df

    def load_sleep(self) -> pd.DataFrame:
        # Collect sleep sessions from sleep-*.json
        cache_path = self._cache_file('sleep')
        src_mtime = self._latest_source_mtime(['sleep-*.json'])
        if cache_path.exists() and cache_path.stat().st_mtime >= src_mtime and cache_path.stat().st_size > 0:
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                pass

        sessions = []
        for src, content in self._iter_matching_file_contents('sleep-*.json'):
            try:
                data = json.loads(content.decode('utf-8'))
            except Exception:
                continue
            if isinstance(data, dict):
                if 'levels' in data:
                    levels = data['levels']
                    for rec in levels.get('data', []):
                        start = rec.get('dateTime') or rec.get('start')
                        duration = rec.get('seconds') or rec.get('duration')
                        sessions.append({'start': start, 'duration_s': duration, 'level': rec.get('level') or rec.get('stage')})
                elif 'sleep' in data:
                    for s in data['sleep']:
                        sessions.append({'start': s.get('startTime'), 'duration_s': s.get('durationMillis', 0) / 1000, 'level': None})

        if not sessions:
            return pd.DataFrame()
        df = pd.DataFrame(sessions)
        df['start'] = pd.to_datetime(df['start'], errors='coerce')
        df = df.dropna(subset=['start']).sort_values('start')
        try:
            df.to_parquet(cache_path, index=False)
        except Exception:
            pass
        return df

    def load_daily_summary(self) -> pd.DataFrame:
        # look for Daily Activity Summary.csv and Sleep Score.csv
        dfs = []
        # local CSV files
        if self._is_dir:
            for dirpath, _, files in os.walk(self.root):
                for fname in files:
                    if fname.lower().endswith('.csv') and 'daily' in fname.lower():
                        p = Path(dirpath) / fname
                        try:
                            dfs.append(pd.read_csv(p))
                        except Exception:
                            continue

        # CSVs inside zip files
        for src, content in self._iter_matching_file_contents('*.csv'):
            name = Path(src).name.lower()
            if 'daily' in name or 'sleep' in name:
                try:
                    dfs.append(pd.read_csv(io.BytesIO(content)))
                except Exception:
                    continue

        cache_path = self._cache_file('daily')
        src_mtime = self._latest_source_mtime(['*daily*.csv','*Daily Activity*.csv'])
        if cache_path.exists() and cache_path.stat().st_mtime >= src_mtime and cache_path.stat().st_size > 0:
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                pass

        if not dfs:
            return pd.DataFrame()
        df = pd.concat(dfs, ignore_index=True)
        # try to standardize date column
        for c in df.columns:
            if 'date' in c.lower():
                df[c] = pd.to_datetime(df[c], errors='coerce')
                df = df.set_index(c)
                break
        try:
            df.to_parquet(cache_path, index=True)
        except Exception:
            pass
        return df

    def _parse_datetime_series(self, series) -> pd.Series:
        """Attempt fast vectorized parsing using common formats before falling back.

        Returns a pd.Series of datetimes (na for unparsable).
        """
        s = pd.Series(series).astype(str)
        # try common ISO formats in order (with/without microseconds)
        formats = [
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%H:%M:%S',
            '%H:%M'
        ]

        parsed = pd.Series([pd.NaT] * len(s), index=s.index)
        remaining_mask = parsed.isna()

        for fmt in formats:
            try:
                candidate = pd.to_datetime(s.where(remaining_mask), format=fmt, errors='coerce')
            except Exception:
                candidate = pd.to_datetime(s.where(remaining_mask), errors='coerce')
            # fill parsed where candidate is not NA
            ok = candidate.notna()
            if ok.any():
                parsed.loc[ok.index[ok]] = candidate.loc[ok.index[ok]]
                remaining_mask = parsed.isna()
            if not remaining_mask.any():
                break

        # final fallback for anything left: let pandas try to infer (slower)
        if parsed.isna().any():
            try:
                fallback = pd.to_datetime(s.where(parsed.isna()), errors='coerce')
                parsed.loc[fallback.notna().index[fallback.notna()]] = fallback.loc[fallback.notna().index[fallback.notna()]]
            except Exception:
                pass

        return parsed

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
