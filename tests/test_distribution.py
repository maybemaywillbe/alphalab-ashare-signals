import numpy as np
import pandas as pd
from alphalab.distribution import analyze_formed

def sample():
    # Positive Spearman with negative Q5-Q1 mean spread: one large outlier in low group.
    rows=[]
    for i in range(25):
        r=float(i)/100
        if i==0:r=5.0
        rows.append(dict(date='2024-01-31',symbol=f'{i:06d}',momentum=float(i),reversal=float(i),future_price_return=r))
    return pd.DataFrame(rows)

def test_outputs_and_identity():
    d,b,t,s=analyze_formed(sample(),min_names=20)
    assert len(d)==2
    assert len(b)==10
    assert len(t)==20
    assert d.mean_spread.lt(0).all()
    assert d.rank_ic.gt(0).all()
    assert d.discordant.all()
    assert np.isfinite(s.avg_winsor_5pct_spread).all()

def test_ineligible():
    import pytest
    with pytest.raises(ValueError,match='No eligible'):
        analyze_formed(sample().iloc[:5],min_names=20)
