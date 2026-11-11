#!/usr/bin/env python3
"""Worldwide-capable source-separated behavioral observation registry.

Normalizes *existing* source records without imposing AIBA's curated-case list.
No inference of hostile intent, country attribution from prose, or verified
preparatory behavior. Unknown availability is not a measured zero.
This is an observation ledger, not an operational alert/forecast engine.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from ops_pipeline import load_json, parse_time, write_json

UTC = dt.timezone.utc
SCHEMA = "aiba.behavioral-observations.v1"
MODES = ("ioda", "nga", "amsa", "official", "commercial", "watchlist")
ALLOWED_STATES = {"collected", "partial"}
FRESH_HOURS = {"ioda": 6, "nga": 6, "amsa": 6,
               "official": 12, "commercial": 48, "watchlist": 12}
FAMILIES = {"ioda": "internet_reachability", "nga": "maritime_restriction",
            "amsa": "maritime_restriction", "official": "protective_notice",
            "commercial": "commercial_media", "watchlist": "market_expectation"}
EVIDENCE = {"ioda": "network_measurement", "nga": "official_notice",
            "amsa": "official_notice", "official": "official_notice",
            "commercial": "media_mention", "watchlist": "market_quote"}
# No source is yet verified as a military preparations sensor.
DIRECT_BEHAVIOR = {"ioda": True, "nga": False, "amsa": False,
                   "official": False, "commercial": False, "watchlist": False}
MAX_PER_MODE = 500
MAX_INDEX = 15000
MAX_SNAPSHOT = 2500


def when(value):
    parsed = parse_time(value)
    return parsed.astimezone(UTC) if parsed else None


def iso(value):
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fingerprint(*components):
    return hashlib.sha256("\x1f".join(str(x) for x in components).encode()).hexdigest()[:28]


def safe_url(value):
    if not isinstance(value, str) or len(value)>2000:
        return None
    v = urlsplit(value)
    if v.scheme != "https" or not v.hostname or v.username or v.password:
        return None
    return value


def mode_status(state, mode, now):
    """Source-by-source freshness, including later failures after a stale latest."""
    state=Path(state)
    if mode in ("ioda", "nga", "amsa"):
        snapshot=load_json(state/"latest"/"friction.json",{}) or {}
        snap_at=when(snapshot.get("collected_at"))
        health=load_json(state/"health"/f"friction_{mode}.json",{}) or {}
        available=mode in snapshot.get("health",{}) and mode in (
            r.get("provider") for r in snapshot.get("records",[]) if isinstance(r,dict)
        )
        # The provider may successfully return zero events. Its presence in
        # snapshot.health, not a nonzero record count, defines success.
        available=mode in snapshot.get("health",{})
    else:
        snapshot=load_json(state/"latest"/f"{mode}.json",{}) or {}
        snap_at=when(snapshot.get("observed_at"))
        health=load_json(state/"health"/f"{mode}.json",{}) or {}
        available=bool(snapshot)
    health_at=when(health.get("checked_at"))
    age=(now-snap_at).total_seconds()/3600 if snap_at else None
    healthy=health.get("status") in ALLOWED_STATES
    if health_at and snap_at and health_at>snap_at and not healthy:
        available=False
    current=(bool(available) and healthy and age is not None
             and 0<=age<=FRESH_HOURS[mode])
    truncated=bool(health.get("truncated")) or health.get("status")=="partial"
    return {"mode":mode,"status":"current_partial" if current and truncated else
            "current" if current else "stale_or_unavailable",
            "provider_status":health.get("status","never_checked"),
            "checked_at":health.get("checked_at"),
            "snapshot_at":iso(snap_at) if snap_at else None,
            "age_hours":round(age,2) if age is not None else None,
            "truncated_or_partial":truncated,
            "source_scope":("IODA country events (first 100 of first page, 4-hour query)" if mode=="ioda"
                            else "NGA active broadcast warnings; provider availability varies" if mode=="nga"
                            else "AMSA NAVAREA X only" if mode=="amsa"
                            else "US State and UK FCDO travel-advice feeds" if mode=="official"
                            else "selected maritime/air-cargo/war-risk press and syndication" if mode=="commercial"
                            else "registered, exact-ID forecast contracts only"),
            "missingness":"not_measured_not_zero" if not current else
                          "partial_sampling_not_worldwide_exhaustive" if truncated else
                          "provider_bounded_not_exhaustive",
            "_current":current, "_snapshot":snapshot}


def location(row, mode):
    """Only source-declared geography; no inferred coordinate from text."""
    if mode=="ioda":
        kind=str(row.get("entity_type") or "").lower().strip()
        code=str(row.get("entity_code") or "").upper().strip()
        if kind=="country" and re.fullmatch(r"[A-Z]{2,3}",code):
            return {"key":f"country:{code}","kind":"country_code","label":code,
                    "precision":"provider_reported_country","verified_iso":False,
                    "latitude":None,"longitude":None}
        if kind in ("region","asn","geoasn") and re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}",code):
            return {"key":f"network:{kind}:{code}","kind":"network_entity","label":f"{kind} {code}",
                    "precision":"provider_network_or_region_not_incident","verified_iso":False,
                    "latitude":None,"longitude":None}
    if mode=="amsa":
        # AMSA's feed is NAVAREA X; a warning's actual hazard point is not inferred.
        return {"key":"navarea:X","kind":"maritime_region","label":"NAVAREA X",
                "precision":"regional_not_point","verified_iso":False,
                "latitude":None,"longitude":None}
    if mode=="nga":
        region=str(row.get("area") or "").strip()
        if region and len(region)<=50 and re.fullmatch(r"[\w /.-]+",region):
            return {"key":f"maritime-area:{region.casefold()}","kind":"maritime_region",
                    "label":region,"precision":"source_text_region_not_point",
                    "verified_iso":False,"latitude":None,"longitude":None}
    return {"key":None,"kind":"unlocated","label":None,
            "precision":"no_source_verified_geography",
            "verified_iso":False,"latitude":None,"longitude":None}


def normalize(mode, row, now):
    if not isinstance(row,dict):
        return None, "invalid_record_shape"
    provider=str(row.get("provider") or mode).strip().lower()
    if mode in ("ioda","nga","amsa") and provider!=mode:
        return None,"friction_provider_mismatch"
    rid=str(row.get("id") or "").strip()
    url=safe_url(row.get("source_url"))
    if not rid or not url or len(rid)>200:
        return None,"missing_source_id_or_https_url"
    collected=when(row.get("collected_at") or row.get("observed_at"))
    if not collected or collected>now+dt.timedelta(minutes=5):
        return None,"missing_or_future_collection_clock"
    published=when(row.get("source_published_at") or row.get("published_at"))
    occurred=when(row.get("event_at"))
    first_feed=when(row.get("first_seen_at"))
    if any(t and t>collected+dt.timedelta(minutes=5) for t in (published,occurred,first_feed)):
        return None,"source_clock_after_observation"
    group=location(row,mode)
    family=FAMILIES[mode]
    root=str(row.get("root") or "").strip() if mode in ("ioda","nga","amsa") else ""
    # Do not promote syndication to independently confirmed commercial action.
    if not root:
        root=f"{mode}:{rid}"
    result={
        "id":"beh:"+fingerprint(mode,rid),
        "raw_source_id":rid,"provider":provider,"source_family":family,
        "evidence_class":EVIDENCE[mode],"direct_observed_behavior":DIRECT_BEHAVIOR[mode],
        "observed_at":iso(collected),"event_at":iso(occurred) if occurred else None,
        "source_published_at":iso(published) if published else None,
        "upstream_first_seen_at":iso(first_feed) if first_feed else None,
        "source_url":url,"information_root":root[:230],
        "title":str(row.get("title") or row.get("event") or "").strip()[:240],
        "source_kind":str(row.get("kind") or row.get("status") or "")[:90],
        "geography":group,
        "case_hint":str(row.get("case_id"))[:90] if row.get("case_id") else None,
        "claim_level":("measurement_no_attribution" if mode=="ioda" else
                       "notice_not_verified_preparation" if mode in ("amsa","nga","official") else
                       "news_mention_not_action" if mode=="commercial" else
                       "market_quote_not_war_probability"),
        "actor_identified":False,
        "alert_eligible":False,
    }
    return result,None


def create(state, clock=None, write=True, run_id=None):
    """Reconcile latest bounded collectors into an auditable normalized registry.

    Stable identities persist 45 days; first pass initializes the baseline.
    A failed or stale provider never contributes an observation.
    """
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    state=Path(state)
    prev=load_json(state/"latest"/"behavioral_registry.json",{}) or {}
    old_index=load_json(state/"index"/"behavioral_seen.json",{}) or {}
    if not isinstance(old_index,dict):
        raise ValueError("Behavioral identity index is not a dictionary")
    index={}
    for k,v in old_index.items():
        if not isinstance(v,dict):
            raise ValueError("Behavioral source identity index corrupted")
        at=when(v.get("last_observed_at"))
        if at and dt.timedelta(0)<=now-at<=dt.timedelta(days=45):
            index[k]=v
    statuses={}
    incoming=[]
    rejects={}
    for mode in MODES:
        status=mode_status(state,mode,now)
        statuses[mode]={k:v for k,v in status.items() if not k.startswith("_")}
        if not status["_current"]:
            continue
        snap=status["_snapshot"]
        if mode in ("ioda","nga","amsa"):
            raw=[r for r in snap.get("records",[]) if isinstance(r,dict) and r.get("provider")==mode]
        else:
            raw=snap.get("records",[])
        if not isinstance(raw,list):
            raise ValueError(f"{mode} source snapshot records are not a list")
        if len(raw)>MAX_PER_MODE:
            statuses[mode]["truncated_or_partial"]=True
            statuses[mode]["missingness"]="partial_sampling_not_worldwide_exhaustive"
            rejects[f"{mode}:bounded"]=len(raw)-MAX_PER_MODE
        for entry in raw[:MAX_PER_MODE]:
            item,error=normalize(mode,entry,now)
            if error:
                rejects[f"{mode}:{error}"]=rejects.get(f"{mode}:{error}",0)+1
            else:
                incoming.append(item)
    if len(incoming)>MAX_SNAPSHOT:
        raise ValueError("Behavioral snapshot exceeds bounded safety cap")
    unique={}
    for item in incoming:
        if item["id"] in unique and item!=unique[item["id"]]:
            raise ValueError(f"Conflicting same-source behavioral identity: {item['id']}")
        unique[item["id"]]=item
    prior_initialized=prev.get("schema")==SCHEMA
    changes=[]
    for item in unique.values():
        old=index.get(item["id"])
        if old and old.get("information_root")!=item["information_root"]:
            raise ValueError("Information root for persistent identity changed; manual reconciliation needed")
        if old:
            first=when(old.get("first_observed_at"))
            if not first or first>now:
                raise ValueError("Corrupt first-observed timestamp")
            item["first_observed_at"]=iso(first)
            item["registry_novelty"]="existing"
        else:
            first=when(item["upstream_first_seen_at"]) or now
            item["first_observed_at"]=iso(first)
            item["registry_novelty"]="newly_observed" if prior_initialized else "initial_baseline"
            if prior_initialized:
                changes.append(item.copy())
        index[item["id"]]={
            "first_observed_at":item["first_observed_at"],
            "last_observed_at":iso(now),
            "information_root":item["information_root"],
            "source_family":item["source_family"]}
    if len(index)>MAX_INDEX:
        raise ValueError("Behavioral index cap exceeded; audit source churn before truncation")
    records=sorted(unique.values(),key=lambda r:(r["source_family"],r["id"]))
    result={
        "schema":SCHEMA,"generated_at":iso(now),"scope":"worldwide_capable_but_source_bounded",
        "records":records,"source_health":statuses,"invalid_records":rejects,
        "record_count":len(records),"new_after_baseline_count":len(changes),
        "first_registry_baseline":not prior_initialized,
        "alert_eligible":False,
        "limitations":[
            "No evidence of preparation or military intent is inferred by normalization.",
            "Commercial trade press is a media mention, not an independently verified commercial action.",
            "NGA and AMSA are maritime notices, not confirmed kinetic events.",
            "An IODA outage is not cyberattack attribution.",
            "Unlocated observations remain unlocated, even when text names a theater.",
            "Current source availability is bounded; no global completeness claim.",
        ],
    }
    if write:
        run=re.sub(r"[^a-zA-Z0-9_-]","",str(run_id or os.environ.get("GITHUB_RUN_ID","local")))[:48]
        filename=now.strftime("%Y%m%dT%H%M%SZ")+"-"+run+".json"
        delta={
            "schema":SCHEMA,"generated_at":iso(now),
            "first_registry_baseline":not prior_initialized,
            "new_records":changes,"source_health":statuses,"invalid_records":rejects,
            "full_snapshot_count":len(records),
            "operational_alerts_generated":0}
        history=state/"history"/"behavioral_registry"/filename
        if history.exists():
            raise ValueError("Append-only behavioral run identity collision; no overwrite")
        write_json(history,delta)
        write_json(state/"index"/"behavioral_seen.json",index)
        write_json(state/"latest"/"behavioral_registry.json",result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",type=Path,required=True)
    args=p.parse_args()
    result=create(args.state)
    print(json.dumps({"registry_count":result["record_count"],
                      "new_after_baseline":result["new_after_baseline_count"],
                      "source_health":result["source_health"],
                      "invalid":result["invalid_records"],
                      "alert_eligible":False},indent=2))


if __name__=="__main__":
    main()
