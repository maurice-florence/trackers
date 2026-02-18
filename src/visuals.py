import pandas as pd
import plotly.graph_objects as go
import numpy as np


def plot_polar_activity(df: pd.DataFrame) -> go.Figure:
    # expects df with DatetimeIndex and 'bpm' or 'steps'
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(title_text='No data')
        return fig

    # Use steps if available, else bpm
    if 'steps' in df.columns:
        series = df['steps']
    elif 'bpm' in df.columns:
        series = df['bpm']
    else:
        series = df.iloc[:, 0]

    samp = series.resample('15T').mean().fillna(0)
    times = samp.index.time
    dates = samp.index.date

    # Map time to degrees
    degrees = np.array([t.hour * 15 + t.minute * 0.25 for t in times]) % 360
    # Map dates to radial values (ordinal)
    unique_dates = np.unique(dates)
    date_to_r = {d: i + 1 for i, d in enumerate(unique_dates)}
    r = np.array([date_to_r[d] for d in dates])

    fig = go.Figure(go.Barpolar(r=r, theta=degrees, marker=dict(color=samp, colorscale='Viridis', showscale=True), opacity=0.9))
    fig.update_layout(template='plotly_dark', polar=dict(radialaxis=dict(visible=False)))
    fig.update_layout(height=600, title_text='Circadian Activity (15-min bins)')
    return fig


def poincare_plot(ibi_df: pd.DataFrame) -> go.Figure:
    # Expects IBI series in milliseconds in column 'ibi' or first column
    if ibi_df is None or ibi_df.empty:
        fig = go.Figure()
        fig.update_layout(title_text='No IBI data')
        return fig

    s = ibi_df.iloc[:, 0].dropna().astype(float)
    if len(s) < 2:
        fig = go.Figure()
        fig.update_layout(title_text='Not enough IBI samples')
        return fig

    x = s[:-1].values
    y = s[1:].values
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode='markers', marker=dict(size=3, opacity=0.5)))
    fig.update_layout(title='Poincaré Plot', xaxis_title='IBI_n (ms)', yaxis_title='IBI_n+1 (ms)', template='plotly_white')
    return fig


def sleep_ribbon_plot(sleep_df: pd.DataFrame) -> go.Figure:
    # sleep_df expected to have 'start' (datetime), 'duration_s', 'level'
    if sleep_df is None or sleep_df.empty:
        fig = go.Figure()
        fig.update_layout(title_text='No sleep data')
        return fig

    fig = go.Figure()
    colors = {'wake': '#FF0000', 'rem': '#00FFFF', 'deep': '#00008B', 'light': '#ADD8E6', None: '#888'}

    for idx, row in sleep_df.iterrows():
        start = row.get('start')
        dur = row.get('duration_s') or 0
        level = str(row.get('level') or '').lower()
        color = colors.get(level, colors[None])
        try:
            base = start.hour + start.minute / 60
            y_label = start.date().isoformat()
        except Exception:
            base = 0
            y_label = str(idx)
        fig.add_trace(go.Bar(x=[dur / 3600], y=[y_label], base=[base], orientation='h', marker_color=color, showlegend=False))

    fig.update_layout(title='Sleep Architecture Ribbon', template='plotly_white', height=400)
    return fig
