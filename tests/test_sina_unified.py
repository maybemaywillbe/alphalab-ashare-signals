import json
import pandas as pd
from alphalab.sina_unified import collect

def make_frame():
    return pd.DataFrame({'date':['2025-01-02','2025-01-03'], 'open':[10,10.5],
                         'high':[11,11], 'low':[9,10], 'close':[10.5,10.7], 'volume':[100,120]})

def test_sina_pair_and_cache(tmp_path):
    u=tmp_path/'u.csv';u.write_text('symbol,source,listed_on,delisted_on,verified\n000001,test,,,false\n')
    calls=[]
    def fetch(symbol,start,end,adjust):
        calls.append(adjust);return make_frame()
    dest=tmp_path/'sina'
    log=collect(u,dest,retries=0,sleep=0,fetcher=fetch)
    assert list(log.status)==['downloaded','downloaded']
    assert calls==['','qfq']
    assert list(pd.read_csv(dest/'sina_pair_audit.csv').status)==['matched_dates']
    log=collect(u,dest,retries=0,sleep=0,fetcher=fetch)
    assert list(log.status)==['cached','cached']
    assert len(calls)==2
    assert json.loads((dest/'000001_qfq.meta.json').read_text())['adjust']=='qfq'

def test_sina_failure_isolated(tmp_path):
    u=tmp_path/'u.csv';u.write_text('symbol,source,listed_on,delisted_on,verified\n000001,test,,,false\n')
    def fetch(symbol,start,end,adjust):
        if adjust=='qfq':raise RuntimeError('qfq down')
        return make_frame()
    log=collect(u,tmp_path/'sina',retries=0,sleep=0,fetcher=fetch)
    assert list(log.status)==['downloaded','failed']
    assert pd.read_csv(tmp_path/'sina'/'sina_pair_audit.csv').iloc[0]['status']=='missing_variant'
