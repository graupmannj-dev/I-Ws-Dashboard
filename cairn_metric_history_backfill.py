#!/usr/bin/env python3
"""Bounded official historical metric backfill, separate from live warning inputs.

Never manufacture historical observations from a missing source; the ONS
backfill requests nine same-weekday one-day samples for each macroregion,
while Singapore MPA returns its bounded 500 most recent monthly-type rows.
This is comparative historical evidence, NOT live collection and NOT an
automated security warning.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode

from cairn_brazil_power import AREAS,BASE as ONS_BASE,DOC as ONS_DOC,_utc as ons_time
from cairn_singapore_port import (RESOURCE_ID as SG_ID,DOC as SG_DOC,TYPES as SG_TYPES)
from ops_pipeline import load_json,write_json

UTC=dt.timezone.utc
SCHEMA="cairn.metric-historical-backfill.v1"
ONS_WEEKS=9
MIN_HALF_HOURS_PER_DAY=40
MAX_ONS_DAY_RECORDS=60
MAX_SG_ROWS=500
MAX_HISTORY_RECORDS=50000
ONS_LOOKBACK_DAYS=70
REFRESH_HOURS_SUCCESS=21*24
REFRESH_HOURS_PARTIAL=24

SG_URL=("https://data.gov.sg/api/action/datastore_search?"
        +urlencode({"resource_id":SG_ID,"limit":MAX_SG_ROWS,"offset":0,"sort":"month desc"}))

def iso(t):return t.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")

def utc(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except ValueError:return None

def _number(v):
    if isinstance(v,bool) or type(v) not in (int,float,str):return None
    try:
        v=float(v)
        return v if math.isfinite(v) and abs(v)<1000000 else None
    except ValueError:return None

def ons_urls(now):
    """Exactly nine one-day same-weekday windows for each macroregion."""
    latest_day=(now-dt.timedelta(days=2)).date()
    for area in AREAS:
        for weeks in range(1,ONS_WEEKS+1):
            day=latest_day-dt.timedelta(days=7*weeks)
            datestr=day.isoformat()
            yield (area,day,ONS_BASE+urlencode({
                "dat_inicio":datestr,"dat_fim":datestr,"cod_areacarga":area}))

def adapt_ons_day(data,area,day,url,checked):
    """Reject incomplete days; 40 distinct half-hour cells are required."""
    rows=data if isinstance(data,list) else (data.get("data") if isinstance(data,dict) else None)
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_ONS_DAY_RECORDS:
        raise ValueError("ONS historical day missing, invalid or over sample cap")
    unique={}
    for row in rows:
        if not isinstance(row,dict) or row.get("cod_areacarga")!=area:
            raise ValueError("ONS historical data contains unexpected load region")
        stamp=ons_time(row.get("din_referenciautc"))
        if not stamp or stamp.date()!=day or stamp.minute not in (0,30) or stamp.second:
            raise ValueError("ONS source day clock or half-hour misaligned")
        val=_number(row.get("val_cargaglobal"))
        if val is None:
            raise ValueError("ONS historical load invalid, not equivalent to zero")
        key=iso(stamp)
        if key in unique and unique[key]!=val:
            raise ValueError("Conflicting official load revisions within one ONS day")
        unique[key]=val
    if len(unique)<MIN_HALF_HOURS_PER_DAY:
        raise ValueError("ONS historical half-hour coverage below declared completeness threshold")
    return [{
      "id":"hist:ons_br:"+area+":"+key,
      "collection_mode":"ons_br","event_at":key,
      "source_url":ONS_DOC,
      "historical_backfill":True,
      "original_observation_reference":url,
      "collected_at":iso(checked),
      "source_measurement":{"name":"verified_half_hour_global_load",
        "value":val,"load_area_code":area,"historical_verified_not_live":True,
        "unit":"MWmed","source_field":"val_cargaglobal",
        "original_source_clock":key,"baseline_status":"not_calibrated"}
    } for key,val in sorted(unique.items())]

def adapt_sg(data,url,checked):
    if not isinstance(data,dict) or data.get("success") is not True:
        raise ValueError("Singapore government CKAN response invalid")
    body=data.get("result")
    if not isinstance(body,dict) or body.get("resource_id")!=SG_ID:
        raise ValueError("Singapore MPA dataset identity does not match")
    rows=body.get("records")
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_SG_ROWS:
        raise ValueError("Singapore bounded historical sample invalid")
    unique={}
    for item in rows:
        if not isinstance(item,dict):
            raise ValueError("Singapore MPA row schema invalid")
        period=item.get("month")
        kind=item.get("vessel_type")
        raw=item.get("number_of_vessels")
        if not isinstance(period,str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])",period):
            raise ValueError("Singapore MPA source period invalid")
        if kind not in SG_TYPES:raise ValueError("Unknown historical vessel type")
        if type(raw) not in (int,str) or isinstance(raw,bool):
            raise ValueError("Missing Singapore measured arrivals")
        try:count=int(raw)
        except ValueError:raise ValueError("Non-numeric Singapore arrivals") from None
        if count<0 or count>10_000_000:raise ValueError("Singapore arrivals outside bounds")
        if period>checked.strftime("%Y-%m"):
            raise ValueError("Future MPA source period")
        key=(period,kind)
        if key in unique and unique[key]!=count:
            raise ValueError("Conflicting monthly source count")
        unique[key]=count
    if not unique:raise ValueError("No verified monthly historical source records")
    # Require at least two years represented before describing the snapshot
    # as a useful historical backfill; the model's three-year requirement is
    # separately enforced during cohort matching.
    years={int(p[:4]) for p,_ in unique}
    if len(years)<2:raise ValueError("Singapore historical API sample lacks multiple years")
    cohorts={}
    for period,kind in unique:
        cohorts.setdefault((period[5:],kind),set()).add(period[:4])
    if not any(len(years)>=4 for years in cohorts.values()):
        raise ValueError("Singapore history lacks a four-year matching monthly/type cohort")
    return [{
      "id":"hist:sg_mpa:"+p+":"+kind.lower().replace(" ","-"),
      "collection_mode":"sg_mpa","source_url":SG_DOC,
      "historical_backfill":True,"original_observation_reference":url,
      "collected_at":iso(checked),
      "source_measurement":{"name":"monthly_vessel_arrivals_over_75_gt",
        "period":p,"vessel_type":kind,"value":n,
        "not_live_tracking":True,"unit":"vessels",
        "baseline_status":"not_calibrated"}
    } for (p,kind),n in sorted(unique.items())]

def collect(state,clock=None,fetcher=None,write=True):
    """One targeted backfill per eligible window; each request independently bounded."""
    # Import only during call to avoid a network import cycle. Production uses
    # the same bounded JSON getter / official allowlisted endpoint policy.
    if fetcher is None:
        from alternative_sensor_pipeline import json_get
        fetcher=json_get
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    root=Path(state)/"metric_history"
    path=root/"official_metric_backfill.json"
    previous=load_json(path,{})
    if previous and (not isinstance(previous,dict) or previous.get("schema")!=SCHEMA):
        raise ValueError("Historical source archive corrupted")
    last=utc(previous.get("checked_at")) if isinstance(previous,dict) else None
    if last:
        hours=(now-last).total_seconds()/3600
        previous_status=previous.get("status")
        minimum=REFRESH_HOURS_SUCCESS if previous_status=="all_sources_completed" else REFRESH_HOURS_PARTIAL
        if 0<=hours<minimum:
            return {**previous,"collection_skipped_due_to_refresh_window":True}
    historical={}
    for row in previous.get("records",[]) if isinstance(previous,dict) else []:
        if not isinstance(row,dict) or not isinstance(row.get("id"),str):
            raise ValueError("Corrupt prior metric history")
        historical[row["id"]]=row
    errors=[]
    completed=0
    for area,day,url in ons_urls(now):
        try:
            rows=adapt_ons_day(fetcher(url),area,day,url,now)
            for row in rows:
                prior=historical.get(row["id"])
                if prior and prior.get("source_measurement")!=row["source_measurement"]:
                    raise ValueError("ONS source revised historical measurement: review required")
                historical[row["id"]]=prior or row
            completed+=1
        except (ValueError,TypeError,KeyError,TimeoutError,OSError) as error:
            errors.append({"mode":"ons_br","area":area,
                           "day":day.isoformat(),"error":(type(error).__name__+": "+str(error))[:180]})
    try:
        records=adapt_sg(fetcher(SG_URL),SG_URL,now)
        for row in records:
            prior=historical.get(row["id"])
            if prior and prior.get("source_measurement")!=row["source_measurement"]:
                raise ValueError("Singapore published monthly count changed; source revision review required")
            historical[row["id"]]=prior or row
        completed+=1
    except (ValueError,TypeError,KeyError,TimeoutError,OSError) as error:
        errors.append({"mode":"sg_mpa","error":(type(error).__name__+": "+str(error))[:180]})
    if len(historical)>MAX_HISTORY_RECORDS:
        raise ValueError("Physical historical source archive exceeds declared bounded capacity")
    result={
      "schema":SCHEMA,"checked_at":iso(now),
      "status":"all_sources_completed" if completed==ONS_WEEKS*len(AREAS)+1
               else "partial_failed_source_windows",
      "requested_source_windows":ONS_WEEKS*len(AREAS)+1,
      "successful_source_windows":completed,
      "failed_source_windows":len(errors),
      "collection_skipped_due_to_refresh_window":False,
      "records_total":len(historical),
      "historical_provenance":"official_source_times_not_scrape_clocks",
      "not_live_or_automatically_warning_eligible":True,
      "errors":errors[:45],
      "records":sorted(historical.values(),key=lambda x:x["id"]),
      "baseline_calibrated_as_warning":False,
    }
    if write:write_json(path,result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",required=True,type=Path)
    args=p.parse_args()
    report=collect(args.state)
    print(json.dumps({k:report[k] for k in ("status","records_total",
       "requested_source_windows","successful_source_windows","failed_source_windows")},indent=2))

if __name__=="__main__":main()
