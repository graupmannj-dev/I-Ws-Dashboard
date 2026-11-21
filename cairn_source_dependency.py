#!/usr/bin/env python3
"""Cross-publisher physical-event identity audit, never a security inference.

First pass only: earthquake origin time, epicenter and magnitude from official
USGS/BMKG observations. Two independent agencies describing ONE earthquake
are not two independent earthquakes. WMO relays are the originating national
authority's documents, never additional observing agencies.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
from ops_pipeline import load_json,write_json

UTC=dt.timezone.utc
SCHEMA="cairn.source-dependency-audit.v1"
MAX_ROWS=250
MAX_DELTA_MINUTES=20
MAX_DISTANCE_KM=150
MAX_MAG_DELTA=0.6
MAX_SOURCE_AGE_HOURS=12

def utc(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo is not None else None
    except ValueError:return None

def distance(lat1,lon1,lat2,lon2):
    a,b,c,d=(math.radians(v) for v in (lat1,lon1,lat2,lon2))
    ds=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088*2*math.asin(min(1,math.sqrt(max(0,ds))))

def quake(item,mode,now):
    if not isinstance(item,dict) or item.get("provider")!=mode:return None
    m=item.get("source_measurement")
    g=item.get("geography")
    if not isinstance(m,dict) or m.get("name")!="earthquake_magnitude" or not isinstance(g,dict):
        return None
    v=m.get("value");lat=g.get("latitude");lon=g.get("longitude")
    if not all(type(x) in (int,float) and math.isfinite(x) for x in (v,lat,lon)):
        return None
    if not (-90<=lat<=90 and -180<=lon<=180 and 0<=v<=10):return None
    t=utc(item.get("event_at"))
    if not t or not dt.timedelta(0)<=now-t<=dt.timedelta(hours=72):return None
    ident=item.get("id")
    if not isinstance(ident,str) or not ident.startswith(mode+":") or len(ident)>200:
        return None
    return {"id":ident,"mode":mode,"event_at":t,"lat":lat,
            "lon":lon,"magnitude":v,"source_url":item.get("source_url")}

def _current(snapshot,health,mode,now):
    if not isinstance(snapshot,dict) or snapshot.get("mode")!=mode:
        return False,"no_same_mode_snapshot"
    if snapshot.get("schema")!="cairn.alternative-sensors.v1":
        return False,"invalid_snapshot_schema"
    if not isinstance(health,dict) or health.get("mode")!=mode:
        return False,"no_current_health_receipt"
    if health.get("status") not in ("collected","partial"):
        return False,"source_not_healthy"
    checked=utc(health.get("checked_at"))
    if checked is None or not dt.timedelta(0)<=now-checked<=dt.timedelta(hours=MAX_SOURCE_AGE_HOURS):
        return False,"health_check_stale_or_future"
    observed=utc(snapshot.get("observed_at"))
    if not observed or abs((observed-checked).total_seconds())>300:
        return False,"snapshot_health_clock_mismatch"
    rows=snapshot.get("records")
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:
        return False,"invalid_bounded_records"
    return True,None

def build(snapshots,receipts,now=None):
    now=now or dt.datetime.now(UTC)
    now=now.astimezone(UTC)
    modes=("usgs","bmkg_quake")
    health={}
    inputs={}
    for mode in modes:
        shot=snapshots.get(mode)
        ok,reason=_current(shot,receipts.get(mode),mode,now)
        health[mode]={"usable":ok,"reason":reason}
        inputs[mode]=[q for row in shot["records"] if (q:=quake(row,mode,now))] if ok else []
    report={
      "schema":SCHEMA,"generated_at":now.isoformat().replace("+00:00","Z"),
      "mode":"public_independent_origin_physical_event_candidate_audit",
      "source_health":health,"comparison_available":all(x["usable"] for x in health.values()),
      "publisher_relay_rules":[
        {"mode":"imd_in","original_issuer":"India Meteorological Department",
         "distribution":"WMO CAP Alert Hub","independent_new_observer":False},
        {"mode":"saws_za","original_issuer":"South African Weather Service",
         "distribution":"WMO CAP Alert Hub","independent_new_observer":False},
      ],
      "candidate_common_event_pairs":[],
      "ambiguous_pair_candidates":[],
      "checked_recent_event_counts":{mode:len(inputs[mode]) if health[mode]["usable"] else None for mode in modes},
      "independent_physical_event_count_estimated":None,
      "approved_corroborations":0,"warning_approved":False,
      "interpretation":"Independent publishing institutions may measure the same physical earthquake. Candidate links are NOT reviewed event identities, military indicators, or extra physical-event counts.",
    }
    if not report["comparison_available"]:return report
    a,b=inputs["usgs"],inputs["bmkg_quake"]
    pairs={}
    nearest_a={}
    nearest_b={}
    for x in a:
        for y in b:
            seconds=abs((x["event_at"]-y["event_at"]).total_seconds())
            if seconds>MAX_DELTA_MINUTES*60:continue
            km=distance(x["lat"],x["lon"],y["lat"],y["lon"])
            dmag=abs(x["magnitude"]-y["magnitude"])
            if km>MAX_DISTANCE_KM or dmag>MAX_MAG_DELTA:continue
            ident=(x["id"],y["id"])
            match={"source_ids":[x["id"],y["id"]],
                "source_modes":["usgs","bmkg_quake"],
                "origin_time_difference_seconds":round(seconds),
                "epicenter_distance_km":round(km,1),
                "source_magnitude_difference":round(dmag,2),
                "status":"possible_same_earthquake_unreviewed",
                "source_independence_not_event_independence":True,
                "source_urls":[x["source_url"],y["source_url"]],
            }
            pairs[ident]=match
            nearest_a.setdefault(x["id"],[]).append(ident)
            nearest_b.setdefault(y["id"],[]).append(ident)
    unique=[];ambiguous=[]
    for ident,match in sorted(pairs.items()):
        if len(nearest_a[ident[0]])==1 and len(nearest_b[ident[1]])==1:
            unique.append(match)
        else:ambiguous.append(match)
    report["candidate_common_event_pairs"]=unique[:MAX_ROWS]
    report["ambiguous_pair_candidates"]=ambiguous[:MAX_ROWS]
    report["pairs_truncated"]=len(unique)>MAX_ROWS or len(ambiguous)>MAX_ROWS
    report["independent_physical_event_count_estimated"]=None
    return report

def collect(state,clock=None,write=True):
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    root=Path(state)
    modes=("usgs","bmkg_quake")
    shots={m:load_json(root/"latest"/(m+".json"),{}) for m in modes}
    health={m:load_json(root/"health"/(m+".json"),{}) for m in modes}
    out=build(shots,health,now)
    if write:write_json(root/"latest"/"source_dependency_audit.json",out)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",required=True)
    args=p.parse_args()
    r=collect(args.state)
    print(json.dumps({k:r[k] for k in
        ("comparison_available","checked_recent_event_counts","approved_corroborations")},indent=2))

if __name__=="__main__":main()
