"""Run the frozen AlphaLab study on the selected sample.

Does not fetch data. Never represents a new sample as a PIT universe or a
reused date window as independent OOS. Derived reports are computed from the
verified local snapshots and frozen plan.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from . import release, robustness
from .study_plan import file_sha256, load_frozen_plan
from .universe import read_universe


def period_for(dates: pd.Series, plan: dict) -> pd.Series:
    x = pd.to_datetime(dates)
    result = pd.Series('outside_frozen_formations', index=dates.index, dtype='object')
    for name, (start, end) in plan['period_boundaries'].items():
        result.loc[x.between(pd.Timestamp(start), pd.Timestamp(end), inclusive='both')] = name
    return result


def _valid_metadata(folder: Path, symbol: str, kind: str, plan: dict,
                    allow_unverified: bool) -> None:
    path = folder / f'{symbol}_{kind}.csv'
    meta = path.with_suffix('.meta.json')
    if not path.exists():
        raise FileNotFoundError(f'Missing required input file: {path}')
    if not meta.exists():
        if not allow_unverified:
            raise FileNotFoundError(f'Missing {meta.name}; re-download or specify --allow-unverified-input-metadata')
        return
    info = json.loads(meta.read_text(encoding='utf-8'))
    if info.get('sha256') != file_sha256(path):
        raise ValueError(f'Corrupt or changed input file: {path.name}')
    if info.get('provider') != 'AKShare Sina daily history' and not allow_unverified:
        raise ValueError(f'Source provider for {path.name} is not the declared Sina feed')
    if info.get('adjust') != ('qfq' if kind == 'qfq' else '') and not allow_unverified:
        raise ValueError(f'Adjustment policy mismatch for {path.name}')
    start, end = info.get('start', ''), info.get('end', '')
    want_start = plan['data_start_for_lookback'].replace('-', '')
    want_end = plan['data_end'].replace('-', '')
    if (start > want_start or end < want_end) and not allow_unverified:
        raise ValueError(f'Cached request range {start}..{end} does not cover frozen {want_start}..{want_end}: {symbol}_{kind}')


def stage_subset(snapshot_root: Path, target: Path, selected: pd.DataFrame, plan: dict,
                 allow_unverified: bool = False) -> pd.DataFrame:
    """Create time-capped, selected-only temporary snapshots. Never edit original prices."""
    target.mkdir(parents=True, exist_ok=False)
    cap_start = pd.Timestamp(plan['data_start_for_lookback'])
    cap_end = pd.Timestamp(plan['data_end'])
    calendar_path = snapshot_root / 'exchange_calendar.csv'
    if not calendar_path.exists():
        raise FileNotFoundError('Missing official exchange_calendar.csv; never infer calendar from observed stock dates')
    cal = pd.read_csv(calendar_path)
    if 'date' not in cal.columns:
        raise ValueError('Missing calendar date column')
    cal_date = pd.to_datetime(cal['date'], errors='raise')
    cal = cal.loc[cal_date.between(cap_start, cap_end)].copy()
    if len(cal) < 252:
        raise ValueError('Calendar must cover a full momentum lookback')
    cal.to_csv(target / 'exchange_calendar.csv', index=False)
    details = [{'symbol':'', 'kind':'calendar', 'source_sha256':file_sha256(calendar_path),
                'staged_sha256':file_sha256(target/'exchange_calendar.csv'),'rows':len(cal)}]
    for r in selected.itertuples(index=False):
        for kind in ('raw', 'qfq'):
            _valid_metadata(snapshot_root, r.symbol, kind, plan, allow_unverified)
            src = snapshot_root / f'{r.symbol}_{kind}.csv'
            data = pd.read_csv(src)
            if 'date' not in data.columns:
                raise ValueError(f'Missing source date: {src.name}')
            src_dates = pd.to_datetime(data['date'], errors='raise')
            valid = src_dates.between(cap_start, cap_end)
            if r.listed_on:
                valid &= src_dates.ge(pd.Timestamp(r.listed_on))
            if r.delisted_on:
                valid &= src_dates.le(pd.Timestamp(r.delisted_on))
            data = data.loc[valid].copy()
            if data.empty:
                raise ValueError(f'Empty selected history for {src.name}; frozen universe must not be silently replaced')
            data.to_csv(target / src.name, index=False)
            meta_src = src.with_suffix('.meta.json')
            prior = json.loads(meta_src.read_text()) if meta_src.exists() else {}
            prior.update({'sha256': file_sha256(target/src.name),
                          'derived_stage_only': True, 'original_input_sha256':file_sha256(src),
                          'stage_sample_dates':['2014-01-01',plan['data_end']],
                          'PIT_membership_claim':False})
            (target / f'{r.symbol}_{kind}.meta.json').write_text(json.dumps(prior,indent=2),encoding='utf-8')
            details.append({'symbol':r.symbol,'kind':kind,'source_sha256':file_sha256(src),
                            'staged_sha256':file_sha256(target/src.name),'rows':len(data)})
    return pd.DataFrame(details)


def summarize_new_run(result_root: Path, output_root: Path, plan: dict) -> dict:
    """Summarize diagnostics generated in the current validated study run."""
    ic = pd.read_csv(result_root/'canonical_rank_ic_complete_case.csv',parse_dates=['date'])
    funnel = pd.read_csv(result_root/'factor_month_eligibility_funnel.csv',parse_dates=['date'])
    membership = pd.read_csv(result_root/'group_policy_comparison.csv',parse_dates=['date'])
    raw_monthly = pd.read_csv(result_root/'descriptive_complete_case'/'monthly_diagnostics.csv',parse_dates=['date'])
    selected = []
    for source in (ic, funnel, membership, raw_monthly):
        x = source.copy()
        x['study_period'] = period_for(x['date'],plan)
        x = x.loc[x.study_period != 'outside_frozen_formations'].copy()
        selected.append(x)
    ic, funnel, membership, raw_monthly = selected
    if ic.empty:
        raise ValueError('No eligible observations in frozen study window')
    ic.to_csv(output_root/'study_rank_ic_monthly.csv',index=False)
    funnel.to_csv(output_root/'study_eligibility_funnel.csv',index=False)
    membership.to_csv(output_root/'study_membership_audit.csv',index=False)
    raw_monthly.to_csv(output_root/'study_descriptive_monthly.csv',index=False)
    stats = []
    for (factor, period), part in ic.groupby(['factor','study_period'],sort=True):
        ci = robustness.hac_mean(part.rank_ic_complete_case.to_numpy(),lags=plan['hac_lags'])
        stats.append({'factor':factor,'study_period':period,'n_factor_months':len(part),
                      'mean_rank_ic':ci['mean'],'hac_lags':plan['hac_lags'],
                      'hac_standard_error':ci['se'],'ci_low':ci['ci_low'],'ci_high':ci['ci_high'],
                      'positive_ic_share':float((part.rank_ic_complete_case>0).mean())})
    summary = pd.DataFrame(stats)
    summary.to_csv(output_root/'study_ic_summary.csv',index=False)
    membership_eligible = membership.loc[membership.ic_descriptive_eligible.astype(str).str.lower().eq('true')].copy()
    gaps = membership_eligible.groupby(['factor','study_period'],as_index=False).agg(
        eligible_factor_months=('date','size'),
        top_group_changed=('same_top_members',lambda s: int((~s.astype(str).str.lower().eq('true')).sum())),
        bottom_group_changed=('same_bottom_members',lambda s: int((~s.astype(str).str.lower().eq('true')).sum())))
    gaps.to_csv(output_root/'study_group_policy_summary.csv',index=False)
    source_stats = json.loads((result_root/'release_validation.json').read_text())
    result = {'study_id':plan['study_id'],'status':'fresh_run_exploratory_not_investable',
              'frozen_protocol_hash_sha256':None,
              'included_stock_count':source_stats['snapshot_symbols_usable'],
              'eligible_factor_month_rows':len(ic),
              'factor_period_summary_rows':len(summary),
              'period_names':sorted(set(ic.study_period)),
              'top_membership_mismatch_months':int(gaps.top_group_changed.sum()),
              'historical_PIT_universe_verified':False,
              'publishable_input_provenance':False,
              'untouched_prospective_holdout':False,
              'notable_limits':plan['risks'],
              'data_license':'Sina input histories intentionally excluded from public deliverables'}
    (output_root/'study_validation.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result


def run_study(snapshots: str, plan_file: str, selected_file: str, output: str,
              allow_unverified_input_metadata: bool = False) -> dict:
    plan = load_frozen_plan(plan_file, selected_file)
    selected = read_universe(selected_file)
    snapshots_path = Path(snapshots).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    if snapshots_path == output_root or snapshots_path in output_root.parents or output_root in snapshots_path.parents:
        raise ValueError('Keep frozen snapshots and outputs in separate directories')
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError('Refusing to overwrite existing research outputs; provide a new output folder')
    output_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='staged_',dir=output_root) as stage_name:
        stage = Path(stage_name)/'subset'
        source_checksums = stage_subset(snapshots_path,stage,selected,plan,allow_unverified_input_metadata)
        source_checksums.to_csv(output_root/'source_input_checksums_PRIVATE.csv',index=False)
        result_root=output_root/'pipeline'
        release.run(str(stage),str(result_root),
                    min_names=plan['minimum_complete_case_names'],hac_lags=plan['hac_lags'])
        summary = summarize_new_run(result_root, output_root, plan)
    summary['frozen_protocol_hash_sha256']=file_sha256(plan_file)
    summary['publishable_input_provenance']=not allow_unverified_input_metadata
    (output_root/'study_validation.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description='Run the frozen A-share research plan; raw provider data is not redistributed')
    p.add_argument('--snapshots',default='inputs/sina_snapshots')
    p.add_argument('--plan',default='configs/study_plan.json')
    p.add_argument('--selected',default='inputs/universe_selected.csv')
    p.add_argument('--output',default='outputs/study_2026')
    p.add_argument('--allow-unverified-input-metadata',action='store_true',
                   help='Explicitly override missing/stale cache-request metadata; never certifies the source')
    a=p.parse_args()
    print(json.dumps(run_study(a.snapshots,a.plan,a.selected,a.output,a.allow_unverified_input_metadata),indent=2))


if __name__ == '__main__':
    main()
