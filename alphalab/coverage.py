"""Auditable cross-sectional coverage, with no fabricated universe history."""
from __future__ import annotations
import numpy as np
import pandas as pd

FACTORS=('momentum','reversal')

def coverage_table(formed, min_names=20, oos_start='2023-01-01'):
    if min_names<3: raise ValueError('min_names must be >= 3')
    rows=[]
    for dt,g in formed.groupby('date'):
        for factor in FACTORS:
            signal=g[factor].replace([np.inf,-np.inf],np.nan).notna()
            target=g['future_price_return'].replace([np.inf,-np.inf],np.nan).notna()
            paired=signal & target
            n=int(paired.sum())
            valid=n>=min_names and g.loc[paired,factor].nunique()>1 and g.loc[paired,'future_price_return'].nunique()>1
            rows.append({'date':dt,'factor':factor,'split':'oos' if pd.Timestamp(dt)>=pd.Timestamp(oos_start) else 'development',
                'universe_rows':len(g),'signal_available':int(signal.sum()),'future_available':int(target.sum()),
                'paired_available':n,'paired_coverage':n/len(g) if len(g) else np.nan,
                'min_names':min_names,'eligible_for_ic':bool(valid),
                'reason':'eligible' if valid else ('insufficient_names' if n<min_names else 'constant_values')})
    return pd.DataFrame(rows,columns=['date','factor','split','universe_rows','signal_available','future_available','paired_available','paired_coverage','min_names','eligible_for_ic','reason'])

def universe_history_check(path, symbols, sessions):
    """Optional evidence inventory only; never treats unverified dates as certified."""
    from pathlib import Path
    if not path or not Path(path).exists():
        return {'status':'unverified','reason':'No independent historical security master supplied','symbols_checked':len(symbols)}
    x=pd.read_csv(path,dtype={'symbol':str})
    required={'symbol','listed_on','delisted_on','source','verified'}
    if not required.issubset(x.columns): raise ValueError(f'universe evidence missing columns: {sorted(required-set(x.columns))}')
    x=x[x.symbol.isin(symbols)]
    valid=x[x.verified.astype(str).str.lower().isin(['true','1','yes'])]
    # Even user-marked verified evidence is not independently authenticated.
    return {'status':'user_evidence_only_not_certified','rows':len(x),'user_marked_verified_rows':len(valid),
            'symbols_without_rows':sorted(set(symbols)-set(x.symbol))}
