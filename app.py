import os
import os
from pathlib import Path
import streamlit as st
import pandas as pd

from src.ingestion import FitbitLoader
from src.algorithms import calculate_readiness
from src.visuals import plot_polar_activity, poincare_plot, sleep_ribbon_plot
from src.components import render_metric_cards


DEFAULT_PATH = r"G:\Mijn Drive\Data Analyse\00_DATA-Life_Analysis\fitbit-data"


st.set_page_config(page_title="Fitbit Analytics", layout="wide")


@st.cache_data(ttl=3600)
def load_master_dataframe(path: str):
    loader = FitbitLoader(path)
    return loader.process_all()


def main():
    st.sidebar.title("Data & Settings")
    data_path = st.sidebar.text_input("Data Path", DEFAULT_PATH)
    use_local = st.sidebar.checkbox("Use local path", value=True)

    if use_local and not Path(data_path).exists():
        st.sidebar.error(f"Path not found: {data_path}")

    with st.sidebar.expander("Load data"):
        if st.button("Load / Refresh"):
            try:
                st.session_state['dfs'] = load_master_dataframe(data_path)
                st.success("Data loaded into cache")
            except Exception as e:
                st.error(f"Failed to load data: {e}")

    if 'dfs' not in st.session_state:
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
            metrics['avg_steps'] = int(daily.get('steps', pd.Series()).dropna().mean() or 0)
            metrics['rhr'] = int(daily.get('resting_heart_rate', pd.Series()).dropna().mean() or 0)
            metrics['sleep_score'] = int(daily.get('sleep_score', pd.Series()).dropna().mean() or 0)

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
