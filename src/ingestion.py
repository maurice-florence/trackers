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
        self.progress_log = []

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

    def _processed_metadata_path(self) -> Path:
        return self._cache_dir() / 'processed_sources.json'

    def _load_processed_metadata(self) -> Dict[str, float]:
        p = self._processed_metadata_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_processed_metadata(self, meta: Dict[str, float]):
        p = self._processed_metadata_path()
        try:
            p.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        except Exception:
            pass

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
    def process_all(self, progress_callback=None) -> Dict[str, pd.DataFrame]:
        """
        Incrementally process available sources (files and zip archives) and append to parquet caches.

        If `progress_callback` is provided it will be called with two args: (source_name, message).
        A running `self.progress_log` list of tuples (timestamp, source, message) is maintained.
        """
        # Load metadata of already processed sources
        processed = self._load_processed_metadata()

        # Prepare holders for newly parsed rows
        new_hr_rows = []
        new_steps_rows = []
        new_sleep_sessions = []
        new_daily_dfs = []

        def _report(src, msg):
            ts = time.time()
            rec = {'ts': ts, 'source': str(src), 'msg': msg}
            self.progress_log.append(rec)
            if progress_callback:
                try:
                    progress_callback(str(src), msg)
                except Exception:
                    pass

        # Collect candidate sources: files matching patterns and zip files
        sources = []
        if not self._exists:
            _report(self.root, 'root_missing')
            return {'heart_rate': pd.DataFrame(), 'ibi': pd.DataFrame(), 'steps': pd.DataFrame(), 'sleep': pd.DataFrame(), 'daily': pd.DataFrame()}

        if self._is_dir:
            # plain files
            for dirpath, _, files in os.walk(self.root):
                for fname in files:
                    fpath = Path(dirpath) / fname
                    if fname.lower().endswith('.zip'):
                        sources.append(fpath)
                    else:
                        # include any file that matches our target patterns
                        if fnmatch.fnmatch(fname, 'heart_rate-*.json') or fnmatch.fnmatch(fname, 'steps-*.json') or fnmatch.fnmatch(fname, 'sleep-*.json') or fname.lower().endswith('.csv'):
                            sources.append(fpath)
        if self._is_zip:
            sources.append(self.root)

        # Helper to parse json content for heart/steps/sleep
        def _parse_heart_from_bytes(src_label, content_bytes):
            try:
                data = json.loads(content_bytes.decode('utf-8'))
            except Exception:
                return []
            entries = None
            if isinstance(data, dict) and 'value' in data:
                entries = data['value']
            elif isinstance(data, list):
                entries = data
            base_date = None
            try:
                base_date = self._extract_date_from_filename(Path(src_label))
            except Exception:
                base_date = None
            rows = []
            for v in entries or []:
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
            return rows

        def _parse_steps_from_bytes(src_label, content_bytes):
            try:
                data = json.loads(content_bytes.decode('utf-8'))
            except Exception:
                return []
            entries = data.get('value') if isinstance(data, dict) else data
            base = None
            try:
                base = self._extract_date_from_filename(Path(src_label))
            except Exception:
                base = None
            rows = []
            for v in entries or []:
                dt = v.get('dateTime') or v.get('time')
                val = v.get('value') or v.get('steps')
                if dt and len(str(dt)) <= 8 and base:
                    dt = f"{base}T{dt}"
                rows.append({'dateTime': dt, 'steps': val})
            return rows

        def _parse_sleep_from_bytes(src_label, content_bytes):
            try:
                data = json.loads(content_bytes.decode('utf-8'))
            except Exception:
                return []
            sessions = []
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
            return sessions

        # Process each source incrementally
        for src in sources:
            try:
                src_key = str(src)
                try:
                    src_mtime = Path(src).stat().st_mtime
                except Exception:
                    src_mtime = time.time()
                prev_mtime = processed.get(src_key, 0)
                if src_mtime <= prev_mtime:
                    _report(src_key, 'skipped')
                    continue

                # if zip, iterate members
                if str(src).lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(src) as zf:
                            for member in zf.namelist():
                                name = Path(member).name
                                try:
                                    content = zf.read(member)
                                except Exception:
                                    continue
                                if fnmatch.fnmatch(name, 'heart_rate-*.json'):
                                    rows = _parse_heart_from_bytes(f"{src}!{member}", content)
                                    new_hr_rows.extend(rows)
                                    _report(f"{src}!{member}", f"parsed:{len(rows)}")
                                elif fnmatch.fnmatch(name, 'steps-*.json'):
                                    rows = _parse_steps_from_bytes(f"{src}!{member}", content)
                                    new_steps_rows.extend(rows)
                                    _report(f"{src}!{member}", f"parsed:{len(rows)}")
                                elif fnmatch.fnmatch(name, 'sleep-*.json'):
                                    rows = _parse_sleep_from_bytes(f"{src}!{member}", content)
                                    new_sleep_sessions.extend(rows)
                                    _report(f"{src}!{member}", f"parsed_sleep:{len(rows)}")
                                elif name.lower().endswith('.csv') and ('daily' in name.lower() or 'sleep' in name.lower()):
                                    try:
                                        df = pd.read_csv(io.BytesIO(content))
                                        new_daily_dfs.append(df)
                                        _report(f"{src}!{member}", f"parsed_daily:{len(df)}")
                                    except Exception:
                                        _report(f"{src}!{member}", 'parsed_daily:0')
                    except Exception as e:
                        _report(src_key, f'zip_error:{e}')
                        continue
                else:
                    # plain file
                    name = Path(src).name
                    try:
                        content = Path(src).read_bytes()
                    except Exception:
                        _report(src_key, 'read_error')
                        continue
                    if fnmatch.fnmatch(name, 'heart_rate-*.json'):
                        rows = _parse_heart_from_bytes(src_key, content)
                        new_hr_rows.extend(rows)
                        _report(src_key, f'parsed:{len(rows)}')
                    elif fnmatch.fnmatch(name, 'steps-*.json'):
                        rows = _parse_steps_from_bytes(src_key, content)
                        new_steps_rows.extend(rows)
                        _report(src_key, f'parsed:{len(rows)}')
                    elif fnmatch.fnmatch(name, 'sleep-*.json'):
                        rows = _parse_sleep_from_bytes(src_key, content)
                        new_sleep_sessions.extend(rows)
                        _report(src_key, f'parsed_sleep:{len(rows)}')
                    elif name.lower().endswith('.csv') and ('daily' in name.lower() or 'sleep' in name.lower()):
                        try:
                            df = pd.read_csv(io.BytesIO(content))
                            new_daily_dfs.append(df)
                            _report(src_key, f'parsed_daily:{len(df)}')
                        except Exception:
                            _report(src_key, 'parsed_daily:0')

                # mark processed
                processed[src_key] = src_mtime
                self._save_processed_metadata(processed)
                _report(src_key, 'processed')
            except Exception as e:
                _report(src, f'error:{e}')

        # Now merge new rows into caches
        # Heart rate
        hr_cache = self._cache_file('heart_rate')
        try:
            existing_hr = pd.read_parquet(hr_cache) if hr_cache.exists() and hr_cache.stat().st_size > 0 else pd.DataFrame()
        except Exception:
            existing_hr = pd.DataFrame()
        hr_new_df = pd.DataFrame(new_hr_rows)
        if not hr_new_df.empty:
            hr_new_df['dateTime'] = self._parse_datetime_series(hr_new_df['dateTime'])
            hr_new_df = hr_new_df.dropna(subset=['dateTime']).set_index('dateTime')
            hr_new_df['bpm'] = pd.to_numeric(hr_new_df['bpm'], errors='coerce')
            if not existing_hr.empty:
                merged = pd.concat([existing_hr, hr_new_df]).sort_index()
            else:
                merged = hr_new_df.sort_index()
            try:
                merged.to_parquet(hr_cache)
            except Exception:
                pass
        else:
            merged = existing_hr

        # Steps
        steps_cache = self._cache_file('steps')
        try:
            existing_steps = pd.read_parquet(steps_cache) if steps_cache.exists() and steps_cache.stat().st_size > 0 else pd.DataFrame()
        except Exception:
            existing_steps = pd.DataFrame()
        steps_new_df = pd.DataFrame(new_steps_rows)
        if not steps_new_df.empty:
            steps_new_df['dateTime'] = pd.to_datetime(steps_new_df['dateTime'], errors='coerce')
            steps_new_df = steps_new_df.dropna(subset=['dateTime']).set_index('dateTime')
            steps_new_df['steps'] = pd.to_numeric(steps_new_df['steps'], errors='coerce').fillna(0).astype(int)
            if not existing_steps.empty:
                merged_steps = pd.concat([existing_steps, steps_new_df]).sort_index()
            else:
                merged_steps = steps_new_df.sort_index()
            try:
                merged_steps.to_parquet(steps_cache)
            except Exception:
                pass
        else:
            merged_steps = existing_steps

        # Sleep
        sleep_cache = self._cache_file('sleep')
        try:
            existing_sleep = pd.read_parquet(sleep_cache) if sleep_cache.exists() and sleep_cache.stat().st_size > 0 else pd.DataFrame()
        except Exception:
            existing_sleep = pd.DataFrame()
        sleep_new_df = pd.DataFrame(new_sleep_sessions)
        if not sleep_new_df.empty:
            sleep_new_df['start'] = pd.to_datetime(sleep_new_df['start'], errors='coerce')
            sleep_new_df = sleep_new_df.dropna(subset=['start']).sort_values('start')
            if not existing_sleep.empty:
                merged_sleep = pd.concat([existing_sleep, sleep_new_df], ignore_index=True)
                merged_sleep = merged_sleep.drop_duplicates().sort_values('start')
            else:
                merged_sleep = sleep_new_df
            try:
                merged_sleep.to_parquet(sleep_cache, index=False)
            except Exception:
                pass
        else:
            merged_sleep = existing_sleep

        # Daily
        daily_cache = self._cache_file('daily')
        try:
            existing_daily = pd.read_parquet(daily_cache) if daily_cache.exists() and daily_cache.stat().st_size > 0 else pd.DataFrame()
        except Exception:
            existing_daily = pd.DataFrame()
        if new_daily_dfs:
            try:
                concat_daily = pd.concat(new_daily_dfs, ignore_index=True)
            except Exception:
                concat_daily = pd.DataFrame()
            if not concat_daily.empty:
                if not existing_daily.empty:
                    merged_daily = pd.concat([existing_daily, concat_daily], ignore_index=True).drop_duplicates()
                else:
                    merged_daily = concat_daily
                try:
                    merged_daily.to_parquet(daily_cache, index=True)
                except Exception:
                    pass
            else:
                merged_daily = existing_daily
        else:
            merged_daily = existing_daily

        # derive IBI
        ibi_df = pd.DataFrame()
        try:
            if not merged.empty and 'bpm' in merged.columns:
                ibi = 60000.0 / merged['bpm'].replace({0: None})
                ibi = ibi.dropna()
                ibi_df = pd.DataFrame({'ibi': ibi.astype(float)})
                ibi_df.index = ibi.index
        except Exception:
            ibi_df = pd.DataFrame()

        return {
            'heart_rate': merged,
            'ibi': ibi_df,
            'steps': merged_steps,
            'sleep': merged_sleep,
            'daily': merged_daily,
        }

    def get_progress_log(self):
        return list(self.progress_log)

    def get_file_listing(self) -> Dict:
        """Return info about files and zips in the data folder."""
        info = {
            'root_path': str(self.root),
            'exists': self._exists,
            'zip_files': [],
            'data_files': [],
            'total_items': 0
        }
        
        if not self._exists:
            return info
        
        try:
            if self._is_dir:
                # List all files in directory
                for dirpath, _, files in os.walk(self.root):
                    for fname in files:
                        fpath = Path(dirpath) / fname
                        try:
                            size = fpath.stat().st_size
                            if fname.lower().endswith('.zip'):
                                info['zip_files'].append({
                                    'name': fname,
                                    'path': str(fpath),
                                    'size': size
                                })
                            elif fname.lower().endswith(('.json', '.csv')):
                                info['data_files'].append({
                                    'name': fname,
                                    'path': str(fpath),
                                    'size': size
                                })
                        except Exception:
                            pass
            elif self._is_zip:
                # Single zip file
                info['zip_files'].append({
                    'name': self.root.name,
                    'path': str(self.root),
                    'size': self.root.stat().st_size
                })
        except Exception:
            pass
        
        info['total_items'] = len(info['zip_files']) + len(info['data_files'])
        return info
