"""Exploratory factor inference and parameter stability.

This is NOT a PIT-certified backtest. HAC is a diagnostic, not a cure for
survivorship bias, overlapping targets, or retrospective adjustment.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .factors import factor_panel, month_end_signals, evaluate, load_sessions
from .collect import validate_bars


def hac_mean(x, lags=3):
    """Newey-West Bartlett HAC standard error of a time-series mean."""
    a=np.asarray(x,dtype=float); a=a[np.isfinite(a)]; n=len(a)
    if n<3:return dict(n=n,mean=float(np.mean(a)) if n else None,se=None,t=None,ci_low=None,ci_high=None)
    lags=min(max(int(lags),0),n-1)
    centered=a-a.mean()
    omega=float(np.dot(centered,centered)/n)
    for lag in range(1,lags+1):
        gamma=float(np.dot(centered[lag:],centered[:-lag])/n)
        omega+=2*(1-lag/(lags+1))*gamma
    se=float(np.sqrt(max(omega,0)/n))
    mean=float(a.mean())
    return dict(n=n,mean=mean,se=se,t=mean/se if se>0 else None,
                ci_low=mean-1.96*se,ci_high=mean+1.96*se)


def summarize_ic(ic,lags=3):
    rows=[]
    for (factor,split),g in ic.groupby(['factor','split']):
        z=hac_mean(g.sort_values('date')['rank_ic'],lags)
        rows.append({'factor':factor,'split':split,'hac_lags':lags,**z,
                     'positive_share':float((g.rank_ic>0).mean())})
    return pd.DataFrame(rows)


def annual_ic(ic):
    d=ic.copy();d['year']=pd.to_datetime(d.date).dt.year
    return d.groupby(['factor','split','year'],as_index=False).agg(
        periods=('rank_ic','size'),mean_rank_ic=('rank_ic','mean'),
        median_rank_ic=('rank_ic','median'),positive_share=('rank_ic',lambda x:float((x>0).mean())),
        mean_names=('n','mean'))


def quantile_spread(bins):
    if bins.empty:return pd.DataFrame(columns=['factor','split','periods','mean_high_minus_low','positive_share'])
    rows=[]
    for (factor,split,dt),g in bins.groupby(['factor','split','date']):
        g=g.sort_values('bin')
        if len(g)<2:continue
        rows.append({'factor':factor,'split':split,'date':dt,
                     'high_minus_low':float(g.iloc[-1].mean_future_price_return-g.iloc[0].mean_future_price_return)})
    x=pd.DataFrame(rows)
    if x.empty:return pd.DataFrame(columns=['factor','split','periods','mean_high_minus_low','positive_share'])
    return x.groupby(['factor','split'],as_index=False).agg(periods=('high_minus_low','size'),
        mean_high_minus_low=('high_minus_low','mean'),positive_share=('high_minus_low',lambda s:float((s>0).mean())))


def load_qfq(folder):
    frames=[]; excluded=[]
    for p in sorted(Path(folder).glob('*_qfq.csv')):
        sym=p.name.split('_')[0]
        if len(sym)!=6 or not sym.isdigit():continue
        try:
            x=validate_bars(pd.read_csv(p),sym)
            x=x[['date','close']].copy();x['symbol']=sym;frames.append(x)
        except Exception as e:excluded.append({'symbol':sym,'reason':str(e)})
    if not frames:raise ValueError('No valid *_qfq.csv files')
    return pd.concat(frames,ignore_index=True),excluded


def run(snapshots,output,oos_start='2023-01-01',min_names=20,hac_lags=3):
    folder=Path(snapshots);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    raw,excluded=load_qfq(folder)
    sessions=load_sessions(folder/'exchange_calendar.csv',raw.date.min(),raw.date.max())
    configs=[('baseline_252_21_21',252,21,21),('momentum_126_21_21',126,21,21),
             ('momentum_189_21_21',189,21,21),('reversal_252_5_21',252,5,21),
             ('reversal_252_10_21',252,10,21),('reversal_252_42_21',252,42,21)]
    all_sensitivity=[];baseline_ic=None;baseline_bins=None
    for label,long,skip,horizon in configs:
        panel=factor_panel(raw,sessions,momentum_long=long,skip=skip,horizon=horizon)
        formed=month_end_signals(panel)
        ic,bins=evaluate(formed,min_names=min_names,oos_start=oos_start)
        if label=='baseline_252_21_21':baseline_ic,baseline_bins=ic,bins
        for _,row in summarize_ic(ic,hac_lags).iterrows():
            if label.startswith('momentum_') and row.factor!='momentum':continue
            if label.startswith('reversal_') and row.factor!='reversal':continue
            all_sensitivity.append({'configuration':label,'momentum_long':long,'skip':skip,
                                    'forward_horizon':horizon,**row.to_dict()})
    if baseline_ic is None:raise ValueError('No baseline IC')
    inference=summarize_ic(baseline_ic,hac_lags)
    yearly=annual_ic(baseline_ic)
    spreads=quantile_spread(baseline_bins)
    sensitivity=pd.DataFrame(all_sensitivity)
    for name,data in [('rank_ic_baseline.csv',baseline_ic),('ic_inference.csv',inference),
                      ('annual_ic.csv',yearly),('quantile_spreads.csv',spreads),
                      ('parameter_sensitivity.csv',sensitivity),
                      ('excluded_qfq.csv',pd.DataFrame(excluded,columns=['symbol','reason']))]:
        data.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'exploratory_not_pit_or_tradable',
            'included_symbols':int(raw.symbol.nunique()),'excluded_symbols':len(excluded),
            'oos_start':oos_start,'min_names':min_names,'hac_lags':hac_lags,
            'baseline_ic_rows':len(baseline_ic),'sensitivity_configurations':[c[0] for c in configs],
            'cautions':['Retrospective qfq is not point-in-time certified.',
                        'Current-listed candidate universe has survivorship and selection bias.',
                        'HAC normal-approximation CI is descriptive; small sample and dependence remain.',
                        'Parameter sweeps are exploratory, not an untouched out-of-sample test.',
                        'No execution costs, price limits, suspensions or tradability model.',
                        'Bin spreads are forward-return descriptions, not portfolio PnL.']}
    (out/'robustness_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description='Exploratory factor diagnostics')
    p.add_argument('--snapshots',default='inputs/sina_snapshots')
    p.add_argument('--output',default='outputs/robustness')
    p.add_argument('--oos-start',default='2023-01-01')
    p.add_argument('--min-names',type=int,default=20)
    p.add_argument('--hac-lags',type=int,default=3)
    a=p.parse_args();print(json.dumps(run(a.snapshots,a.output,a.oos_start,a.min_names,a.hac_lags),indent=2))
if __name__=='__main__':main()
