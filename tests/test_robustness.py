import numpy as np
import pandas as pd
from alphalab.robustness import hac_mean, summarize_ic, annual_ic, quantile_spread

def test_hac_constant():
    r=hac_mean([1,1,1,1]);assert r['mean']==1 and r['se']==0 and r['t'] is None

def test_hac_short():
    assert hac_mean([0,1])['se'] is None

def test_hac_lags():
    assert np.isfinite(hac_mean([.1,.2,-.1,.3,.1],lags=3)['se'])

def test_group_summaries():
    x=pd.DataFrame({'factor':['reversal']*4,'split':['oos']*4,'date':pd.date_range('2023-01-01',periods=4,freq='MS'),'rank_ic':[.1,.2,.1,-.1],'n':[50]*4})
    assert len(summarize_ic(x))==1
    assert annual_ic(x).iloc[0]['periods']==4

def test_spread():
    x=pd.DataFrame({'factor':['momentum']*2,'split':['oos']*2,'date':['2023-01-01']*2,'bin':[1,5],'mean_future_price_return':[.01,.03]})
    assert abs(quantile_spread(x).iloc[0].mean_high_minus_low-.02)<1e-12
