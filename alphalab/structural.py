"""Descriptive regime-composition decomposition and HAC interaction.

All regimes/outcomes are exploratory. This is not a predictive trading test.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd


def prepare(path):
    x=pd.read_csv(path)
    need={'date','factor','split','rank_ic','mean_spread','trend_regime','regime_eligible'}
    if not need.issubset(x.columns):raise ValueError(f'missing columns: {sorted(need-set(x.columns))}')
    x['date']=pd.to_datetime(x.date)
    if x.duplicated(['date','factor']).any():raise ValueError('duplicate date/factor')
    if x['split'].isna().any():raise ValueError('missing split')
    valid=x.regime_eligible.astype(str).str.lower().eq('true')
    x=x.loc[valid & x.trend_regime.isin(['up','down'])].copy()
    for c in ['rank_ic','mean_spread']:x[c]=pd.to_numeric(x[c],errors='coerce')
    x=x.sort_values(['factor','date']).reset_index(drop=True)
    return x


def decompose(x):
    """Delta = composition using development conditional means + within-state shift at OOS weights.

    This is an accounting identity, not causal attribution.
    """
    rows=[];cells=[]
    for factor,g in x.groupby('factor'):
        for metric in ['rank_ic','mean_spread']:
            z=g.dropna(subset=[metric]).copy()
            groups={s:z[z.split==s] for s in ['development','oos']}
            if any(v.empty for v in groups.values()):continue
            if any(set(v.trend_regime.unique())!={'up','down'} for v in groups.values()):
                rows.append(dict(factor=factor,metric=metric,status='missing_regime_cell'))
                continue
            p={s:groups[s].trend_regime.value_counts(normalize=True).to_dict() for s in groups}
            mu={s:groups[s].groupby('trend_regime')[metric].mean().to_dict() for s in groups}
            for state in ['up','down']:
                cells.append(dict(factor=factor,metric=metric,regime=state,
                    dev_months=int((groups['development'].trend_regime==state).sum()),
                    oos_months=int((groups['oos'].trend_regime==state).sum()),
                    dev_weight=p['development'][state],oos_weight=p['oos'][state],
                    dev_mean=mu['development'][state],oos_mean=mu['oos'][state]))
            comp=sum((p['oos'][s]-p['development'][s])*mu['development'][s] for s in ['up','down'])
            within=sum(p['oos'][s]*(mu['oos'][s]-mu['development'][s]) for s in ['up','down'])
            dev=float(groups['development'][metric].mean());oos=float(groups['oos'][metric].mean())
            delta=oos-dev
            if not np.isclose(delta,comp+within,atol=1e-12):raise AssertionError('decomposition mismatch')
            rows.append(dict(factor=factor,metric=metric,status='ok',dev_months=len(groups['development']),
                oos_months=len(groups['oos']),dev_mean=dev,oos_mean=oos,total_change=delta,
                composition_effect=comp,within_regime_effect=within,
                composition_share_of_change=comp/delta if abs(delta)>1e-12 else np.nan))
    return pd.DataFrame(rows),pd.DataFrame(cells)


def hac_ols(y,X,lags=3):
    """OLS with Bartlett Newey-West sandwich, time-ordered observations, no statsmodels."""
    y=np.asarray(y,float);X=np.asarray(X,float)
    n,k=X.shape
    if n<=k or np.linalg.matrix_rank(X)<k:return None
    beta=np.linalg.lstsq(X,y,rcond=None)[0];e=y-X@beta
    xe=X*e[:,None];meat=xe.T@xe
    L=min(max(0,int(lags)),n-1)
    for lag in range(1,L+1):
        gamma=xe[lag:].T@xe[:-lag]
        meat+=(1-lag/(L+1))*(gamma+gamma.T)
    inv=np.linalg.pinv(X.T@X)
    vcov=inv@meat@inv
    se=np.sqrt(np.maximum(np.diag(vcov),0))
    return beta,se


def interactions(x,lags=3):
    rows=[]
    for factor,g in x.groupby('factor'):
        for metric in ['rank_ic','mean_spread']:
            z=g.dropna(subset=[metric]).sort_values('date')
            oos=(z.split=='oos').astype(float).to_numpy()
            down=(z.trend_regime=='down').astype(float).to_numpy()
            X=np.column_stack([np.ones(len(z)),oos,down,oos*down])
            result=hac_ols(z[metric].to_numpy(),X,lags)
            if result is None:
                rows.append(dict(factor=factor,metric=metric,term='not_estimable',n=len(z)))
                continue
            beta,se=result
            for i,term in enumerate(['intercept_dev_up','oos_shift_up','dev_down_minus_up','oos_x_down_interaction']):
                rows.append(dict(factor=factor,metric=metric,term=term,n=len(z),hac_lags=lags,
                    estimate=float(beta[i]),hac_se=float(se[i]),t_descriptive=float(beta[i]/se[i]) if se[i]>0 else np.nan,
                    ci_low=float(beta[i]-1.96*se[i]),ci_high=float(beta[i]+1.96*se[i])))
    return pd.DataFrame(rows)


def annual_check(x):
    z=x.copy();z['year']=z.date.dt.year
    return z.groupby(['factor','split','year','trend_regime'],as_index=False).agg(
        months=('date','size'),mean_rank_ic=('rank_ic','mean'),mean_spread=('mean_spread','mean'))


def run(monthly,output,lags=3):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    x=prepare(monthly)
    dec,cells=decompose(x);inter=interactions(x,lags);annual=annual_check(x)
    for name,df in [('regime_decomposition.csv',dec),('regime_cells.csv',cells),
                    ('regime_interaction_hac.csv',inter),('annual_trend_stability.csv',annual)]:
        df.to_csv(out/name,index=False)
    report={'version':'1.0.0','status':'exploratory_accounting_not_causal_or_predictive',
        'eligible_rows':len(x),'factors':sorted(x.factor.unique().tolist()),'hac_lags':lags,
        'limitations':['Two-state up/down analysis pools high/low volatility; not a four-state causal model.',
        'Composition and within-state terms depend on development-period reference means.',
        'HAC interaction coefficients are descriptive; no multiple-comparison correction or untouched OOS.',
        'Monthly observations can have overlapping holding windows; HAC lag sensitivity remains.',
        'Retrospective QFQ and survivorship-selected 100-stock proxy remain unresolved.',
        'Market state is sample-derived and not an independently validated broad-market benchmark.']}
    (out/'structural_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description='Regime-stability and decomposition diagnostics')
    p.add_argument('--monthly-regime',default='outputs/regime/monthly_regime_diagnostics.csv')
    p.add_argument('--output',default='outputs/structural_stability')
    p.add_argument('--hac-lags',type=int,default=3)
    a=p.parse_args();print(json.dumps(run(a.monthly_regime,a.output,a.hac_lags),indent=2))
if __name__=='__main__':main()
