# A-Share Momentum and Short-Term Reversal: Study Design and Limitations

## Scope

This is an empirical study inspired by cross-sectional price momentum research. It is not a literal replication of Jegadeesh and Titman (1993): the market, sample, signal definitions, observation schedule, and reported estimands differ. The analysis evaluates associations in a fixed sample and does not establish causal effects or executable performance.

## Candidate universe and sample

The candidate roster is based on a BaoStock `query_stock_basic()` response retrieved on 2026-10-23, filtering `type=1` and `status=1`. The retained third-party response contained 5,224 current SSE/SZSE listings (2,318 SSE; 2,906 SZSE; no BSE records). These vendor fields and counts were not independently certified as a complete official ordinary-share master or reconciled to same-date exchange totals. The source is not represented as an official exchange file or a historical point-in-time universe. The candidate CSV is not distributed; the frozen sample is available for reproducing the analysis, but the original candidate lottery and its source hash cannot be independently verified or reconstructed from this repository.

Before analysis, a SHA-256 ranked lottery with seed `20261023` selected 100 stocks from four predeclared strata: Shanghai main board 40, Shenzhen main board 40, ChiNext 15, and STAR 5. The study package contains the frozen selected list and plan hashes. Failed or incomplete price histories are not replaced with other stocks.

The sample plan was frozen before final data collection but after earlier exploratory work. This is not a prospective preregistration.

The sample contains currently listed survivors and omits companies delisted before candidate collection. The selection procedure removes code-order concentration; it does not remove survivorship bias or make the sample representative of the historical A-share market. The board quotas are researcher-defined and are not historical market-cap weights.

## Data sources and dates

BaoStock supplies the frozen current candidate-list source only. AKShare/Sina supplies the historical raw and retrospectively adjusted QFQ daily prices and the exchange calendar. The two sources serve separate roles; historical prices do not recreate membership. The public repository excludes raw provider price histories. Provider revisions to daily bars, adjustments, or backfilled observations may prevent exact numerical reproduction from a later download.

The frozen plan requests history from 2014-01-01 for lookback coverage and defines formation windows through 2026-10-23:

- Development: 2015-01-01 through 2022-12-31.
- Reused historical evaluation: 2023-01-01 through 2025-12-31; this interval was examined previously and is not an untouched holdout.
- Historical extension: 2026-01-01 through 2026-10-23; it is not prospective validation. The final available formation months may lack a fully observed 22-session forward outcome and are not imputed or force-included.

## Signals and outcome

Signals use retrospective QFQ closes at month-end session `t`:

- Skipped-month momentum: `P[t−21] / P[t−252] − 1`.
- Short-term reversal: `−(P[t] / P[t−21] − 1)`.
- Forward price observation: `P[t+22] / P[t+1] − 1`, requiring the full future path to be observed.

The factor ranking is computed from information at or before `t`; future returns are used only as outcomes and for ex-post complete-case descriptions. Signals and outcomes use the same retrospective QFQ close series. These are price returns, not independently verified total returns or execution prices. The QFQ adjustment vintage is not point-in-time certified.

## Estimation and interpretation

Monthly cross-sectional Spearman Rank IC is calculated for complete factor/outcome pairs when at least 20 names remain and both variables vary. Mean monthly IC uncertainty uses HAC with three monthly lags, as specified in the frozen plan. The 2026 sensitivity table compares HAC lags 0, 1, 3, and 6; with only eight months, intervals are sensitive to lag choice and are descriptive. No multiple-testing adjustment is applied.

Quintile spreads use ex-post complete-case membership. Signal-first cohort analysis assigns group membership before observing future outcome availability. Missing outcomes can therefore cause group membership to differ; these procedures estimate different quantities. Neither describes executable portfolio PnL.

## Limitations

- The candidate universe is current-listed and survivor-biased, not historical PIT; historical listing eligibility and delisted securities are not reconstructed.
- BaoStock type/status semantics and market totals lack independent same-date official certification; the retained source covers SSE/SZSE and no BSE records.
- 2023–2025 was examined previously. The 2026 extension is historical, short, and not a preregistered prospective test.
- QFQ history is retrospective; corporate-action vintages and total-return treatment are not independently verified.
- Complete-case estimates condition on future outcome availability. Signal-first cohorts have separately audited membership and missingness.
- Monthly outcome horizons overlap. HAC normal intervals with few observations are fragile, and exploratory analyses are subject to specification search.
- The study does not model verified trading fills, price limits, liquidity, turnover, short availability, borrow costs, or a complete transaction-cost schedule. No investment alpha, Sharpe ratio, or NAV claim follows.
- Provider redistribution permissions are not established for source price histories; those raw histories are excluded from this repository.
