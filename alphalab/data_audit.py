"""Coverage audit; distinguish observed absence from proven suspension or delisting."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from .universe import read_universe
from .factors import load_sessions
from .collect import validate_bars

def audit(snapshots, universe, output):
    folder=Path(snapshots); out=Path(output);out.mkdir(parents=True,exist_ok=True)
    master=read_universe(universe)
    cal=folder/'exchange_calendar.csv'
    if not cal.exists(): raise FileNotFoundError('exchange_calendar.csv is missing from the configured snapshots directory')
    sessions=load_sessions(cal)
    records=[]
    for _,r in master.iterrows():
        path=folder/f'{r.symbol}_raw.csv'
        base={'symbol':r.symbol,'source':r.source,'listed_on':r.listed_on,'delisted_on':r.delisted_on,
              'historical_membership_verified':str(r.verified).lower() in ('true','1','yes')}
        if not path.exists():
            records.append({**base,'status':'missing_file','observed_bars':0,'missing_within_observed_span':None,
                            'coverage_within_observed_span':None,'first_date':'','last_date':'','error':''});continue
        try:
            df=validate_bars(pd.read_csv(path),r.symbol)
            if df.empty: raise ValueError('empty bars')
            dates=pd.DatetimeIndex(df.date)
            if not dates.isin(sessions).all(): raise ValueError('bars outside exchange calendar')
            window=sessions[(sessions>=dates.min())&(sessions<=dates.max())]
            missing=len(window)-len(df)
            records.append({**base,'status':'observed','observed_bars':len(df),
                            'missing_within_observed_span':missing,
                            'coverage_within_observed_span':len(df)/len(window) if len(window) else None,
                            'first_date':str(dates.min().date()),'last_date':str(dates.max().date()),'error':''})
        except Exception as exc:
            records.append({**base,'status':'invalid','observed_bars':0,'missing_within_observed_span':None,
                            'coverage_within_observed_span':None,'first_date':'','last_date':'','error':str(exc)})
    result=pd.DataFrame(records)
    result.to_csv(out/'security_coverage.csv',index=False)
    report={'version':'1.0.0','candidate_symbols':len(master),'observed':int((result.status=='observed').sum()),
            'missing_files':int((result.status=='missing_file').sum()),'invalid':int((result.status=='invalid').sum()),
            'calendar_sessions':len(sessions),'historical_pit_certified':False,
            'return_series':'raw unadjusted; NOT corporate-action safe',
            'warning':'Missing within observed span is not independently classified as suspension, delisting, or provider outage.'}
    (out/'data_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshots',default='inputs/snapshots')
    p.add_argument('--universe',required=True);p.add_argument('--output',default='outputs/data_audit')
    a=p.parse_args();print(json.dumps(audit(a.snapshots,a.universe,a.output),indent=2))
if __name__=='__main__':main()
