import pandas as pd
from alphalab.decision import classify_gaps, qfq_diagnostic

def test_unverified_by_default():
    x=classify_gaps({'600519':['2025-01-02']},None)
    assert x[0]['status']=='unverified'

def test_evidence_requires_url():
    df=pd.DataFrame([{'symbol':'600519','date':'2025-01-02','classification':'suspended','source_url':''}])
    assert classify_gaps({'600519':['2025-01-02']},df)[0]['status']=='unverified'

def test_evidence_with_url():
    df=pd.DataFrame([{'symbol':'600519','date':'2025-01-02','classification':'suspended','source_url':'https://example.org/evidence'}])
    assert classify_gaps({'600519':['2025-01-02']},df)[0]['status']=='suspended'

def test_nonpositive_detection(tmp_path):
    p=tmp_path/'qfq.csv'
    pd.DataFrame({'date':['2020-01-01'],'open':[-1],'high':[1],'low':[0],'close':[1]}).to_csv(p,index=False)
    d=qfq_diagnostic(p)
    assert d['nonpositive_counts']['open']==1 and d['nonpositive_counts']['low']==1

def test_missing_csv(tmp_path):
    assert qfq_diagnostic(tmp_path/'missing.csv')['status']=='csv_not_supplied'
