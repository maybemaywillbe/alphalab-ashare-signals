import pandas as pd
import pytest
from alphalab.paired import analyze

def sample():
    rows=[]; members=[]
    for date,top,all_ in [('2024-01-31',True,True),('2024-02-29',True,False)]:
        for portfolio,full,gross in [('top_quintile',top,.10),('all_signals',all_,.05)]:
            rows.append(dict(date=pd.Timestamp(date),factor='reversal',split='oos',portfolio=portfolio,selected=5,observed=5 if full else 4,coverage=1 if full else .8,gross_mean_observed=gross,net_after_fixed_cost=gross-.002,fully_observed=full))
        members.append(dict(date=pd.Timestamp(date),factor='reversal',split='oos',symbol='000158',bin=5,observed_return=True,future_price_return=1.31))
    return pd.DataFrame(rows),pd.DataFrame(members)

def test_paired_months_not_mismatched():
    p,s,t,c=analyze(*sample())
    assert len(p)==2 and p.both_full.sum()==1
    assert s.iloc[0].full_paired_mean_net_diff==pytest.approx(.05)
    assert s.iloc[0].partial_observed_mean_net_diff==pytest.approx(.05)
    assert len(t)==2

def test_no_pair_rejected():
    a,b=sample();a=a.iloc[:-1]
    with pytest.raises(ValueError,match='unpaired'):analyze(a,b)

def test_threshold():
    with pytest.raises(ValueError):analyze(*sample(),tail_threshold=0)
