import pandas as pd
from alphalab.coverage import coverage_table, universe_history_check
from alphalab.factors import evaluate

def sample(n):
    return pd.DataFrame({'date':[pd.Timestamp('2024-01-31')]*n,'symbol':[f'{i:06d}' for i in range(n)],
      'momentum':list(range(n)),'reversal':list(range(n-1,-1,-1)),
      'future_price_return':[float(i*i) for i in range(n)]})

def test_default_blocks_five_names():
    x=sample(5); ic,bins=evaluate(x)
    assert ic.empty and bins.empty
    c=coverage_table(x)
    assert len(c)==2 and not c.eligible_for_ic.any()
    assert set(c.reason)=={'insufficient_names'}

def test_explicit_three_name_diagnostic():
    x=sample(5);ic,bins=evaluate(x,min_names=3,quantiles=3)
    assert len(ic)==2 and not bins.empty
    assert coverage_table(x,min_names=3).eligible_for_ic.all()

def test_twenty_name_default():
    x=sample(20); ic,_=evaluate(x)
    assert len(ic)==2
    assert coverage_table(x).eligible_for_ic.all()

def test_coverage_missing_target():
    x=sample(20);x.loc[:2,'future_price_return']=float('nan')
    c=coverage_table(x)
    assert set(c.paired_available)=={17}
    assert not c.eligible_for_ic.any()

def test_universe_unknown():
    assert universe_history_check(None,['600519'],[] )['status']=='unverified'
