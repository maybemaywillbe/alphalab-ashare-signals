"""Single offline research release pipeline with explicit data/estimand audit.

Source snapshots are READ ONLY. No data collection or prediction claims.
The original numerical estimators remain available in their individual modules.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from . import distribution, portfolio, paired, missing_audit, regime, structural, robustness
from .factors import factor_panel, load_sessions, month_end_signals, evaluate
from .selection import rank_bins

FACTORS = ("momentum", "reversal")
PUBLIC_EVALUATION = "historical_evaluation_reused"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_inventory(folder: Path, retrieval_date: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Record every frozen input checksum. Retrieval date is NEVER inferred from file mtime."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"snapshot folder not found: {folder}")
    if retrieval_date is not None:
        pd.to_datetime(retrieval_date, format="%Y-%m-%d", errors="raise")
    prices = sorted(folder.glob("*_qfq.csv"))
    if not prices or not (folder / "exchange_calendar.csv").is_file():
        raise FileNotFoundError("need *_qfq.csv and exchange_calendar.csv in snapshot folder")
    rows = []
    files = sorted(set(folder.glob("*_qfq.csv")) | set(folder.glob("*_raw.csv")) | {folder / "exchange_calendar.csv"})
    for file in files:
        kind = "calendar" if file.name == "exchange_calendar.csv" else file.stem.rsplit("_", 1)[-1]
        symbol = "" if kind == "calendar" else file.stem.split("_")[0]
        meta_file = file.with_suffix(".meta.json")
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
        digest = sha256_file(file)
        if meta.get("sha256") and meta["sha256"] != digest:
            raise ValueError(f"source metadata checksum conflict: {file.name}. Keep original data immutable and investigate.")
        dates = pd.read_csv(file, usecols=["date"])["date"]
        parsed = pd.to_datetime(dates, errors="raise")
        if parsed.isna().any() or parsed.duplicated().any():
            raise ValueError(f"invalid/duplicate source dates: {file.name}")
        rows.append({
            "file": file.name, "symbol": symbol, "kind": kind, "sha256": digest,
            "rows": len(parsed), "first_date": parsed.min().strftime("%Y-%m-%d") if len(parsed) else None,
            "last_date": parsed.max().strftime("%Y-%m-%d") if len(parsed) else None,
            "provider_as_declared": meta.get("provider", "unspecified_in_metadata"),
            "adjust_as_declared": meta.get("adjust", "unspecified_in_metadata"),
            "requested_start": meta.get("start", ""), "requested_end": meta.get("end", ""),
            "retrieval_date_user_declared": retrieval_date or "unknown",
            "meta_sha256_present": bool(meta.get("sha256")),
            "pit_verified": False,
        })
    frame = pd.DataFrame(rows)
    qfq_symbols = set(frame.loc[frame.kind == "qfq", "symbol"])
    raw_symbols = set(frame.loc[frame.kind == "raw", "symbol"])
    provenance = {
        "code_version": __version__, "price_file_count": len(frame) - 1,
        "qfq_symbol_files": len(qfq_symbols), "raw_symbol_files": len(raw_symbols),
        "calendar_file": "exchange_calendar.csv", "retrieval_date_user_declared": retrieval_date,
        "universe_selection": "CURRENT-listed, code-order-selected convenience sample; historical PIT membership unverified",
        "historical_pit_universe_verified": False, "historical_adjustment_vintage_verified": False,
        "missing_metadata_count": int((~frame.meta_sha256_present).sum()),
        "symbol_set_difference_raw_qfq": sorted(raw_symbols ^ qfq_symbols),
    }
    return frame, provenance


def membership_policy_audit(formed: pd.DataFrame, quantiles: int = 5) -> pd.DataFrame:
    """Evidence that ex-post descriptive bins and signal-first cohorts differ."""
    rows = []
    for factor in FACTORS:
        for date, g in formed.groupby("date", sort=True):
            s = rank_bins(g, factor, quantiles, policy="signal")
            c = rank_bins(g, factor, quantiles, policy="complete_case")
            if s.empty:
                continue
            s_hi = set(s.loc[s.bin == s.bin.max(), "symbol"])
            c_hi = set(c.loc[c.bin == c.bin.max(), "symbol"]) if len(c) else set()
            s_lo = set(s.loc[s.bin == s.bin.min(), "symbol"])
            c_lo = set(c.loc[c.bin == c.bin.min(), "symbol"]) if len(c) else set()
            rows.append({"date": date, "factor": factor,
                         "signal_selected_count": len(s), "outcome_observed_count": len(c),
                         "signal_first_top_n": len(s_hi), "complete_case_top_n": len(c_hi),
                         "signal_first_top_outcomes_observed": int(s.loc[s.symbol.isin(s_hi), "future_price_return"].notna().sum()),
                         "same_top_members": s_hi == c_hi,
                         "same_bottom_members": s_lo == c_lo,
                         "top_symmetric_difference_n": len(s_hi ^ c_hi),
                         "bottom_symmetric_difference_n": len(s_lo ^ c_lo),
                         "definition": "signal-first membership versus outcome-complete descriptive bins"})
    return pd.DataFrame(rows)


def eligibility_funnel(formed: pd.DataFrame, bars: pd.DataFrame, cohorts: pd.DataFrame,
                       ic: pd.DataFrame, monthly_regime: pd.DataFrame,
                       min_names: int = 20, quantiles: int = 5) -> pd.DataFrame:
    """One factor/month row; keep attempted and ineligible dates, never condition selection on outcomes."""
    close = bars.set_index(["symbol", "date"])["close"]
    if close.index.has_duplicates:
        raise ValueError("duplicate source symbol/date pairs")
    # Reindex on the *planned* future endpoint dates, without filling missing values.
    formed = formed.copy()
    formed["entry_bar_available"] = pd.Series(close.reindex(pd.MultiIndex.from_arrays([
        formed.symbol.to_numpy(), pd.to_datetime(formed.entry_date).to_numpy()
    ])).to_numpy(), index=formed.index).gt(0)
    formed["exit_bar_available"] = pd.Series(close.reindex(pd.MultiIndex.from_arrays([
        formed.symbol.to_numpy(), pd.to_datetime(formed.exit_date).to_numpy()
    ])).to_numpy(), index=formed.index).gt(0)
    c = cohorts[cohorts.portfolio == "top_quintile"].copy()
    c = c.set_index(["date", "factor"]) if len(c) else pd.DataFrame()
    ic = ic.set_index(["date", "factor"]) if len(ic) else pd.DataFrame()
    r = monthly_regime.set_index(["date", "factor"]) if len(monthly_regime) else pd.DataFrame()
    records = []
    for factor in FACTORS:
        for dt, g in formed.groupby("date", sort=True):
            s = rank_bins(g, factor, quantiles, policy="signal")
            valid = rank_bins(g, factor, quantiles, policy="complete_case")
            key = (pd.Timestamp(dt), factor)
            eligible_ic = key in ic.index
            eligible_cohort = key in c.index
            record = {
                "date": dt, "factor": factor,
                "public_period": "historical_evaluation_reused" if pd.Timestamp(dt) >= pd.Timestamp("2023-01-01") else "development",
                "candidate_stock_rows_in_calendar": len(g), "signal_valid": len(s),
                "signal_with_entry_price": int(s.entry_bar_available.sum()) if len(s) else 0,
                "signal_with_exit_price": int(s.exit_bar_available.sum()) if len(s) else 0,
                "signal_with_both_endpoints": int((s.entry_bar_available & s.exit_bar_available).sum()) if len(s) else 0,
                "strict_full_path_outcome_valid": len(valid),
                "endpoint_available_but_strict_path_missing": int((s.entry_bar_available & s.exit_bar_available & s.future_price_return.isna()).sum()) if len(s) else 0,
                "signal_valid_but_outcome_missing": int(s.future_price_return.isna().sum()) if len(s) else 0,
                "ic_descriptive_complete_case_eligible": eligible_ic,
                "cohort_signal_first_eligible": eligible_cohort,
                "eligible_min_names": min_names,
                "ic_sample_names": int(ic.loc[key, "n"]) if eligible_ic else 0,
                "top_signal_first_selected": int(c.loc[key, "selected"]) if eligible_cohort else 0,
                "top_signal_first_observed": int(c.loc[key, "observed"]) if eligible_cohort else 0,
                "top_signal_first_outcome_coverage": float(c.loc[key, "coverage"]) if eligible_cohort else np.nan,
                "regime_four_state_eligible": bool(r.loc[key, "regime_eligible"]) if key in r.index else False,
                "regime_sample_proxy_trend": r.loc[key, "trend_regime"] if key in r.index else None,
            }
            records.append(record)
    return pd.DataFrame(records)


def audit_hac_sensitivity(monthly_regime: pd.DataFrame, lag_values=(0, 1, 3, 6)) -> pd.DataFrame:
    """Post-hoc HAC lag sensitivity, not independent predictive validation."""
    frame = monthly_regime.copy()
    frame["date"] = pd.to_datetime(frame.date)
    frame["regime_eligible"] = frame.regime_eligible.astype(str).str.lower().eq("true")
    x = frame.loc[frame.regime_eligible & frame.trend_regime.isin(["up", "down"])].copy()
    if x.empty:
        return pd.DataFrame(columns=["factor", "metric", "term", "n", "hac_lags", "estimate", "hac_se", "ci_low", "ci_high"])
    rows = []
    for lag in lag_values:
        result = structural.interactions(x, lags=lag)
        if not result.empty:
            rows.append(result)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def summarize_membership(audit: pd.DataFrame, ic: pd.DataFrame) -> dict:
    valid = audit.merge(ic[["date", "factor"]].drop_duplicates(), on=["date", "factor"], how="inner")
    return {"comparable_factor_months": len(valid),
            "different_top_membership_months": int((~valid.same_top_members).sum()),
            "different_bottom_membership_months": int((~valid.same_bottom_members).sum())}


def relabel_period(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "split" in out.columns:
        out["split"] = out["split"].replace({"oos": PUBLIC_EVALUATION})
    return out


def run(snapshots: str, output: str = "outputs/final", retrieval_date: str | None = None,
        min_names: int = 20, hac_lags: int = 3, skip_robustness_sweep: bool = True) -> dict:
    if min_names < 5 or hac_lags < 0:
        raise ValueError("min_names>=5 and hac_lags>=0 required")
    snap = Path(snapshots).expanduser().resolve()
    out = Path(output).expanduser().resolve()
    if out == snap or snap in out.parents or out in snap.parents:
        raise ValueError("keep output and input snapshots in separate directories")
    out.mkdir(parents=True, exist_ok=True)
    inventory, provenance = snapshot_inventory(snap, retrieval_date)
    inventory.to_csv(out / "input_sha256_inventory.csv", index=False)
    (out / "input_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    # Source analyses preserve original estimands. No data-source calls or silent cache refresh.
    distribution.run(snap, out / "descriptive_complete_case", min_names=min_names)
    portfolio.run(snap, out / "signal_first_cohorts", min_names=min_names)
    paired.run(out / "signal_first_cohorts" / "cohort_returns.csv",
               out / "signal_first_cohorts" / "cohort_members.csv", out / "paired_diagnostics")
    missing_audit.run(out / "signal_first_cohorts" / "cohort_members.csv",
                      out / "signal_first_cohorts" / "cohort_returns.csv",
                      out / "missingness", snapshots=snap)
    regime.run(snap, out / "descriptive_complete_case" / "monthly_diagnostics.csv", out / "sample_proxy_regime")
    structural.run(out / "sample_proxy_regime" / "monthly_regime_diagnostics.csv",
                   out / "structural_exploratory", lags=hac_lags)
    if not skip_robustness_sweep:
        robustness.run(snap, out / "legacy_parameter_sweep", min_names=min_names, hac_lags=hac_lags)
    bars, excluded = robustness.load_qfq(snap)
    sessions = load_sessions(snap / "exchange_calendar.csv", bars.date.min(), bars.date.max())
    formed = month_end_signals(factor_panel(bars, sessions))
    ic, _ = evaluate(formed, min_names=min_names)
    cohorts = pd.read_csv(out / "signal_first_cohorts" / "cohort_returns.csv", parse_dates=["date"])
    mr = pd.read_csv(out / "sample_proxy_regime" / "monthly_regime_diagnostics.csv", parse_dates=["date"])
    pa = membership_policy_audit(formed)
    funnel = eligibility_funnel(formed, bars, cohorts, ic, mr, min_names=min_names)
    pa = pa.merge(ic[["date", "factor"]].assign(ic_descriptive_eligible=True),
                  on=["date", "factor"], how="left")
    pa["ic_descriptive_eligible"] = pa.ic_descriptive_eligible.eq(True)
    # Freeze exact, unambiguous public-facing names; keep legacy files in subdirectories for comparison.
    pa.to_csv(out / "group_policy_comparison.csv", index=False)
    funnel.to_csv(out / "factor_month_eligibility_funnel.csv", index=False)
    relabel_period(ic).rename(columns={"n": "outcome_observed_stock_count", "rank_ic": "rank_ic_complete_case"}).to_csv(
        out / "canonical_rank_ic_complete_case.csv", index=False)
    relabel_period(robustness.summarize_ic(ic, hac_lags)).to_csv(
        out / "canonical_ic_hac_inference_descriptive.csv", index=False)
    relabel_period(robustness.annual_ic(ic)).to_csv(
        out / "canonical_annual_ic_descriptive.csv", index=False)
    relabel_period(pd.read_csv(out / "descriptive_complete_case" / "spread_summary.csv")).to_csv(
        out / "canonical_complete_case_spread_summary.csv", index=False)
    relabel_period(pd.read_csv(out / "paired_diagnostics" / "paired_monthly.csv")).to_csv(
        out / "canonical_signal_first_paired_cohorts.csv", index=False)
    relabel_period(mr).to_csv(out / "canonical_regime_monthly_exploratory.csv", index=False)
    sensitivity = audit_hac_sensitivity(mr)
    sensitivity.to_csv(out / "hac_lag_sensitivity_exploratory.csv", index=False)
    counts = summarize_membership(pa, ic)
    e = pd.read_csv(out / "missingness" / "extreme_return_crosscheck.csv", dtype={"symbol": str})
    event_key = ["symbol", "entry_date", "exit_date"]
    unique_events = e.drop_duplicates(event_key).copy() if len(e) else e.copy()
    unique_events.to_csv(out / "unique_extreme_price_events_unverified.csv", index=False)
    structural_core = sensitivity[(sensitivity.factor == "reversal") &
                                  (sensitivity.metric == "rank_ic") &
                                  (sensitivity.term == "oos_x_down_interaction")]
    report = {
        "code_version": __version__, "status": "exploratory_research_only_not_tradable",
        "run_mode": "offline_from_existing_snapshots_no_download",
        "python": sys.version.split()[0], "platform": platform.platform(),
        "pandas": pd.__version__, "numpy": np.__version__,
        "input_provenance_file": "input_provenance.json",
        "snapshot_symbols_usable": int(bars.symbol.nunique()), "excluded_qfq": len(excluded),
        "factor_month_funnel_rows": len(funnel), "descriptive_ic_factor_month_rows": len(ic),
        "membership_audit": counts,
        "extreme_factor_stock_records": len(e),
        "unique_extreme_symbol_entry_exit_events": len(unique_events),
        "headline_interaction_hac_lag_sensitivity_available": not structural_core.empty,
        "methodology_notes": [
            "Group assignments use signal-first and complete-case policies with different eligibility requirements.",
            "2023+ observations are reused historical evaluation, not an untouched out-of-sample period.",
            "The month/factor eligibility funnel reports denominators for each estimate.",
            "Gross and equal-fixed-cost paired differences are identical by design and do not estimate cost efficacy.",
            "Input checksums and provider metadata are recorded; source metadata claims are not independently authenticated.",
            "Regime-interaction HAC lag sensitivity is descriptive and unadjusted for multiple testing."],
        "limitations": [
            "No historical PIT universe or complete delisted population.",
            "Retrospective Sina QFQ: historical adjustment vintage and total returns unverified.",
            "Sample market proxy uses same selected names with changing daily coverage.",
            "Strict forward path conditions on outcome availability; observed-case selection risk.",
            "No executable trade fills, market limits, turnover, borrowing, or verified differential costs.",
            "The 2023+ period was examined during development and is not an untouched holdout.",
            "No independent benchmark or independent corporate-action validation."],
        "warnings": [
            "This command cannot establish retrieval dates absent independent evidence; use --retrieval-date only when documented.",
            "The reported results are exploratory; cohort summaries should not be compounded into NAV.",
            "HAC normal intervals and regime tests are post-selection descriptive associations."],
    }
    (out / "release_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline reproducible exploratory AlphaLab release")
    parser.add_argument("--snapshots", default="inputs/sina_snapshots", help="existing local raw/QFQ snapshots; read-only")
    parser.add_argument("--output", default="outputs/final", help="separate output directory")
    parser.add_argument("--retrieval-date", default=None, help="documented original data download date YYYY-MM-DD, optional")
    parser.add_argument("--min-names", type=int, default=20)
    parser.add_argument("--hac-lags", type=int, default=3)
    parser.add_argument("--include-parameter-sweep", action="store_true", help="run an optional exploratory window sweep")
    args = parser.parse_args()
    result = run(args.snapshots, args.output, args.retrieval_date,
                 args.min_names, args.hac_lags, not args.include_parameter_sweep)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
