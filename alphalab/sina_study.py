"""Exploratory research on Sina retrospective qfq. NOT point-in-time or executable."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import pandas as pd
from .factors import load_sessions,factor_panel,month_end_signals,evaluate,summary_table
from .coverage import coverage_table
from .collect import validate_bars

def run(snapshots, output, min_names=20, oos_start='2023-01-01'):
    folder=Path(snapshots);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    frames=[];excluded=[]
    for path in sorted(folder.glob('*_qfq.csv')):
        sym=path.name.split('_')[0]
        if len(sym)!=6 or not sym.isdigit():continue
        try:
            x=validate_bars(pd.read_csv(path),sym)
            x=x[['date','close']].copy();x['symbol']=sym
            frames.append(x)
        except Exception as exc:excluded.append({'symbol':sym,'reason':str(exc)})
    if not frames:raise ValueError('No valid qfq files found. Collect Sina snapshots first.')
    raw=pd.concat(frames,ignore_index=True)
    sessions=load_sessions(folder/'exchange_calendar.csv',raw.date.min(),raw.date.max())
    panel=factor_panel(raw,sessions)
    formed=month_end_signals(panel)
    coverage=coverage_table(formed,min_names=min_names,oos_start=oos_start)
    ic,bins=evaluate(formed,min_names=min_names,oos_start=oos_start)
    summary=summary_table(ic)
    for name,data in [('factor_observations.csv',formed),('coverage.csv',coverage),('rank_ic.csv',ic),
                      ('quantile_descriptives.csv',bins),('summary.csv',summary),
                      ('excluded_qfq.csv',pd.DataFrame(excluded,columns=['symbol','reason']))]:
        data.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'retrospective_qfq_exploratory_only',
            'included_symbols':len(frames),'excluded_symbols':len(excluded),
            'eligible_factor_dates':len(ic),'oos_start':oos_start,
            'warning':'Retrospective qfq can incorporate future corporate actions. NOT PIT-certified; no tradability or costs.',
            'return_type':'retrospectively_forward_adjusted_close_to_close; not verified total return',
            'universe':'current listed candidates; survivorship bias unresolved',
            'summary':summary.to_dict(orient='records')}
    (out/'sina_study.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshots',default='inputs/sina_snapshots')
    p.add_argument('--output',default='outputs/sina_study');p.add_argument('--min-names',type=int,default=20)
    p.add_argument('--oos-start',default='2023-01-01')
    a=p.parse_args();print(json.dumps(run(a.snapshots,a.output,a.min_names,a.oos_start),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
