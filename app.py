import os
import os
from pathlib import Path
import streamlit as st
import pandas as pd

from src.ingestion import FitbitLoader
from src.algorithms import calculate_readiness
from src.visuals import plot_polar_activity, poincare_plot, sleep_ribbon_plot
from src.components import render_metric_cards


DEFAULT_PATH = r"G:\Mijn Drive\Takeout"


st.set_page_config(page_title="Fitbit Analytics", layout="wide")


@st.cache_data(ttl=3600)
def load_master_dataframe(path: str):
    loader = FitbitLoader(path)
    return loader.process_all()


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

    if 'dfs' not in st.session_state:
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
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No heart rate data available to render polar chart.")

    # Sleep Lab
    with tabs[1]:
        st.header("Sleep Lab")
        sleep = d.get('sleep', pd.DataFrame())
        if not sleep.empty:
            fig = sleep_ribbon_plot(sleep)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sleep logs found.")

    # Activity tab
    with tabs[2]:
        st.header("Activity")
        ibi = d.get('ibi', pd.DataFrame())
        if not ibi.empty:
            fig = poincare_plot(ibi)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No IBI/HRV data available for Poincaré plot.")


if __name__ == '__main__':
    main()
