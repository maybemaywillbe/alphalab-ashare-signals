"""Get Sina official exchange sessions via AKShare; never infer them from sampled stocks."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd


def download_calendar(out: str | Path, start: str, end: str) -> int:
    import akshare as ak
    data=ak.tool_trade_date_hist_sina()
    col='trade_date' if 'trade_date' in data.columns else 'date'
    if col not in data.columns:raise ValueError('Unexpected AKShare trading calendar schema')
    dates=pd.to_datetime(data[col],errors='raise').dt.normalize()
    dates=dates[dates.between(pd.Timestamp(start),pd.Timestamp(end))].sort_values().drop_duplicates()
    if len(dates)<252:raise ValueError('Trading calendar unavailable or less than 252 sessions')
    output=Path(out);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError('Existing calendar is immutable; use a new snapshot folder')
    pd.DataFrame({'date':dates}).to_csv(output,index=False)
    return len(dates)


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='inputs/sina_snapshots/exchange_calendar.csv')
    p.add_argument('--start',default='2014-01-01');p.add_argument('--end',default='2026-10-23')
    a=p.parse_args();print(f'{download_calendar(a.out,a.start,a.end)} sessions written')
if __name__=='__main__':main()
