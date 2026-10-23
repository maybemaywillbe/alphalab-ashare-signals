import pandas as pd
import pytest
from alphalab.portfolio import simulate_cohorts

def panel(missing=False):
    rows=[]
    for i in range(25):
        rows.append(dict(date=pd.Timestamp('2024-01-31'),symbol=f'{i:06d}',
          entry_date=pd.Timestamp('2024-02-01'),exit_date=pd.Timestamp('2024-03-01'),
          reversal=float(i),momentum=float(i),future_price_return=float(i)/100 if not (missing and i==24) else float('nan')))
    return pd.DataFrame(rows)

def test_cohorts_no_lookahead_selection():
    a,m=simulate_cohorts(panel(),side_cost_bps=10)
    top=a[(a.factor=='reversal')&(a.portfolio=='top_quintile')].iloc[0]
    assert top.selected==5 and top.observed==5
    assert top.net_after_fixed_cost==pytest.approx(top.gross_mean_observed-.002)
    assert set(m[(m.factor=='reversal')&(m.portfolio=='top_quintile')].symbol)=={f'{i:06d}' for i in range(20,25)}

def test_missing_outcome_is_not_silently_dropped():
    a,m=simulate_cohorts(panel(missing=True))
    top=a[(a.factor=='reversal')&(a.portfolio=='top_quintile')].iloc[0]
    assert top.selected==5 and top.observed==4 and not top.fully_observed

def test_cost_negative_rejected():
    with pytest.raises(ValueError):simulate_cohorts(panel(),side_cost_bps=-1)
