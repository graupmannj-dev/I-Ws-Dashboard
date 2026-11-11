#!/usr/bin/env python3
"""Source-specific descriptive baselines for AIBA's observation ledger.

NO news-driven gate; NO statistical prediction; NO inference from source
outages; NO hidden truncation. Daily samples are provider snapshots, not
complete 24-hour sensor exposure, military activity or world event counts.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import datetime as dt
import json
from pathlib import Path
import re
import statistics

from behavioral_registry import MODES,SCHEMA as REGISTRY_SCHEMA,iso,when
from ops_pipeline import load_json,write_json

UTC=dt.timezone.utc
SCHEMA="aiba.behavioral-provider-baseline.v1"
WINDOW_DAYS=28
MIN_COMPARABLE_DAYS=14
MAX_RECENT_FILES=7000
VALID=("current","current_partial")


def read_recent(state,now):
    root=Path(state)/"history"/"behavioral_registry"
    begin=(now.date()-dt.timedelta(days=WINDOW_DAYS-1)).strftime("%Y%m%d")
    files=[p for p in sorted(root.glob("*.json")) if p.name[:8]>=begin]
    if len(files)>MAX_RECENT_FILES:
        raise ValueError("Too many behavioral snapshots in baseline window; archive/repartition rather than silently truncate")
    snapshots=[]
    seen=set()
    for file in files:
        o=load_json(file)
        if not isinstance(o,dict) or o.get("schema")!=REGISTRY_SCHEMA:
            raise ValueError("Unrecognized provider history schema; no baseline output")
        stamp=when(o.get("generated_at"))
        if stamp is None or stamp>now+dt.timedelta(minutes=5):
            raise ValueError("Invalid or future provider-history clock")
        if stamp.date()<now.date()-dt.timedelta(days=WINDOW_DAYS-1):
            continue
        if stamp.date()>now.date():
            raise ValueError("Snapshot from a future UTC day")
        if "snapshot_counts_by_mode" not in o or "first_seen_counts_by_mode" not in o:
            # Older registry snapshots predate this measurement contract.
            # They cannot be treated as verified zero-source days.
            continue
        if file.name in seen:
            raise ValueError("Duplicate frozen source file identity")
        seen.add(file.name)
        snapshots.append((stamp,o))
    return snapshots


def one_mode(mode,snapshots,now):
    """Select one *actual provider-check* sample per UTC day."""
    days={}
    day_first_seen=defaultdict(set)
    invalid_or_unavailable=set()
    baseline_days=set()
    records_by_day=defaultdict(set)
    for at,d in snapshots:
        h=d["source_health"].get(mode)
        if not isinstance(h,dict):
            raise ValueError(f"Missing source-health entry for {mode}")
        checked=when(h.get("checked_at"))
        if checked and checked>at+dt.timedelta(minutes=5):
            raise ValueError(f"Provider check after registry clock for {mode}")
        if not checked or checked.date()!=at.date():
            # Replaying yesterday's healthy snapshot today does NOT
            # manufacture an independent sampling day.
            continue
        day=checked.date().isoformat()
        status=h.get("status")
        if status not in VALID:
            invalid_or_unavailable.add(day)
            continue
        count=d["snapshot_counts_by_mode"].get(mode)
        novelty=d["first_seen_counts_by_mode"].get(mode)
        if type(count) is not int or type(novelty) is not int or count<0 or novelty<0:
            raise ValueError(f"Unsupported per-provider counts for {mode} at {day}")
        if h.get("first_provider_baseline"):
            baseline_days.add(day)
        for record in d.get("new_records",[]):
            if not isinstance(record,dict) or record.get("collection_mode") not in MODES:
                raise ValueError("Invalid source identity in recorded first-seen delta")
            if record["collection_mode"]==mode:
                day_first_seen[day].add(record["id"])
        sample=(checked,at,status,count)
        if day not in days or (checked,at)>days[day][:2]:
            days[day]=sample
    for day in invalid_or_unavailable:
        # A day with any known provider outage is not fully comparable.
        # A single success that day does NOT prove 24h completeness.
        days.pop(day,None)
    latest=days.get(now.date().isoformat())
    newest_status=latest[2] if latest else None
    comparable=[(d,x[3]) for d,x in sorted(days.items())
                if x[2]==newest_status] if newest_status else []
    # A first provider collection is a baseline, not an observed zero
    # for novel events. Exclude baseline initialization dates.
    novelty_days=[(d,len(day_first_seen[d])) for d,_ in comparable if d not in baseline_days]
    current_counts=[count for _,count in comparable]
    ready=(newest_status in VALID and len(comparable)>=MIN_COMPARABLE_DAYS
           and len(novelty_days)>=MIN_COMPARABLE_DAYS-1)
    med_count=statistics.median(current_counts) if ready else None
    med_new=statistics.median(x for _,x in novelty_days) if ready else None
    mad=(statistics.median(abs(x-med_count) for x in current_counts) if ready else None)
    current_count=latest[3] if latest else None
    return {
        "source":mode,
        "source_status_current_snapshot":newest_status or "not_currently_sampled",
        "current_provider_snapshot_count":current_count,
        "source_days_with_usable_snapshots":len(days),
        "source_days_with_known_interruptions":len(invalid_or_unavailable),
        "source_days_unobserved_or_uncomparable":WINDOW_DAYS-len(days),
        "comparable_provider_snapshot_days":len(comparable),
        "initial_baseline_days_excluded":len(baseline_days),
        "daily_first_seen_reviewable_days":len(novelty_days),
        "median_daily_source_snapshot_records":med_count,
        "median_daily_first_seen_records":med_new,
        "median_absolute_deviation_snapshot_records":mad,
        "status":"descriptive_reference_only" if ready else "insufficient_comparable_source_days",
        "coverage_definition":"latest bounded provider snapshot per UTC day; not full-day/global observation",
        "warning_eligible":False,
        "probability_of_conflict":None,
    }


def build(state,clock=None,write=True,run_id="local"):
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    snapshots=read_recent(state,now)
    sources={mode:one_mode(mode,snapshots,now) for mode in MODES}
    report={
        "schema":SCHEMA,"generated_at":iso(now),
        "window_start":(now.date()-dt.timedelta(days=WINDOW_DAYS-1)).isoformat(),
        "window_end":now.date().isoformat(),
        "window_days":WINDOW_DAYS,"minimum_comparable_days":MIN_COMPARABLE_DAYS,
        "history_deltas_with_per_provider_counts":len(snapshots),
        "sources":sources,
        "coverage_is_not_global":True,
        "alerts_generated":0,"anomalies_promoted":0,
        "calibrated_forecast_skill":None,
        "interpretation":"Only descriptive source-visible activity levels. Partial and failed feeds have selection bias; provider sampling is not 24h or global coverage. Do not infer military preparation from restrictions volume.",
    }
    if write:
        state=Path(state)
        history=state/"history"/"behavioral_baselines"/(
            now.strftime("%Y%m%dT%H%M%SZ")+"-"+re.sub(r"[^A-Za-z0-9_-]","",run_id)[:48]+".json")
        if history.exists():
            raise ValueError("Append-only descriptive-baseline run ID already exists")
        write_json(history,report)
        write_json(state/"latest"/"behavioral_baselines.json",report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",required=True,type=Path)
    a=p.parse_args()
    x=build(a.state)
    print(json.dumps({"generated_at":x["generated_at"],
                      "sources":{k:{"status":v["status"],
                                    "days":v["comparable_provider_snapshot_days"],
                                    "provider_count":v["current_provider_snapshot_count"]}
                                 for k,v in x["sources"].items()},
                      "alerts_generated":0},indent=2))


if __name__=="__main__":
    main()
