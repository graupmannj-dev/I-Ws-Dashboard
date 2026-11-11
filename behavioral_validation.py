#!/usr/bin/env python3
"""Forward-time, independently reviewed behavioral warning research audit.

NO source gap is a non-event. NO GDELT press anomaly is a UCDP dyad match.
Requires an ex-ante monitoring frame with adjudicated positive AND negative
windows. Even then, only descriptive observations; no calibrated skill.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlsplit

from behavioral_fusion import SCHEMA as FUSION_SCHEMA
from behavioral_registry import when, iso, MODES
from ops_pipeline import load_json, write_json

UTC=dt.timezone.utc
SCHEMA="aiba.behavioral-validation-ledger.v1"
MAX_UNITS=1000
MAX_FILES=20000
MAX_CADENCE_HOURS=12


def strict_time(value,field):
    if not isinstance(value,str) or not value or not (value.endswith("Z") or "+" in value[10:]):
        raise ValueError(f"{field} requires an explicit offset-aware clock")
    x=when(value)
    if x is None:
        raise ValueError(f"Invalid timestamp for {field}")
    return x


def domain(url):
    if not isinstance(url,str) or len(url)>2048:
        return None
    try:
        p=urlsplit(url)
        if p.scheme=="https" and p.hostname and not p.username and not p.password:
            return p.hostname.lower().removeprefix("www.")
    except ValueError:
        pass
    return None


def independent_review(reviewers,urls):
    return (isinstance(reviewers,list) and len(reviewers)==2 and
            all(isinstance(x,str) and x.strip() and len(x)<=80 for x in reviewers)
            and reviewers[0].strip().casefold()!=reviewers[1].strip().casefold()
            and isinstance(urls,list) and len(urls)==2
            and all(domain(x) for x in urls)
            and domain(urls[0])!=domain(urls[1]))


def validate_spec(spec):
    if not isinstance(spec,dict) or spec.get("version")!=1:
        raise ValueError("Expected behavioral evaluation specification version 1")
    horizon=spec.get("horizon_hours")
    if type(horizon) is not int or not 1<=horizon<=168:
        raise ValueError("Review horizon must be between 1 and 168 hours")
    units=spec.get("units")
    labels=spec.get("labels")
    if not isinstance(units,list) or len(units)>MAX_UNITS or not isinstance(labels,list) or len(labels)>MAX_UNITS:
        raise ValueError("Invalid bounded monitoring frame or outcome labels")
    seen=set()
    valid_units={}
    for r in units:
        if not isinstance(r,dict):
            raise ValueError("Frame unit must be an object")
        uid=r.get("unit_id");geo=r.get("geo_key")
        if not isinstance(uid,str) or not uid or len(uid)>120 or uid in seen:
            raise ValueError("Duplicate/missing monitoring unit ID")
        seen.add(uid)
        if not isinstance(geo,str) or not geo or len(geo)>180 or not (
                geo.startswith("country:") or geo.startswith("navarea:") or geo.startswith("maritime-area:")):
            raise ValueError("Unit must have source-declared geographic key, not inferred theater text")
        registered=strict_time(r.get("registered_at"),"registered_at")
        start=strict_time(r.get("window_start"),"window_start")
        end=strict_time(r.get("window_end"),"window_end")
        if registered>=start or end<=start or end-start>dt.timedelta(days=30):
            raise ValueError("Monitoring frame must be registered before its 1–30-day observation window")
        providers=r.get("coverage_providers")
        if not isinstance(providers,list) or not providers or len(set(providers))!=len(providers):
            raise ValueError("Explicit per-unit provider coverage requirements needed")
        if any(x not in MODES for x in providers):
            raise ValueError("Unrecognized provider in coverage frame")
        reviewed=r.get("geographic_footprint_reviewed") is True
        if reviewed and not independent_review(r.get("coverage_reviewers"),r.get("coverage_evidence_urls")):
            raise ValueError("Verified geographic footprint requires two reviewers and independent sources")
        valid_units[uid]={**r,"_start":start,"_end":end,"_registered":registered,
                          "_footprint":reviewed}
    valid_labels={}
    for row in labels:
        if not isinstance(row,dict):
            raise ValueError("Outcome label must be an object")
        uid=row.get("unit_id")
        if uid not in valid_units or uid in valid_labels:
            raise ValueError("Outcome must match exactly one pre-registered unit")
        outcome=row.get("outcome")
        if outcome not in ("event","no_event"):
            raise ValueError("Outcome must be event or independently adjudicated no_event")
        finalized=strict_time(row.get("finalized_at"),"finalized_at")
        unit=valid_units[uid]
        if finalized<unit["_end"]:
            raise ValueError("Outcome adjudication must be finalized after the observation window")
        event=strict_time(row["event_at"],"event_at") if outcome=="event" else None
        if event and not unit["_start"]<=event<unit["_end"]:
            raise ValueError("Positive event lies outside predeclared window")
        if outcome=="no_event" and row.get("event_at") is not None:
            raise ValueError("Non-event label cannot contain an event timestamp")
        if not independent_review(row.get("reviewers"),row.get("independent_sources")):
            raise ValueError("Positive and negative labels require independent reviewed outcome evidence")
        valid_labels[uid]={**row,"_finalized":finalized,"_event":event}
    return horizon,valid_units,valid_labels


def read_traces(state):
    folder=Path(state)/"history"/"behavioral_fusion"
    files=sorted(folder.glob("*.json"))
    if len(files)>MAX_FILES:
        raise ValueError("Too many fusion trace files: archive before evaluation")
    times={}
    for path in files:
        obj=load_json(path)
        if not isinstance(obj,dict) or obj.get("schema")!=FUSION_SCHEMA:
            raise ValueError("Malformed frozen behavioral fusion trace")
        asof=strict_time(obj.get("generated_at"),"fusion generated_at")
        if asof in times:
            raise ValueError("Duplicate source decision clock; cannot reconstruct unique as-of evidence")
        if not isinstance(obj.get("review_groups"),list) or not isinstance(obj.get("collection_coverage"),dict):
            raise ValueError("Incomplete fusion source coverage trace")
        times[asof]=obj
    return sorted(times.items())


def has_coverage(unit,traces):
    """Provider success is necessary, never sufficient, for country coverage."""
    observed=[(t,r) for t,r in traces if unit["_start"]<=t<unit["_end"]]
    if not observed:
        return False,"no_source_snapshots"
    if not unit["_footprint"]:
        return False,"geographic_provider_footprint_not_verified"
    required=unit["coverage_providers"]
    if any(any(r["collection_coverage"].get(mode,{}).get("status")!="current"
               for mode in required) for _,r in observed):
        return False,"partial_or_unavailable_provider"
    clocks=[unit["_start"]]+[t for t,_ in observed]+[unit["_end"]]
    if max((b-a).total_seconds()/3600 for a,b in zip(clocks,clocks[1:]))>MAX_CADENCE_HOURS:
        return False,"source_observation_gap_exceeds_12_hours"
    return True,"provider_clocks_and_reviewed_geographic_footprint_eligible"


def evaluate(state,spec,clock=None,write=True):
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    horizon,units,labels=validate_spec(spec)
    traces=read_traces(state)
    cases=[]
    excluded=[]
    for uid,u in sorted(units.items()):
        label=labels.get(uid)
        if not label or label["_finalized"]>now:
            excluded.append({"unit_id":uid,"reason":"outcome_not_adjudicated_as_of_evaluation"})
            continue
        eligible,reason=has_coverage(u,traces)
        if not eligible:
            excluded.append({"unit_id":uid,"reason":reason,"outcome":label["outcome"]})
            continue
        last_event=label["_event"]
        if label["outcome"]=="event":
            lower=last_event-dt.timedelta(hours=horizon)
            scope=[(t,g) for t,r in traces if max(u["_start"],lower)<=t<last_event
                   for g in r.get("review_groups",[])
                   if (g.get("geography") or {}).get("key")==u["geo_key"]]
            lead_hours=round((last_event-min(t for t,_ in scope)).total_seconds()/3600,2) if scope else None
            result="geographic_review_preceded_event" if scope else "no_pre_event_geographic_review"
        else:
            scope=[(t,g) for t,r in traces if u["_start"]<=t<u["_end"]
                   for g in r.get("review_groups",[])
                   if (g.get("geography") or {}).get("key")==u["geo_key"]]
            lead_hours=None
            result="unreviewed_fusion_during_reviewed_non_event" if scope else "no_fusion_during_reviewed_non_event"
        cases.append({"unit_id":uid,"geo_key":u["geo_key"],"outcome":label["outcome"],
                      "review_status":"independently_source_documented_not_actor_verified",
                      "result":result,"first_lead_hours":lead_hours,
                      "review_count":len(scope),
                      "source_claim":"Geographic co-occurrence only; no dyad/actor causal identity established"})
    n_pos=sum(r["outcome"]=="event" for r in cases)
    n_neg=sum(r["outcome"]=="no_event" for r in cases)
    result={
        "schema":SCHEMA,"evaluated_at":iso(now),
        "status":"no_approved_labels_or_frame" if not units or not labels else
                 "descriptive_curated_only" if n_pos and n_neg else
                 "insufficient_balanced_outcome_sample",
        "horizon_hours":horizon,
        "pre_registered_units":len(units),
        "independently_reviewed_outcome_labels":len(labels),
        "eligible_event_windows":n_pos,"eligible_non_event_windows":n_neg,
        "excluded_or_unadjudicated_windows":excluded,
        "source_trace_count":len(traces),
        "case_descriptions":cases,
        "calibrated_precision":None,
        "calibrated_recall":None,
        "false_alarm_rate":None,
        "attack_probability":None,
        "warning_probability":None,
        "interpretation":"Descriptive geographic review timing only. Outcome labels, temporal sampling, actor matching, sampling-frame representativeness and sensor coverage do not establish predictive skill.",
    }
    if write:
        write_json(Path(state)/"latest"/"behavioral_validation.json",result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",required=True,type=Path)
    p.add_argument("--spec",required=True,type=Path)
    args=p.parse_args()
    spec=json.loads(args.spec.read_text(encoding="utf-8"))
    report=evaluate(args.state,spec)
    print(json.dumps({k:v for k,v in report.items() if k not in
                      ("case_descriptions","excluded_or_unadjudicated_windows")},indent=2))


if __name__=="__main__":
    main()
