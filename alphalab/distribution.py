"""Diagnose why positive rank IC can coexist with negative Q5-Q1.
Exploratory, retrospective QFQ; no executable portfolio inference.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from .robustness import load_qfq
from .factors import factor_panel,month_end_signals,load_sessions,evaluate
from .selection import rank_bins

def analyze_formed(formed, min_names=20, oos_start='2023-01-01', quantiles=5):
    detail=[]; binrows=[]; tails=[]
    for factor in ('momentum','reversal'):
        for dt,g in formed.groupby('date',sort=True):
            x=g[['symbol',factor,'future_price_return']].replace([np.inf,-np.inf],np.nan).dropna().copy()
            if len(x)<min_names or x[factor].nunique()<2 or x.future_price_return.nunique()<2:continue
            x=rank_bins(x,factor,quantiles,policy='complete_case')
            ret=x.future_price_return
            # Cross-sectional clipping, not PIT return corrections; diagnostic only.
            x['ret_w01']=ret.clip(*ret.quantile([.01,.99]).values)
            x['ret_w05']=ret.clip(*ret.quantile([.05,.95]).values)
            split='oos' if pd.Timestamp(dt)>=pd.Timestamp(oos_start) else 'development'
            group=x.groupby('bin')
            stats=group.agg(n=('symbol','size'),mean_return=('future_price_return','mean'),median_return=('future_price_return','median'),winsor_1pct=('ret_w01','mean'),winsor_5pct=('ret_w05','mean')).reset_index()
            for _,r in stats.iterrows():binrows.append({'date':dt,'factor':factor,'split':split,**r.to_dict()})
            hi,lo=stats.iloc[-1],stats.iloc[0]
            ic=float(x[factor].corr(x.future_price_return,method='spearman'))
            spread=float(hi.mean_return-lo.mean_return)
            detail.append(dict(date=dt,factor=factor,split=split,n=len(x),rank_ic=ic,
                mean_spread=spread,median_spread=float(hi.median_return-lo.median_return),
                winsor_1pct_spread=float(hi.winsor_1pct-lo.winsor_1pct),
                winsor_5pct_spread=float(hi.winsor_5pct-lo.winsor_5pct),
                discordant=bool(ic>0 and spread<0),
                high_max_return=float(x.loc[x.bin==x.bin.max(),'future_price_return'].max()),
                low_max_return=float(x.loc[x.bin==x.bin.min(),'future_price_return'].max())))
            # Per-name contributions to the Q5-Q1 equal-name mean, signed by side.
            for b,sign in ((1,-1),(int(x.bin.max()),1)):
                p=x[x.bin==b]
                for _,r in p.iterrows():
                    tails.append(dict(date=dt,factor=factor,split=split,symbol=r.symbol,bin=b,
                        future_price_return=float(r.future_price_return),
                        contribution=float(sign*r.future_price_return/len(p)),
                        side='high' if sign==1 else 'low'))
    d=pd.DataFrame(detail); b=pd.DataFrame(binrows); t=pd.DataFrame(tails)
    if d.empty:raise ValueError('No eligible factor dates')
    cols=['mean_spread','median_spread','winsor_1pct_spread','winsor_5pct_spread']
    rows=[]
    for (f,s),g in d.groupby(['factor','split']):
        row={'factor':f,'split':s,'periods':len(g),'mean_rank_ic':float(g.rank_ic.mean()),
             'positive_ic_share':float((g.rank_ic>0).mean()),
             'positive_spread_share':float((g.mean_spread>0).mean()),
             'discordant_share':float(g.discordant.mean())}
        for c in cols:row['avg_'+c]=float(g[c].mean())
        rows.append(row)
    summary=pd.DataFrame(rows)
    return d,b,t,summary

def run(snapshots,output,min_names=20,oos_start='2023-01-01'):
    folder=Path(snapshots);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    raw,excluded=load_qfq(folder)
    sessions=load_sessions(folder/'exchange_calendar.csv',raw.date.min(),raw.date.max())
    formed=month_end_signals(factor_panel(raw,sessions))
    dates,bins,tails,summary=analyze_formed(formed,min_names,oos_start)
    ic,baseline_bins=evaluate(formed,min_names=min_names,oos_start=oos_start)
    merged=dates.merge(ic[['date','factor','rank_ic']],on=['date','factor'],suffixes=('_diagnostic','_baseline'),validate='one_to_one')
    if len(merged)!=len(ic) or not np.allclose(merged.rank_ic_diagnostic,merged.rank_ic_baseline,rtol=0,atol=1e-12):
        raise AssertionError('Baseline IC mismatch; diagnostics must reproduce baseline')
    old=baseline_bins.pivot_table(index=['date','factor'],columns='bin',values='mean_future_price_return')
    new=dates.set_index(['date','factor'])['mean_spread']
    expected=old[5]-old[1]
    if not np.allclose(new.loc[expected.index],expected,rtol=0,atol=1e-12):
        raise AssertionError('Baseline quantile spread mismatch')
    annual=dates.assign(year=pd.to_datetime(dates.date).dt.year).groupby(['factor','split','year'],as_index=False).agg(periods=('mean_spread','size'),mean_ic=('rank_ic','mean'),mean_spread=('mean_spread','mean'),mean_winsor_5pct_spread=('winsor_5pct_spread','mean'),discordant_share=('discordant','mean'))
    worst=tails.sort_values('contribution').groupby(['factor','split'],group_keys=False).head(15)
    for name,frame in [('monthly_diagnostics.csv',dates),('bin_distributions.csv',bins),('tail_contributions.csv',tails),('worst_tail_contributions.csv',worst),('spread_summary.csv',summary),('annual_spread.csv',annual)]:frame.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'exploratory_distribution_diagnostics','included_symbols':int(raw.symbol.nunique()),'excluded_symbols':len(excluded),'months':len(dates),'baseline_reproduced':True,'summary':summary.to_dict(orient='records'),'limitations':['Winsorization is an ex-post robustness diagnostic, not a tradable return adjustment.','Mean-vs-median spreads compare different estimands; median spreads are not portfolio PnL.','QFQ is retrospectively adjusted and universe is current-listed, not point-in-time.','No tradability, fees, shorting, or execution model.','Multiple analyses are exploratory; 2023–2025 was examined during development and is not an untouched holdout.']}
    (out/'distribution_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description='Diagnose IC vs high-low quantile spread disagreement')
    p.add_argument('--snapshots',default='inputs/sina_snapshots');p.add_argument('--output',default='outputs/distribution')
    p.add_argument('--min-names',type=int,default=20);p.add_argument('--oos-start',default='2023-01-01')
    a=p.parse_args();r=run(a.snapshots,a.output,a.min_names,a.oos_start)
    print(json.dumps({'version':r['version'],'months':r['months'],'baseline_reproduced':r['baseline_reproduced'],'output':a.output},indent=2))
if __name__=='__main__':main()
