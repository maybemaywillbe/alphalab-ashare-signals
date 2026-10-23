"""Read-only data integrity diagnostics. Never certifies total returns or corporate actions."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from .collect import validate_bars
from .provider import fetch_daily, fetch_sina_daily

PROVIDERS={'eastmoney':fetch_daily,'sina':fetch_sina_daily}

def compare_bars(primary, secondary, *, price_tolerance=0.005, volume_tolerance=0.05):
    """Compare aligned daily bars; relative price tolerance is in decimal units."""
    a=validate_bars(primary,'primary'); b=validate_bars(secondary,'secondary')
    x=a.merge(b,on='date',how='outer',suffixes=('_a','_b'),indicator=True)
    overlap=x[x['_merge']=='both'].copy()
    for field in ('open','high','low','close','volume'):
        if len(overlap):
            left=overlap[field+'_a'].astype(float)
            right=overlap[field+'_b'].astype(float)
            denom=np.maximum(np.maximum(left.abs(),right.abs()),1e-12)
            overlap[field+'_relative_difference']=(left-right).abs()/denom
        else:
            overlap[field+'_relative_difference']=pd.Series(dtype=float)
    price_cols=[c+'_relative_difference' for c in ('open','high','low','close')]
    overlap['price_mismatch']=overlap[price_cols].gt(price_tolerance).any(axis=1)
    overlap['volume_mismatch']=overlap['volume_relative_difference'].gt(volume_tolerance)
    stats={'primary_days':len(a),'secondary_days':len(b),'overlap_days':len(overlap),
           'primary_only_days':int((x['_merge']=='left_only').sum()),
           'secondary_only_days':int((x['_merge']=='right_only').sum()),
           'price_mismatch_days':int(overlap.price_mismatch.sum()),
           'volume_mismatch_days':int(overlap.volume_mismatch.sum()),
           'max_close_relative_difference':float(overlap.close_relative_difference.max()) if len(overlap) else None,
           'max_volume_relative_difference':float(overlap.volume_relative_difference.max()) if len(overlap) else None}
    return stats,overlap

def suspicious_price_jumps(df, threshold=0.15):
    """Flag large adjacent-row raw price moves; these are NOT proven corporate actions.

    Adjacent observed rows may straddle suspensions; gap size is included.
    """
    x=validate_bars(df,'audit').copy()
    x['previous_date']=x.date.shift(1)
    x['previous_close']=x.close.shift(1)
    x['raw_close_change']=x.close/x.previous_close-1
    x['calendar_gap_days']=(x.date-x.previous_date).dt.days
    return x.loc[x.raw_close_change.abs()>threshold,
                 ['date','previous_date','calendar_gap_days','previous_close','close','raw_close_change']].copy()

def read_provenance(snapshots,symbol):
    meta=Path(snapshots)/f'{symbol}_raw.meta.json'
    if not meta.exists():return {'provider':'unknown','metadata_status':'missing'}
    try:
        d=json.loads(meta.read_text(encoding='utf-8'))
        return {'provider':d.get('provider','unknown'),'metadata_status':'present','requested_start':d.get('start'),
                'requested_end':d.get('end'),'adjust':d.get('adjust'),'volume_unit':d.get('volume_unit')}
    except (OSError,ValueError):return {'provider':'unknown','metadata_status':'invalid'}

def audit_integrity(snapshots,output,*,universe=None, compare=False, compare_limit=8,
                    jump_threshold=0.15,price_tolerance=0.005,volume_tolerance=0.05,
                    start='20150101',end='20251231'):
    """Offline-first. Comparison mode fetches a small number of alternative-provider bars."""
    folder=Path(snapshots);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if not (0<jump_threshold<10 and 0<=price_tolerance<1 and 0<=volume_tolerance<1):
        raise ValueError('invalid diagnostic thresholds')
    if compare_limit<0:raise ValueError('compare_limit must be nonnegative')
    paths=sorted(p for p in folder.glob('*_raw.csv') if len(p.stem)==10 and p.stem[:6].isdigit())
    if universe:
        from .universe import read_universe
        allowed=set(read_universe(universe).symbol)
        paths=[p for p in paths if p.stem[:6] in allowed]
    if not paths:raise ValueError('No raw CSV snapshots found')
    status=[]; jumps=[]; comparisons=[];comparison_days=[]
    for path in paths:
        symbol=path.stem[:6]; meta=read_provenance(folder,symbol)
        try:
            df=validate_bars(pd.read_csv(path),symbol)
            if df.empty:raise ValueError('empty snapshot')
            events=suspicious_price_jumps(df,jump_threshold)
            for _,row in events.iterrows():
                jumps.append({'symbol':symbol,'provider':meta['provider'],
                    'date':row.date.strftime('%Y-%m-%d'),
                    'previous_date':row.previous_date.strftime('%Y-%m-%d'),
                    'calendar_gap_days':int(row.calendar_gap_days),
                    'previous_close':float(row.previous_close),'close':float(row.close),
                    'raw_close_change':float(row.raw_close_change),
                    'classification':'unverified_price_jump'})
            status.append({'symbol':symbol,'status':'valid_structure','rows':len(df),'jump_flags':len(events),**meta})
        except Exception as exc:
            status.append({'symbol':symbol,'status':'invalid','rows':0,'jump_flags':0,
                           'error':f'{type(exc).__name__}: {str(exc)[:160]}',**meta})
    good={r['symbol']:r for r in status if r['status']=='valid_structure'}
    # Select provider-balanced candidates where possible, and compare with the OTHER provider.
    if compare:
        ordered=sorted(good, key=lambda s: (0 if 'Sina' in good[s]['provider'] else 1,s))
        for symbol in ordered[:compare_limit]:
            row=good[symbol]; current=row['provider']
            alt='eastmoney' if 'Sina' in current else 'sina' if 'Eastmoney' in current else None
            rec={'symbol':symbol,'original_provider':current,'alternate_provider':alt or 'unknown',
                 'status':'failed','error':''}
            if alt is None:
                rec['status']='skipped_unknown_source';comparisons.append(rec);continue
            try:
                original=validate_bars(pd.read_csv(folder/f'{symbol}_raw.csv'),symbol)
                other=PROVIDERS[alt](symbol,start,end,adjust='')
                stats,detail=compare_bars(original,other,price_tolerance=price_tolerance,
                                          volume_tolerance=volume_tolerance)
                rec.update(stats)
                rec['status']='compared' if stats['overlap_days']>0 else 'no_overlap'
                for _,d in detail.loc[detail.price_mismatch | detail.volume_mismatch].iterrows():
                    comparison_days.append({'symbol':symbol,'date':d.date.strftime('%Y-%m-%d'),
                        'close_primary':float(d.close_a),'close_alternate':float(d.close_b),
                        'close_relative_difference':float(d.close_relative_difference),
                        'volume_relative_difference':float(d.volume_relative_difference),
                        'price_mismatch':bool(d.price_mismatch),'volume_mismatch':bool(d.volume_mismatch)})
            except Exception as exc:
                rec['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
            comparisons.append(rec)
    pd.DataFrame(status).to_csv(out/'source_inventory.csv',index=False)
    pd.DataFrame(jumps,columns=['symbol','provider','date','previous_date','calendar_gap_days',
        'previous_close','close','raw_close_change','classification']).to_csv(out/'price_jump_flags.csv',index=False)
    pd.DataFrame(comparisons,columns=['symbol','original_provider','alternate_provider','status','error',
        'primary_days','secondary_days','overlap_days','primary_only_days','secondary_only_days',
        'price_mismatch_days','volume_mismatch_days','max_close_relative_difference',
        'max_volume_relative_difference']).to_csv(out/'cross_source_summary.csv',index=False)
    pd.DataFrame(comparison_days,columns=['symbol','date','close_primary','close_alternate',
        'close_relative_difference','volume_relative_difference','price_mismatch','volume_mismatch']).to_csv(out/'cross_source_mismatches.csv',index=False)
    report={'version':'1.0.0','gate':'diagnostic_only','files':len(paths),
        'valid_structure':len(good),'invalid':len(paths)-len(good),
        'unverified_large_raw_price_jumps':len(jumps),
        'providers':pd.Series([r['provider'] for r in status]).value_counts().to_dict(),
        'cross_source_attempted':len(comparisons),
        'cross_source_compared':sum(x['status']=='compared' for x in comparisons),
        'cross_source_failures':sum(x['status']=='failed' for x in comparisons),
        'cross_source_price_mismatch_days':sum(x.get('price_mismatch_days',0) for x in comparisons),
        'cross_source_volume_mismatch_days':sum(x.get('volume_mismatch_days',0) for x in comparisons),
        'thresholds':{'raw_price_jump_abs':jump_threshold,'price_relative_difference':price_tolerance,
                      'volume_relative_difference':volume_tolerance},
        'limitations':['Raw price jumps are not confirmed corporate actions.',
            'Comparison is a sampled diagnostic, not a certification of provider equivalence.',
            'Raw returns are not corporate-action-safe; no adjusted or total-return series produced.',
            'Current candidate universe is not point-in-time certified.',
            'A successful comparison does not establish tradability or data completeness.']}
    (out/'integrity_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description='Read-only provenance, jump and cross-provider diagnostics')
    p.add_argument('--snapshots',required=True);p.add_argument('--output',default='outputs/integrity')
    p.add_argument('--universe');p.add_argument('--compare',action='store_true',help='network: sample alternative provider')
    p.add_argument('--compare-limit',type=int,default=8)
    p.add_argument('--jump-threshold',type=float,default=0.15)
    p.add_argument('--price-tolerance',type=float,default=0.005)
    p.add_argument('--volume-tolerance',type=float,default=0.05)
    p.add_argument('--start',default='20150101');p.add_argument('--end',default='20251231')
    a=p.parse_args();print(json.dumps(audit_integrity(a.snapshots,a.output,universe=a.universe,
        compare=a.compare,compare_limit=a.compare_limit,jump_threshold=a.jump_threshold,
        price_tolerance=a.price_tolerance,volume_tolerance=a.volume_tolerance,
        start=a.start,end=a.end),indent=2,ensure_ascii=False))
if __name__=='__main__':main()
