import sys
from types import SimpleNamespace

import pandas as pd
import pytest
from alphalab.universe import candidate_current_snapshot


def master():
    return pd.DataFrame({'code':['600000','000001','302132','830001'], 'name':['A','B','C','D']})


def test_primary_success(tmp_path):
    out=tmp_path/'universe.csv'
    assert candidate_current_snapshot(out, primary=master)==4
    saved=pd.read_csv(out)
    assert set(saved.symbol.astype(str).str.zfill(6))=={'600000','000001','302132','830001'}
    assert 'primary stock master' in saved.source.iloc[0]


def test_fallback_after_primary_failure(tmp_path):
    def fail(): raise OSError('TLS EOF')
    out=tmp_path/'universe.csv'
    assert candidate_current_snapshot(out,primary=fail,fallback=master)==4
    assert 'fallback stock master' in pd.read_csv(out).source.iloc[0]


def test_cache_reused_without_network(tmp_path):
    out=tmp_path/'universe.csv'
    candidate_current_snapshot(out,primary=master)
    assert candidate_current_snapshot(out,primary=lambda: pytest.fail('network called'))==4


def test_frozen_100_stock_sample_is_not_accepted_as_complete_cache(tmp_path):
    out=tmp_path/'universe.csv'
    pd.DataFrame({'symbol':['600000','000001','830001'],
                  'name':['A','B','C'],
                  'source':['frozen selected sample']*3}).to_csv(out,index=False)
    with pytest.raises(ValueError,match='not a complete current candidate snapshot'):
        candidate_current_snapshot(out,primary=master)


def test_corrupt_cache_fails_explicitly(tmp_path):
    out=tmp_path/'universe.csv'
    out.write_text('symbol,name,source\n600000,A,CURRENT snapshot\n000001,B,CURRENT snapshot\n',encoding='utf-8')
    with pytest.raises(ValueError,match='board coverage'):
        candidate_current_snapshot(out,primary=master)


@pytest.mark.parametrize('frame, message', [
 (pd.DataFrame({'code':['600001','600001','830001'],'name':['a','b','c']}),'duplicate'),
 (pd.DataFrame({'code':['600001','000001'],'name':['a','b']}),'board coverage'),
 (pd.DataFrame({'code':['600001','000001','830001'],'name':['a','','c']}),'empty name'),
])
def test_invalid_master_rejected_without_fallback(tmp_path,frame,message):
    with pytest.raises(RuntimeError,match=message):
        candidate_current_snapshot(tmp_path/'u.csv',primary=lambda:frame,fallback=lambda:frame)


def test_all_providers_fail_explicitly(tmp_path):
    def fail(): raise OSError('provider offline')
    with pytest.raises(RuntimeError,match='unable to obtain a complete validated'):
        candidate_current_snapshot(tmp_path/'u.csv',primary=fail,fallback=fail)


def test_default_cache_is_the_requested_output(tmp_path):
    out=tmp_path/'universe.csv'
    candidate_current_snapshot(out,primary=master)
    assert candidate_current_snapshot(out,primary=lambda: pytest.fail('network called'))==4


def test_exchange_fallback_adapts_chinese_columns(monkeypatch,tmp_path):
    from alphalab import universe
    calls=[]
    def sh(symbol):
        calls.append(symbol)
        if symbol=='主板A股':
            return pd.DataFrame({'证券代码':['600000'],'证券简称':['沪股']})
        return pd.DataFrame({'证券代码':['688001'],'证券简称':['科创']})
    def sz(symbol): return pd.DataFrame({'A股代码':['000001','302132'],'A股简称':['深股','中航成飞']})
    def bj(): return pd.DataFrame({'证券代码':['830001'],'证券简称':['北证']})
    # AKShare is an optional fetch extra. Inject the API surface used here so
    # this unit test checks the adapter without requiring network dependencies.
    ak = SimpleNamespace(
        stock_info_a_code_name=lambda: (_ for _ in ()).throw(OSError('SZSE TLS EOF')),
        stock_info_sh_name_code=sh,
        stock_info_sz_name_code=sz,
        stock_info_bj_name_code=bj,
    )
    monkeypatch.setitem(sys.modules, 'akshare', ak)
    # Ensure fallback path exercises the built-in exchange aggregator.
    out=tmp_path/'universe.csv'
    n=universe.candidate_current_snapshot(out)
    assert n==5
    assert set(pd.read_csv(out).symbol.astype(str).str.zfill(6))=={'600000','688001','000001','302132','830001'}
    assert calls==['主板A股','科创板']
