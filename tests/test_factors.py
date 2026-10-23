import numpy as np
import pandas as pd
import pytest
from alphalab.factors import factor_panel,month_end_signals,evaluate,load_raw_panel


def fixture():
    s=pd.bdate_range('2022-01-03',periods=330)
    rows=[]
    for k,symbol in enumerate(['000001','000002','000003','000004','000005']):
        for i,d in enumerate(s): rows.append({'date':d,'symbol':symbol,'close':float(10+k+i*(.01+.002*k))})
    return pd.DataFrame(rows),s

def test_signal_and_forward_alignment():
    raw,s=fixture(); x=factor_panel(raw,s)
    r=x[(x.symbol=='000001')&(x.date==s[260])].iloc[0]
    assert r.momentum==pytest.approx(raw[(raw.symbol=='000001')&(raw.date==s[239])].close.iloc[0]/raw[(raw.symbol=='000001')&(raw.date==s[8])].close.iloc[0]-1)
    assert r.future_price_return==pytest.approx((10+282*.01)/(10+261*.01)-1)
    assert r.entry_date==s[261]
    assert r.exit_date==s[282]

def test_missing_session_invalidates_windows():
    raw,s=fixture();raw=raw[~((raw.symbol=='000001')&(raw.date==s[255]))]
    x=factor_panel(raw,s)
    r=x[(x.symbol=='000001')&(x.date==s[260])].iloc[0]
    assert pd.isna(r.momentum) and pd.isna(r.reversal)
    # Missing session in forward path invalidates future return even if endpoints exist
    raw,s=fixture();raw=raw[~((raw.symbol=='000001')&(raw.date==s[265]))]
    x=factor_panel(raw,s)
    r=x[(x.symbol=='000001')&(x.date==s[260])].iloc[0]
    assert pd.isna(r.future_price_return)

def test_no_future_data_for_signal():
    raw,s=fixture();base=factor_panel(raw,s)
    raw.loc[(raw.symbol=='000001')&(raw.date==s[282]),'close']*=5
    changed=factor_panel(raw,s)
    a=base[(base.symbol=='000001')&(base.date==s[260])].iloc[0]
    b=changed[(changed.symbol=='000001')&(changed.date==s[260])].iloc[0]
    assert a.momentum==b.momentum and a.reversal==b.reversal
    assert a.future_price_return!=b.future_price_return

def test_month_end_and_evaluate():
    raw,s=fixture();p=factor_panel(raw,s);m=month_end_signals(p)
    assert m.date.nunique()<p.date.nunique()
    ic,bins=evaluate(m,min_names=3,quantiles=3)
    assert set(ic.columns)=={'date','factor','split','n','rank_ic'}
    assert set(bins.columns)=={'date','factor','split','bin','n','mean_future_price_return'}

def test_nonpositive_raw_rejected(tmp_path):
    pd.DataFrame({'date':['2023-01-03'],'close':[-1]}).to_csv(tmp_path/'000001_raw.csv',index=False)
    with pytest.raises(ValueError,match='nonpositive'):load_raw_panel(tmp_path)

def test_bad_parameters():
    raw,s=fixture()
    with pytest.raises(ValueError):factor_panel(raw,s,21,21,1)
