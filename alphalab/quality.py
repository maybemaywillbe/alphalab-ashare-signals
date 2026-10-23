"""Basic OHLCV integrity checks; not a complete point-in-time audit."""
from __future__ import annotations
import pandas as pd

REQUIRED = ['date','open','high','low','close','volume']

def validate_bars(df: pd.DataFrame) -> dict:
    findings = []
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return {'passed': False, 'rows': len(df), 'findings': [f'missing_columns:{missing}']}
    if df.empty:
        return {'passed': False, 'rows': 0, 'findings': ['empty_dataset']}
    x = df.copy()
    dates = pd.to_datetime(x['date'], errors='coerce')
    if dates.isna().any(): findings.append(f'invalid_dates:{int(dates.isna().sum())}')
    if dates.duplicated().any(): findings.append(f'duplicate_dates:{int(dates.duplicated().sum())}')
    if not dates.is_monotonic_increasing: findings.append('unsorted_dates')
    for col in REQUIRED[1:]:
        x[col] = pd.to_numeric(x[col], errors='coerce')
        if x[col].isna().any(): findings.append(f'{col}_missing_or_nonnumeric:{int(x[col].isna().sum())}')
    p = x[['open','high','low','close']]
    if (p <= 0).any().any(): findings.append('nonpositive_price')
    if (x['volume'] < 0).any(): findings.append('negative_volume')
    # Adjusted historical OHLC can violate raw-price intuition due to provider conventions;
    # report but do not silently fix anomalies.
    if (x['high'] < x[['open','close','low']].max(axis=1)).any(): findings.append('high_below_ohlc')
    if (x['low'] > x[['open','close','high']].min(axis=1)).any(): findings.append('low_above_ohlc')
    return {'passed': not findings, 'rows': len(x), 'first_date': str(dates.min().date()) if dates.notna().any() else None,
            'last_date': str(dates.max().date()) if dates.notna().any() else None, 'findings': findings}
