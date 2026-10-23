"""Resumable raw daily CSV collection, with atomic writes and explicit failures."""
from __future__ import annotations
import argparse, json, time, hashlib
from pathlib import Path
import pandas as pd
from .provider import fetch_daily, fetch_sina_daily
from .universe import read_universe,candidate_current_snapshot

REQUIRED=['date','open','high','low','close','volume']

def validate_bars(df, symbol):
    if not set(REQUIRED).issubset(df.columns): raise ValueError('missing OHLCV columns')
    x=df.copy()
    x['date']=pd.to_datetime(x.date,errors='raise').dt.normalize()
    if x.date.isna().any() or x.date.duplicated().any(): raise ValueError('invalid or duplicate dates')
    for c in REQUIRED[1:]: x[c]=pd.to_numeric(x[c],errors='coerce')
    if x[REQUIRED[1:]].isna().any().any(): raise ValueError('non-numeric OHLCV')
    if (x[['open','high','low','close']]<=0).any().any() or (x.volume<0).any(): raise ValueError('invalid prices or volume')
    if ((x.high < x[['open','close','low']].max(axis=1)) | (x.low > x[['open','close','high']].min(axis=1))).any():
        raise ValueError('OHLC consistency failure')
    return x.sort_values('date').reset_index(drop=True)

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def collect(universe, snapshots, start, end, retries=2, sleep=0.4, limit=None, refresh=False, fetcher=None, fallback="sina"):
    """Collect candidate symbols; do not claim PIT membership or adjusted returns.

    A valid cached file is skipped; invalid cached files are recorded as failures,
    never silently overwritten unless --refresh is specified.
    """
    if retries<0 or sleep<0: raise ValueError('retries/sleep must be nonnegative')
    if fallback not in ('sina','none'): raise ValueError('fallback must be sina or none')
    pd.to_datetime(start,format='%Y%m%d',errors='raise')
    pd.to_datetime(end,format='%Y%m%d',errors='raise')
    if start>end: raise ValueError('start must precede end')
    rows=read_universe(universe)
    if limit is not None:
        if limit<1: raise ValueError('limit must be positive')
        rows=rows.head(limit)
    out=Path(snapshots);out.mkdir(parents=True,exist_ok=True)
    fetcher=fetcher or fetch_daily
    results=[]
    for _,r in rows.iterrows():
        sym=r.symbol;path=out/f'{sym}_raw.csv'; status='failed';error=''; data=None; provider_used=''
        if path.exists() and not refresh:
            try:
                data=validate_bars(pd.read_csv(path),sym)
                if len(data)==0: raise ValueError('empty cached file')
                # Cache only reusable when requested date range is covered by the original request metadata.
                # Do not infer requested coverage from first/last trade: IPOs and suspensions cause gaps.
                meta_path=out/f'{sym}_raw.meta.json'
                if not meta_path.exists(): raise ValueError('missing cache request metadata; use --refresh')
                meta=json.loads(meta_path.read_text(encoding='utf-8'))
                if not (meta.get('start','')<=start and meta.get('end','')>=end):
                    raise ValueError('cached request range does not cover requested range; use --refresh')
                if meta.get('sha256')!=sha256(path): raise ValueError('cached checksum mismatch; use --refresh')
                status='cached'; provider_used=meta.get('provider','unknown')
            except Exception as exc:
                error=f'cache validation: {exc}'
        else:
            # Never replace a valid cached file; fallback only applies to uncached symbols.
            # Injected test fetchers use the single-provider test interface.
            sources=[('AKShare Eastmoney daily history',fetcher)]
            if fallback=='sina' and fetcher is fetch_daily:
                sources.append(('AKShare Sina daily history',fetch_sina_daily))
            errors=[]
            for source_name,source_fn in sources:
                for attempt in range(retries+1):
                    try:
                        data=validate_bars(source_fn(sym,start,end,adjust=''),sym)
                        if data.empty: raise ValueError('provider returned no bars')
                        tmp=path.with_suffix('.csv.tmp')
                        data.to_csv(tmp,index=False,date_format='%Y-%m-%d')
                        tmp.replace(path)
                        meta={'symbol':sym,'start':start,'end':end,'adjust':'raw','sha256':sha256(path),
                              'provider':source_name, 'volume_unit':'100_share_lots',
                              'universe_source':r.source,'historical_pit_certified':False}
                        tmpmeta=out/f'{sym}_raw.meta.json.tmp'
                        tmpmeta.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
                        tmpmeta.replace(out/f'{sym}_raw.meta.json')
                        status='downloaded';error='';provider_used=source_name
                        break
                    except Exception as exc:
                        msg=f'{source_name} attempt {attempt+1}: {type(exc).__name__}: {str(exc)[:260]}'
                        errors.append(msg)
                        if attempt<retries and sleep: time.sleep(sleep*(attempt+1))
                if status=='downloaded':break
            if status!='downloaded': error=' | '.join(errors[-4:])
        results.append({'symbol':sym,'status':status,'rows':len(data) if status in ('cached','downloaded') else 0,
                        'first_date':data.date.min().strftime('%Y-%m-%d') if status in ('cached','downloaded') else '',
                        'last_date':data.date.max().strftime('%Y-%m-%d') if status in ('cached','downloaded') else '',
                        'error':error,'source':r.source,'provider':provider_used})
    log=pd.DataFrame(results)
    log.to_csv(out/'collection_status.csv',index=False)
    return log

def main():
    p=argparse.ArgumentParser(description='Candidate-universe collection and resumable raw history download')
    sub=p.add_subparsers(dest='command',required=True)
    u=sub.add_parser('current-candidates',help='current-listed candidate snapshot, NOT PIT')
    u.add_argument('--output',default='inputs/universe_candidates.csv');u.add_argument('--limit',type=int)
    c=sub.add_parser('collect',help='download raw daily OHLCV for explicit candidate list')
    c.add_argument('--universe',required=True);c.add_argument('--snapshots',default='inputs/snapshots')
    c.add_argument('--start',default='20150101');c.add_argument('--end',default='20251231')
    c.add_argument('--limit',type=int);c.add_argument('--retries',type=int,default=2)
    c.add_argument('--sleep',type=float,default=0.4);c.add_argument('--refresh',action='store_true')
    c.add_argument('--fallback',choices=['sina','none'],default='sina',help='try independent Sina API after Eastmoney fails')
    a=p.parse_args()
    if a.command=='current-candidates':
        print(f'{candidate_current_snapshot(a.output,a.limit)} CURRENT candidates written to {a.output}; NOT historical PIT')
    else:
        log=collect(a.universe,a.snapshots,a.start,a.end,a.retries,a.sleep,a.limit,a.refresh,fallback=a.fallback)
        print(log.status.value_counts().to_string());print(f'collection status: {a.snapshots}/collection_status.csv')
if __name__=='__main__':main()
