#!/usr/bin/env python3
"""Build a report and figures from validated outputs of alphalab.study_run."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

P = ['development', 'historical_evaluation_reused', 'new_historical_extension_not_prospective']
SHORT = {'development':'2015-22 development', 'historical_evaluation_reused':'2023-25 reused',
         'new_historical_extension_not_prospective':'2026 historical extension'}
COLORS = {'momentum':'#C16E43', 'reversal':'#087D86'}
FIGURE_CAPTIONS = {
    '01_mean_ic_hac': 'Mean Rank IC with HAC(3) Confidence Intervals',
    '02_monthly_ic': 'Monthly Cross-Sectional Rank IC',
    '03_ic_distribution': 'Distribution of Monthly Rank IC',
    '04_membership_policy': 'Signal-First and Complete-Case Group Membership',
    '05_eligibility': 'Signal and Forward-Outcome Coverage',
    '06_descriptive_spread': 'Descriptive Reversal Q5–Q1 Spreads',
}


def save(fig, folder:Path, name:str):
    fig.tight_layout()
    fig.savefig(folder/(name+'.png'), dpi=185, bbox_inches='tight')
    fig.savefig(folder/(name+'.svg'), bbox_inches='tight')
    plt.close(fig)


def render_pdf(markdown_path:Path, figure_folder:Path, pdf_path:Path) -> None:
    """Render an existing report narrative and figures without recalculating results."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image, PageBreak)
    from reportlab.lib.utils import ImageReader

    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ALSub',parent=styles['Heading2'],spaceBefore=13,spaceAfter=7,keepWithNext=True))
    doc=SimpleDocTemplate(str(pdf_path),pagesize=A4,rightMargin=1.7*cm,leftMargin=1.7*cm,
                          topMargin=1.5*cm,bottomMargin=1.5*cm)
    story=[]
    body_style=ParagraphStyle(name='ALReportBody',parent=styles['BodyText'],leading=13,spaceAfter=5)
    table_rows=[]

    def flush_table():
        nonlocal table_rows
        if not table_rows:return
        cells=[[Paragraph(str(cell),body_style) for cell in row] for row in table_rows]
        tbl=Table(cells,repeatRows=1,hAlign='LEFT')
        tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#182D47')),
                                ('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                                ('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),
                                ('GRID',(0,0),(-1,-1),.25,colors.lightgrey),('LEFTPADDING',(0,0),(-1,-1),4),
                                ('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),
                                ('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        story.append(tbl);story.append(Spacer(1,7));table_rows=[]

    for raw_line in Path(markdown_path).read_text(encoding='utf-8').splitlines():
        line=raw_line.strip()
        if line.startswith('|'):
            cells=[c.strip() for c in line.strip('|').split('|')]
            if all(set(c)<=set('-: ') for c in cells):continue
            table_rows.append(cells);continue
        flush_table()
        if line == '## Figures':continue
        if not line:continue
        if line.startswith('# '):story.append(Paragraph(line[2:],styles['Title']))
        elif line.startswith('## '):story.append(Paragraph(line[3:],styles['ALSub']))
        elif line.startswith('- '):
            item=line[2:].replace('–','-').replace('−','-').replace('—','-').replace('`','')
            story.append(Paragraph('• '+item,body_style))
        elif line.startswith('!['):continue
        else:
            line=line.replace('–','-').replace('−','-').replace('—','-')
            line=line.replace('**','').replace('`','')
            story.append(Paragraph(line,body_style))
    flush_table()

    for idx,name in enumerate(FIGURE_CAPTIONS,1):
        imgpath=Path(figure_folder)/(name+'.png')
        if not imgpath.exists():continue
        if idx % 2 == 1:story.append(PageBreak())
        story.append(Paragraph(f'Figure {idx:02d}. {FIGURE_CAPTIONS[name]}',styles['ALSub']))
        reader=ImageReader(str(imgpath)); w,h=reader.getSize(); maxw=16.4*cm
        story.append(Image(str(imgpath),width=maxw,height=maxw*h/w))
    story.extend([Paragraph('Data rights and verification',styles['ALSub']),
                  Paragraph('Original downloaded price histories are not included. Reproducing figures from a saved study run and reproducing price-dependent estimates using independently downloaded data are distinct verification levels.',styles['BodyText']),
                  Spacer(1,8),Paragraph('This analysis does not establish investment alpha, general A-share applicability, or predictive market timing. Review the code, data manifest and frozen protocol before quoting results.',styles['BodyText'])])
    doc.build(story)


def build(results:Path, out:Path, allow_fixture:bool=False) -> dict:
    results=Path(results);out=Path(out)
    validation=json.loads((results/'study_validation.json').read_text(encoding='utf-8'))
    if validation.get('status') != 'fresh_run_exploratory_not_investable':
        raise ValueError('This report requires an actual fresh study_run result')
    if not allow_fixture and not validation.get('publishable_input_provenance'):
        raise ValueError('Synthetic fixture cannot be published as historical results')
    figs=out/'figures';figs.mkdir(parents=True,exist_ok=True)
    ic=pd.read_csv(results/'study_rank_ic_monthly.csv',parse_dates=['date'])
    summary=pd.read_csv(results/'study_ic_summary.csv')
    audit=pd.read_csv(results/'study_group_policy_summary.csv')
    funnel=pd.read_csv(results/'study_eligibility_funnel.csv',parse_dates=['date'])
    desc=pd.read_csv(results/'study_descriptive_monthly.csv',parse_dates=['date'])
    have_periods=[p for p in P if p in set(ic.study_period)]
    if len(have_periods)==0:raise ValueError('No comparable factor months')
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white'})
    # 01 Mean IC with HAC uncertainty, no assumption that CI is meaningful for <3 months.
    fig,ax=plt.subplots(figsize=(9,4.2))
    positions=[]; labels=[]
    for p in have_periods:
        for factor in ('reversal','momentum'):
            x=summary[(summary.factor==factor)&(summary.study_period==p)]
            if x.empty:continue
            r=x.iloc[0]; pos=len(positions);positions.append(pos)
            labels.append(f'{factor.title()} · {SHORT[p]} (n={int(r.n_factor_months)})')
            low=r.mean_rank_ic-r.ci_low if pd.notna(r.ci_low) else 0
            high=r.ci_high-r.mean_rank_ic if pd.notna(r.ci_high) else 0
            ax.errorbar(r.mean_rank_ic,pos,xerr=np.array([[low],[high]]),fmt='o',ms=7,
                        capsize=4,color=COLORS[factor])
    ax.axvline(0,ls='--',color='#999');ax.set_yticks(positions,labels);ax.invert_yaxis()
    ax.set_xlabel('Monthly mean Spearman Rank IC; HAC(3) 95% descriptive CI')
    ax.set_title('Mean monthly Rank IC by research window')
    ax.grid(axis='x',alpha=.2); save(fig,figs,'01_mean_ic_hac')
    # 02 Monthly cross-sectional Rank IC across the reported study windows.
    fig,axes=plt.subplots(2,1,figsize=(9,5.3),sharex=True)
    for ax,fac in zip(axes,('reversal','momentum')):
        x=ic[ic.factor==fac].sort_values('date')
        ax.plot(x.date,x.rank_ic_complete_case,color=COLORS[fac],lw=1.3,marker='.',ms=3)
        ax.axhline(0,color='#999',lw=.8)
        for boundary in ('2023-01-01','2026-01-01'):
            ax.axvline(pd.Timestamp(boundary),color='#aaa',ls='--',lw=.8)
        ax.set_ylabel(f'{fac.title()} IC');ax.grid(alpha=.16)
    axes[0].set_title('Monthly cross-sectional Rank IC')
    save(fig,figs,'02_monthly_ic')
    # 03 Distribution of monthly Rank IC.
    fig,ax=plt.subplots(figsize=(9,3.8))
    for fac in ('reversal','momentum'):
        x=ic.loc[ic.factor==fac,'rank_ic_complete_case'].dropna()
        ax.hist(x,bins=np.linspace(-1,1,31),alpha=.58,label=f'{fac} (n={len(x)})',color=COLORS[fac])
    ax.set_xlabel('Monthly Rank IC');ax.set_ylabel('Factor-month observations');ax.legend(frameon=False)
    ax.set_title('Rank IC distributions across the planned windows');save(fig,figs,'03_ic_distribution')
    # 04 Membership differences: proper denominator.
    fig,ax=plt.subplots(figsize=(9,3.8));labels=[];v=[];c=[]
    for p in have_periods:
        for fac in ('reversal','momentum'):
            sub=audit[(audit.factor==fac)&(audit.study_period==p)]
            if sub.empty:continue
            r=sub.iloc[0];labels.append(f'{fac.title()} · {SHORT[p]}')
            v.append(100*r.top_group_changed/r.eligible_factor_months if r.eligible_factor_months else 0)
            c.append(COLORS[fac])
    ax.barh(np.arange(len(v)),v,color=c);ax.set_yticks(np.arange(len(v)),labels)
    ax.invert_yaxis();ax.set_xlim(0,105);ax.set_xlabel('Eligible months with different top quintile (%)')
    ax.set_title('Signal-first vs outcome-complete membership differences')
    save(fig,figs,'04_membership_policy')
    # 05 Coverage: ensure denominator is computed on planned formation dates.
    funnel=funnel.copy();funnel['coverage_pct']=100*funnel.strict_full_path_outcome_valid/funnel.signal_valid.replace(0,np.nan)
    cov=funnel.groupby(['study_period','factor'],as_index=False).agg(
        mean_signal_names=('signal_valid','mean'),mean_outcome_names=('strict_full_path_outcome_valid','mean'))
    fig,ax=plt.subplots(figsize=(9,4.0));labels=[];total=[];observed=[]
    for p in have_periods:
        for fac in ('reversal','momentum'):
            s=cov[(cov.study_period==p)&(cov.factor==fac)]
            if s.empty:continue
            r=s.iloc[0];labels.append(f'{fac.title()} · {SHORT[p]}')
            total.append(r.mean_signal_names);observed.append(r.mean_outcome_names)
    pos=np.arange(len(total));ax.barh(pos,total,color='#CED7E1',label='Signal-valid names')
    ax.barh(pos,observed,color='#087D86',label='Strict outcome-observed names')
    ax.set_yticks(pos,labels);ax.invert_yaxis();ax.set_xlabel('Average names per formation month')
    ax.legend(frameon=False);ax.set_title('Eligibility and future-observation coverage')
    save(fig,figs,'05_eligibility')
    # 06 Descriptive top-bottom spreads, three metrics without claiming tradable returns.
    if not desc.empty and {'mean_spread','median_spread','winsor_5pct_spread'}.issubset(desc):
        s=desc.loc[desc.factor=='reversal'].groupby('study_period',as_index=False)[
            ['mean_spread','median_spread','winsor_5pct_spread']].mean()
        s=s.set_index('study_period').reindex(have_periods)
        fig,ax=plt.subplots(figsize=(9,3.8)); xx=np.arange(len(have_periods)); width=.25
        for offset,metric,label,color in [(-1,'mean_spread','Mean','#087D86'),(0,'median_spread','Median','#C16E43'),
                                           (1,'winsor_5pct_spread','5% winsor','#647CA2')]:
            ax.bar(xx+offset*width,s[metric]*100,width,label=label,color=color)
        ax.axhline(0,color='#999',lw=.8);ax.set_xticks(xx,[SHORT[p] for p in have_periods],rotation=10)
        ax.set_ylabel('Q5-Q1 descriptive spread (percentage points)');ax.legend(frameon=False)
        ax.set_title('Reversal Q5–Q1 spreads: descriptive, not executable returns')
        save(fig,figs,'06_descriptive_spread')
    # Report HAC lag sensitivity for the actual monthly IC series, without
    # altering the frozen primary HAC(3) estimator or any study output.
    from alphalab.robustness import hac_mean
    lag_rows=[]
    for (factor, period), part in ic.groupby(['factor','study_period'],sort=True):
        values=part.sort_values('date').rank_ic_complete_case.to_numpy()
        for lag in (0,1,3,6):
            lag_rows.append({'factor':factor,'study_period':period,'months':len(values),
                             'hac_lags':lag,**hac_mean(values,lags=lag)})
    pd.DataFrame(lag_rows).to_csv(out/'hac_ic_lag_sensitivity.csv',index=False)
    # Detailed report generated only from the frozen run and its saved diagnostics.
    lines=['# AlphaLab: Cross-Sectional Momentum and Short-Term Reversal in a Frozen A-Share Sample','',
           '**Status:** exploratory price-only associations; not PIT-certified, prospective validation, or investable performance.','',
           f"**Study:** `{validation['study_id']}`  ",
           f"**Frozen protocol SHA-256:** `{validation['frozen_protocol_hash_sha256']}`  ",
           f"**Sample:** {validation['included_stock_count']} currently listed stocks; target 100; seed 20261023; quotas 40/40/15/5.  ",
           f"**Eligible factor-month rows:** {len(ic)}.",'',
           '## Research Motivation','',
           'This study describes whether skipped-month momentum and short-term reversal signals are associated with subsequent price changes in a fixed, board-stratified sample of Chinese A-shares. It does not establish causality, market-wide representativeness, or achievable trading profits.','',
           '## Data and Sample Construction','',
           'The 100-stock sample was selected without replacement from the current candidate roster using a SHA-256 lottery (seed 20261023): Shanghai main board 40, Shenzhen main board 40, ChiNext 15, and STAR 5. Candidate membership includes current listings only and excludes firms delisted before roster collection; the sample therefore has survivorship bias and is not a historical point-in-time (PIT) universe.','',
           'The candidate roster is based on BaoStock `query_stock_basic()` retrieved 2026-10-23 with `type=1` and `status=1`: 5,224 current SSE/SZSE records (2,318 SSE, 2,906 SZSE; no BSE records). These third-party fields and counts are not an official exchange completeness certification or a same-date count reconciliation. The source candidate CSV is not included in this public repository, so its recorded source hash and the original lottery cannot be independently verified or reconstructed; analyses can be reproduced from the included frozen 100-stock list. The sample plan was frozen before final data collection but after earlier exploratory work; it is not a prospective preregistration. AKShare/Sina supplies historical raw and retrospective QFQ daily prices and the exchange calendar; it does not define the frozen membership. Observations end at 2026-10-23. Windows are 2015–2022 development, 2023–2025 reused historical evaluation, and 2026 historical extension. The 2023–2025 period is not an untouched holdout; 2026 is not prospective or an independent out-of-sample test.','',
           '## Factor Definitions','',
           '- Momentum: `P[t−21] / P[t−252] − 1`.',
           '- Short-term reversal: `−(P[t] / P[t−21] − 1)`.',
           '- Forward outcome: price-only `P[t+22] / P[t+1] − 1`, requiring a fully observed forward path.',
           '',
           'Here `t` is a month-end exchange session. The frozen analysis loads QFQ close series for both signals and the forward price outcome, using the same adjusted series at the specified session offsets. This is not a raw-price outcome, certified total return, achieved execution, or a transaction-cost-adjusted result. QFQ adjustment vintages are not independently verified.','',
           '## Empirical Methodology','',
           'Monthly Rank IC is Spearman correlation between a factor and forward price return among complete cases. The estimator requires at least 20 paired names and non-constant factor and return cross-sections; missing values are not imputed. Effective name counts vary. By window (development / reused 2023–2025 / 2026 extension), momentum has 82/36/8 eligible months with 20–77 / 79–94 / 87–90 names; reversal has 96/36/8 months with 23–91 / 91–98 / 97–100 names.','',
           'Mean monthly IC uncertainty uses Newey–West/HAC with 3 monthly lags, as frozen in the plan. HAC(3) is a reasonable prespecified short-run serial-dependence adjustment, but it does not solve selection, overlapping horizons, specification search, or small-sample uncertainty. Eight 2026 months are particularly few for asymptotic inference.','',
           'Quintile spreads are ex-post complete-case descriptions. A separate signal-first cohort audit assigns groups before future outcomes are known. When outcomes are missing, those group definitions differ; neither is an executable backtest.','',
           '## Results and Interpretation','',
           '| Signal | Window | Months | Mean Rank IC | HAC(3) 95% interval |','|---|---|---:|---:|---|']
    for r in summary.itertuples():
        ci=(f'[{r.ci_low:+.4f}, {r.ci_high:+.4f}]' if pd.notna(r.ci_low) else 'insufficient months')
        lines.append(f'| {r.factor} | {SHORT.get(r.study_period,r.study_period)} | {r.n_factor_months} | {r.mean_rank_ic:+.4f} | {ci} |')
    lines+=['','The 2026 reversal Rank IC mean is +0.1432 over eight months (HAC(3) interval +0.0220 to +0.2643); momentum is −0.0388 (−0.1343 to +0.0567). These intervals are descriptive and fragile at this sample size.','',
            '## Robustness and Sensitivity','',
           'Mean monthly Rank IC was compared under HAC lags 0, 1, 3, and 6 (full estimates: `research_inputs/hac_ic_lag_sensitivity.csv`). For 2026 reversal, the mean remains +0.1432 while 95% intervals are [−0.0023, +0.2886], [−0.0085, +0.2948], [+0.0220, +0.2643], and [+0.0377, +0.2486]. Whether the interval crosses zero depends on lag choice; with only eight months this is not robust significance evidence. HAC(3) remains the frozen primary specification. Regime-interaction sensitivities are separate exploratory estimates and address a different quantity.','',
            'The 2026 reversal Q5–Q1 mean spread is +5.53 percentage points per observed horizon across eight months; the average of monthly median spreads is +4.32 points and the average 5%-winsorized spread is +4.86 points. June alone contributes +35.84 points mean (+33.32 median; +31.17 winsorized); its Q1 mean return is −31.56% (5%-winsorized −29.87%) while Q5 averages +4.27% (+1.31% winsorized). This points to broad Q1 underperformance in that month rather than only one Q5 winner, although the tail remains large after winsorization. Excluding June, the seven-month mean is +1.20 points. May is discordant (mean −3.86 points; median −2.82 points) and has large group maximum returns, consistent with noisy tails. Complete-case counts in these months are 97–100, so the June result is not caused by a sharply depleted cross-section. Spreads remain descriptive, not PnL.','',
            'The reported 65 top-group mismatches are summed across factor/window cells, not 65 unique calendar months. Reversal mismatches are 42/96 development months, 1/36 reused 2023–2025 months, and 1/8 2026 months; momentum mismatches are 16/82, 5/36, and 0/8. Bottom-group mismatches also occur. These counts do not change the frozen 100-stock sample: they show that names without complete future outcomes cannot enter ex-post complete-case quintiles, changing within-month membership and the estimand.','',
            'Signals are measured at close `t`; the code calculates the future price return from QFQ close `t+1` to `t+22`, requiring every session in the forward path. Factors and outcomes therefore share the same QFQ series. Factor ranking does not use the forward outcome, so the source contains no direct outcome look-ahead in ranking; however QFQ is retrospectively adjusted and its vintage is not PIT-certified, and total-return treatment and executable prices remain unverified.','',
            '## Limitations','',
            '- Current-listed sample has survivorship bias and is not a historical PIT universe.',
            '- 2023–2025 is a reused historical evaluation period, not an untouched holdout; 2026 is a short historical extension, not independent prospective evidence.',
            '- QFQ adjustment vintage and corporate actions are not independently validated; outcomes are not certified total returns.',
            '- Missing outcomes are not imputed. Complete-case spreads condition on future availability; signal-first membership is separately audited.',
            '- Monthly horizons overlap; HAC normal intervals with few months are fragile. Exploratory analyses are not adjusted for specification search or multiple testing.',
            '- No tradability, price-limit, liquidity, shorting, execution, turnover, borrow, or full transaction-cost model is included.',
            '- Raw Sina histories are excluded from the public package; provider data redistribution permission is not established.',
            '',
            '## Conclusion','',
            'The estimates show positive average reversal Rank IC in the three labelled windows and negative momentum Rank IC in reused 2023–2025; the 2026 momentum estimate is imprecise. The 2026 reversal average is dominated by one strong month and is based on eight observations. These findings do not establish persistent alpha, broad-market validity, timing ability, or investable performance.','',
            '## Reproducibility and Data Sources','',
            '- Candidate roster source: BaoStock `query_stock_basic()` current SSE/SZSE response retrieved 2026-10-23. Historical daily prices and calendar: AKShare/Sina.',
            '- The candidate source CSV is not distributed; the selected sample is included, but the original candidate lottery cannot be independently reconstructed or verified from this package.',
            '- The public repository includes code, the frozen plan and selected sample, aggregate statistics, report, and figures.',
            '- Raw per-stock Sina histories and the private source-checksum inventory are not distributed.',
            '', '## Figures','']
    for name,desc_ in [('01_mean_ic_hac','Rank IC HAC uncertainty'),('02_monthly_ic','Monthly IC'),
                                     ('03_ic_distribution','IC distribution'),('04_membership_policy','Group-policy differences'),
                                     ('05_eligibility','Outcome eligibility'),('06_descriptive_spread','Tail sensitivity')]:
        lines.append(f'![{desc_}](figures/{name}.png)')
        lines.append('')
    out.joinpath('research_report.md').write_text('\n'.join(lines),encoding='utf-8')
    # Render the saved report text only; this does not recalculate research results.
    render_pdf(out/'research_report.md',figs,out/'research_report.pdf')
    return {'figures_png':len(list(figs.glob('*.png'))),'pdf':str(out/'research_report.pdf'),'study_periods':have_periods}


def main():
    p=argparse.ArgumentParser();p.add_argument('--results',required=True);p.add_argument('--out',default='reports/research_report')
    a=p.parse_args();print(json.dumps(build(Path(a.results),Path(a.out)),indent=2))
if __name__=='__main__':main()
