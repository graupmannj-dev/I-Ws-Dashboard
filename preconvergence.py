#!/usr/bin/env python3
"""AIBA pre-convergence: anomaly relationships, not war probability.

Runs on dated, time-aligned observations. Uses trailing data only, preserves
missingness, never equates a change in one contract with any other outcome.
A 'quiet divergence' means a contemporaneous discrepancy deserving investigation.
It is not a validated lead indicator of conflict.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
PANEL=HERE/'data'/'market_attention_2026-10-01_11-04.csv'
OUT=HERE/'data'/'preconvergence.json'

def f(x):
    try:return float(x) if x not in (None,'') else None
    except (ValueError,TypeError):return None

def trailing_robust_z(history, val, min_days=14, lookback=21):
    """Robust surprise score from strictly preceding observations.
    Fall back to sample standard deviation if MAD vanishes; no score if
    reference is degenerate. No future leakage or instant rebaselining.
    """
    if val is None:return None
    hist=[x for x in history[-lookback:] if x is not None]
    if len(hist)<min_days:return None
    center=statistics.median(hist)
    mad=statistics.median([abs(x-center) for x in hist])
    sigma=1.4826*mad
    if sigma<=1e-9:
        sigma=statistics.stdev(hist) if len(hist)>1 else 0
    if sigma<=1e-9:return None
    return (val-center)/sigma

def examine(rows):
    """Returns all usable dated rows, investigatory leads and quality counts."""
    history=[]; days=[]; flags=[]
    for item in sorted(rows,key=lambda r:r['date']):
        date=item['date']; ratio=f(item.get('iran_to_canada_ratio'))
        z=trailing_robust_z(history,ratio)
        change=f(item.get('iran_daily_change_pp'))
        # A price for ground invasion cannot be treated as price for airstrike.
        status='insufficient_history' if z is None else 'within_baseline'
        if z is not None and z>=2.5:
            status='unusual_attention'
            if change is not None and change<=0:
                status='quiet_divergence'
                flags.append({
                    'date':date,'area':'Iran (worldwide English Wikipedia audience)',
                    'signal':'Attention ↑ while U.S. ground-invasion forecast did not rise',
                    'classification':'Investigatory discrepancy — not an attack warning',
                    'attention_robust_z':round(z,3),'market_change_pp':round(change,2),
                    'evidence_date':date,'coverage':'Paired dated observations',
                    'independence':'Two measurement systems; underlying news drivers may be shared',
                    'causal_warning':'Market contract is U.S. ground invasion of Iran before 2027, NOT near-term airstrike probability.',
                    'source_urls':['https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/',
                                   str(item.get('iran_market_source',''))],
                    'next':'Check same-day news roots, airline suspensions, insurer terms, independent diplomatic action; assess whether attention shift precedes these.'})
            elif change is None:status='attention_without_market_observation'
        days.append({'date':date,'ratio':ratio,'robust_z':round(z,3) if z is not None else None,
                     'invasion_market_change_pp':change,'state':status})
        history.append(ratio)
    # Stop treating all changes in relation as leading war warnings.
    return {'data_start':min(r['date'] for r in rows),'data_end':max(r['date'] for r in rows),
            'model':'Trailing 21-observation median/MAD; min 14 dates; 2.5 robust-sigma attention threshold',
            'measured_variable':'Iran/Canada English Wikipedia daily pageview ratio, not local population activity',
            'matched_market':'U.S. ground invasion of Iran before 2027; daily market change, percentage points',
            'flags':flags,'daily_diagnostics':days,
            'coverage':{'dated_rows':len(rows),'scorable_days':sum(x['robust_z'] is not None for x in days),
                        'quiet_divergence_days':len(flags)},
            'missing_components':['Daily airline cancellation rate','Dated war-risk insurance terms',
                                  'Daily crowd forecast of equivalent outcome','Outage time series','Independent news-root labels'],
            'disclaimer':'Retrospective investigatory flags, not out-of-sample warning skill; no calibrated conflict posterior.'}

def generate(panel=PANEL,out=OUT):
    with Path(panel).open(newline='',encoding='utf-8') as fp: rows=list(csv.DictReader(fp))
    result=examine(rows);Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f"Pre-convergence: {result['coverage']['quiet_divergence_days']} discrepancies from {result['coverage']['scorable_days']} scorable days (historical).")
    return result
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--panel',type=Path,default=PANEL)
    ap.add_argument('--out',type=Path,default=OUT);arg=ap.parse_args()
    generate(arg.panel,arg.out)
if __name__=='__main__':main()
