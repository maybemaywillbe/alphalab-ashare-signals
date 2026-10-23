"""Confirm new-run dates, licensing gates and metadata cannot silently drift."""
import json
from pathlib import Path
import pandas as pd
import pytest
from alphalab.study_run import period_for, _valid_metadata
from alphalab.study_plan import file_sha256


def test_period_labels_distinguish_reused_and_historical_extension():
    dates=pd.Series(['2014-12-31','2020-01-31','2023-09-28','2026-09-30','2027-01-29'])
    plan={'period_boundaries':{
        'development':['2015-01-01','2022-12-31'],
        'historical_evaluation_reused':['2023-01-01','2025-12-31'],
        'new_historical_extension_not_prospective':['2026-01-01','2026-10-23']}}
    assert period_for(dates,plan).tolist()==[
        'outside_frozen_formations','development','historical_evaluation_reused',
        'new_historical_extension_not_prospective','outside_frozen_formations']


def test_stale_or_non_sina_metadata_blocked(tmp_path):
    src=tmp_path/'600001_qfq.csv'
    src.write_text('date,close\n2025-01-02,10\n',encoding='utf-8')
    meta=src.with_suffix('.meta.json')
    spec={'start':'20140101','end':'20261023','adjust':'qfq',
          'provider':'AKShare Sina daily history','sha256':file_sha256(src)}
    meta.write_text(json.dumps(spec))
    plan={'data_start_for_lookback':'2014-01-01','data_end':'2026-10-23'}
    _valid_metadata(tmp_path,'600001','qfq',plan,False)
    spec['end']='20251231';meta.write_text(json.dumps(spec))
    with pytest.raises(ValueError,match='does not cover'):
        _valid_metadata(tmp_path,'600001','qfq',plan,False)
    spec['end']='20261023';spec['provider']='not verified';meta.write_text(json.dumps(spec))
    with pytest.raises(ValueError,match='Source provider'):
        _valid_metadata(tmp_path,'600001','qfq',plan,False)
    with pytest.raises(FileNotFoundError,match='Missing required'):
        _valid_metadata(tmp_path,'600002','raw',plan,True)


def test_publication_rejects_synthetic_or_unverified(tmp_path):
    from scripts.prepare_public_release import stage_public
    run=tmp_path/'run';run.mkdir()
    (run/'study_validation.json').write_text(json.dumps({
        'status':'fresh_run_exploratory_not_investable','publishable_input_provenance':False}))
    with pytest.raises(ValueError,match='not verified'):
        stage_public(tmp_path,run,tmp_path/'public')
