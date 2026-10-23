"""Exploratory, ex-ante sample-proxy regime stratification of factor outcomes.

Regime known by formation close; proxy is NOT a broad market benchmark.
The sample universe is retrospectively selected and price series are retrospective QFQ.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .robustness import load_qfq, hac_mean
from .factors import load_sessions


def build_proxy(bars, sessions, min_daily_names=20, trend_days=63, vol_days=21, vol_history=252):
    """Equal-weight daily sample proxy; only consecutive session returns count.

    Volatility threshold uses PRIOR observed rolling volatility values, excluding
    the formation-day volatility; at least 63 prior observations required.
    """
    if min_daily_names<2 or trend_days<2 or vol_days<3 or vol_history<63:
        raise ValueError('invalid regime settings')
    dates=pd.DatetimeIndex(sessions).sort_values().unique()
    panel=bars.pivot(index='date',columns='symbol',values='close').reindex(dates)
    valid=panel.where(panel>0)
    # pct_change(fill_method=None) prevents accidental padding across missing bars.
    returns=valid.pct_change(fill_method=None).replace([np.inf,-np.inf],np.nan)
    count=returns.notna().sum(axis=1)
    ew=returns.mean(axis=1).where(count>=min_daily_names)
    # Rolling cumulative sample proxy (not a tradable index); no missing days allowed.
    logret=np.log1p(ew.where(ew>-1))
    trend=np.expm1(logret.rolling(trend_days,min_periods=trend_days).sum())
    vol=ew.rolling(vol_days,min_periods=vol_days).std(ddof=1)
    prior_med=vol.shift(1).rolling(vol_history,min_periods=63).median()
    state=pd.DataFrame({'date':dates,'proxy_daily_return':ew.values,
                        'daily_names':count.values,'trailing_trend':trend.values,
                        'trailing_volatility':vol.values,'prior_vol_median':prior_med.values})
    state['trend_regime']=np.where(state.trailing_trend.notna(),
                    np.where(state.trailing_trend>=0,'up','down'),None)
    state['vol_regime']=np.where(state.trailing_volatility.notna() & state.prior_vol_median.notna(),
                    np.where(state.trailing_volatility>=state.prior_vol_median,'high','low'),None)
    state['regime']=state.trend_regime.fillna('unknown')+'_'+state.vol_regime.fillna('unknown')
    return state


def join_diagnostics(monthly, proxy, min_names=20):
    required={'date','factor','split','n','rank_ic','mean_spread'}
    if not required.issubset(monthly.columns):
        raise ValueError(f'monthly diagnostics missing {sorted(required-set(monthly.columns))}')
    m=monthly.copy();m['date']=pd.to_datetime(m.date).dt.normalize()
    if m.duplicated(['date','factor']).any(): raise ValueError('duplicate factor/date rows')
    m=m.loc[(m.n>=min_names) & np.isfinite(pd.to_numeric(m.rank_ic,errors='coerce'))].copy()
    p=proxy[['date','daily_names','trailing_trend','trailing_volatility','prior_vol_median','trend_regime','vol_regime','regime']]
    out=m.merge(p,on='date',how='left',validate='many_to_one')
    out['year']=out.date.dt.year
    out['regime_eligible']=out.trend_regime.notna() & out.vol_regime.notna()
    return out.sort_values(['factor','date']).reset_index(drop=True)


def summarize(merged, min_months=6, hac_lags=3):
    eligible=merged.loc[merged.regime_eligible].copy()
    rows=[]
    for (factor,split,regime),g in eligible.groupby(['factor','split','regime'],sort=True):
        g=g.sort_values('date')
        ic=hac_mean(g.rank_ic,hac_lags)
        spread=hac_mean(g.mean_spread,hac_lags)
        rows.append({'factor':factor,'split':split,'regime':regime,'months':len(g),
                     'mean_rank_ic':ic['mean'],'ic_hac_t_descriptive':ic['t'] if len(g)>=min_months else np.nan,
                     'mean_q5_q1_spread':spread['mean'],
                     'spread_hac_t_descriptive':spread['t'] if len(g)>=min_months else np.nan,
                     'positive_ic_share':float((g.rank_ic>0).mean()),
                     'positive_spread_share':float((g.mean_spread>0).mean()),
                     'sufficient_months':len(g)>=min_months})
    cols=['factor','split','regime','months','mean_rank_ic','ic_hac_t_descriptive',
          'mean_q5_q1_spread','spread_hac_t_descriptive','positive_ic_share',
          'positive_spread_share','sufficient_months']
    return pd.DataFrame(rows,columns=cols)


def annual(merged):
    x=merged.loc[merged.regime_eligible]
    if x.empty:return pd.DataFrame(columns=['factor','split','year','regime','months','mean_rank_ic','mean_q5_q1_spread'])
    return x.groupby(['factor','split','year','regime'],as_index=False).agg(
        months=('rank_ic','size'),mean_rank_ic=('rank_ic','mean'),mean_q5_q1_spread=('mean_spread','mean'))


def run(snapshots,monthly_diagnostics,output,min_daily_names=20,trend_days=63,
        vol_days=21,vol_history=252,min_regime_months=6):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    bars,excluded=load_qfq(snapshots)
    sessions=load_sessions(Path(snapshots)/'exchange_calendar.csv',bars.date.min(),bars.date.max())
    proxy=build_proxy(bars,sessions,min_daily_names,trend_days,vol_days,vol_history)
    merged=join_diagnostics(pd.read_csv(monthly_diagnostics),proxy)
    summary=summarize(merged,min_regime_months)
    yearly=annual(merged)
    for name,data in [('sample_market_proxy.csv',proxy),('monthly_regime_diagnostics.csv',merged),
                      ('regime_summary.csv',summary),('regime_annual.csv',yearly)]:
        data.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'exploratory_regime_analysis_not_predictive_validation',
      'included_symbols':int(bars.symbol.nunique()),'excluded_symbols':len(excluded),
      'monthly_factor_rows':len(merged),'regime_eligible_rows':int(merged.regime_eligible.sum()),
      'min_daily_names':min_daily_names,'trend_days':trend_days,'vol_days':vol_days,
      'vol_history':vol_history,'min_regime_months':min_regime_months,
      'warnings':['Regime proxy uses the same retrospectively selected 100-stock sample, not a broad-market index.',
       'Regime variables use prices observable by formation close, but QFQ prices are retrospectively adjusted.',
       'Factor outcomes are descriptive Rank IC and Q5-Q1, not executable returns.',
       'The 2023+ sample has been repeatedly examined; all regime comparisons are exploratory.',
       'Regime subgroup t-statistics are descriptive, not multiple-testing-adjusted evidence.',
       'Sample-proxy daily returns exclude stocks missing either adjacent session; composition varies.',
       'Trailing proxy trend is based on compounding daily equal-weight sample returns, not an investable index.']}
    (out/'regime_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description='Sample market-regime and factor-stability diagnostics')
    p.add_argument('--snapshots',default='inputs/sina_snapshots')
    p.add_argument('--monthly-diagnostics',default='outputs/distribution/monthly_diagnostics.csv')
    p.add_argument('--output',default='outputs/regime')
    p.add_argument('--min-daily-names',type=int,default=20)
    p.add_argument('--trend-days',type=int,default=63)
    p.add_argument('--vol-days',type=int,default=21)
    p.add_argument('--vol-history',type=int,default=252)
    p.add_argument('--min-regime-months',type=int,default=6)
    a=p.parse_args()
    print(json.dumps(run(a.snapshots,a.monthly_diagnostics,a.output,a.min_daily_names,
                         a.trend_days,a.vol_days,a.vol_history,a.min_regime_months),indent=2))
if __name__=='__main__':main()
