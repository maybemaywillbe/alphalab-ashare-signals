import pandas as pd
from alphalab import collect as c
from alphalab import provider
from test_v06 import master, bars

def test_fallback_and_cache(tmp_path,monkeypatch):
    p=master(tmp_path); snap=tmp_path/'snap'; calls=[]
    def primary(*a,**k):calls.append('primary');raise ConnectionError('unavailable')
    def secondary(*a,**k):calls.append('secondary');return bars()
    monkeypatch.setattr(c,'fetch_daily',primary)
    monkeypatch.setattr(c,'fetch_sina_daily',secondary)
    x=c.collect(p,snap,'20200101','20200131',retries=0,sleep=0)
    assert x.status.tolist()==['downloaded'] and calls==['primary','secondary']
    assert x.provider.iloc[0]=='AKShare Sina daily history'
    y=c.collect(p,snap,'20200101','20200131',retries=0,sleep=0)
    assert y.status.tolist()==['cached'] and len(calls)==2

def test_no_fallback(tmp_path,monkeypatch):
    p=master(tmp_path); snap=tmp_path/'snap'
    def primary(*a,**k):raise ConnectionError('unavailable')
    def secondary(*a,**k):raise AssertionError('must not call')
    monkeypatch.setattr(c,'fetch_daily',primary)
    monkeypatch.setattr(c,'fetch_sina_daily',secondary)
    x=c.collect(p,snap,'20200101','20200131',retries=0,sleep=0,fallback='none')
    assert x.status.tolist()==['failed']

def test_sina_normalization(monkeypatch):
    import sys,types
    raw=bars();raw['volume']=[10000,12000]
    fake=types.SimpleNamespace(stock_zh_a_daily=lambda **kw: raw)
    monkeypatch.setitem(sys.modules,'akshare',fake)
    x=provider.fetch_sina_daily('000166','20200101','20200131')
    assert x.volume.tolist()==[100,120]
