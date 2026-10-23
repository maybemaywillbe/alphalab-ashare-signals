"""Run an offline exploratory factor study from supplied raw history snapshots."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import pandas as pd
from .factors import load_raw_panel,load_sessions,factor_panel,month_end_signals,evaluate,summary_table
from .coverage import coverage_table, universe_history_check


def run(snapshots, output, momentum_long=252, skip=21, horizon=21, oos_start='2023-01-01', min_names=20, quantiles=5, universe_evidence=None):
    folder=Path(snapshots);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    raw=load_raw_panel(folder)
    sessions=load_sessions(folder/'exchange_calendar.csv',raw['date'].min(),raw['date'].max())
    panel=factor_panel(raw,sessions,momentum_long,skip,horizon)
    formed=month_end_signals(panel)
    coverage=coverage_table(formed,min_names=min_names,oos_start=oos_start)
    ics,bins=evaluate(formed,min_names=min_names,quantiles=quantiles,oos_start=oos_start)
    universe=universe_history_check(universe_evidence,sorted(raw.symbol.unique().tolist()),sessions)
    summary=summary_table(ics)
    formed.to_csv(out/'factor_observations.csv',index=False)
    coverage.to_csv(out/'coverage.csv',index=False)
    ics.to_csv(out/'rank_ic.csv',index=False)
    bins.to_csv(out/'quantile_descriptives.csv',index=False)
    summary.to_csv(out/'summary.csv',index=False)
    result={'version':'1.0.0','status':'exploratory_price_only','symbols':sorted(raw.symbol.unique().tolist()),
        'sessions':len(sessions),'formation_dates':int(formed.date.nunique()),
        'valid_ic_observations':len(ics),'oos_start':oos_start,'min_cross_section_names':min_names,'quantiles':quantiles,
        'coverage_eligible_rows':int(coverage.eligible_for_ic.sum()),'coverage_total_rows':len(coverage),
        'universe_evidence':universe,'research_gate':'engineering_only',
        'assumptions':{'momentum_long_sessions':momentum_long,'skip_sessions':skip,'forward_horizon_sessions':horizon,
          'entry':'next_session_close','exit':'close_after_horizon_sessions_from_entry',
          'return_type':'unadjusted_raw_price_only','missing_session_policy':'exclude affected windows, never fill',
          'selection':'CSV-provided securities; historical point-in-time universe not independently certified'},
        'limitations':['Raw close-to-close price returns omit dividends, splits and other corporate actions.',
          'Small or selected cross-sections are not reliable evidence of alpha; IC uses a minimum name threshold.',
          'OOS label denotes a calendar split only; no historical universe certification.',
          'Bins are descriptive and overlapping forward returns are not independent.',
          'No execution model, commissions, stamp duty, slippage, or tradability checks.']}
    (out/'research.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Candidate-Universe Factor Analysis','',
      '**NOT a backtest, alpha claim, or total-return series.**','',
      f"Symbols: {', '.join(result['symbols'])}; exchange sessions: {len(sessions)}; monthly formation dates: {result['formation_dates']}.",
      f"Valid factor-date rank IC observations: {len(ics)}. OOS split begins {oos_start}.",
      f"Minimum names per cross-section: {min_names}; eligible factor-dates: {int(coverage.eligible_for_ic.sum())}/{len(coverage)}.",
      f"Historical universe evidence: {universe['status']}.",'',
      '## Factor definitions','',
      f'- Momentum: P(t-{skip}) / P(t-{momentum_long}) - 1.',
      f'- Short-term reversal: -(P(t) / P(t-{skip}) - 1).',
      f'- Future return: P(t+1+{horizon}) / P(t+1) - 1, with entry at next session close.',
      '- Missing exchange sessions invalidate the affected entire calculation window.','',
      '## Descriptive rank IC (not annualized)','',
      summary.to_markdown(index=False) if not summary.empty else 'No eligible cross-sections; this is a valid outcome for a tiny sample.',
      '', '## Research restrictions','']
    lines.extend('- '+s for s in result['limitations'])
    lines+=['','## Outputs','','- `factor_observations.csv`: signal dates, factor values and forward *price* returns.',
            '- `coverage.csv`: per-date signal and target coverage, eligibility, and exclusion reasons.',
            '- `rank_ic.csv`: per-date Spearman correlations for eligible cross-sections only.','- `quantile_descriptives.csv`: descriptive group means; **not** executable portfolios.',
            '- `summary.csv`: grouped IC means and unannualized mean/std.',
            '- `research.json`: machine-readable scope and caveats.']
    (out/'research_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description='Offline exploratory factors on raw CSV snapshots')
    p.add_argument('--snapshots',default='inputs/snapshots')
    p.add_argument('--output',default='outputs/research')
    p.add_argument('--momentum-long',type=int,default=252)
    p.add_argument('--skip',type=int,default=21)
    p.add_argument('--horizon',type=int,default=21)
    p.add_argument('--oos-start',default='2023-01-01')
    p.add_argument('--min-names',type=int,default=20,help='minimum paired securities for Rank IC (default: 20)')
    p.add_argument('--quantiles',type=int,default=5)
    p.add_argument('--universe-evidence',default=None,help='optional user-supplied historical security evidence CSV')
    a=p.parse_args()
    print(json.dumps(run(a.snapshots,a.output,a.momentum_long,a.skip,a.horizon,a.oos_start,a.min_names,a.quantiles,a.universe_evidence),indent=2))
if __name__=='__main__':main()
