#!/usr/bin/env python3
"""Conservative global behavioral convergence nominations.

Evidence-first: consumes the normalized source registry, NOT GDELT headlines,
a predefined theater list, or UCDP outcome labels. As-of timeline and
geography must agree before displaying a cross-family REVIEW candidate.

This is not an automatic war warning, multisource causal proof, risk score,
or classifier of military preparations. No executive severity changes.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

from behavioral_registry import SCHEMA as REGISTRY_SCHEMA, iso, when
from ops_pipeline import load_json, write_json

UTC=dt.timezone.utc
SCHEMA="aiba.behavioral-convergence-shadow.v1"
LOOKBACK_HOURS=72
MAX_HISTORY_FILES=500
MAX_RECENT=3000
MAX_SINGLE_LEADS=50
MAX_REVIEW_GROUPS=25
# A shared news article or market quote can *contextualize*, but never
# contribute an independent observed-behavior family to convergence.
REVIEW_FAMILIES={"internet_reachability","maritime_restriction","airspace_restriction","protective_notice"}
ADDITIONAL_CONTEXT_FAMILIES={"commercial_media","market_expectation"}


def stamp(item):
    return when(item.get("first_observed_at"))


def candidate_observation(item, now):
    first=stamp(item)
    if not first or first>now or now-first>dt.timedelta(hours=LOOKBACK_HOURS):
        return False,"outside_asof_window"
    published=when(item.get("source_published_at"))
    if published and published>first+dt.timedelta(minutes=5):
        return False,"published_after_first_observed"
    if published and now-published>dt.timedelta(hours=LOOKBACK_HOURS):
        return False,"old_source_publication"
    updated=when(item.get("source_updated_at"))
    if updated and (updated>first+dt.timedelta(minutes=5) or
                    now-updated>dt.timedelta(hours=LOOKBACK_HOURS)):
        # A first-seen old scheduled restriction is not a new
        # preparation signal simply because AIBA ingested it today.
        return False,"old_or_future_source_revision"
    if item.get("alert_eligible") is not False:
        return False,"unexpected_alert_eligibility"
    if item.get("source_family") not in REVIEW_FAMILIES|ADDITIONAL_CONTEXT_FAMILIES:
        return False,"unsupported_family"
    return True,None


def recently_observed(state,now,limit=MAX_HISTORY_FILES):
    """Replay frozen *previously generated* deltas, not future outcomes."""
    folder=Path(state)/"history"/"behavioral_registry"
    files=sorted(folder.glob("*.json"))
    if len(files)>limit:
        # Prevent silently declaring complete time-window coverage
        # when the 72-hour trace may be missing from the tail.
        oldest=when(load_json(files[-limit],{}).get("generated_at"))
        if not oldest or now-oldest<dt.timedelta(hours=LOOKBACK_HOURS):
            raise ValueError("72-hour behavioral history exceeds bounded file cap; review retention")
    records={}
    rejected=Counter()
    historical_files=0
    for f in files[-limit:]:
        d=load_json(f)
        if not isinstance(d,dict) or d.get("schema")!=REGISTRY_SCHEMA:
            raise ValueError("Behavioral history schema invalid; cannot trust provenance")
        at=when(d.get("generated_at"))
        if not at or at>now+dt.timedelta(minutes=5):
            raise ValueError("Future or unparseable behavioral history clock")
        if now-at>dt.timedelta(hours=LOOKBACK_HOURS):
            continue
        historical_files+=1
        if d.get("first_registry_baseline"):
            continue
        for row in d.get("new_records",[]):
            valid,why=candidate_observation(row,now)
            if not valid:
                rejected[why]+=1
                continue
            rid=row["id"]
            if rid in records and records[rid]["information_root"]!=row["information_root"]:
                raise ValueError("Historical identity provenance changed")
            records[rid]=row
    if len(records)>MAX_RECENT:
        raise ValueError("Recent source observations exceed fusion cap; do not silently truncate")
    return records,{"lookback_hours":LOOKBACK_HOURS,
                    "history_files_examined":historical_files,
                    "recent_unique_records":len(records),
                    "excluded_observations":dict(rejected)}


def review_queue(registry,recent, now):
    """New single-source records always remain visible, including unlocated."""
    fresh={x["id"]:x for x in registry.get("records",[])
           if x.get("registry_novelty")=="newly_observed"}
    results=[]
    for ident,row in sorted(fresh.items()):
        allowed,reason=candidate_observation(row,now)
        if not allowed:
            continue
        results.append({
            "observation_id":ident,
            "first_observed_at":row["first_observed_at"],
            "source_published_at":row.get("source_published_at"),
            "geography":row["geography"],
            "source_family":row["source_family"],
            "evidence_class":row["evidence_class"],
            "information_root":row["information_root"],
            "source_url":row["source_url"],
            "title":row["title"],
            "status":"single_source_unreviewed",
            "meaning":"Observation novelty, not evidence of impending violence.",
            "requires_geolocation":row["geography"]["key"] is None,
        })
    results.sort(key=lambda x:(x["requires_geolocation"],x["source_family"],x["observation_id"]))
    return results[:MAX_SINGLE_LEADS],len(results)


def converge(recent,new_ids,now):
    """Require exact source-declared geo scope and distinct non-news families.

    No title-only country inference, no media double-count, no 2*press,
    no repeated maritime notices from two issuers as two independent
    information families, and no automatic escalation based on co-occurrence.
    """
    by_geo=defaultdict(list)
    for row in recent.values():
        g=row.get("geography") or {}
        scope=g.get("key")
        if scope and row["source_family"] in REVIEW_FAMILIES:
            by_geo[scope].append(row)
    groups=[]
    for loc,rows in by_geo.items():
        # Dedup claims with same family and information root; use earliest
        # first observation only. Same family = one behavioral sensor class.
        by_root={}
        for r in rows:
            ident=(r["source_family"],r["information_root"])
            if ident not in by_root or stamp(r)<stamp(by_root[ident]):
                by_root[ident]=r
        vals=sorted(by_root.values(),key=lambda r:(r["first_observed_at"],r["id"]))
        families={v["source_family"] for v in vals}
        providers={v["provider"] for v in vals}
        if len(families)<2 or len(providers)<2:
            continue
        # At least one observation must have entered the registry this
        # run; avoid repeatedly rediscovering standing evidence.
        new=[v for v in vals if v["id"] in new_ids]
        if not new:
            continue
        earliest=min(stamp(v) for v in vals)
        latest=max(stamp(v) for v in vals)
        if latest-earliest>dt.timedelta(hours=LOOKBACK_HOURS):
            continue
        group_id="behavioral:"+hashlib.sha256(
            ("|".join([loc]+sorted(v["id"] for v in vals))).encode()
        ).hexdigest()[:24]
        groups.append({
            "id":group_id,"geography":vals[0]["geography"],
            "first_observed_at":iso(earliest),"last_observed_at":iso(latest),
            "source_family_count":len(families),
            "distinct_source_families":sorted(families),
            "distinct_provider_count":len(providers),
            "source_root_count":len({v["information_root"] for v in vals}),
            "observation_ids":[v["id"] for v in vals],
            "new_observation_ids":[v["id"] for v in new],
            "source_links":[{"id":v["id"],"family":v["source_family"],
                             "provider":v["provider"],"url":v["source_url"],
                             "first_observed_at":v["first_observed_at"],
                             "published_at":v.get("source_published_at")} for v in vals],
            "status":"cross_family_cooccurrence_unreviewed",
            "warning_level_change":False,
            "assessment":"Geographically co-occurring source observations warrant checking; "
                         "shared cause, strategic relevance, actor attribution and military "
                         "intent are UNVERIFIED.",
            "alternative_explanations":[
                "Routine safety/compliance announcements",
                "Technical outages or environmental disruptions",
                "A shared public announcement prompted both signals",
            ],
            "next_checks":[
                "Validate exact locations and relevant actors from primary records",
                "Check historical local baselines and normal scheduled activity",
                "Establish information-root and causal independence",
                "Identify evidence against the escalation hypothesis",
            ],
        })
    groups.sort(key=lambda x:(-x["source_family_count"],-len(x["new_observation_ids"]),x["id"]))
    return groups[:MAX_REVIEW_GROUPS],len(groups)


def build(state,clock=None,write=True,run_id=None):
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    state=Path(state)
    registry=load_json(state/"latest"/"behavioral_registry.json",{}) or {}
    if registry.get("schema")!=REGISTRY_SCHEMA:
        raise ValueError("Normalized behavioral registry missing or wrong version")
    generated=when(registry.get("generated_at"))
    if not generated or generated>now+dt.timedelta(minutes=5) or now-generated>dt.timedelta(minutes=20):
        raise ValueError("Behavioral registry latest is not a fresh bounded collection; no stale re-alert")
    recent,history_diag=recently_observed(state,now)
    if registry.get("first_registry_baseline"):
        # First-pass data are the reference population, even if an
        # upstream adapter mislabels its initial items as novel.
        # Never send first-seen backfills as live review leads.
        single,single_total=[],0
        groups,total=[],0
    else:
        single,single_total=review_queue(registry,recent,now)
        recent_ids={x["id"] for x in registry["records"] if x.get("registry_novelty")=="newly_observed"}
        groups,total=converge(recent,recent_ids,now)
    output={
        "schema":SCHEMA,"generated_at":iso(now),
        "registry_asof":registry["generated_at"],
        "registry_source_count":registry.get("record_count"),
        "geographic_scope":"source_declared_only",
        "review_groups":groups,"review_groups_count_total":total,
        "new_single_source_leads":single,"new_single_source_count_total":single_total,
        "collection_coverage":registry["source_health"],
        "history_diagnostics":history_diag,
        "gdelt_context":"separate_analytical_stream_not_a_gate_or_confirmation",
        "ucdp_outcomes":"separate_retrospective_validation_not_an_alert_trigger",
        "prediction_horizon":None,
        "forecast_probability":None,
        "approved_warning_count":0,
        "automated_severity_changes":0,
        "limit_notes":[
            "No automated threat warning. These are unreviewed investigatory leads.",
            "Distinct providers and families do not prove causal independence.",
            "Media syndication, markets and source-only notices are not military preparations.",
            "Unlocated records cannot produce automatic geographic convergence.",
            "Unavailable collection is not evidence of no threatening activity.",
        ],
    }
    if write:
        run=re.sub(r"[^a-zA-Z0-9_-]","",str(run_id or os.environ.get("GITHUB_RUN_ID","local")))[:48]
        filename=now.strftime("%Y%m%dT%H%M%SZ")+"-"+run+".json"
        destination=state/"history"/"behavioral_fusion"/filename
        if destination.exists():
            raise ValueError("Append-only fusion run collision; refuse to overwrite")
        write_json(destination,output)
        write_json(state/"latest"/"behavioral_fusion.json",output)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",type=Path,required=True)
    a=p.parse_args()
    v=build(a.state)
    print(json.dumps({
        "asof":v["generated_at"],
        "new_single_source_leads":v["new_single_source_count_total"],
        "cross_family_review_groups":v["review_groups_count_total"],
        "history":v["history_diagnostics"],
        "approved_warning_count":0},indent=2))


if __name__=="__main__":
    main()
