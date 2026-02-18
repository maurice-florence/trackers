import pandas as pd


def calculate_readiness(df_daily: pd.DataFrame, span: int = 14) -> pd.DataFrame:
    """Compute a simple shadow readiness score.

    Expects `df_daily` with columns: 'rmssd', 'total_sleep_minutes', 'activity_calories'.
    Returns df_daily with added 'shadow_readiness_score'.
    """
    if df_daily is None or df_daily.empty:
        return df_daily

    df = df_daily.copy()
    # Ensure numeric
    for c in ['rmssd', 'total_sleep_minutes', 'activity_calories']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        else:
            df[c] = 0

    # Baselines via EMA
    df['rmssd_base'] = df['rmssd'].ewm(span=span, adjust=False).mean().fillna(method='ffill')
    df['sleep_base'] = df['total_sleep_minutes'].ewm(span=span, adjust=False).mean().fillna(method='ffill')
    df['activity_base'] = df['activity_calories'].ewm(span=span, adjust=False).mean().fillna(method='ffill')

    # Normalized component scores (0-100)
    df['z_hrv'] = (df['rmssd'] / df['rmssd_base']) * 100
    df['z_sleep'] = (df['total_sleep_minutes'] / df['sleep_base']) * 100
    # Activity: lower activity may increase readiness — so invert ratio
    df['z_activity'] = (df['activity_base'] / (df['activity_calories'] + 1)) * 100

    # Clip
    for c in ['z_hrv', 'z_sleep', 'z_activity']:
        df[c] = df[c].clip(lower=0, upper=200)

    # Weights
    w_hrv, w_sleep, w_activity = 0.5, 0.3, 0.2
    df['shadow_readiness_score'] = (w_hrv * df['z_hrv'] + w_sleep * df['z_sleep'] + w_activity * df['z_activity'])
    df['shadow_readiness_score'] = df['shadow_readiness_score'].clip(0, 100)

    return df
import pandas as pd


def calculate_readiness(df_daily: pd.DataFrame, span: int = 14) -> pd.DataFrame:
    """Compute a simple shadow readiness score.

    Expects `df_daily` with columns: 'rmssd', 'total_sleep_minutes', 'activity_calories'.
    Returns df_daily with added 'shadow_readiness_score'.
    """
    if df_daily is None or df_daily.empty:
        return df_daily

    df = df_daily.copy()
    # Ensure numeric
    for c in ['rmssd', 'total_sleep_minutes', 'activity_calories']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        else:
            df[c] = 0

    # Baselines via EMA
    df['rmssd_base'] = df['rmssd'].ewm(span=span, adjust=False).mean().fillna(method='ffill')
    df['sleep_base'] = df['total_sleep_minutes'].ewm(span=span, adjust=False).mean().fillna(method='ffill')
    df['activity_base'] = df['activity_calories'].ewm(span=span, adjust=False).mean().fillna(method='ffill')

    # Normalized component scores (0-100)
    df['z_hrv'] = (df['rmssd'] / df['rmssd_base']) * 100
    df['z_sleep'] = (df['total_sleep_minutes'] / df['sleep_base']) * 100
    # Activity: lower activity may increase readiness — so invert ratio
    df['z_activity'] = (df['activity_base'] / (df['activity_calories'] + 1)) * 100

    # Clip
    for c in ['z_hrv', 'z_sleep', 'z_activity']:
        df[c] = df[c].clip(lower=0, upper=200)

    # Weights
    w_hrv, w_sleep, w_activity = 0.5, 0.3, 0.2
    df['shadow_readiness_score'] = (w_hrv * df['z_hrv'] + w_sleep * df['z_sleep'] + w_activity * df['z_activity'])
    df['shadow_readiness_score'] = df['shadow_readiness_score'].clip(0, 100)

    return df
