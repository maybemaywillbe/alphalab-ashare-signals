"""Sina-only raw + qfq daily snapshots, isolated from legacy mixed-provider cache.

Current qfq is a retrospective adjustment, NOT a point-in-time historical series.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import pandas as pd
from .universe import read_universe
from .collect import validate_bars, sha256


def fetch_sina(symbol, start, end, adjust):
    import akshare as ak
    symbol=str(symbol).zfill(6)
    if symbol.startswith(('4','8')):
        raise ValueError('Beijing exchange Sina coverage not verified')
    prefix='sh' if symbol.startswith(('6','9')) else 'sz'
    frame=ak.stock_zh_a_daily(symbol=prefix+symbol,start_date=start,end_date=end,adjust=adjust)
    if frame is None or frame.empty:
        raise ValueError('Sina returned no bars')
    frame=frame.copy()
    frame.columns=[str(c).lower() for c in frame.columns]
    # AKShare Sina returns volume in shares. Store in 100-share lots for continuity.
    frame['volume']=pd.to_numeric(frame['volume'],errors='raise')/100
    return frame


def collect(universe, snapshots, start='20150101', end='20251231', limit=None,
            retries=2, sleep=1.0, refresh=False, fetcher=fetch_sina):
    if retries<0 or sleep<0: raise ValueError('retries/sleep must be >= 0')
    if pd.to_datetime(start,format='%Y%m%d')>pd.to_datetime(end,format='%Y%m%d'):
        raise ValueError('start must precede end')
    master=read_universe(universe)
    if limit is not None:
        if limit<1: raise ValueError('limit must be >=1')
        master=master.head(limit)
    out=Path(snapshots);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for _,r in master.iterrows():
        sym=r.symbol
        for adjust,variant in (('', 'raw'),('qfq','qfq')):
            dest=out/f'{sym}_{variant}.csv';meta_path=out/f'{sym}_{variant}.meta.json'
            status='failed';error='';rows=0
            if dest.exists() and meta_path.exists() and not refresh:
                try:
                    meta=json.loads(meta_path.read_text(encoding='utf-8'))
                    if (meta.get('provider')!='AKShare Sina daily history' or meta.get('adjust')!=adjust
                        or meta.get('start','')>start or meta.get('end','')<end
                        or meta.get('sha256')!=sha256(dest)):
                        raise ValueError('cache metadata/checksum mismatch')
                    cached=validate_bars(pd.read_csv(dest),sym)
                    if cached.empty: raise ValueError('empty cached data')
                    rows=len(cached);status='cached'
                except Exception as exc:
                    error=f'cache validation failed: {exc}; use --refresh after checking file'
            elif (dest.exists() or meta_path.exists()) and not refresh:
                error='incomplete cache pair; use --refresh after checking files'
            else:
                for attempt in range(retries+1):
                    try:
                        frame=validate_bars(fetcher(sym,start,end,adjust),sym)
                        if frame.empty: raise ValueError('empty bars')
                        tmp=out/f'.{sym}_{variant}.csv.tmp'
                        frame.to_csv(tmp,index=False,date_format='%Y-%m-%d')
                        digest=sha256(tmp)
                        metadata={'symbol':sym,'provider':'AKShare Sina daily history','adjust':adjust,
                                  'start':start,'end':end,'sha256':digest,'volume_unit':'100_share_lots',
                                  'historical_pit_certified':False,
                                  'adjustment_note':'current retrospective qfq; NOT PIT' if adjust else 'unadjusted raw prices'}
                        tmpmeta=out/f'.{sym}_{variant}.meta.json.tmp'
                        tmpmeta.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
                        tmp.replace(dest);tmpmeta.replace(meta_path)
                        rows=len(frame);status='downloaded';error='';break
                    except Exception as exc:
                        error=f'{type(exc).__name__}: {str(exc)[:220]}'
                        if attempt<retries and sleep: time.sleep(sleep*(attempt+1))
                if sleep: time.sleep(sleep)
            results.append({'symbol':sym,'variant':variant,'status':status,'rows':rows,'error':error})
        # raw and qfq may have different date coverage; explicitly diagnose without silently merging.
    log=pd.DataFrame(results)
    log.to_csv(out/'sina_collection_status.csv',index=False)
    check=[]
    for sym in master.symbol:
        a=out/f'{sym}_raw.csv';b=out/f'{sym}_qfq.csv'
        if not (a.exists() and b.exists()):
            check.append({'symbol':sym,'status':'missing_variant','raw_days':None,'qfq_days':None,'date_difference':None,'large_raw_jumps':None});continue
        try:
            raw=validate_bars(pd.read_csv(a),sym);qfq=validate_bars(pd.read_csv(b),sym)
            rd=set(raw.date);qd=set(qfq.date)
            check.append({'symbol':sym,'status':'matched_dates' if rd==qd else 'date_mismatch',
                          'raw_days':len(rd),'qfq_days':len(qd),'date_difference':len(rd.symmetric_difference(qd)),
                          'large_raw_jumps':int(raw.close.pct_change().abs().gt(.15).sum())})
        except Exception as exc:
            check.append({'symbol':sym,'status':f'invalid: {exc}','raw_days':None,'qfq_days':None,'date_difference':None,'large_raw_jumps':None})
    pd.DataFrame(check).to_csv(out/'sina_pair_audit.csv',index=False)
    return log


def main():
    p=argparse.ArgumentParser(description='Collect Sina raw and retrospective QFQ daily bars into the requested snapshot folder')
    p.add_argument('--universe',required=True);p.add_argument('--snapshots',default='inputs/sina_snapshots')
    p.add_argument('--start',default='20150101');p.add_argument('--end',default='20251231')
    p.add_argument('--limit',type=int);p.add_argument('--retries',type=int,default=2)
    p.add_argument('--sleep',type=float,default=1.0);p.add_argument('--refresh',action='store_true')
    a=p.parse_args()
    log=collect(a.universe,a.snapshots,a.start,a.end,a.limit,a.retries,a.sleep,a.refresh)
    print(log.groupby(['variant','status']).size().to_string())
    print(f'Collection status: {a.snapshots}/sina_collection_status.csv')
    print(f'Paired audit: {a.snapshots}/sina_pair_audit.csv')
if __name__=='__main__':main()
