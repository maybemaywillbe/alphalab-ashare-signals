"""Exploratory, price-only factors. No claim of corporate-action-safe total returns."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .selection import rank_bins


def load_raw_panel(folder):
    """Load raw snapshots only. Do not substitute qfq/hfq or fill missing bars."""
    from pathlib import Path
    frames=[]
    for path in sorted(Path(folder).glob('*_raw.csv')):
        symbol=path.stem.removesuffix('_raw')
        if not (len(symbol)==6 and symbol.isdigit()):
            continue
        x=pd.read_csv(path, dtype={'symbol':str})
        required={'date','close'}
        if not required.issubset(x.columns):
            raise ValueError(f'{path.name}: missing {required-set(x.columns)}')
        x=x[['date','close']].copy()
        x['date']=pd.to_datetime(x['date'],errors='raise').dt.normalize()
        x['close']=pd.to_numeric(x['close'],errors='coerce')
        if x['date'].duplicated().any():
            raise ValueError(f'{path.name}: duplicate dates')
        if (x['close'].dropna()<=0).any():
            raise ValueError(f'{path.name}: nonpositive raw close')
        x['symbol']=symbol
        frames.append(x)
    if not frames:
        raise ValueError('No *_raw.csv files found; provide raw history snapshots in the configured input directory.')
    return pd.concat(frames,ignore_index=True).sort_values(['symbol','date']).reset_index(drop=True)


def load_sessions(path, start=None, end=None):
    x=pd.read_csv(path)
    if 'date' not in x.columns:
        raise ValueError('exchange calendar needs a date column')
    s=pd.DatetimeIndex(pd.to_datetime(x['date'],errors='raise').dt.normalize().unique()).sort_values()
    if start is not None: s=s[s>=pd.Timestamp(start)]
    if end is not None: s=s[s<=pd.Timestamp(end)]
    if not len(s): raise ValueError('empty exchange calendar')
    return s


def factor_panel(raw, sessions, momentum_long=252, skip=21, horizon=21):
    """Signal at close(t); entry at close(t+1); exit at close(t+1+horizon).

    Uses exchange sessions, not row offsets, to prevent jumping across absent bars.
    Momentum = close(t-skip)/close(t-long)-1.
    Reversal = -(close(t)/close(t-skip)-1).
    Future price-only return = close(t+1+horizon)/close(t+1)-1.
    """
    if not (momentum_long>skip>=1 and horizon>=1):
        raise ValueError('Require momentum_long > skip >= 1 and horizon >= 1')
    sessions=pd.DatetimeIndex(sessions).sort_values().unique()
    if sessions.has_duplicates: raise ValueError('duplicate sessions')
    all_out=[]
    for symbol,x in raw.groupby('symbol'):
        x=x.set_index('date').sort_index()
        if x.index.has_duplicates: raise ValueError(f'duplicate dates: {symbol}')
        if not x.index.isin(sessions).all(): raise ValueError(f'bars outside exchange calendar: {symbol}')
        p=x['close'].reindex(sessions).astype(float)
        # Missing bars and non-positive prices are not imputed.
        # Require every exchange session in each factor and return window to be observed.
        ok=p.gt(0) & p.notna()
        bad=(~ok).astype(int)
        # rolling count over inclusive endpoint windows, aligned to t
        mom_complete=bad.rolling(momentum_long+1,min_periods=momentum_long+1).sum().eq(0)
        rev_complete=bad.rolling(skip+1,min_periods=skip+1).sum().eq(0)
        # forward window t+1 through t+1+horizon inclusive
        future_complete=bad.shift(-1).iloc[::-1].rolling(horizon+1,min_periods=horizon+1).sum().iloc[::-1].eq(0)
        out=pd.DataFrame({'date':sessions,'symbol':symbol,
            'momentum':(p.shift(skip)/p.shift(momentum_long)-1).where(mom_complete),
            'reversal':(-(p/p.shift(skip)-1)).where(rev_complete),
            'future_price_return':(p.shift(-(horizon+1))/p.shift(-1)-1).where(future_complete),
            'entry_date':pd.Series(sessions,index=sessions).shift(-1).values,
            'exit_date':pd.Series(sessions,index=sessions).shift(-(horizon+1)).values})
        all_out.append(out)
    return pd.concat(all_out,ignore_index=True)


def month_end_signals(panel):
    """One formation date per calendar month, chosen from global exchange sessions."""
    dates=pd.DatetimeIndex(panel['date'].unique()).sort_values()
    ends=pd.Series(dates,index=dates.to_period('M')).groupby(level=0).max()
    return panel.loc[panel['date'].isin(ends.values)].copy().sort_values(['date','symbol'])


def evaluate(panel, min_names=20, quantiles=5, oos_start='2023-01-01'):
    """Complete-case cross-sectional Rank IC and ex-post descriptive bins; NOT a tradable backtest.

    Each factor evaluated independently; no leakage of future returns into signals.
    """
    if min_names<3 or quantiles<2: raise ValueError('min_names >=3 and quantiles>=2')
    detail=[]; groups=[]
    for factor in ('momentum','reversal'):
        for dt,g in panel.groupby('date'):
            x=g[['symbol',factor,'future_price_return']].replace([np.inf,-np.inf],np.nan).dropna()
            if len(x)<min_names or x[factor].nunique()<2 or x['future_price_return'].nunique()<2:
                continue
            ic=float(x[factor].corr(x['future_price_return'],method='spearman'))
            split='oos' if pd.Timestamp(dt)>=pd.Timestamp(oos_start) else 'development'
            detail.append({'date':dt,'factor':factor,'split':split,'n':len(x),'rank_ic':ic})
            # Stable ranks avoid qcut errors from duplicate scores. Bins are descriptive.
            n_bins=min(quantiles,len(x))
            ordered=rank_bins(x,factor,n_bins,policy='complete_case')
            for b,part in ordered.groupby('bin'):
                groups.append({'date':dt,'factor':factor,'split':split,'bin':int(b),'n':len(part),
                               'mean_future_price_return':float(part['future_price_return'].mean())})
    return pd.DataFrame(detail,columns=['date','factor','split','n','rank_ic']),pd.DataFrame(groups,columns=['date','factor','split','bin','n','mean_future_price_return'])


def summary_table(ics):
    if ics.empty: return pd.DataFrame(columns=['factor','split','periods','mean_rank_ic','icir_descriptive'])
    result=[]
    for (factor,split),x in ics.groupby(['factor','split']):
        sd=x['rank_ic'].std(ddof=1)
        result.append({'factor':factor,'split':split,'periods':len(x),
                       'mean_rank_ic':float(x['rank_ic'].mean()),
                       'icir_descriptive':float(x['rank_ic'].mean()/sd) if pd.notna(sd) and sd>0 else np.nan})
    return pd.DataFrame(result)
