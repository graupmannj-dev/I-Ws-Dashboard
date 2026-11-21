"""Monthly Singapore MPA measured port arrival aggregates (not live vessel tracks).

Data from Singapore's government open data resource d_8f264219109e61fffa87ac64dd5a9a65
is released by the Maritime and Port Authority of Singapore (MPA).
It covers vessel arrivals over 75 GT, by month and vessel type. The most
recent period may be provisional. The product is deliberately HISTORICAL,
not a same-day warning or measured AIS movement.
"""
from __future__ import annotations
import datetime as dt
import re

RESOURCE_ID="d_8f264219109e61fffa87ac64dd5a9a65"
FEED="https://data.gov.sg/api/action/datastore_search?resource_id="+RESOURCE_ID+"&limit=80&sort=month%20desc"
DOC="https://data.gov.sg/datasets/"+RESOURCE_ID+"/view"
SCOPE=("Maritime & Port Authority of Singapore monthly arrivals >75 GT by vessel type; "
       "selected latest months, publication lag, Singapore-only, not live AIS")
TYPES=frozenset(("Container","Freighter","Bulk Carrier","Tanker","Passenger",
                 "Barges","Tug","Miscellaneous"))

def adapt(data,checked,url,entry):
    if not isinstance(data,dict) or data.get("success") is not True:
        raise ValueError("MPA Singapore dataset CKAN response missing success")
    body=data.get("result")
    if not isinstance(body,dict) or body.get("resource_id")!=RESOURCE_ID:
        raise ValueError("Unexpected MPA government dataset identity")
    rows=body.get("records")
    if not isinstance(rows,list) or len(rows)>80:
        raise ValueError("MPA bounded sorted record list missing or too large")
    if not rows:raise ValueError("MPA monthly official series unexpectedly empty")
    current_period=checked.strftime("%Y-%m")
    candidates=[]
    seen=set()
    for source in rows:
        if not isinstance(source,dict):continue
        month=source.get("month")
        vessel_type=source.get("vessel_type")
        count=source.get("number_of_vessels")
        if not isinstance(month,str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])",month):
            continue
        if month>current_period:continue
        if vessel_type not in TYPES:continue
        if not isinstance(count,(int,str)) or isinstance(count,bool):
            continue
        try:
            value=int(count)
        except ValueError:
            continue
        if value<0 or value>10_000_000:continue
        key=(month,vessel_type)
        if key in seen:
            # A repeated exact row can be silently hidden in an offset query;
            # fail closed instead of treating duplicate records as new evidence.
            raise ValueError("Duplicate MPA monthly vessel type record")
        seen.add(key)
        candidates.append((month,vessel_type,value))
    if not candidates:raise ValueError("MPA monthly response contains no validated vessel counts")
    latest=max(x[0] for x in candidates)
    year,mon=(int(x) for x in latest.split("-"))
    # A published monthly series may legitimately be weeks behind; if it is
    # multiple quarters behind, it is not a healthy CURRENT provider sample.
    month_delta=(checked.year-year)*12+(checked.month-mon)
    if not 0<=month_delta<=3:
        raise ValueError("MPA latest monthly data outside 0–3 month currency window")
    result=[]
    for month,kind,value in candidates:
        if (year-int(month[:4]))*12+(mon-int(month[5:]))>10:continue
        rid=month+":"+kind.lower().replace(" ","-")
        row=entry("sg_mpa",rid,"Singapore MPA "+month+" "+kind+" vessel arrivals (>75 GT)",
                  DOC,checked,kind="official_monthly_port_arrival_count_historical",
                  geo={"key":"country:SG","kind":"official_dataset_country",
                       "label":"Singapore","precision":"national_port_scope_not_incident",
                       "latitude":None,"longitude":None,"verified_iso":True},
                  source_scope=SCOPE,
                  measurement={"name":"monthly_vessel_arrivals_over_75_gt",
                               "value":value,"unit":"vessels",
                               "period":month,"vessel_type":kind,
                               "reporting_cadence":"monthly",
                               "period_months_lag":(checked.year-int(month[:4]))*12+
                                   (checked.month-int(month[5:])),
                               "most_recent_month_provisional":month==latest,
                               "denominator":"vessels_greater_than_75_gross_tons",
                               "source_dataset":RESOURCE_ID,
                               "baseline_status":"not_calibrated",
                               "not_live_tracking":True})
        if row:result.append(row)
    if not result:raise ValueError("MPA source had no recent selected months")
    return result
