"""Synthetic golden-pipeline checks. These NEVER certify historical data or tradability."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from alphalab.release import (snapshot_inventory, run, relabel_period,
                              membership_policy_audit, eligibility_funnel)
from alphalab.selection import rank_bins


def make_snapshots(folder: Path, periods=570, count=25):
    folder.mkdir(parents=True)
    dates = pd.bdate_range('2021-01-04', periods=periods)
    pd.DataFrame({'date': dates}).to_csv(folder / 'exchange_calendar.csv', index=False)
    for i in range(count):
        t = np.arange(periods)
        log_ret = .0003*np.sin(t/24)+.003*np.sin(t/19+i*.13)+.0003*(i-12)/12+.001*np.cos(t/7+i)
        price = 20 * np.exp(np.cumsum(log_ret))
        if i == 0:
            price[505:510] = np.nan
        df = pd.DataFrame({'date': dates, 'open': price, 'high': price*1.01,
                           'low': price*.99, 'close': price, 'volume': 10000})
        df = df[df.close.notna()]
        sym = f'{i+1:06d}'
        for suffix in ('raw', 'qfq'):
            df.to_csv(folder / f'{sym}_{suffix}.csv', index=False)
    return dates


def test_rank_bins_explicit_policies():
    x = pd.DataFrame({'symbol':[f'{i:06d}' for i in range(25)],
                      'reversal':np.arange(25), 'future_price_return':np.arange(25)/100})
    x.loc[24, 'future_price_return'] = np.nan
    signal = rank_bins(x, 'reversal', policy='signal')
    complete = rank_bins(x, 'reversal', policy='complete_case')
    assert '000024' in set(signal.loc[signal.bin == 5, 'symbol'])
    assert '000024' not in set(complete.loc[complete.bin == 5, 'symbol'])
    with pytest.raises(ValueError, match='policy'):
        rank_bins(x, 'reversal', policy='oops')


def test_snapshot_manifest_never_infers_retrieval_date(tmp_path):
    make_snapshots(tmp_path / 'snapshot', periods=30, count=2)
    manifest, meta = snapshot_inventory(tmp_path / 'snapshot')
    assert len(manifest) == 5
    assert all(manifest.retrieval_date_user_declared == 'unknown')
    assert meta['historical_pit_universe_verified'] is False
    assert len(set(manifest.sha256)) >= 3
    p = tmp_path / 'snapshot' / '000001_qfq.meta.json'
    p.write_text('{"sha256":"wrong"}', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum conflict'):
        snapshot_inventory(tmp_path / 'snapshot')


def test_full_offline_research_pipeline_golden_fixture(tmp_path):
    snapshots = tmp_path / 'snapshots'
    make_snapshots(snapshots)
    output = tmp_path / 'out'
    report = run(str(snapshots), str(output))
    assert report['snapshot_symbols_usable'] == 25
    assert report['descriptive_ic_factor_month_rows'] == 38
    assert report['membership_audit'] == {'comparable_factor_months': 38,
        'different_top_membership_months': 2, 'different_bottom_membership_months': 1}
    assert (output / 'input_provenance.json').is_file()
    assert (output / 'canonical_rank_ic_complete_case.csv').is_file()
    funnel = pd.read_csv(output / 'factor_month_eligibility_funnel.csv')
    assert len(funnel) == 54
    assert (funnel.signal_with_both_endpoints >= funnel.strict_full_path_outcome_valid).all()
    assert (funnel.signal_valid >= funnel.strict_full_path_outcome_valid).all()
    assert (funnel.endpoint_available_but_strict_path_missing >= 0).all()
    rows = pd.read_csv(output / 'canonical_rank_ic_complete_case.csv')
    assert set(rows['split']).issubset({'development', 'historical_evaluation_reused'})
    assert 'oos' not in set(rows['split'])
    paired = pd.read_csv(output / 'canonical_signal_first_paired_cohorts.csv')
    assert paired.fixed_cost_cancels.all()
    assert (output / 'hac_lag_sensitivity_exploratory.csv').is_file()
    assert (output / 'unique_extreme_price_events_unverified.csv').is_file()
    # Inputs must not be changed by a release run.
    old = snapshot_inventory(snapshots)[0].set_index('file').sha256.to_dict()
    new = pd.read_csv(output / 'input_sha256_inventory.csv').set_index('file').sha256.to_dict()
    assert new == old


def test_public_period_no_oos_label():
    x = pd.DataFrame({'split': ['oos', 'development'], 'rank_ic': [0.1, 0.2]})
    z = relabel_period(x)
    assert list(z.split) == ['historical_evaluation_reused', 'development']
    assert list(x.split) == ['oos', 'development']
