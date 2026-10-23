"""AKShare Eastmoney daily history adapter. Requires internet on user's machine."""
from __future__ import annotations
import pandas as pd

MAP = {'日期':'date','开盘':'open','最高':'high','最低':'low','收盘':'close',
       '成交量':'volume','成交额':'turnover','振幅':'amplitude','涨跌幅':'pct_change',
       '涨跌额':'change','换手率':'turnover_rate','股票代码':'symbol'}

def fetch_daily(symbol: str, start: str, end: str, adjust: str = '') -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_zh_a_hist(symbol=symbol, period='daily', start_date=start, end_date=end, adjust=adjust)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=['date','open','high','low','close','volume'])
    df = raw.rename(columns=MAP).copy()
    for c in ['open','high','low','close','volume','turnover']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df.sort_values('date').reset_index(drop=True)


def fetch_sina_daily(symbol: str, start: str, end: str, adjust: str = '') -> pd.DataFrame:
    """Independent Sina endpoint via AKShare; raw daily bars, no adjustment.

    Sina reports volume in shares; Eastmoney reports volume in 100-share lots.
    Convert Sina volume to lots for consistency with existing raw snapshots.
    """
    if adjust != '':
        raise ValueError('Sina fallback supports raw unadjusted bars only')
    import akshare as ak
    symbol = str(symbol).zfill(6)
    prefix = 'sh' if symbol.startswith(('6','9')) else 'bj' if symbol.startswith(('4','8')) else 'sz'
    if prefix == 'bj':
        raise ValueError('Sina fallback not verified for Beijing Stock Exchange symbols')
    raw = ak.stock_zh_a_daily(symbol=prefix+symbol, start_date=start, end_date=end, adjust='')
    if raw is None or raw.empty:
        return pd.DataFrame(columns=['date','open','high','low','close','volume'])
    df = raw.copy()
    df.columns = [str(c).lower() for c in df.columns]
    if 'volume' not in df.columns:
        raise ValueError('Sina response lacks volume')
    df['volume'] = pd.to_numeric(df['volume'],errors='raise') / 100.0
    return df
