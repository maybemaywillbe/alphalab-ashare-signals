"""Paired cohort diagnostics from saved cohort outputs. No network or downloads.

Paired full observations are the primary descriptive comparison; partial-case
comparisons are sensitivity only, not imputed tradable returns.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

KEY=['date','factor','split']

def analyze(cohorts: pd.DataFrame, members: pd.DataFrame, tail_threshold: float=1.0):
    if tail_threshold<=0: raise ValueError('tail threshold must be positive')
    required=set(KEY+['portfolio','selected','observed','coverage','gross_mean_observed','net_after_fixed_cost','fully_observed'])
    if not required.issubset(cohorts): raise ValueError(f'missing cohort columns: {sorted(required-set(cohorts))}')
    if cohorts.duplicated(KEY+['portfolio']).any(): raise ValueError('duplicate cohort key')
    a=cohorts.loc[cohorts.portfolio=='top_quintile'].set_index(KEY)
    b=cohorts.loc[cohorts.portfolio=='all_signals'].set_index(KEY)
    if not a.index.equals(b.index):
        if set(a.index)!=set(b.index): raise ValueError('unpaired cohort dates')
        b=b.reindex(a.index)
    if a.empty: raise ValueError('no paired cohorts')
    paired=a[['selected','observed','coverage','gross_mean_observed','net_after_fixed_cost','fully_observed']].join(
        b[['selected','observed','coverage','gross_mean_observed','net_after_fixed_cost','fully_observed']],lsuffix='_top',rsuffix='_all').reset_index()
    paired['both_full']=paired.fully_observed_top.astype(bool)&paired.fully_observed_all.astype(bool)
    paired['both_have_some']= (paired.observed_top>0)&(paired.observed_all>0)
    paired['gross_diff_observed']=paired.gross_mean_observed_top-paired.gross_mean_observed_all
    paired['net_diff_observed']=paired.net_after_fixed_cost_top-paired.net_after_fixed_cost_all
    paired['fixed_cost_diff_observed']=paired['net_diff_observed']
    paired['fixed_cost_cancels']=np.isclose(paired['gross_diff_observed'],paired['net_diff_observed'], equal_nan=True)
    if not bool(paired['fixed_cost_cancels'].all()):
        raise ValueError('common fixed cost differs across groups; paired interpretation invalid')
    paired['completeness_class']=np.select([paired.both_full,paired.both_have_some],['both_full','partial_observed'],default='no_observed_pair')
    summary=[]
    for (factor,split),g in paired.groupby(['factor','split'],sort=True):
        full=g[g.both_full];partial=g[g.both_have_some]
        summary.append(dict(factor=factor,split=split,attempted_months=len(g),both_full_months=len(full),
          partial_or_missing_months=int((~g.both_full).sum()),both_some_months=len(partial),
          full_paired_mean_gross_diff=full.gross_diff_observed.mean(),
          full_paired_mean_net_diff=full.net_diff_observed.mean(),
          full_paired_positive_share=(full.net_diff_observed>0).mean() if len(full) else np.nan,
          partial_observed_mean_net_diff=partial.net_diff_observed.mean(),
          mean_top_coverage=g.coverage_top.mean(),mean_all_coverage=g.coverage_all.mean()))
    summary=pd.DataFrame(summary)
    # No imputation; extreme forward returns are flagged, never silently dropped.
    if not {'date','factor','split','symbol','bin','observed_return','future_price_return'}.issubset(members):
        raise ValueError('missing cohort_members columns')
    tail=members.copy();tail['future_price_return']=pd.to_numeric(tail.future_price_return,errors='coerce')
    tail=tail[tail.future_price_return.abs()>=tail_threshold].copy()
    tail['abs_return']=tail.future_price_return.abs()
    tail=tail.sort_values('abs_return',ascending=False)
    # Compare dates to prior IC eligibility separately; do not equate different eligibility rules.
    calendar=paired.groupby(['factor','split'],as_index=False).agg(first_date=('date','min'),last_date=('date','max'),cohort_dates=('date','size'),full_dates=('both_full','sum'))
    return paired,summary,tail,calendar

def run(cohort_returns,cohort_members,output,tail_threshold=1.0):
    cohorts=pd.read_csv(cohort_returns,dtype={'factor':str,'split':str})
    members=pd.read_csv(cohort_members,dtype={'symbol':str,'factor':str,'split':str})
    for df in (cohorts,members): df['date']=pd.to_datetime(df['date'])
    paired,summary,tail,calendar=analyze(cohorts,members,tail_threshold)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    for filename,df in [('paired_monthly.csv',paired),('paired_summary.csv',summary),('extreme_horizon_returns.csv',tail),('cohort_calendar.csv',calendar)]:
        df.to_csv(out/filename,index=False)
    report={'version':'1.0.0','status':'paired_diagnostic_only','paired_rows':len(paired),
      'both_full_rows':int(paired.both_full.sum()),'extreme_horizon_rows':len(tail),
      'limitations':['Paired full-case comparison is conditioned on future outcome availability and may be selected.',
       'Partial observed-case comparison is a sensitivity analysis, not an executable or imputed portfolio.',
       'All-signals benchmark contains the top quintile, so differences are not independent.',
       'Equal fixed roundtrip costs cancel in paired net differences; not a turnover model.',
       'Extreme horizon returns are flags, not verified corporate actions or valid executions.',
       'Retrospective QFQ and current-listed universe are not PIT certified.',
       '2023+ has been repeatedly inspected; it is no longer a pristine holdout.']}
    (out/'paired_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description='Paired cohort analysis (offline)')
    p.add_argument('--cohort-returns',default='outputs/portfolio/cohort_returns.csv')
    p.add_argument('--cohort-members',default='outputs/portfolio/cohort_members.csv')
    p.add_argument('--output',default='outputs/paired')
    p.add_argument('--tail-threshold',type=float,default=1.0,help='absolute 21-session return threshold; 1.0 means 100%%')
    a=p.parse_args()
    print(json.dumps(run(a.cohort_returns,a.cohort_members,a.output,a.tail_threshold),indent=2))
if __name__=='__main__': main()
