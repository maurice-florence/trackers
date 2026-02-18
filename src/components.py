import streamlit as st


def render_metric_cards(values: dict):
    cols = st.columns(4)
    labels = [
        ('Avg Steps', values.get('avg_steps', 0)),
        ('Avg RHR', values.get('rhr', '—')),
        ('Sleep Score', values.get('sleep_score', '—')),
        ('Active Mins', values.get('active_mins', '—')),
    ]
    for col, (title, val) in zip(cols, labels):
        with col:
            st.metric(label=title, value=val)
import streamlit as st


def render_metric_cards(values: dict):
    cols = st.columns(4)
    labels = [
        ('Avg Steps', values.get('avg_steps', 0)),
        ('Avg RHR', values.get('rhr', '—')),
        ('Sleep Score', values.get('sleep_score', '—')),
        ('Active Mins', values.get('active_mins', '—')),
    ]
    for col, (title, val) in zip(cols, labels):
        with col:
            st.metric(label=title, value=val)
