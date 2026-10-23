"""Explicit research candidate universe; no inference of point-in-time membership."""
from __future__ import annotations
import pandas as pd
from pathlib import Path
import os

COLUMNS=['symbol','listed_on','delisted_on','source','verified']

def read_universe(path):
    df=pd.read_csv(path,dtype=str,keep_default_na=False)
    if not set(COLUMNS).issubset(df.columns):
        raise ValueError(f'universe CSV requires {COLUMNS}')
    df=df[COLUMNS].copy()
    df['symbol']=df.symbol.str.strip().str.zfill(6)
    if df.symbol.duplicated().any(): raise ValueError('duplicate universe symbols')
    if not df.symbol.str.fullmatch(r'\d{6}').all(): raise ValueError('invalid six-digit symbol')
    for col in ['listed_on','delisted_on']:
        for value in df[col]:
            if value.strip(): pd.to_datetime(value,format='%Y-%m-%d',errors='raise')
    bad=df[(df.listed_on!='') & (df.delisted_on!='')].copy()
    if len(bad) and (pd.to_datetime(bad.listed_on)>pd.to_datetime(bad.delisted_on)).any():
        raise ValueError('delisted before listed')
    return df.sort_values('symbol').reset_index(drop=True)

def _validate_current_master(df):
    """Normalize and strictly validate a complete A-share code/name master."""
    if not {'code','name'}.issubset(df.columns):
        raise ValueError('current stock master requires code and name columns')
    x=df[['code','name']].copy()
    x['code']=x.code.astype(str).str.strip().str.replace(r'\.0$','',regex=True).str.zfill(6)
    x['name']=x.name.astype(str).str.strip()
    if x.empty: raise ValueError('current stock master is empty')
    if not x.code.str.fullmatch(r'\d{6}').all(): raise ValueError('invalid code in current stock master')
    if x.code.duplicated().any(): raise ValueError('duplicate codes in current stock master')
    if (x.name=='').any(): raise ValueError('empty name in current stock master')
    # A-share boards: Shanghai main/STAR, Shenzhen main/ChiNext, Beijing.
    covered={'sh':x.code.str.startswith(('600','601','603','605','688','689')).any(),
             'sz':x.code.str.startswith(('000','001','002','003','300','301','302')).any(),
             'bj':x.code.str.startswith(('4','8','920')).any()}
    missing=[board for board,ok in covered.items() if not ok]
    if missing: raise ValueError(f'current stock master lacks board coverage: {missing}')
    # Reject unrelated securities; cannot silently let ETFs/bonds into sampling.
    valid=x.code.str.startswith(('600','601','603','605','688','689','000','001','002','003','300','301','302','4','8','920'))
    if not valid.all(): raise ValueError('non-A-share or unsupported code in current stock master')
    return x.sort_values('code').reset_index(drop=True)

def candidate_current_snapshot(output, limit=None, *, cache=None, primary=None, fallback=None):
    """Optional convenience snapshot of *current* listings, NEVER a historical PIT universe."""
    output_path=Path(output)
    cache=Path(cache or os.environ.get('ALPHALAB_UNIVERSE_CACHE',str(output_path)))
    if cache.exists():
        saved=pd.read_csv(cache,dtype=str,keep_default_na=False)
        if not {'symbol','name'}.issubset(saved.columns): raise ValueError(f'invalid cached candidate snapshot: {cache}')
        # A downstream frozen sample also has symbol/name fields. Never treat
        # it as a full current master: require the explicit snapshot marker.
        if not saved.source.astype(str).str.contains('CURRENT snapshot',case=False,regex=False).all():
            raise ValueError(f'cached file is not a complete current candidate snapshot: {cache}')
        base=_validate_current_master(saved.rename(columns={'symbol':'code'}))
        source='validated local candidate snapshot'
    else:
        errors=[]
        providers=[]
        if primary is None:
            import akshare as ak
            providers.append(('AKShare A-share master (Eastmoney/Shenzhen aggregation)',ak.stock_info_a_code_name))
        else: providers.append(('primary stock master',primary))
        if fallback is None:
            try:
                import akshare as ak
                # Combine exchange lists that do not depend on Shenzhen's endpoint.
                def exchange_aggregate():
                    frames=[]
                    for label, fn in (
                        ('SSE main', lambda: ak.stock_info_sh_name_code(symbol='主板A股')),
                        ('SSE STAR', lambda: ak.stock_info_sh_name_code(symbol='科创板')),
                        ('SZSE A-share list', lambda: ak.stock_info_sz_name_code(symbol='A股列表')),
                        ('BSE', ak.stock_info_bj_name_code),
                    ):
                        part=fn()
                        code_col=next((c for c in ('证券代码','A股代码','A股代码 ','代码','证券代码 ','code') if c in part.columns),None)
                        name_col=next((c for c in ('证券简称','A股简称','A股简称 ','证券名称','名称','name') if c in part.columns),None)
                        if code_col is None or name_col is None:
                            raise ValueError(f'{label} master has unexpected schema: {part.columns.tolist()}')
                        frames.append(part[[code_col,name_col]].rename(columns={code_col:'code',name_col:'name'}))
                    return pd.concat(frames,ignore_index=True)
                providers.append(('AKShare SSE/STAR/BSE exchange masters',exchange_aggregate))
            except (ImportError,AttributeError): pass
        else: providers.append(('fallback stock master',fallback))
        base=None;source=''
        for label,provider in providers:
            try:
                candidate=_validate_current_master(provider())
                base=candidate;source=label;break
            except Exception as exc: errors.append(f'{label}: {type(exc).__name__}: {exc}')
        if base is None: raise RuntimeError('unable to obtain a complete validated A-share master; '+' | '.join(errors))
    df=base.rename(columns={'code':'symbol'})
    if limit is not None:
        if limit<1: raise ValueError('limit must be positive')
        # Never persist a truncated list as the canonical candidate cache.
        df=df.head(limit)
    out=pd.DataFrame({'symbol':df.symbol,'listed_on':'','delisted_on':'',
                      'source':source+' CURRENT snapshot; survivor biased',
                      'verified':'false','name':df.name})
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(output_path,index=False)
    return len(out)
