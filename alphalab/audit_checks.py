"""Pure, offline-testable audit functions."""
from __future__ import annotations
import pandas as pd


def calendar_coverage(df, calendar, start, end, gap_warning_sessions=3):
    if calendar is None:
        return {'status':'unknown_calendar_unavailable'}
    if df is None or df.empty:
        return {'status':'unknown_no_bars'}
    observed=pd.to_datetime(df['date'],errors='coerce').dropna().dt.normalize()
    if observed.empty:
        return {'status':'unknown_invalid_dates'}
    calendar=pd.to_datetime(pd.Series(calendar),errors='coerce').dropna().dt.normalize()
    span=calendar[(calendar>=observed.min()) & (calendar<=observed.max())]
    if span.empty:
        return {'status':'unknown_no_calendar_overlap'}
    missing=sorted(set(span)-set(observed))
    missing_set=set(missing)
    gaps=[]; current=[]
    for date in span:
        if date in missing_set: current.append(date)
        elif current:
            if len(current)>=gap_warning_sessions: gaps.append({'start':str(current[0].date()),'end':str(current[-1].date()),'sessions':len(current)})
            current=[]
    if len(current)>=gap_warning_sessions:
        gaps.append({'start':str(current[0].date()),'end':str(current[-1].date()),'sessions':len(current)})
    return {'status':'checked_not_classified','expected_sessions_within_observed_span':len(span),
            'missing_within_observed_span':len(missing),'long_gap_count':len(gaps),
            'long_gaps':gaps[:30], 'truncated_long_gaps':len(gaps)>30,
            'missing_session_dates_sample':[str(x.date()) for x in missing[:20]],
            'calendar_out_of_span_sessions_not_evaluated':True}


def listing_bounds(df,start,end):
    if df is None or df.empty: return {'status':'unknown_no_bars'}
    dates=pd.to_datetime(df['date'],errors='coerce').dropna()
    if dates.empty: return {'status':'unknown_invalid_dates'}
    return {'status':'observed_only','first_bar':str(dates.min().date()),'last_bar':str(dates.max().date()),
            'first_bar_after_requested_start':dates.min().normalize()>pd.to_datetime(start).normalize(),
            'last_bar_before_requested_end':dates.max().normalize()<pd.to_datetime(end).normalize(),
            'ipo_date':'unverified','delisting_date':'unverified'}


def adjustment_comparison(raw,qfq,hfq):
    if any(x is None or x.empty for x in (raw,qfq,hfq)):
        return {'status':'incomplete','details':'one or more price modes unavailable'}
    frames=[]
    for mode,df in [('raw',raw),('qfq',qfq),('hfq',hfq)]:
        x=df[['date','close']].copy(); x['date']=pd.to_datetime(x['date']); x=x.rename(columns={'close':mode})
        frames.append(x)
    merged=frames[0].merge(frames[1],on='date').merge(frames[2],on='date')
    if merged.empty:return {'status':'no_overlapping_dates'}
    same_raw_qfq=bool((merged['raw'].round(6)==merged['qfq'].round(6)).all())
    same_raw_hfq=bool((merged['raw'].round(6)==merged['hfq'].round(6)).all())
    return {'status':'diagnostic_only','overlap_sessions':len(merged),
            'raw_equals_qfq':same_raw_qfq,'raw_equals_hfq':same_raw_hfq,
            'details':'identical series may be legitimate; corporate-action dates not checked'}
