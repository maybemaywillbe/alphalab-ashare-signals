"""Price-event review and non-executable monthly cohort simulations.

Cohorts are selected from signals only; realized-return availability is separately
reported to avoid silently hiding delisted/missing exits. No daily NAV claim.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .collect import validate_bars
from .robustness import load_qfq
from .factors import load_sessions, factor_panel, month_end_signals
from .selection import rank_bins


def review_price_events(folder, threshold=.30):
    """Flag jumps in raw and qfq at matched dates; NEVER infer corporate action."""
    rows=[]
    for rp in sorted(Path(folder).glob('*_raw.csv')):
        sym=rp.name[:6]; qp=Path(folder)/f'{sym}_qfq.csv'
        if not qp.exists(): continue
        try:
            a=validate_bars(pd.read_csv(rp),sym)[['date','close']].rename(columns={'close':'raw_close'})
            b=validate_bars(pd.read_csv(qp),sym)[['date','close']].rename(columns={'close':'qfq_close'})
            z=a.merge(b,on='date',how='outer',indicator=True).sort_values('date')
            both=z[z['_merge']=='both'].copy()
            both['raw_change']=both.raw_close.pct_change()
            both['qfq_change']=both.qfq_close.pct_change()
            both['calendar_gap_days']=both.date.diff().dt.days
            flagged=both[(both.raw_change.abs()>=threshold)|(both.qfq_change.abs()>=threshold)]
            for r in flagged.itertuples():
                rows.append(dict(symbol=sym,date=r.date,raw_close=r.raw_close,qfq_close=r.qfq_close,
                    raw_change=r.raw_change,qfq_change=r.qfq_change,calendar_gap_days=r.calendar_gap_days,
                    review_reason='large_raw_and_qfq' if abs(r.raw_change)>=threshold and abs(r.qfq_change)>=threshold else ('large_raw_only' if abs(r.raw_change)>=threshold else 'large_qfq_only'),
                    verified_corporate_action=False))
            for r in z[z['_merge']!='both'].itertuples():
                rows.append(dict(symbol=sym,date=r.date,raw_close=r.raw_close,qfq_close=r.qfq_close,
                    raw_change=np.nan,qfq_change=np.nan,calendar_gap_days=np.nan,
                    review_reason='raw_qfq_date_mismatch',verified_corporate_action=False))
        except Exception as exc:
            rows.append(dict(symbol=sym,date=pd.NaT,raw_close=np.nan,qfq_close=np.nan,
                raw_change=np.nan,qfq_change=np.nan,calendar_gap_days=np.nan,
                review_reason=f'validation_error: {str(exc)[:140]}',verified_corporate_action=False))
    return pd.DataFrame(rows,columns=['symbol','date','raw_close','qfq_close','raw_change','qfq_change','calendar_gap_days','review_reason','verified_corporate_action'])


def simulate_cohorts(formed, min_names=20, quantiles=5, side_cost_bps=10, oos_start='2023-01-01'):
    """Equal-name top-quintile vs full eligible universe, cohort-by-cohort.

    Membership never conditions on forward return. No rebalance/turnover or
    executable long-short. Missing outcomes are NOT assumed to be zero.
    """
    if min_names<quantiles or side_cost_bps<0:raise ValueError('invalid minimum names or cost')
    out=[];members=[]
    for factor in ('momentum','reversal'):
        for dt,g in formed.groupby('date',sort=True):
            eligible=g[['date','symbol','entry_date','exit_date',factor,'future_price_return']].copy()
            eligible=eligible.replace([np.inf,-np.inf],np.nan).dropna(subset=[factor])
            if len(eligible)<min_names or eligible[factor].nunique()<2:continue
            eligible=rank_bins(eligible,factor,quantiles,policy='signal')
            eligible['portfolio']=np.where(eligible.bin==quantiles,'top_quintile','other')
            eligible['observed_return']=eligible.future_price_return.notna()
            split='oos' if pd.Timestamp(dt)>=pd.Timestamp(oos_start) else 'development'
            for _,r in eligible.iterrows():
                members.append(dict(date=dt,factor=factor,split=split,symbol=r.symbol,bin=int(r.bin),
                    portfolio=r.portfolio,entry_date=r.entry_date,exit_date=r.exit_date,
                    observed_return=bool(r.observed_return),future_price_return=r.future_price_return))
            for name,part in [('top_quintile',eligible[eligible.bin==quantiles]),('all_signals',eligible)]:
                n=len(part); observed=part.future_price_return.dropna();nobs=len(observed)
                # Two one-way costs: buy at next close, sell at horizon close.
                gross=float(observed.mean()) if nobs else np.nan
                cost=2*side_cost_bps/10000
                out.append(dict(date=dt,factor=factor,split=split,portfolio=name,
                    selected=n,observed=nobs,missing_outcome=n-nobs,coverage=nobs/n,
                    gross_mean_observed=gross,net_after_fixed_cost=gross-cost if nobs else np.nan,
                    fixed_cost_scenario_return=gross-cost if nobs else np.nan,
                    assumed_roundtrip_cost=cost,fully_observed=nobs==n,
                    assumption='illustrative uniform two-way fixed cost; cancels versus equal-cost benchmark; no turnover, price limits, suspension or liquidity'))
    return pd.DataFrame(out),pd.DataFrame(members)


def run(snapshots,output,min_names=20,side_cost_bps=10,oos_start='2023-01-01'):
    folder=Path(snapshots);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    events=review_price_events(folder)
    raw,excluded=load_qfq(folder)
    sessions=load_sessions(folder/'exchange_calendar.csv',raw.date.min(),raw.date.max())
    formed=month_end_signals(factor_panel(raw,sessions))
    cohorts,members=simulate_cohorts(formed,min_names,5,side_cost_bps,oos_start)
    if cohorts.empty:raise ValueError('No eligible cohorts')
    # Only full-outcome cohorts qualify for summary; no silent survivor-only average.
    valid=cohorts[cohorts.fully_observed].copy()
    summary=valid.groupby(['factor','split','portfolio'],as_index=False).agg(
        fully_observed_cohorts=('date','size'),avg_gross=('gross_mean_observed','mean'),
        avg_net_fixed_cost=('net_after_fixed_cost','mean'))
    total=cohorts.groupby(['factor','split','portfolio'],as_index=False).agg(
        attempted_cohorts=('date','size'),partial_cohorts=('fully_observed',lambda s:int((~s).sum())),
        mean_outcome_coverage=('coverage','mean'))
    summary=total.merge(summary,how='left',on=['factor','split','portfolio'])
    for name,frame in [('price_event_review.csv',events),('cohort_members.csv',members),
        ('cohort_returns.csv',cohorts),('cohort_summary.csv',summary),
        ('excluded_qfq.csv',pd.DataFrame(excluded,columns=['symbol','reason']))]:frame.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'exploratory_non_executable_cohort_analysis',
        'price_events_flagged':len(events),'cohort_rows':len(cohorts),
        'cohorts_with_missing_outcomes':int((~cohorts.fully_observed).sum()),
        'one_way_cost_bps':side_cost_bps,
        'limitations':['Current-listed sample; survivorship bias unresolved.',
          'Retrospective QFQ; not a point-in-time certified total-return series.',
          'Month-end entry next-session close and exit 21 sessions later: cohort windows can overlap; do not compound into NAV.',
          'Membership uses only signals, but future availability is not guaranteed; incomplete cohorts excluded from summary.',
          'Fixed cost sensitivity is NOT measured turnover or executable PnL.',
          'No independent corporate-action events, price limits, suspension or liquidity evidence.',
          '2023+ has been examined repeatedly and is no longer an untouched holdout.']}
    (out/'portfolio_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description='Event review and exploratory non-executable cohort analysis')
    p.add_argument('--snapshots',default='inputs/sina_snapshots');p.add_argument('--output',default='outputs/portfolio')
    p.add_argument('--min-names',type=int,default=20);p.add_argument('--side-cost-bps',type=float,default=10)
    a=p.parse_args();print(json.dumps(run(a.snapshots,a.output,a.min_names,a.side_cost_bps),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
