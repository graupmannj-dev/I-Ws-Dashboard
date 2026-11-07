#!/usr/bin/env python3
"""Optional daily public Wikipedia attention feed, with source and coverage audit.

Public attention is NOT evidence of country-local behavior or imminent hostilities.
Missing or unavailable daily measurements are never replaced with zeros.
"""
from __future__ import annotations
import datetime as dt, json, urllib.parse, urllib.request, statistics, math
from pathlib import Path
from preconvergence import trailing_robust_z
HERE=Path(__file__).resolve().parent
PAGES=['Iran','Taiwan','Ethiopia','Eritrea','Sudan','Kenya','Pakistan','Afghanistan',
       'Democratic_Republic_of_the_Congo','Rwanda','Thailand','Cambodia','South_Korea','North_Korea','Canada']
URL='https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/{title}/daily/{start}00/{end}00'

def collect(asof:dt.date, days=90,fetch=None):
    """Request ~90 consecutive days ending at last completed day (source can lag)."""
    begin=asof-dt.timedelta(days=days-1); start=begin.strftime('%Y%m%d');end=asof.strftime('%Y%m%d')
    records={};statuses={};fetch=fetch or _fetch
    for title in PAGES:
        url=URL.format(title=urllib.parse.quote(title,safe=''),start=start,end=end)
        try:
            result=fetch(url);items=result['items']
            series={}
            for item in items:
                date=dt.datetime.strptime(item['timestamp'][:8],'%Y%m%d').date().isoformat()
                if item.get('views') is not None:series[date]=int(item['views'])
            if not series:raise ValueError('No pageview observations')
            records[title]=series
            statuses[title]={'status':'collected' if len(series)==days and max(series)==asof.isoformat() else 'partial','days':len(series),'latest':max(series),'source':url}
        except Exception as exc:
            statuses[title]={'status':'unavailable','error':f'{type(exc).__name__}: {exc}','source':url}
    return records,statuses

def _fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'AIBAEarlyWarning/5.0 (public research; contact through published repository)', 'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)

def score_attention(records, asof, threshold=3.0):
    control=records.get('Canada',{})
    out=[];daily=[]
    for title,series in records.items():
        if title=='Canada':continue
        dates=sorted(set(series).intersection(control));hist=[]
        for date in dates:
            a=series.get(date);b=control.get(date)
            if b is None or b<=0 or a is None:continue
            ratio=a/b;z=trailing_robust_z(hist,ratio,min_days=21,lookback=42)
            hist.append(ratio)
            if z is None:continue
            daily.append({'date':date,'page':title,'ratio':ratio,'z':round(z,3),'source':'Wikimedia Analytics API'})
            if z>=threshold:
                out.append({'date':date,'name':title.replace('_',' '),'type':'Attention anomaly (not paired forecast divergence)',
                   'robust_z':round(z,2),'interpretation':'Global English Wikipedia audience attention increased versus Canada control; news-driven responses are common.',
                   'source':f'https://en.wikipedia.org/wiki/{title}',
                   'dataset_date':date,'validation':'Unverified behavioral relevance; requires independent AIBA corroboration'})
    # Only recent window results are surfaced, historical ones retained in JSON.
    recent=(asof-dt.timedelta(days=7)).isoformat()
    return {'method':'Trailing 42-observation median/MAD, min 21; only positive 3.0 robust-sigma anomalies','all_flags':out,
            'recent_flags':[f for f in out if f['date']>=recent],
            'daily':daily,
            'note':'Public attention is downstream of information exposure and not a validated conflict precursor.'}

def write_outputs(asof,days=90,output=None):
    records,statuses=collect(asof,days)
    scored=score_attention(records,asof)
    out={'collected_utc':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
         'requested_through':asof.isoformat(),'pages':statuses,'results':scored,
         'completeness':{'success':sum(x['status']=='collected' for x in statuses.values()),'attempted':len(statuses)}}
    if output is not None:
        Path(output).write_text(json.dumps(out,indent=2),encoding='utf-8')
    print('Wikipedia collection:',out['completeness'],'recent anomalies:',len(scored['recent_flags']))
    return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--as-of',default=(dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=1)).isoformat());p.add_argument('--days',type=int,default=90)
    a=p.parse_args();write_outputs(dt.date.fromisoformat(a.as_of),a.days, HERE/'data'/'live_attention.json')
