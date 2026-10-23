"""Offline missing-return attribution and paired coverage sensitivity.

Only classify what the available evidence supports. No invented exit fills.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .collect import validate_bars

KEY=['date','factor','split']

def _load_bars(folder,symbol,kind,cache):
    key=(symbol,kind)
    if key in cache:return cache[key]
    p=Path(folder)/f'{symbol}_{kind}.csv'
    if not p.exists():cache[key]=None;return None
    try:cache[key]=validate_bars(pd.read_csv(p),symbol).set_index('date')['close']
    except Exception:cache[key]=None
    return cache[key]

def audit_members(members,snapshots=None,data_end=None):
    required=set(KEY+['symbol','entry_date','exit_date','observed_return','future_price_return','portfolio'])
    if not required.issubset(members):raise ValueError(f'missing member columns: {sorted(required-set(members))}')
    m=members.copy()
    for c in ['date','entry_date','exit_date']:m[c]=pd.to_datetime(m[c],errors='coerce')
    if m['date'].isna().any():raise ValueError('invalid formation dates')
    m['symbol']=m.symbol.astype(str).str.zfill(6)
    m['future_price_return']=pd.to_numeric(m.future_price_return,errors='coerce')
    if m.duplicated(KEY+['symbol']).any():raise ValueError('duplicate member key')
    m['is_observed']=m.future_price_return.notna()
    if (m['is_observed']!=m.observed_return.astype(str).str.lower().eq('true')).any():raise ValueError('observed flag conflicts with return')
    end=pd.Timestamp(data_end) if data_end else None
    cache={};records=[]
    for r in m.itertuples(index=False):
        reason='observed';qfirst=qend=raw_entry=raw_exit=q_entry=q_exit=np.nan
        if not r.is_observed:
            reason='unclassified_no_snapshot'
            if pd.isna(r.entry_date) or pd.isna(r.exit_date):reason='planned_horizon_dates_unavailable_at_sample_end'
            elif end is not None and r.exit_date>end:reason='horizon_beyond_declared_data_end'
            elif snapshots:
                q=_load_bars(snapshots,r.symbol,'qfq',cache)
                if q is None:reason='qfq_missing_or_invalid_file'
                elif q.empty:reason='qfq_empty'
                else:
                    qfirst=q.index.min();qend=q.index.max()
                    if r.entry_date<q.index.min():reason='entry_before_symbol_history'
                    elif r.exit_date>q.index.max():
                        # A local file ending before the planned exit is not proof of suspension/delisting.
                        reason='exit_after_symbol_last_bar_unknown_cause'
                    elif r.entry_date not in q.index:reason='entry_bar_missing'
                    elif r.exit_date not in q.index:reason='exit_bar_missing'
                    else:reason='interior_gap_or_signal_alignment'
        if snapshots and r.is_observed and abs(r.future_price_return)>=1.0:
            q=_load_bars(snapshots,r.symbol,'qfq',cache)
            raw=_load_bars(snapshots,r.symbol,'raw',cache)
            if q is not None and r.entry_date in q.index and r.exit_date in q.index:
                q_entry=float(q.loc[r.entry_date]);q_exit=float(q.loc[r.exit_date])
            if raw is not None and r.entry_date in raw.index and r.exit_date in raw.index:
                raw_entry=float(raw.loc[r.entry_date]);raw_exit=float(raw.loc[r.exit_date])
        records.append(dict(date=r.date,factor=r.factor,split=r.split,symbol=r.symbol,portfolio=r.portfolio,
            entry_date=r.entry_date,exit_date=r.exit_date,observed=r.is_observed,reason=reason,
            qfq_first_date=qfirst,qfq_last_date=qend,reported_return=r.future_price_return,
            raw_entry_close=raw_entry,raw_exit_close=raw_exit,qfq_entry_close=q_entry,qfq_exit_close=q_exit))
    a=pd.DataFrame(records)
    return a

def extreme_check(a,threshold=1.0):
    e=a[a.observed & (a.reported_return.abs()>=threshold)].copy()
    e['raw_horizon_return']=e.raw_exit_close/e.raw_entry_close-1
    e['qfq_horizon_return']=e.qfq_exit_close/e.qfq_entry_close-1
    e['reported_minus_qfq']=e.reported_return-e.qfq_horizon_return
    e['raw_minus_qfq']=e.raw_horizon_return-e.qfq_horizon_return
    e['verification_status']=np.select([
        e.qfq_horizon_return.isna(),
        (e.reported_minus_qfq.abs()>1e-6),
        e.raw_horizon_return.isna(),
        (e.raw_minus_qfq.abs()>0.02)],
        ['qfq_bars_unavailable','reported_qfq_mismatch','raw_bars_unavailable','raw_qfq_diverge_review_corporate_actions'],
        default='raw_qfq_consistent_not_execution_verified')
    return e

def coverage_sensitivity(cohorts,thresholds=(0.9,0.95,0.99,1.0)):
    required=set(KEY+['portfolio','coverage','net_after_fixed_cost','observed'])
    if not required.issubset(cohorts):raise ValueError('missing cohort fields')
    if cohorts.duplicated(KEY+['portfolio']).any():raise ValueError('duplicate cohort key')
    top=cohorts[cohorts.portfolio=='top_quintile'].set_index(KEY)
    all_=cohorts[cohorts.portfolio=='all_signals'].set_index(KEY)
    if set(top.index)!=set(all_.index):raise ValueError('unpaired cohort keys')
    z=top[['coverage','observed','net_after_fixed_cost']].join(all_[['coverage','observed','net_after_fixed_cost']],lsuffix='_top',rsuffix='_all').reset_index()
    z['paired_net_diff']=z.net_after_fixed_cost_top-z.net_after_fixed_cost_all
    out=[]
    for (factor,split),g in z.groupby(['factor','split']):
        for t in thresholds:
            if not 0<t<=1:raise ValueError('coverage threshold outside (0,1]')
            v=g[(g.coverage_top>=t)&(g.coverage_all>=t)&(g.observed_top>0)&(g.observed_all>0)].dropna(subset=['paired_net_diff'])
            out.append(dict(factor=factor,split=split,min_coverage=t,eligible_months=len(v),attempted_months=len(g),
                mean_paired_net_diff=v.paired_net_diff.mean(),median_paired_net_diff=v.paired_net_diff.median(),
                positive_month_share=(v.paired_net_diff>0).mean() if len(v) else np.nan,
                mean_top_coverage=v.coverage_top.mean(),mean_all_coverage=v.coverage_all.mean()))
    return pd.DataFrame(out),z

def run(members_path,cohorts_path,output,snapshots=None,data_end=None,threshold=1.0):
    members=pd.read_csv(members_path,dtype={'symbol':str})
    cohorts=pd.read_csv(cohorts_path)
    audit=audit_members(members,snapshots,data_end)
    extremes=extreme_check(audit,threshold)
    sensitivity,paired=coverage_sensitivity(cohorts)
    missing=audit[~audit.observed]
    reasons=missing.groupby(['factor','split','reason'],as_index=False).size().rename(columns={'size':'rows'})
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    for name,df in [('missing_outcome_audit.csv',missing),('missing_reason_summary.csv',reasons),
                    ('extreme_return_crosscheck.csv',extremes),('coverage_sensitivity.csv',sensitivity),('paired_coverage_monthly.csv',paired)]:
        df.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'exploratory_missingness_and_horizon_crosscheck',
        'members':len(audit),'missing_member_records':len(missing),'distinct_missing_symbol_dates':int(missing[['date','symbol']].drop_duplicates().shape[0]),
        'extreme_factor_symbol_records':len(extremes),'snapshot_folder_used':bool(snapshots),
        'declared_data_end':str(data_end) if data_end else None,
        'limitations':['Without snapshots, missing outcomes cannot be assigned a data-level cause.',
        'Exit after last symbol bar does not establish suspension or delisting.',
        'A declared data-end is a user-provided boundary, not inferred from observed exits.',
        'Observed-case coverage thresholds condition on future availability; not unbiased PnL.',
        'Raw vs retrospective QFQ differences do not independently verify corporate actions.',
        'Repeated factor rows are not independent price events.',
        'Current-listed universe and retrospectively adjusted QFQ remain non-PIT.',
        'No execution, price-limit, turnover, liquidity or complete transaction-cost model.',
        '2023+ has been repeatedly explored; not a pristine holdout.']}
    (out/'missing_audit_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description='Offline missingness audit, coverage sensitivity and extreme-return cross-check')
    p.add_argument('--cohort-members',default='outputs/portfolio/cohort_members.csv')
    p.add_argument('--cohort-returns',default='outputs/portfolio/cohort_returns.csv')
    p.add_argument('--snapshots',default=None,help='optional local inputs/sina_snapshots for price evidence; never downloads')
    p.add_argument('--data-end',default=None,help='optional explicit last date of source download, YYYY-MM-DD')
    p.add_argument('--output',default='outputs/missing_audit')
    p.add_argument('--tail-threshold',type=float,default=1.0)
    a=p.parse_args()
    print(json.dumps(run(a.cohort_members,a.cohort_returns,a.output,a.snapshots,a.data_end,a.tail_threshold),indent=2))
if __name__=='__main__':main()
