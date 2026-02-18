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

    samp = series.resample('15min').mean().fillna(0)
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


def heart_rate_trend(hr_df: pd.DataFrame) -> go.Figure:
    """Plot heart rate trend over time."""
    if hr_df is None or hr_df.empty or 'bpm' not in hr_df.columns:
        fig = go.Figure()
        fig.update_layout(title_text='No heart rate data')
        return fig
    bpm = hr_df['bpm'].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bpm.index, y=bpm, mode='lines+markers', name='BPM', line=dict(color='#EF4444')))
    fig.update_layout(title='Heart Rate Trend', xaxis_title='Time', yaxis_title='BPM', template='plotly_white', hovermode='x unified')
    return fig


def steps_trend(steps_df: pd.DataFrame) -> go.Figure:
    """Plot daily steps trend."""
    if steps_df is None or steps_df.empty or 'steps' not in steps_df.columns:
        fig = go.Figure()
        fig.update_layout(title_text='No steps data')
        return fig
    daily = steps_df.resample('D')['steps'].sum()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=daily.index, y=daily, name='Steps', marker=dict(color='#10B981')))
    fig.update_layout(title='Daily Steps', xaxis_title='Date', yaxis_title='Steps', template='plotly_white')
    return fig


def resting_heart_rate_trend(daily_df: pd.DataFrame) -> go.Figure:
    """Plot resting heart rate trend from daily summary."""
    if daily_df is None or daily_df.empty or 'resting_heart_rate' not in daily_df.columns:
        fig = go.Figure()
        fig.update_layout(title_text='No RHR data')
        return fig
    rhr = daily_df['resting_heart_rate'].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rhr.index, y=rhr, mode='lines+markers', name='RHR', line=dict(color='#F59E0B', width=2), fill='tozeroy'))
    fig.update_layout(title='Resting Heart Rate Trend', xaxis_title='Date', yaxis_title='RHR (bpm)', template='plotly_white')
    return fig


def sleep_duration_trend(sleep_df: pd.DataFrame) -> go.Figure:
    """Plot sleep duration per night."""
    if sleep_df is None or sleep_df.empty:
        fig = go.Figure()
        fig.update_layout(title_text='No sleep data')
        return fig
    sleep_df = sleep_df.copy()
    if 'start' in sleep_df.columns:
        sleep_df['date'] = pd.to_datetime(sleep_df['start']).dt.date
        daily_sleep = sleep_df.groupby('date')['duration_s'].sum() / 3600
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily_sleep.index, y=daily_sleep, name='Hours', marker=dict(color='#6366F1')))
        fig.update_layout(title='Sleep Duration per Night', xaxis_title='Date', yaxis_title='Hours', template='plotly_white')
        return fig
    fig = go.Figure()
    fig.update_layout(title_text='Cannot parse sleep data')
    return fig


def activity_heatmap(steps_df: pd.DataFrame) -> go.Figure:
    """Create hourly activity heatmap."""
    if steps_df is None or steps_df.empty or 'steps' not in steps_df.columns:
        fig = go.Figure()
        fig.update_layout(title_text='No steps data')
        return fig
    steps_df = steps_df.copy()
    steps_df['hour'] = steps_df.index.hour
    steps_df['date'] = steps_df.index.date
    pivot = steps_df.pivot_table(values='steps', index='date', columns='hour', aggfunc='sum', fill_value=0)
    fig = go.Figure(data=go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index, colorscale='Viridis'))
    fig.update_layout(title='Hourly Activity Heatmap', xaxis_title='Hour of Day', yaxis_title='Date', template='plotly_white')
    return fig


def heart_rate_distribution(hr_df: pd.DataFrame) -> go.Figure:
    """Histogram of heart rate distribution."""
    if hr_df is None or hr_df.empty or 'bpm' not in hr_df.columns:
        fig = go.Figure()
        fig.update_layout(title_text='No heart rate data')
        return fig
    bpm = hr_df['bpm'].dropna()
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=bpm, nbinsx=30, name='BPM', marker=dict(color='#EF4444')))
    fig.update_layout(title='Heart Rate Distribution', xaxis_title='BPM', yaxis_title='Frequency', template='plotly_white')
    return fig


def ibi_trend(ibi_df: pd.DataFrame) -> go.Figure:
    """Plot IBI (heart rate variability) trend over time."""
    if ibi_df is None or ibi_df.empty:
        fig = go.Figure()
        fig.update_layout(title_text='No IBI data')
        return fig
    ibi = ibi_df.iloc[:, 0].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ibi.index, y=ibi, mode='lines', name='IBI', line=dict(color='#06B6D4')))
    fig.update_layout(title='Heart Rate Variability (IBI) Trend', xaxis_title='Time', yaxis_title='IBI (ms)', template='plotly_white')
    return fig
