import json
import pandas as pd
import pytest
from alphalab.universe import read_universe
from alphalab.collect import collect,validate_bars
from alphalab.data_audit import audit

def master(tmp_path,symbols=('000001',)):
    p=tmp_path/'universe.csv'
    pd.DataFrame([dict(symbol=s,listed_on='',delisted_on='',source='test',verified='false') for s in symbols]).to_csv(p,index=False)
    return p

def bars():
    return pd.DataFrame({'date':['2020-01-02','2020-01-03'],'open':[10.,11.],'high':[11.,12.],
      'low':[9.,10.],'close':[10.,11.],'volume':[100,120]})

def test_read_master(tmp_path):
    assert read_universe(master(tmp_path)).symbol.tolist()==['000001']

def test_duplicate_rejected(tmp_path):
    with pytest.raises(ValueError,match='duplicate'):read_universe(master(tmp_path,['000001','000001']))

def test_bad_dates(tmp_path):
    p=master(tmp_path);x=pd.read_csv(p,dtype=str).fillna('');x.loc[0,'listed_on']='2025-12-01';x.loc[0,'delisted_on']='2020-01-01';x.to_csv(p,index=False)
    with pytest.raises(ValueError,match='delisted'):read_universe(p)

def test_invalid_ohlc():
    x=bars();x.loc[0,'high']=1
    with pytest.raises(ValueError,match='OHLC'):validate_bars(x,'000001')

def test_download_cache_and_range(tmp_path):
    p=master(tmp_path);snap=tmp_path/'snap';calls=[]
    def fetch(s,start,end,adjust):
        calls.append(s);return bars()
    first=collect(p,snap,'20200101','20200131',sleep=0,fetcher=fetch)
    assert first.status.tolist()==['downloaded'] and calls==['000001']
    assert (snap/'000001_raw.meta.json').exists()
    second=collect(p,snap,'20200105','20200120',sleep=0,fetcher=fetch)
    assert second.status.tolist()==['cached'] and len(calls)==1
    third=collect(p,snap,'20190101','20200131',sleep=0,fetcher=fetch)
    assert third.status.tolist()==['failed'] and 'range' in third.error.iloc[0]
    fourth=collect(p,snap,'20190101','20200131',sleep=0,refresh=True,fetcher=fetch)
    assert fourth.status.tolist()==['downloaded'] and len(calls)==2

def test_retry_and_failure(tmp_path):
    p=master(tmp_path);snap=tmp_path/'snap';attempts=[]
    def fail(*args,**kwargs):attempts.append(1);raise ConnectionError('offline')
    result=collect(p,snap,'20200101','20200131',retries=2,sleep=0,fetcher=fail)
    assert result.status.tolist()==['failed'] and len(attempts)==3
    assert not (snap/'000001_raw.csv').exists()

def test_audit_missing(tmp_path):
    p=master(tmp_path);snap=tmp_path/'snap';snap.mkdir()
    pd.DataFrame({'date':['2020-01-02','2020-01-03']}).to_csv(snap/'exchange_calendar.csv',index=False)
    report=audit(snap,p,tmp_path/'out')
    assert report['missing_files']==1 and report['historical_pit_certified'] is False

def test_audit_gap(tmp_path):
    p=master(tmp_path);snap=tmp_path/'snap';snap.mkdir()
    pd.DataFrame({'date':['2020-01-02','2020-01-03','2020-01-06']}).to_csv(snap/'exchange_calendar.csv',index=False)
    x=bars();x.loc[1,'date']='2020-01-06';x.to_csv(snap/'000001_raw.csv',index=False)
    report=audit(snap,p,tmp_path/'out')
    assert report['observed']==1
    row=pd.read_csv(tmp_path/'out'/'security_coverage.csv').iloc[0]
    assert row['missing_within_observed_span']==1
