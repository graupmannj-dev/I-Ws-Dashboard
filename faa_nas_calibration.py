#!/usr/bin/env python3
"""Calibrate FAA NAS *source-reported airport event counts*, not threat levels.

Collect one minimal numeric sample per successful FAA NAS sensor check. Reference
28 prior UTC days at matched clock minutes; require >=14 distinct prior-day
samples, nonzero variance, fresh current sample and a fixed source contract.
No zero is imputed when a collector fails. Not a global aviation baseline,
a flight cancellation rate, evidence of hostile intent, or attribution.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from ops_pipeline import load_json, write_json

UTC = dt.timezone.utc
SCHEMA = "aiba.faa-nas-calibration.v1"
DAY_SCHEMA = "aiba.faa-nas-calibration-day.v1"
SOURCE_SCHEMA = "aiba.faa-nas-systemic-disruption.v1"
HEALTH_SCHEMA = "aiba.faa-nas-health.v1"
MIN_DAYS = 14
WINDOW_DAYS = 28
MAX_PER_DAY = 240
MAX_AGE_MINUTES = 25
MAX_CLOCK_OFFSET_MINUTES = 45
MAX_EVIDENCE_AGE_HOURS = 6
SOURCE_KIND = "faa_nas_airport_event_count"
SOURCE_URL = "https://nasstatus.faa.gov/api/airport-events"


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        x = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if x.tzinfo is None or x.utcoffset() != dt.timedelta(0):
            return None
        return x.astimezone(UTC)
    except ValueError:
        return None


def sample(source, health, now):
    if not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA:
        raise ValueError("No validated FAA NAS measurement")
    if not isinstance(health, dict) or health.get("schema") != HEALTH_SCHEMA:
        raise ValueError("No FAA NAS collector health")
    checked = stamp(source.get("checked_at"))
    if health.get("status") != "collected" or stamp(health.get("checked_at")) != checked:
        raise ValueError("FAA NAS collection failed or health clocks disagree")
    if checked is None or not dt.timedelta(0) <= now-checked <= dt.timedelta(minutes=MAX_AGE_MINUTES):
        raise ValueError("Stale or future FAA NAS sample")
    if source.get("source_url") != SOURCE_URL:
        raise ValueError("FAA NAS source URL changed; calibration requires review")
    count = source.get("airports_with_any_nas_event")
    seen = source.get("monitored_airport_count")
    if type(count) is not int or type(seen) is not int or not 0 <= count <= seen <= 450:
        raise ValueError("FAA event count outside the source envelope")
    roster = source.get("monitored_airport_roster_sha256")
    if not isinstance(roster, str) or not re.fullmatch(r"[0-9a-f]{64}", roster):
        raise ValueError("FAA airport roster missing or source contract changed")
    fingerprint = source.get("state_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint or len(fingerprint) > 200:
        raise ValueError("Missing source-state identity")
    return {
        "checked_at": checked.isoformat(),
        "value": count, "source_count": seen,
        "state_fingerprint": fingerprint,
        "roster_sha256": roster,
        "source_scope": source.get("source_scope") or "FAA NAS sampled airport-status records",
        "status": source.get("status"),
        "source_url": SOURCE_URL,
        "source_schema": SOURCE_SCHEMA,
    }


def clock_distance_minutes(a, b):
    return abs((a.hour*60 + a.minute) - (b.hour*60 + b.minute))


def prior_samples(state, current, current_source_count, current_roster):
    matches=[]
    day0=current.date()
    for number in range(1,WINDOW_DAYS+1):
        day=day0-dt.timedelta(days=number)
        path=Path(state)/"calibration"/"faa_nas"/(day.isoformat()+".json")
        if not path.is_file():
            continue
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != DAY_SCHEMA or data.get("day") != day.isoformat():
            raise ValueError("Incompatible historical FAA calibration partition")
        checked=[]
        for row in data.get("samples", []):
            t=stamp(row.get("checked_at"))
            if t is None or t.date() != day or type(row.get("value")) is not int:
                raise ValueError("Invalid prior FAA source sample")
            if row.get("source_schema") != SOURCE_SCHEMA or row.get("source_url") != SOURCE_URL:
                raise ValueError("Source collection contract changed")
            # Even identical airport counts can represent a different
            # airport cohort. Only the identical roster is comparable.
            if (row.get("source_count") != current_source_count or
                    row.get("roster_sha256") != current_roster):
                continue
            if clock_distance_minutes(t,current) <= MAX_CLOCK_OFFSET_MINUTES:
                checked.append((clock_distance_minutes(t,current),t,row))
        if checked:
            checked.sort(key=lambda x:(x[0],x[1]))
            matches.append(checked[0][2])
    return matches


def build(state, *, clock=None, write=True):
    state=Path(state)
    now=(clock or dt.datetime.now(UTC)).astimezone(UTC)
    source=load_json(state/"latest"/"faa_nas.json",{}) or {}
    health=load_json(state/"health"/"faa_nas.json",{}) or {}
    row=sample(source,health,now)
    checked=stamp(row["checked_at"])
    day=checked.date().isoformat()
    path=state/"calibration"/"faa_nas"/(day+".json")
    today=load_json(path,{"schema":DAY_SCHEMA,"day":day,"samples":[]})
    if today.get("schema")!=DAY_SCHEMA or today.get("day")!=day:
        raise ValueError("FAA day archive incompatible")
    existing={x.get("checked_at"):x for x in today["samples"]}
    old=existing.get(row["checked_at"])
    if old and old != row:
        raise ValueError("Same-timestamp FAA measurement changed")
    existing[row["checked_at"]]=row
    if len(existing)>MAX_PER_DAY:
        raise ValueError("FAA sampling capacity reached; do not drop measurements")
    today["samples"]=[existing[x] for x in sorted(existing)]
    prior=prior_samples(state,checked,row["source_count"],row["roster_sha256"])
    values=[x["value"] for x in prior]
    enough=len(values)>=MIN_DAYS
    variance=statistics.stdev(values) if enough else None
    calibrated=enough and variance is not None and variance>0 and math.isfinite(variance)
    mean=statistics.mean(values) if enough else None
    z=(row["value"]-mean)/variance if calibrated else None
    z=round(z,3) if z is not None else None
    metric=({
        "metric":"FAA-reported affected airport records",
        "metric_family":"aviation_operations",
        "unit":"airport records",
        "source_id":None,
        "source_url":SOURCE_URL,
        "observed_window":checked.strftime("%Y-%m-%d %H:%M UTC"),
        "reference_window":(checked.date()-dt.timedelta(days=WINDOW_DAYS)).isoformat()+
            " to "+(checked.date()-dt.timedelta(days=1)).isoformat(),
        "observed":row["value"],
        "mean":round(mean,5) if mean is not None else None,
        "sd":round(variance,5) if variance is not None else None,
        "comparable_days":len(prior),
        "reference_sample_count":len(prior),
        "baseline_ready":bool(calibrated),
        "coverage_current":True,
        "z_score":z,
        "comparison_method":"one successful same-clock-time AND identical airport-roster sample per prior UTC day",
        "scope_note":"FAA sampled airport-event records; not all airports, flight volume, or hostile cause.",
    })
    unusual=(z is not None and abs(z)>=2)
    salient=source.get("status") != "no_systemic_disruption_in_monitored_sample"
    # A first reporting episode is created for a new salient operational
    # pattern, without conflating unrelated disruptions across different days.
    episode_path=state/"calibration"/"faa_nas_episode.json"
    episode=load_json(episode_path,{}) or {}
    active=bool(unusual or salient)
    source_item=None
    if active:
        previous=stamp(episode.get("last_evidence_at"))
        if (not previous or checked-previous>dt.timedelta(hours=MAX_EVIDENCE_AGE_HOURS)
                or checked<previous):
            episode={"episode_started_at":checked.isoformat(),
                     "episode_id":checked.strftime("%Y%m%dT%H%M%SZ")}
        episode["last_evidence_at"]=checked.isoformat()
        # The same underlying operational state is one report fragment, not
        # independent confirmations from each repeated collector invocation.
        identity=hashlib.sha256(row["state_fingerprint"].encode()).hexdigest()[:18]
        observation_id="faa:nas:"+episode["episode_id"]+":"+identity
        metric["source_id"]=observation_id
        source_item={
            "id":observation_id,
            "information_root":"faa:nas:episode:"+episode["episode_id"],
            "source_family":"aviation_operations",
            "source_kind":"faa_nas_operational_observation",
            "source_url":SOURCE_URL,
            "provider":"faa_nas",
            "collection_mode":"faa_nas",
            "title":"FAA NAS monitored-airport operational pattern",
            "first_observed_at":checked.isoformat(),
            "published_at":None, "event_at":None,
            "geography_key":None,"geography_label":"United States monitored FAA airport sample",
            "geography_precision":"source_scope_not_event_location",
            "case_hint":None,"direct_measurement":False,
            "claim_level":"FAA_observed_operational_effects_not_cause",
            "origin":"faa_nas_calibration",
            "calibrated_metric":metric if calibrated else None,
        }
    output={
        "schema":SCHEMA,"generated_at":now.isoformat(),
        "sample_checked_at":row["checked_at"],
        "status":"calibrated" if calibrated else "insufficient_or_zero_variance",
        "observed":row["value"],"baseline_days":len(values),
        "missing_reference_days":WINDOW_DAYS-len(values),
        "sample_count_total_today":len(existing),
        "z_score":z,
        "metric":metric,
        "candidate_source":source_item,
        "automatic_warning_count":0,"adversary_inference":False,
        "source_scope":"FAA NAS sampled airport operations only",
        "missing_source_is_not_zero":True,
    }
    if write:
        write_json(path,today)
        if active:
            write_json(episode_path,episode)
        write_json(state/"latest"/"faa_nas_calibration.json",output)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state",required=True,type=Path)
    args=parser.parse_args()
    result=build(args.state)
    print(json.dumps({"status":result["status"],"baseline_days":result["baseline_days"],
                      "z_score":result["z_score"],
                      "observation_is_candidate":bool(result["candidate_source"]),
                      "automatic_warning_count":0}))


if __name__=="__main__":
    main()
