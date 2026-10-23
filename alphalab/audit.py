"""Optional legacy network diagnostic; not part of the frozen research workflow.

Retained for compatibility pending retirement in a future breaking release.
Requires a user-supplied configuration because no network-triggering sample
configuration is bundled with the public study package.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import yaml
from .provider import fetch_daily
from .quality import validate_bars
from .audit_checks import calendar_coverage, adjustment_comparison, listing_bounds


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attempt(fn, attempts, wait):
    error = None
    for i in range(max(1, int(attempts))):
        try:
            return fn(), None
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            if i + 1 < attempts:
                time.sleep(wait * (i + 1))
    return None, error


def fetch_calendar():
    import akshare as ak
    raw = ak.tool_trade_date_hist_sina()
    col = 'trade_date' if 'trade_date' in raw.columns else raw.columns[0]
    dates = pd.to_datetime(raw[col], errors='coerce').dropna().dt.normalize().drop_duplicates().sort_values()
    if dates.empty:
        raise ValueError('empty_calendar')
    return dates


def fetch_current_master():
    import akshare as ak
    raw = ak.stock_info_a_code_name()
    if raw is None or raw.empty:
        raise ValueError('empty_current_master')
    return raw


def main():
    p = argparse.ArgumentParser(description='Legacy optional data audit; requires an explicit YAML config and is outside the frozen research workflow.')
    p.add_argument('--config', required=True, help='user-supplied YAML configuration; no default is bundled')
    p.add_argument('--output', default='outputs/audit_diagnostics')
    args = p.parse_args()
    config_path = Path(args.config)
    cfg = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    rawdir = out / 'snapshots'; rawdir.mkdir(exist_ok=True)
    retries = int(cfg.get('retry_attempts', 2)); wait = float(cfg.get('retry_wait_seconds', 3))
    calendar, calendar_error = attempt(fetch_calendar, retries, wait)
    calendar_meta = {'status':'available' if calendar is not None else 'unavailable', 'error':calendar_error}
    if calendar is not None:
        path = rawdir / 'exchange_calendar.csv'
        pd.DataFrame({'date':calendar.dt.strftime('%Y-%m-%d')}).to_csv(path,index=False)
        calendar_meta.update({'file':str(path),'sha256':digest(path),'sessions':len(calendar),
                              'first_date':str(calendar.min().date()),'last_date':str(calendar.max().date())})
    master, master_error = attempt(fetch_current_master, retries, wait)
    master_meta = {'status':'available_current_only' if master is not None else 'unavailable', 'error':master_error,
                   'historical_point_in_time':False}
    current_codes = None
    if master is not None:
        path=rawdir/'current_stock_master.csv'; master.to_csv(path,index=False,encoding='utf-8-sig')
        master_meta.update({'file':str(path),'sha256':digest(path),'rows':len(master),'columns':list(map(str,master.columns))})
        code_col = next((c for c in master.columns if str(c).lower() in ('code','代码','证券代码','股票代码')),None)
        if code_col is not None:
            current_codes=set(master[code_col].astype(str).str.zfill(6))
    results=[]; series={}
    symbols=list(dict.fromkeys([str(s).zfill(6) for s in cfg['symbols'] + cfg.get('delisted_probe_symbols',[])]))
    for symbol in symbols:
        for adj in cfg.get('adjustments',['']):
            mode=adj or 'raw'
            df,error=attempt(lambda: fetch_daily(symbol,cfg['start_date'],cfg['end_date'],adj),retries,wait)
            entry={'symbol':symbol,'adjustment':mode,'fetch_status':'error' if error else 'ok','error':error}
            if df is not None:
                quality=validate_bars(df)
                entry['basic_quality']=quality
                entry['calendar_coverage']=calendar_coverage(df,calendar,cfg['start_date'],cfg['end_date'],int(cfg.get('gap_warning_sessions',3)))
                entry['listing_bounds']=listing_bounds(df,cfg['start_date'],cfg['end_date'])
                if not df.empty:
                    path=rawdir/f'{symbol}_{mode}.csv'; df.to_csv(path,index=False)
                    entry.update({'file':str(path),'sha256':digest(path)})
                    series[(symbol,mode)]=df
            results.append(entry)
            print(f'{symbol} {mode}: {entry["fetch_status"]}',flush=True)
            time.sleep(float(cfg.get('request_pause_seconds',1)))
    comparisons={s:adjustment_comparison(series.get((s,'raw')),series.get((s,'qfq')),series.get((s,'hfq'))) for s in symbols}
    membership={s:{'in_current_master':(s in current_codes if current_codes is not None else None),
                   'historical_membership':'unverified'} for s in symbols}
    audit={
        'run_id':datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
        'utc_created':datetime.now(timezone.utc).isoformat(),
        'environment':{'python':sys.version.split()[0],'platform':platform.platform()},
        'config':cfg,'config_sha256':digest(config_path),
        'exchange_calendar':calendar_meta,'current_master':master_meta,
        'membership':membership,'results':results,'adjustment_comparisons':comparisons,
        'unverified':[
            'Point-in-time full-market security universe including delisted names',
            'Historical ST flags and corporate-action effective/announcement dates',
            'Suspension vs missing-data classification for absent sessions',
            'Limit-up/limit-down order execution and historical tradability',
            'Independent verification of adjusted-price conventions',
            'Provider data redistribution rights',
        ]}
    (out/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    lines=['# Historical Data Feasibility Audit','',
           f'Run: {audit["run_id"]} (UTC)','',
           '**Scope:** small sample; this does NOT certify a survivorship-bias-free historical A-share universe.','',
           f'Calendar: **{calendar_meta["status"]}**; current stock master: **{master_meta["status"]}**.','',
           '| Symbol | Mode | Fetch | Basic OHLCV | Missing sessions (within observed span) | Long gaps |',
           '|---|---|---|---|---:|---:|']
    for r in results:
        cov=r.get('calendar_coverage',{})
        lines.append(f'| {r["symbol"]} | {r["adjustment"]} | {r["fetch_status"]} | {r.get("basic_quality",{}).get("passed","unknown")} | {cov.get("missing_within_observed_span","unknown")} | {cov.get("long_gap_count","unknown")} |')
    lines+=['','## Adjustment comparisons (diagnostic only)']
    for s,c in comparisons.items():
        lines.append(f'- `{s}`: {c["status"]}; {c.get("details", "")}')
    lines+=['','## Important unverified items']+[f'- {item}' for item in audit['unverified']]
    lines+=['','## Interpretation',
            '- Missing exchange sessions may be suspension or missing vendor observations. The audit does not silently classify them.',
            '- Current master membership is not historical membership; a stock absent today may have delisted or changed code.',
            '- Equal adjusted series hashes do not prove a corporate-action error; differing series do not prove correctness.',
            '- Listing bounds reflect first/last downloaded bar, NOT verified IPO/delisting dates.',
            '- Never publish downloaded provider data to GitHub without checking license and permissions.']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Wrote {out / "report.md"} and {out / "audit.json"}')

if __name__=='__main__': main()
