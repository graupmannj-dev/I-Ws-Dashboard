#!/usr/bin/env python3
"""CAIRN auditable matched-cohort baselines for actual numeric physical sensors.

Input: durable, source-identified family-archive records, NOT headlines or
duplicated collector polls. This produces descriptive calibration readiness
and historical deviation diagnostics; never a validated security forecast,
causal attribution or automatic supporting/contradicting hypothesis weights.
"""
from __future__ import annotations
from collections import defaultdict
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import statistics
from ops_pipeline import load_json,write_json

UTC=dt.timezone.utc
SCHEMA="cairn.metric-cohort-baselines.v1"
ARCHIVE_SCHEMA="aiba.family-archive.v1"
MAX_INPUT=30000
ONS_HISTORY_DAYS=180
MPA_HISTORY_YEARS=12
MIN_ONS_MATCH=8
MIN_MPA_YEARS=3

def utc(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except ValueError:return None

def numeric(value):
    if type(value) in (int,float) and math.isfinite(value):
        return float(value)
    return None

def measurement(row):
    if not isinstance(row,dict):return None
    mode=row.get("collection_mode")
    m=row.get("source_measurement")
    if not isinstance(m,dict):return None
    v=numeric(m.get("value"))
    if v is None:return None
    if mode=="ons_br":
        area=m.get("load_area_code")
        stamp=utc(row.get("event_at"))
        if (m.get("name")!="verified_half_hour_global_load" or
            area not in ("SECO","N","NE","S") or stamp is None or
            stamp.minute not in (0,30) or stamp.second!=0 or
            not m.get("historical_verified_not_live")):
            return None
        return {"mode":mode,"series":"br-ons:"+area,"value":v,
                "key":stamp.strftime("%Y-%m-%dT%H:%MZ"),
                "time":stamp,"cohort":f"weekday:{stamp.weekday()}:utc:{stamp:%H:%M}",
                "unit":"MWmed","provider_clock":stamp.isoformat()}
    if mode=="sg_mpa":
        kind=m.get("vessel_type")
        period=m.get("period")
        if (m.get("name")!="monthly_vessel_arrivals_over_75_gt"
            or not isinstance(kind,str) or not isinstance(period,str)
            or not isinstance(m.get("not_live_tracking"),bool)
            or not m["not_live_tracking"]):
            return None
        try:stamp=dt.datetime.strptime(period,"%Y-%m").replace(tzinfo=UTC)
        except ValueError:return None
        if v<0 or not v.is_integer():return None
        return {"mode":mode,"series":"sg-mpa:"+kind,"value":v,
                "key":period,"time":stamp,
                "cohort":"month:"+str(stamp.month).zfill(2),
                "unit":"arrivals_over_75_gt","provider_clock":period}
    return None

def measure_archive(archive,source_health,now):
    """Reject identity collisions: one real measurement cannot get two values."""
    if not isinstance(archive,dict) or archive.get("schema")!=ARCHIVE_SCHEMA:
        return {"schema":SCHEMA,"generated_at":now.isoformat(),
                "status":"archive_unavailable_no_metric_scores",
                "series":[],"eligible_anomaly_count":0,
                "warnings_approved":0,"probability_of_conflict":None}
    raw=archive.get("records")
    if not isinstance(raw,list) or len(raw)>MAX_INPUT:
        raise ValueError("Bounded family-archive cache missing or over limit")
    if archive.get("public_snapshot_truncated"):
        # Archive cache can be incomplete; its absence is not representative.
        return {"schema":SCHEMA,"generated_at":now.isoformat(),
                "status":"archive_public_cache_truncated_no_completeness",
                "series":[],"eligible_anomaly_count":0,
                "warnings_approved":0,"probability_of_conflict":None}
    by_key={}
    for row in raw:
        obs=measurement(row)
        if obs is None:continue
        if obs["time"]>now+dt.timedelta(minutes=5):
            raise ValueError("Measurement occurs after report time")
        token=(obs["series"],obs["key"])
        previous=by_key.get(token)
        if previous and previous["value"]!=obs["value"]:
            raise ValueError("Conflicting measurement for one immutable source-period identity")
        by_key[token]=obs
    groups=defaultdict(list)
    for o in by_key.values():groups[o["series"]].append(o)
    result=[]
    for series,samples in sorted(groups.items()):
        samples.sort(key=lambda x:(x["time"],x["key"]))
        latest=samples[-1]
        mode=latest["mode"]
        recent=[x for x in samples[:-1] if x["cohort"]==latest["cohort"]]
        if mode=="ons_br":
            recent=[x for x in recent if
                    dt.timedelta(days=0)<latest["time"]-x["time"]<=dt.timedelta(days=ONS_HISTORY_DAYS)]
            # Weekday+half-hour for ONS; each date/time unique, not poll runs.
            independent_periods=len({x["time"].date() for x in recent})
            enough=len(recent)>=MIN_ONS_MATCH and independent_periods>=MIN_ONS_MATCH
            requirement="8 historical readings on matching UTC weekday/half-hour within 180 days"
            latest_age_hours=(now-latest["time"]).total_seconds()/3600
            current_valid=(0<=latest_age_hours<=96)
        else:
            recent=[x for x in recent if 0<(latest["time"].year-x["time"].year)<=MPA_HISTORY_YEARS]
            independent_periods=len({x["time"].year for x in recent})
            enough=independent_periods>=MIN_MPA_YEARS
            requirement="same calendar month and vessel type in at least 3 prior distinct years"
            latest_age_hours=(now-latest["time"]).total_seconds()/3600
            current_valid=(0<=latest_age_hours<=96*24)  # lagged monthly reporting
        # A collector's recent "current_partial" is not proof that every
        # eligible region/time/type was sampled, only that publisher responded.
        h=source_health.get(mode,{}) if isinstance(source_health,dict) else {}
        provider_ok=isinstance(h,dict) and h.get("status") in ("current","current_partial")
        eligible=enough and current_valid and provider_ok
        values=[x["value"] for x in recent]
        median=statistics.median(values) if eligible else None
        mad=(statistics.median(abs(x-median) for x in values) if eligible else None)
        robust_z=((latest["value"]-median)/(1.4826*mad)
                  if eligible and mad and mad>0 else None)
        result.append({
          "mode":mode,"series":series,"current_period":latest["key"],
          "cohort":latest["cohort"],"unit":latest["unit"],
          "current_measured_value":latest["value"],
          "source_clock":latest["provider_clock"],
          "historical_unique_points_total":len(samples),
          "comparable_historical_points":len(recent),
          "independent_comparable_periods":independent_periods,
          "minimum_comparability_contract":requirement,
          "collector_current":provider_ok,"latest_source_fresh_enough":current_valid,
          "status":"descriptive_matched_cohort" if eligible else "insufficient_or_incomplete_baseline",
          "historical_median":median,"median_absolute_deviation":mad,
          "robust_deviation_score":round(robust_z,3) if robust_z is not None else None,
          "zero_mad_no_division":bool(eligible and mad==0),
          "directional_hypothesis_evidence":None,
          "calibrated_conflict_risk":None,"warning_approved":False,
          "sample_completeness_not_established":True
        })
    return {
      "schema":SCHEMA,"generated_at":now.isoformat(),
      "status":"source_measurement_history_descriptive_only",
      "series":result,"series_total":len(result),
      "series_ready_for_descriptive_deviation":sum(x["status"]=="descriptive_matched_cohort" for x in result),
      "eligible_anomaly_count":0,"warnings_approved":0,
      "probability_of_conflict":None,
      "interpretation":("No source anomaly is a security warning. "
        "Comparability requires same source, region/type and timing; "
        "missing periods and truncation disqualify negative inference. "
        "No independent source observations are duplicated by polling.")
    }

def full_metric_archive(state):
    """Read immutable source-root shards rather than lossy 5k public cache.

    Only the two calibrated *physical metrics* are admitted; archived
    source records must never be replaced by today's latest readings.
    """
    archive_root=Path(state)/"family_archive"
    manifest=load_json(archive_root/"manifest.json",{})
    if not isinstance(manifest,dict) or manifest.get("schema")!=ARCHIVE_SCHEMA:
        return load_json(Path(state)/"latest"/"family_archive.json",{})
    shard_paths=sorted((archive_root/"shards").glob("??.json"))
    if len(shard_paths)>256:raise ValueError("Unexpected family shard partition count")
    rows=[]
    scanned=0
    for path in shard_paths:
        if not path.is_file() or path.is_symlink() or path.stat().st_size>8_000_000:
            raise ValueError("Unsafe or oversized family shard")
        shard=load_json(path)
        if not isinstance(shard,dict) or shard.get("schema")!=ARCHIVE_SCHEMA or not isinstance(shard.get("roots"),dict):
            raise ValueError("Invalid durable source-root shard")
        for family in shard["roots"].values():
            if not isinstance(family,dict) or not isinstance(family.get("members"),dict):
                raise ValueError("Invalid family source members")
            for record in family["members"].values():
                scanned+=1
                if scanned>200_000:raise ValueError("Archive too large for bounded calibration scan")
                if isinstance(record,dict) and record.get("collection_mode") in ("ons_br","sg_mpa"):
                    rows.append(record)
                    if len(rows)>30_000:raise ValueError("Source metrics need dedicated sharding")
    return {"schema":ARCHIVE_SCHEMA,"records":rows,"public_snapshot_truncated":False}


def build(state,clock=None,write=True):
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    base=Path(state)
    archive=full_metric_archive(base)
    registry=load_json(base/"latest"/"behavioral_registry.json",{})
    out=measure_archive(archive,registry.get("source_health",{}) if
                        isinstance(registry,dict) else {},now)
    if write:write_json(base/"latest"/"metric_cohort_baselines.json",out)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",required=True,type=Path)
    args=p.parse_args()
    out=build(args.state)
    print(json.dumps({k:out.get(k) for k in
        ("status","series_total","series_ready_for_descriptive_deviation","warnings_approved")},indent=2))

if __name__=="__main__":main()
