import pandas as pd
from alphalab.quality import validate_bars

def sample():
    return pd.DataFrame({'date':['2025-01-02','2025-01-03'], 'open':[10,11], 'high':[12,12],
                         'low':[9,10], 'close':[11,11.5], 'volume':[100,120]})

def test_good_bars():
    assert validate_bars(sample())['passed']

def test_duplicate_date():
    df = sample(); df.loc[1,'date'] = df.loc[0,'date']
    assert 'duplicate_dates:1' in validate_bars(df)['findings']

def test_impossible_high():
    df = sample(); df.loc[0,'high'] = 8
    assert 'high_below_ohlc' in validate_bars(df)['findings']

def test_missing_column():
    assert not validate_bars(sample().drop(columns=['volume']))['passed']

def test_unsorted():
    assert 'unsorted_dates' in validate_bars(sample().iloc[::-1])['findings']

def test_negative_volume():
    df = sample(); df.loc[0,'volume'] = -1
    assert 'negative_volume' in validate_bars(df)['findings']
