# AlphaLab: A-Share Momentum and Short-Term Reversal

**Exploratory empirical research. The reported associations are not investment performance.**

[Research report](reports/research_report.pdf) · [Study design](docs/STUDY_METHOD.md) · [中文复现指南](docs/REPRODUCIBILITY_CN.md)

## Study design

The analysis uses 100 currently listed SSE/SZSE stocks selected with SHA-256 seed `20261023` and fixed quotas: Shanghai main board 40, Shenzhen main board 40, ChiNext 15, and STAR 5. Current-list membership creates survivorship bias; this is not a historical point-in-time universe.

BaoStock `query_stock_basic()` supplies the recorded current candidate-list source; the original candidate CSV is not distributed, so the source hash and original lottery cannot be independently verified or reconstructed. The included frozen 100-stock list supports analysis reproduction. AKShare/Sina supplies historical raw/QFQ daily prices and the exchange calendar. These data sources serve separate roles. Sina history does not recreate or change the frozen sample.

Signals are skipped-month momentum and short-term reversal. Monthly cross-sectional Spearman Rank IC is the primary association statistic; mean IC uncertainty uses HAC(3). Forward outcomes are QFQ price returns, not total returns or executable portfolio PnL. The 2023–2025 period is reused historical evaluation, not an untouched holdout. The 2026 observations are a historical extension, not prospective validation.

| Factor | Study period | Factor-months | Mean Rank IC |
|---|---|---:|---:|
| momentum | 2015–2022 development | 82 | +0.0091 |
| momentum | 2023–2025 reused historical evaluation | 36 | -0.0582 |
| momentum | 2026 historical extension | 8 | -0.0388 |
| reversal | 2015–2022 development | 96 | +0.0475 |
| reversal | 2023–2025 reused historical evaluation | 36 | +0.0549 |
| reversal | 2026 historical extension | 8 | +0.1432 |

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
