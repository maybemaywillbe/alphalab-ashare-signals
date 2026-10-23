import json
import pandas as pd
from alphalab.integrity import compare_bars,suspicious_price_jumps,audit_integrity

def bars(closes,dates=None):
    dates=dates if dates is not None else pd.date_range('2020-01-01',periods=len(closes),freq='D')
    return pd.DataFrame({'date':dates,'open':closes,'high':[x+1 for x in closes],
        'low':[x-1 for x in closes],'close':closes,'volume':[100]*len(closes)})

def test_comparison_identical():
    a=bars([10,11,12]);s,d=compare_bars(a,a)
    assert s['overlap_days']==3 and s['price_mismatch_days']==0 and s['volume_mismatch_days']==0

def test_comparison_mismatch_and_calendar():
    a=bars([10,11,12]);b=bars([10,15,13],pd.date_range('2020-01-02',periods=3,freq='D'))
    s,d=compare_bars(a,b)
    assert s['overlap_days']==2 and s['primary_only_days']==1 and s['secondary_only_days']==1
    assert s['price_mismatch_days']>=1

def test_volume_unit_mismatch():
    a=bars([10,11]);b=a.copy();b['volume']*=100
    s,_=compare_bars(a,b)
    assert s['volume_mismatch_days']==2 and s['price_mismatch_days']==0

def test_jump_flag_not_certification():
    x=suspicious_price_jumps(bars([100,60,62]))
    assert len(x)==1 and x.iloc[0].raw_close_change<-.3

def test_offline_audit_and_provenance(tmp_path):
    src=tmp_path/'snap';src.mkdir();bars([10,11,8]).to_csv(src/'000001_raw.csv',index=False)
    (src/'000001_raw.meta.json').write_text(json.dumps({'provider':'AKShare Sina daily history',
        'start':'20150101','end':'20251231','adjust':'raw','volume_unit':'100_share_lots'}))
    result=audit_integrity(src,tmp_path/'out',jump_threshold=.15)
    assert result['files']==1 and result['unverified_large_raw_price_jumps']==1
    assert result['providers']=={'AKShare Sina daily history':1}
    assert result['cross_source_attempted']==0
    assert (tmp_path/'out'/'cross_source_summary.csv').exists()

def test_compare_network_failure_is_recorded(tmp_path,monkeypatch):
    import alphalab.integrity as i
    src=tmp_path/'snap';src.mkdir();bars([10,11]).to_csv(src/'000001_raw.csv',index=False)
    (src/'000001_raw.meta.json').write_text(json.dumps({'provider':'AKShare Eastmoney daily history'}))
    def fail(*a,**k):raise ConnectionError('test offline')
    monkeypatch.setitem(i.PROVIDERS,'sina',fail)
    result=i.audit_integrity(src,tmp_path/'out',compare=True,compare_limit=1)
    assert result['cross_source_failures']==1
    assert pd.read_csv(tmp_path/'out'/'cross_source_summary.csv').iloc[0]['status']=='failed'

def test_invalid_file_does_not_stop_other_files(tmp_path):
    src=tmp_path/'snap';src.mkdir();bars([10,11]).to_csv(src/'000001_raw.csv',index=False)
    (src/'000002_raw.csv').write_text('not,csv\n1,2\n')
    result=audit_integrity(src,tmp_path/'out')
    assert result['files']==2 and result['invalid']==1
