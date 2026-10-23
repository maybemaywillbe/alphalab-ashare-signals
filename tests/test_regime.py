import numpy as np
import pandas as pd
from alphalab.regime import build_proxy, join_diagnostics, summarize

def test_no_forward_regime_leakage():
    dates=pd.bdate_range('2023-01-02',periods=350)
    a=pd.DataFrame({'date':list(dates)*3,'symbol':sum(([s]*len(dates) for s in ['000001','000002','000003']),[]),
        'close':np.tile(100*np.cumprod(np.full(len(dates),1.001)),3)})
    x=build_proxy(a,dates,min_daily_names=2,trend_days=21,vol_days=10,vol_history=70)
    assert x.loc[150,'regime']!='unknown_unknown'
    altered=a.copy();altered.loc[altered.date>dates[150],'close']*=10
    y=build_proxy(altered,dates,min_daily_names=2,trend_days=21,vol_days=10,vol_history=70)
    assert x.loc[150,'regime']==y.loc[150,'regime']
    assert np.isclose(x.loc[150,'trailing_trend'],y.loc[150,'trailing_trend'])

def test_missing_session_does_not_pad_returns():
    dates=pd.bdate_range('2024-01-01',periods=100)
    bars=pd.DataFrame({'date':list(dates)*2,'symbol':['000001']*100+['000002']*100,
                       'close':list(np.arange(1,101,dtype=float))*2})
    bars=bars.loc[~((bars.symbol=='000002')&(bars.date==dates[40]))]
    proxy=build_proxy(bars,dates,min_daily_names=2,trend_days=5,vol_days=4,vol_history=65)
    assert np.isnan(proxy.loc[40,'proxy_daily_return'])
    assert np.isnan(proxy.loc[41,'proxy_daily_return'])
    assert np.isnan(proxy.loc[42,'trailing_trend'])

def test_join_and_small_subgroups():
    dates=pd.bdate_range('2024-01-01',periods=5)
    m=pd.DataFrame({'date':dates,'factor':['reversal']*5,'split':['oos']*5,'n':[50]*5,
       'rank_ic':[.1,.2,-.1,.3,.1],'mean_spread':[.01,.02,-.01,.03,.01]})
    p=pd.DataFrame({'date':dates,'daily_names':[50]*5,'trailing_trend':[.1]*5,
       'trailing_volatility':[.02]*5,'prior_vol_median':[.01]*5,
       'trend_regime':['up']*5,'vol_regime':['high']*5,'regime':['up_high']*5})
    z=join_diagnostics(m,p);r=summarize(z,min_months=6)
    assert len(r)==1 and r.iloc[0]['months']==5
    assert not bool(r.iloc[0]['sufficient_months'])
    assert np.isnan(r.iloc[0]['ic_hac_t_descriptive'])
