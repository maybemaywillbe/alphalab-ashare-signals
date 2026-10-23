#!/usr/bin/env python3
"""Create a privacy-scoped public package from a validated study run.

Only explicit allowlisted files are copied into the destination.
"""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
import pandas as pd


def stage_public(root:Path, run:Path, dest:Path) -> Path:
    root,run,dest=[Path(x).resolve() for x in (root,run,dest)]
    if dest.exists():raise FileExistsError(f'Public tree already exists: {dest}')
    study=json.loads((run/'study_validation.json').read_text(encoding='utf-8'))
    if study.get('status')!='fresh_run_exploratory_not_investable':
        raise ValueError('Refusing publication: a validated study-run record is required')
    if not study.get('publishable_input_provenance'):
        raise ValueError('Refusing publication: source snapshot metadata not verified; synthetic fixtures cannot be published')
    report=run/'public_report'
    if not (report/'research_report.pdf').exists() or len(list((report/'figures').glob('*.png')))!=6:
        raise FileNotFoundError('Expected study report PDF and six figures are missing')
    for key in ('configs/study_plan.json','configs/study_plan.json.sha256','inputs/universe_selected.csv'):
        if not (root/key).exists():raise FileNotFoundError(f'Frozen public input missing: {key}')
    # Verify the plan and selected universe BEFORE opening the output directory.
    from alphalab.study_plan import load_frozen_plan
    load_frozen_plan(root/'configs/study_plan.json',root/'inputs/universe_selected.csv')
    target=dest/'AlphaLab'
    target.mkdir(parents=True)
    allowed_root=['pyproject.toml','requirements.txt','.gitignore','LICENSE','THIRD_PARTY_DATA.md']
    for file in allowed_root:
        if not (root/file).is_file(): raise FileNotFoundError(f'Public deliverable missing required {file}')
        (target/file).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/file,target/file)
    for folder in ('alphalab','tests'):
        for src in (root/folder).rglob('*.py'):
            relative=src.relative_to(root);copy_to=target/relative
            copy_to.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,copy_to)
    public_scripts=['build_research_report.py','prepare_public_release.py','run_end_to_end_mac.sh','run_study_analysis_mac.sh']
    for name in public_scripts:
        src=root/'scripts'/name
        if not src.is_file():raise FileNotFoundError(f'Missing public script {name}')
        destfile=target/'scripts'/name;destfile.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,destfile)
    for key in ('configs/study_plan.json','configs/study_plan.json.sha256','inputs/universe_selected.csv',
                'docs/REPRODUCIBILITY_CN.md','docs/STUDY_METHOD.md'):
        src=root/key;destfile=target/key;destfile.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,destfile)
    for src in (report/'figures').glob('*'):
        if src.suffix not in ('.png','.svg'):continue
        destfile=target/'reports'/'figures'/src.name;destfile.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,destfile)
    for name in ('research_report.pdf','research_report.md'):
        src=report/name;destfile=target/'reports'/name;destfile.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,destfile)
    for name in ('study_ic_summary.csv','study_group_policy_summary.csv','hac_ic_lag_sensitivity.csv'):
        src=(report/name if name=='hac_ic_lag_sensitivity.csv' else run/name);destfile=target/'research_inputs'/name;destfile.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,destfile)
    # Keep only sanitized numerical counts and provenance flags.
    allowed_status={key:study[key] for key in ('study_id','status','frozen_protocol_hash_sha256',
                  'included_stock_count','eligible_factor_month_rows','factor_period_summary_rows',
                  'period_names','top_membership_mismatch_months','historical_PIT_universe_verified',
                  'untouched_prospective_holdout','notable_limits','data_license')}
    (target/'research_inputs'/'study_validation.json').write_text(json.dumps(allowed_status,indent=2)+'\n',encoding='utf-8')
    # CI installs test dependencies and runs the bundled test suite without downloading market data.
    workflow=target/'.github/workflows/ci.yml';workflow.parent.mkdir(parents=True,exist_ok=True)
    workflow.write_text('''name: tests\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    strategy:\n      matrix:\n        python-version: ["3.11", "3.13"]\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: ${{ matrix.python-version }}\n      - run: python -m pip install -e ".[dev]"\n      - run: python -m pytest -q\n''',encoding='utf-8')
    stats=pd.read_csv(run/'study_ic_summary.csv')
    rows=[]
    labels={'development':'2015–2022 development',
            'historical_evaluation_reused':'2023–2025 reused historical evaluation',
            'new_historical_extension_not_prospective':'2026 historical extension'}
    for r in stats.itertuples():
        rows.append(f'| {r.factor} | {labels.get(r.study_period,r.study_period)} | {int(r.n_factor_months)} | {r.mean_rank_ic:+.4f} |')
    readme=f'''# AlphaLab: A-Share Momentum and Short-Term Reversal

**Exploratory empirical research. The reported associations are not investment performance.**

[Research report](reports/research_report.pdf) · [Study design](docs/STUDY_METHOD.md) · [中文复现指南](docs/REPRODUCIBILITY_CN.md)

## Study design

The analysis uses 100 currently listed SSE/SZSE stocks selected with SHA-256 seed `20261023` and fixed quotas: Shanghai main board 40, Shenzhen main board 40, ChiNext 15, and STAR 5. Current-list membership creates survivorship bias; this is not a historical point-in-time universe.

BaoStock `query_stock_basic()` supplies the recorded current candidate-list source; the original candidate CSV is not distributed, so the source hash and original lottery cannot be independently verified or reconstructed. The included frozen 100-stock list supports analysis reproduction. AKShare/Sina supplies historical raw/QFQ daily prices and the exchange calendar. These data sources serve separate roles. Sina history does not recreate or change the frozen sample.

Signals are skipped-month momentum and short-term reversal. Monthly cross-sectional Spearman Rank IC is the primary association statistic; mean IC uncertainty uses HAC(3). Forward outcomes are QFQ price returns, not total returns or executable portfolio PnL. The 2023–2025 period is reused historical evaluation, not an untouched holdout. The 2026 observations are a historical extension, not prospective validation.

| Factor | Study period | Factor-months | Mean Rank IC |
|---|---|---:|---:|
{chr(10).join(rows)}

See the [research report](reports/research_report.pdf) for confidence intervals, lag sensitivity, monthly coverage, group-membership diagnostics, and limitations.

## Reproducibility

Install the project and run the frozen workflow from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,viz,fetch]'
python -m pytest -q
bash scripts/run_end_to_end_mac.sh
```

The workflow requires `configs/study_plan.json`, `configs/study_plan.json.sha256`, and `inputs/universe_selected.csv`. It verifies the plan hash and 100-stock sample before collecting price history. A missing or invalid frozen input stops execution; the workflow does not fetch a new BaoStock list or resample. Restore the matching frozen files from this release package.

Sina/AKShare provider revisions to daily bars, adjustment factors, or backfilled records may change exact numerical results on a fresh download. Raw Sina histories are not included in this repository.

## Research and data limitations

- The current-listed sample has survivorship bias and is not a historical PIT universe.
- 2023–2025 was not reserved from prior examination; 2026 is a short historical extension.
- Retrospective QFQ adjustment vintage, total-return treatment, execution, liquidity, shorting, and complete transaction costs are not independently verified.
- Third-party price-data redistribution permission is not established; see [data notice](THIRD_PARTY_DATA.md).

## License

The MIT license applies to original project code only. It does not grant rights to third-party data or trademarks.
'''
    (target/'README.md').write_text(readme,encoding='utf-8')
    # Fatal name/pattern screening on every staged file, including nested paths.
    all_files=[p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()]
    forbidden=['_raw.csv','_qfq.csv','sina_snapshots','collection_status.csv','source_input_checksums',
               'input_sha256_inventory','paired_monthly.csv','.env','private_data','local_evidence']
    bad=[f for f in all_files if any(flag in f for flag in forbidden)]
    if bad:raise ValueError(f'Forbidden private data detected in public staging: {bad}')
    (target/'PUBLIC_FILE_MANIFEST.txt').write_text('\n'.join(sorted(all_files))+'\n',encoding='utf-8')
    return target


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='.')
    p.add_argument('--results',default='outputs/study_2026')
    p.add_argument('--destination',default='outputs/public_release_ready')
    a=p.parse_args();print('Safe candidate public tree:',stage_public(Path(a.root),Path(a.results),Path(a.destination)))
if __name__=='__main__':main()
