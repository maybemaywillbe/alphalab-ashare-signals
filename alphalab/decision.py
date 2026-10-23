"""Evidence-driven data gate. Never infer suspension, IPO, or corporate actions from bars alone."""
from __future__ import annotations
import argparse, json, csv, hashlib
from pathlib import Path
import pandas as pd

def load_csv(path):
    return pd.read_csv(path, dtype={'symbol':str}) if path and Path(path).exists() else None

def classify_gaps(gaps, evidence):
    evidence=evidence if evidence is not None else pd.DataFrame(columns=['symbol','date','classification','source_url'])
    out=[]
    for symbol, dates in gaps.items():
        for date in dates:
            match=evidence[(evidence['symbol'].astype(str).str.zfill(6)==symbol)&(evidence['date'].astype(str)==date)] if len(evidence) else pd.DataFrame()
            if len(match) and str(match.iloc[0].get('classification','')) in ('suspended','vendor_missing','other') and str(match.iloc[0].get('source_url','')).startswith(('https://','http://')):
                row=match.iloc[0]
                out.append({'symbol':symbol,'date':date,'status':str(row['classification']),'evidence':str(row['source_url'])})
            else: out.append({'symbol':symbol,'date':date,'status':'unverified','evidence':None})
    return out

def qfq_diagnostic(path):
    if not path.exists(): return {'status':'csv_not_supplied'}
    df=pd.read_csv(path)
    required={'date','open','high','low','close'}
    if not required.issubset(df): return {'status':'invalid_columns'}
    problems=[]
    for col in ['open','high','low','close']:
        values=pd.to_numeric(df[col],errors='coerce')
        bad=df.loc[values.le(0) | values.isna(),['date',col]]
        for _,r in bad.head(15).iterrows(): problems.append({'date':str(r['date']),'column':col,'value':None if pd.isna(r[col]) else str(r[col])})
    counts={c:int((pd.to_numeric(df[c],errors='coerce')<=0).sum()) for c in ['open','high','low','close']}
    return {'status':'inspected','nonpositive_counts':counts,'examples':problems,'example_truncated':sum(counts.values())>len(problems)}

def main():
    p=argparse.ArgumentParser(description='Evaluate saved data-quality results without downloading data')
    p.add_argument('--audit',default='inputs/audit.json')
    p.add_argument('--snapshots',default='inputs/snapshots')
    p.add_argument('--evidence-dir',default='evidence')
    p.add_argument('--output',default='outputs/data_decision')
    args=p.parse_args(); audit=json.loads(Path(args.audit).read_text(encoding='utf-8'))
    output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    root=Path(args.snapshots); ev=Path(args.evidence_dir)
    susp=load_csv(ev/'suspensions.csv'); listing=load_csv(ev/'listing_history.csv')
    gaps={}; qfq={}; all_downloads=True
    for r in audit.get('results',[]):
        symbol=str(r.get('symbol','')).zfill(6); mode=r.get('adjustment')
        if r.get('fetch_status')!='ok': all_downloads=False
        if mode=='raw':
            gaps[symbol]=r.get('calendar_coverage',{}).get('missing_session_dates_sample',[])
            # The prior audit exposes at most 20 dates; if truncated, mark evidence coverage incomplete.
        if mode=='qfq': qfq[symbol]=qfq_diagnostic(root/f'{symbol}_qfq.csv')
    gap_rows=classify_gaps(gaps,susp)
    total_missing=sum(r.get('calendar_coverage',{}).get('missing_within_observed_span',0) for r in audit.get('results',[]) if r.get('adjustment')=='raw')
    unverified_gaps=total_missing-sum(x['status']!='unverified' for x in gap_rows)
    listing_status='unverified'
    if listing is not None and {'symbol','list_date','delist_date','source_url'}.issubset(listing):
        listing_status='partial_user_supplied_evidence_not_full_pit_universe'
    failures=[r for r in audit.get('results',[]) if not r.get('basic_quality',{}).get('passed',False)]
    blocking=[]
    if not all_downloads: blocking.append('some_daily_downloads_failed')
    if failures: blocking.append('quality_findings_in_adjusted_series')
    if unverified_gaps: blocking.append('unclassified_missing_exchange_sessions')
    blocking.append('point_in_time_delisted_universe_not_certified')
    blocking.append('historical_ST_and_tradeability_not_certified')
    blocking.append('corporate_action_and_asof_adjustment_not_certified')
    decision={'version':'1.0.0','source_audit':str(args.audit),'source_audit_sha256':hashlib.sha256(Path(args.audit).read_bytes()).hexdigest(),
       'readiness':{'data_exploration':'conditional','publication_grade_full_market_backtest':'blocked'},
       'blocking_reasons':blocking,'downloads_ok':all_downloads,'raw_missing_sessions':total_missing,
       'unverified_missing_sessions':unverified_gaps,'gap_evidence':gap_rows,'qfq_diagnostics':qfq,
       'listing_evidence_status':listing_status,'notes':['A current master list does not reconstruct a historical universe.',
       'Raw prices alone cannot produce corporate-action-adjusted total returns.',
       'QFQ nonpositive values must not be clipped, forward-filled, or silently excluded.',
       'Absence from daily bars does not establish a suspension.',
       'Historical PIT security universe and ST status require independently verified sources.']}
    (output/'decision.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Data Quality Decision Report','','## Gate decision',
        '- Exploratory factor pipeline: **CONDITIONAL** (only after choosing and documenting a safe return series)',
        '- Publication-grade historical full-market backtest: **BLOCKED**','','## Findings',
        f'- Daily downloads successful: **{all_downloads}**',f'- Missing exchange sessions in raw data: **{total_missing}**',
        f'- Unverified missing sessions: **{unverified_gaps}**',f'- Adjusted series with basic quality failures: **{len(failures)}**',
        f'- Historical listing evidence: **{listing_status}**','','## Blocking reasons']
    lines += ['- '+x for x in blocking]
    lines += ['','## QFQ diagnostic (CSV files optional)']
    for s,d in qfq.items(): lines.append(f'- `{s}`: {d["status"]}; nonpositive counts: {d.get("nonpositive_counts","not available")}')
    lines += ['','## Next research decision','- Use a restricted, clearly disclosed sample for initial factor *engineering* only.',
        '- Do not report investable backtest performance until return construction and point-in-time membership are defensible.',
        '- Obtain a verified historical security master (including delisted securities), suspension/ST records, and corporate-action adjustment data.','','## Important','This report does not independently authenticate user-supplied evidence or confirm the correctness of vendor data.']
    (output/'decision_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Wrote',output/'decision_report.md', 'and',output/'decision.json')
if __name__=='__main__': main()
