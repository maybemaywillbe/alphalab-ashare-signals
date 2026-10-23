"""Frozen, auditable candidate selection and analysis protocol.

This removes *code-order selection*, NOT current-listing survivorship bias.
A genuinely point-in-time universe requires independent historical membership
including delistings; current-stock lists are not a substitute.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from .universe import read_universe

STRATA = ('sh_main', 'sz_main', 'chinext', 'star')
QUOTA_WEIGHTS = {'sh_main': .40, 'sz_main': .40, 'chinext': .15, 'star': .05}


def classify(symbol: str) -> str | None:
    symbol = str(symbol).zfill(6)
    if symbol.startswith(('688', '689')):
        return 'star'
    if symbol.startswith(('600', '601', '603', '605')):
        return 'sh_main'
    if symbol.startswith(('000', '001', '002', '003')):
        return 'sz_main'
    # ChiNext includes the 302 code family assigned for securities such as
    # 302132 (effective 2025-02-17), in addition to the 300/301 ranges.
    # See the SZSE code-range table index and the issuer's filed code-change
    # notice (302132 effective 2025-02-17):
    # https://www.szse.cn/marketServices/technicalservice/index.html
    # https://disc.static.szse.cn/download/disc/disk03/finalpage/2025-02-07/e2d8b9d3-879b-4587-9e1e-235ebf4c8a44.PDF
    # Do not infer unverified 303+ ranges from older generic FAQs.
    if symbol.startswith(('300', '301', '302')):
        return 'chinext'
    return None


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def quota_for(target: int) -> dict[str, int]:
    if target < 20:
        raise ValueError('target must be >=20, enough to support all four market strata')
    basic = {name: int(target * QUOTA_WEIGHTS[name]) for name in STRATA}
    remainder = target - sum(basic.values())
    order = sorted(STRATA, key=lambda name: (-(target * QUOTA_WEIGHTS[name] - basic[name]), STRATA.index(name)))
    for name in order[:remainder]:
        basic[name] += 1
    return basic


def select_universe(source: str | Path, target: int = 100, seed: int = 20261023) -> pd.DataFrame:
    """A fixed SHA256 lottery within prespecified A-share board quotas.

    Must NEVER be interpreted as a PIT or unbiased historical market universe.
    Input candidate frame is independently snapshotted before returns are run.
    """
    candidate = read_universe(source)
    candidate = candidate.assign(stratum=candidate.symbol.map(classify))
    candidate = candidate[candidate.stratum.isin(STRATA)].copy()
    quotas = quota_for(target)
    selected = []
    for name in STRATA:
        part = candidate[candidate.stratum == name].copy()
        required = quotas[name]
        if len(part) < required:
            raise ValueError(f'only {len(part)} {name} candidates; need {required}. Refusing to change quotas after seeing data.')
        part['selection_hash'] = part.symbol.apply(
            lambda sym: hashlib.sha256(f'AlphaLab|{seed}|{name}|{sym}'.encode()).hexdigest()
        )
        selected.append(part.sort_values(['selection_hash', 'symbol']).head(required))
    return pd.concat(selected, ignore_index=True).sort_values(['stratum','selection_hash']).reset_index(drop=True)


def freeze_plan(source: str | Path, plan_path: str | Path,
                selected_path: str | Path, target: int = 100, seed: int = 20261023,
                formation_start: str = '2015-01-01', data_end: str = '2026-10-23') -> dict:
    if pd.Timestamp(formation_start) >= pd.Timestamp(data_end):
        raise ValueError('formation_start must be before data_end')
    source = Path(source)
    plan_path = Path(plan_path)
    selected_path = Path(selected_path)
    if plan_path.exists() or selected_path.exists():
        raise FileExistsError('Frozen design already exists; never silently overwrite a study plan')
    selected = select_universe(source, target=target, seed=seed)
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    export_cols = ['symbol','listed_on','delisted_on','source','verified','stratum','selection_hash']
    selected[export_cols].to_csv(selected_path, index=False)
    plan = {
        'study_id': 'Ashare_stratified_hash_20261023',
        'protocol_status': 'frozen_before_this_new_data_run_not_preregistered_before_old_exploration',
        'selection_method': 'stratified_SHA256_seeded_without_replacement',
        'selection_seed': seed,
        'target_names': target,
        'quota': quota_for(target),
        'candidate_source_sha256': file_sha256(source),
        'selected_universe_sha256': file_sha256(selected_path),
        'candidate_source_file': source.name,
        'selected_universe_file': selected_path.name,
        'data_source': 'AKShare Sina daily raw and retrospective qfq; third-party redistribution permission not established',
        'data_start_for_lookback': '2014-01-01',
        'formation_start': formation_start,
        'data_end': data_end,
        'factors': {'momentum': 'P[t-21]/P[t-252]-1', 'reversal': '-(P[t]/P[t-21]-1)'},
        'outcome': 'P[t+22]/P[t+1]-1 with observed full forward path',
        'minimum_complete_case_names': 20,
        'hac_lags': 3,
        'period_boundaries': {
            'development': ['2015-01-01', '2022-12-31'],
            'historical_evaluation_reused': ['2023-01-01', '2025-12-31'],
            'new_historical_extension_not_prospective': ['2026-01-01', data_end],
        },
        'not_point_in_time_universe': True,
        'risks': [
            'Current-listed candidate pool still excludes companies delisted before candidate collection.',
            'Stratification removes code-order concentration only, not survivorship or historical market representation.',
            '2023-2025 already inspected; no untouched time-based OOS period.',
            'Retrospective QFQ and price-only forward outcomes; not investable returns.',
            '2026 extension is historical and may be incomplete; not prospective validation.',
        ],
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    plan_path.with_suffix(plan_path.suffix + '.sha256').write_text(file_sha256(plan_path) + '\n', encoding='ascii')
    return plan


def load_frozen_plan(plan_path: str | Path, selected_path: str | Path) -> dict:
    path = Path(plan_path)
    digest_path = path.with_suffix(path.suffix + '.sha256')
    if not digest_path.exists():
        raise FileNotFoundError('Missing committed study plan SHA256 sidecar')
    if digest_path.read_text().strip() != file_sha256(path):
        raise ValueError('Frozen study plan modified; do not silently update the plan')
    plan = json.loads(path.read_text(encoding='utf-8'))
    if plan['selected_universe_sha256'] != file_sha256(selected_path):
        raise ValueError('Frozen selected universe changed after study plan creation')
    selected = read_universe(selected_path)
    if len(selected) != plan['target_names']:
        raise ValueError('Frozen selected universe sample size changed')
    for name in STRATA:
        if sum(selected.symbol.map(classify).eq(name)) != plan['quota'][name]:
            raise ValueError('Frozen market-board quota changed')
    return plan


def main() -> None:
    p = argparse.ArgumentParser(description='Freeze pre-analysis sample lottery; cannot fix historical survivorship')
    p.add_argument('--candidates', required=True)
    p.add_argument('--plan', default='configs/study_plan.json')
    p.add_argument('--selected', default='inputs/universe_selected.csv')
    p.add_argument('--target', type=int, default=100)
    p.add_argument('--seed', type=int, default=20261023)
    p.add_argument('--formation-start', default='2015-01-01')
    p.add_argument('--data-end', default='2026-10-23')
    a = p.parse_args()
    result = freeze_plan(a.candidates, a.plan, a.selected, a.target, a.seed, a.formation_start, a.data_end)
    print(f"Frozen {result['target_names']} names; sha256 {file_sha256(a.plan)}")
    print('WARNING: current-listed survivor bias remains; this is NOT a PIT universe.')


if __name__ == '__main__':
    main()
