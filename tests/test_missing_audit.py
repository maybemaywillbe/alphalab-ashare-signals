import pandas as pd
import pytest
from alphalab.missing_audit import audit_members,coverage_sensitivity,extreme_check

def member(symbol='000001', observed=False, ret=None, exit='2026-01-30'):
    return pd.DataFrame([dict(date='2025-12-31',factor='reversal',split='oos',symbol=symbol,portfolio='top_quintile',entry_date='2026-01-02',exit_date=exit,observed_return=observed,future_price_return=ret)])

def test_end_censor():
    a=audit_members(member(),data_end='2025-12-31')
    assert a.reason.iloc[0]=='horizon_beyond_declared_data_end'

def test_unclassified_without_snapshots():
    assert audit_members(member()).reason.iloc[0]=='unclassified_no_snapshot'

def test_missing_planned_horizon():
    a=audit_members(member(exit=None))
    assert a.reason.iloc[0]=='planned_horizon_dates_unavailable_at_sample_end'

def test_missing_snapshot(tmp_path):
    assert audit_members(member(),snapshots=tmp_path).reason.iloc[0]=='qfq_missing_or_invalid_file'

def test_entry_before_history(tmp_path):
    d=pd.DataFrame([dict(date='2026-01-10',open=10,high=10,low=10,close=10,volume=100),dict(date='2026-02-02',open=11,high=11,low=11,close=11,volume=100)])
    d.to_csv(tmp_path/'000001_qfq.csv',index=False)
    assert audit_members(member(),snapshots=tmp_path).reason.iloc[0]=='entry_before_symbol_history'

def test_coverage():
    rows=[]
    for name,cov,net in [('top_quintile',1,0.03),('all_signals',0.94,0.02)]:
        rows.append(dict(date='2025-01-31',factor='reversal',split='oos',portfolio=name,coverage=cov,observed=10,net_after_fixed_cost=net))
    s,_=coverage_sensitivity(pd.DataFrame(rows))
    assert s[s.min_coverage==0.9].eligible_months.iloc[0]==1
    assert s[s.min_coverage==0.95].eligible_months.iloc[0]==0

def test_extreme_not_verified_without_bars():
    a=audit_members(member(observed=True,ret=1.5))
    assert extreme_check(a).verification_status.iloc[0]=='qfq_bars_unavailable'

def test_duplicate_rejected():
    x=member()
    with pytest.raises(ValueError,match='duplicate'):audit_members(pd.concat([x,x]))
