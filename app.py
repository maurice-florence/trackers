import os
import os
from pathlib import Path
import streamlit as st
import pandas as pd

from src.ingestion import FitbitLoader
from src.algorithms import calculate_readiness
from src.visuals import (plot_polar_activity, poincare_plot, sleep_ribbon_plot, heart_rate_trend, 
                         steps_trend, resting_heart_rate_trend, sleep_duration_trend, 
                         activity_heatmap, heart_rate_distribution, ibi_trend)
from src.components import render_metric_cards


DEFAULT_PATH = r"G:\Mijn Drive\Takeout"


st.set_page_config(page_title="Fitbit Analytics", layout="wide")


@st.cache_data(ttl=3600)
def load_master_dataframe(path: str):
    loader = FitbitLoader(path)
    return loader.process_all()


def get_data_availability(dfs: dict) -> dict:
    """Analyze loaded dataframes and return availability info."""
    info = {
        'heart_rate': {'available': False, 'count': 0, 'date_range': None},
        'steps': {'available': False, 'count': 0, 'date_range': None},
        'sleep': {'available': False, 'count': 0, 'date_range': None},
        'daily': {'available': False, 'count': 0, 'date_range': None},
        'ibi': {'available': False, 'count': 0, 'date_range': None},
    }
    
    for key in info.keys():
        df = dfs.get(key, pd.DataFrame())
        if df is not None and not df.empty:
            info[key]['available'] = True
            info[key]['count'] = len(df)
            try:
                if df.index.name in ['dateTime', 'start'] or isinstance(df.index, pd.DatetimeIndex):
                    idx = df.index
                else:
                    # Try first datetime column
                    for col in df.columns:
                        if pd.api.types.is_datetime64_any_dtype(df[col]):
                            idx = df[col]
                            break
                    else:
                        idx = None
                
                if idx is not None:
                    min_date = pd.to_datetime(idx.min()).date()
                    max_date = pd.to_datetime(idx.max()).date()
                    info[key]['date_range'] = (min_date, max_date)
            except Exception:
                pass
    
    return info


def main():
    st.sidebar.title("Data & Settings")
    data_path = st.sidebar.text_input("Data Path", DEFAULT_PATH)
    use_local = st.sidebar.checkbox("Use local path", value=True)
    auto_load = st.sidebar.checkbox("Auto-load on start", value=False, help="If enabled the app will load data on startup (may take time)")

    if use_local and not Path(data_path).exists():
        st.sidebar.error(f"Path not found: {data_path}")

    with st.sidebar.expander("Load data"):
        show_cache = st.sidebar.checkbox("Show cache status", value=True)
        use_cache_if_fresh = st.sidebar.checkbox("Use cached when fresh", value=True)

        if show_cache:
            try:
                loader_tmp = FitbitLoader(data_path)
                status = loader_tmp.get_cache_status()
                st.sidebar.markdown("**Cache status**")
                for k, v in status.items():
                    fresh_mark = '✅' if v['fresh'] else '❌'
                    mtime = pd.to_datetime(v['mtime'], unit='s') if v['mtime'] else None
                    st.sidebar.write(f"- **{k}**: {fresh_mark} size={v['size']} mtime={mtime}")
            except Exception:
                st.sidebar.write("Could not determine cache status.")

        if st.button("Load / Refresh"):
            # perform stepwise load with progress
            try:
                pbar = st.sidebar.progress(0)
                status_text = st.sidebar.empty()
                loader = FitbitLoader(data_path)
                steps = [
                    ('heart_rate', loader.load_heart_rate),
                    ('steps', loader.load_steps),
                    ('sleep', loader.load_sleep),
                    ('daily', loader.load_daily_summary),
                ]
                total = len(steps)
                dfs = {}
                for i, (k, fn) in enumerate(steps, start=1):
                    status_text.text(f'Loading {k} ({i}/{total})...')
                    dfs[k] = fn()
                    pbar.progress(int(i / total * 100))

                # derive ibi
                hr = dfs.get('heart_rate', pd.DataFrame())
                if not hr.empty and 'bpm' in hr.columns:
                    ibi = 60000.0 / hr['bpm'].replace({0: None})
                    ibi = ibi.dropna()
                    ibi_df = pd.DataFrame({'ibi': ibi.astype(float)})
                    ibi_df.index = ibi.index
                else:
                    ibi_df = pd.DataFrame()

                dfs['ibi'] = ibi_df
                st.session_state['dfs'] = dfs
                pbar.progress(100)
                status_text.text('Load complete.')
                st.success('Data loaded (with progress)')
            except Exception as e:
                st.error(f'Failed to load data: {e}')
    
    # Show data availability summary
    with st.sidebar.expander("Data Summary", expanded=True):
        d = st.session_state.get('dfs', {})
        if d and any(not df.empty if isinstance(df, pd.DataFrame) else False for df in d.values()):
            availability = get_data_availability(d)
            for key, info in availability.items():
                if info['available']:
                    date_range_str = f"{info['date_range'][0]} to {info['date_range'][1]}" if info['date_range'] else "Unknown range"
                    st.write(f"✅ **{key.replace('_', ' ').title()}**: {info['count']} records ({date_range_str})")
            
            # Overall date range
            all_dates = []
            for key, info in availability.items():
                if info['available'] and info['date_range']:
                    all_dates.extend(info['date_range'])
            if all_dates:
                overall_min = min(all_dates)
                overall_max = max(all_dates)
                st.divider()
                st.write(f"📅 **Overall Date Range**: {overall_min} to {overall_max}")
                st.write("✅ **Status**: All available data is being displayed")
        else:
            st.write("No data loaded. Click 'Load / Refresh' to load data.")
        st.session_state['dfs'] = {}
        if auto_load:
            try:
                st.session_state['dfs'] = load_master_dataframe(data_path)
            except Exception:
                st.session_state['dfs'] = {}

    d = st.session_state['dfs']

    st.title("Fitbit Analytics — Local Dashboard")

    tabs = st.tabs(["Overview", "Sleep Lab", "Activity"])

    # Overview
    with tabs[0]:
        st.header("Overview")
        
        # Show data availability at top
        availability = get_data_availability(d)
        if any(info['available'] for info in availability.values()):
            col1, col2, col3 = st.columns(3)
            data_types_available = [k.replace('_', ' ').title() for k, v in availability.items() if v['available']]
            
            with col1:
                st.metric("Data Types Available", len(data_types_available))
            with col2:
                total_records = sum(v['count'] for v in availability.values() if v['available'])
                st.metric("Total Records", f"{total_records:,}")
            with col3:
                all_dates = []
                for key, info in availability.items():
                    if info['available'] and info['date_range']:
                        all_dates.extend(info['date_range'])
                if all_dates:
                    date_span = (max(all_dates) - min(all_dates)).days
                    st.metric("Date Span", f"{date_span} days")
            
            st.info(f"📊 Data loaded: {', '.join(data_types_available)} — All available data is displayed")
            st.divider()
        metrics = {
            'avg_steps': 0,
            'rhr': None,
            'sleep_score': None,
        }

        daily = d.get('daily', pd.DataFrame())
        if not daily.empty:
            avg_steps = daily.get('steps', pd.Series()).dropna().mean()
            metrics['avg_steps'] = int(avg_steps) if pd.notna(avg_steps) else 0
            rhr = daily.get('resting_heart_rate', pd.Series()).dropna().mean()
            metrics['rhr'] = int(rhr) if pd.notna(rhr) else 0
            sleep_score = daily.get('sleep_score', pd.Series()).dropna().mean()
            metrics['sleep_score'] = int(sleep_score) if pd.notna(sleep_score) else 0

        render_metric_cards(metrics)

        hr = d.get('heart_rate', pd.DataFrame())
        if not hr.empty:
            st.subheader("Circadian Activity (Polar)")
            fig = plot_polar_activity(hr)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No heart rate data available to render polar chart.")

        # Additional overview charts
        col1, col2 = st.columns(2)
        with col1:
            hr = d.get('heart_rate', pd.DataFrame())
            if not hr.empty:
                st.plotly_chart(heart_rate_distribution(hr), width='stretch')
        with col2:
            daily = d.get('daily', pd.DataFrame())
            if not daily.empty:
                st.plotly_chart(resting_heart_rate_trend(daily), width='stretch')

        st.divider()
        hr = d.get('heart_rate', pd.DataFrame())
        if not hr.empty:
            st.plotly_chart(heart_rate_trend(hr), width='stretch')

    # Sleep Lab
    with tabs[1]:
        st.header("Sleep Lab")
        sleep = d.get('sleep', pd.DataFrame())
        if not sleep.empty:
            fig = sleep_ribbon_plot(sleep)
            st.plotly_chart(fig, width='stretch')
            st.divider()
            st.plotly_chart(sleep_duration_trend(sleep), width='stretch')
        else:
            st.info("No sleep logs found.")

    # Activity tab
    with tabs[2]:
        st.header("Activity")
        
        col1, col2 = st.columns(2)
        with col1:
            steps = d.get('steps', pd.DataFrame())
            if not steps.empty:
                st.plotly_chart(steps_trend(steps), width='stretch')
        with col2:
            ibi = d.get('ibi', pd.DataFrame())
            if not ibi.empty:
                st.plotly_chart(ibi_trend(ibi), width='stretch')
        
        st.divider()
        steps = d.get('steps', pd.DataFrame())
        if not steps.empty:
            st.plotly_chart(activity_heatmap(steps), width='stretch')
        
        st.divider()
        ibi = d.get('ibi', pd.DataFrame())
        if not ibi.empty:
            fig = poincare_plot(ibi)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No IBI/HRV data available for Poincaré plot.")


if __name__ == '__main__':
    main()
