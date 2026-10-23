import pandas as pd
from alphalab.audit_checks import calendar_coverage,listing_bounds,adjustment_comparison

def bars(dates, closes=None):
    closes=closes or [10]*len(dates)
    return pd.DataFrame({'date':pd.to_datetime(dates),'close':closes})

def test_gap_calendar_holiday_excluded():
    cal=pd.to_datetime(['2025-01-02','2025-01-03','2025-01-06','2025-01-07','2025-01-08'])
    r=calendar_coverage(bars(['2025-01-02','2025-01-08']),cal,'20250101','20250109',3)
    assert r['missing_within_observed_span']==3 and r['long_gap_count']==1

def test_calendar_unknown():
    assert calendar_coverage(bars(['2025-01-02']),None,'20250101','20250103')['status'].startswith('unknown')

def test_gap_not_assumed_suspension():
    cal=pd.to_datetime(['2025-01-02','2025-01-03','2025-01-06'])
    r=calendar_coverage(bars(['2025-01-02','2025-01-06']),cal,'20250101','20250107')
    assert r['status']=='checked_not_classified'

def test_listing_bounds_not_ipo():
    r=listing_bounds(bars(['2025-01-02']),'20250101','20251231')
    assert r['ipo_date']=='unverified' and r['last_bar_before_requested_end']

def test_adjustments_identical():
    x=bars(['2025-01-02','2025-01-03'],[10,11])
    r=adjustment_comparison(x,x,x)
    assert r['raw_equals_qfq'] and r['raw_equals_hfq']

def test_adjustments_different():
    x=bars(['2025-01-02'],[10]); y=bars(['2025-01-02'],[9])
    assert not adjustment_comparison(x,y,x)['raw_equals_qfq']

def test_adjustments_incomplete():
    assert adjustment_comparison(None,None,None)['status']=='incomplete'
