import numpy as np
import pandas as pd
from alphalab.structural import decompose,hac_ols,interactions,prepare

def panel():
    rows=[]
    for split,year in [('development',2021),('oos',2024)]:
        for i in range(20):
            state='down' if i < (10 if split=='development' else 15) else 'up'
            y=(0.1 if state=='down' else -0.1)+(0.03 if split=='oos' else 0)
            rows.append(dict(date=f'{year}-{i//2+1:02d}-{1+i%2:02d}',factor='reversal',split=split,
                trend_regime=state,regime_eligible=True,rank_ic=y,mean_spread=y/10))
    return pd.DataFrame(rows)

def test_exact_decomposition():
    dec,cells=decompose(panel())
    assert len(cells)==4
    for r in dec.itertuples():
        assert np.isclose(r.total_change,r.composition_effect+r.within_regime_effect)
        assert np.isclose(r.within_regime_effect,0.03 if r.metric=='rank_ic' else 0.003)

def test_hac_regression_coefficients():
    g=panel();r=interactions(g)
    z=r[(r.metric=='rank_ic')].set_index('term')
    assert np.isclose(z.loc['oos_x_down_interaction','estimate'],0,atol=1e-10)
    assert np.isclose(z.loc['oos_shift_up','estimate'],0.03)

def test_hac_rank_deficiency():
    assert hac_ols([1,2,3],np.ones((3,2))) is None

def test_prepare_excludes_unknown_and_false(tmp_path):
    g=panel();g.loc[0,'regime_eligible']=False
    p=tmp_path/'x.csv';g.to_csv(p,index=False)
    assert len(prepare(p))==len(g)-1
