"""Bounded, provenance-preserving behavioral discovery input for the Atlas.

Embedding an existing rendered shadow data feed is read-only: it never
geocodes missing coordinates, promotes warnings or depends on GDELT.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA="aiba.behavioral-convergence-shadow.v1"
MAX_BYTES=2_000_000
MAX_GROUPS=25
MAX_LEADS=50
MAX_PROVIDERS=30
MAX_SOURCES_PER_GROUP=12


def empty(reason="not_collected"):
    return {
        "schema":SCHEMA,"status":"unavailable",
        "reason":reason,"source_generated_at":None,
        "site_snapshot_fresh":False,
        "cross_family_count_total":0,"single_source_count_total":0,
        "review_groups":[],"new_single_source_leads":[],
        "collection_coverage":{},"provider_baselines":{},
        "approved_warning_count":0,"automated_severity_changes":0,
        "source_continuity_proven":False,
        "forecast_probability":None,
        "map_coordinates_inferred":False,
    }


def as_string(value,max_chars=500):
    return value[:max_chars] if isinstance(value,str) else ""


def iso(value):
    if not isinstance(value,str) or len(value)>35:
        return None
    try:
        parsed=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset()!=dt.timedelta(0):
        return None
    return parsed.isoformat().replace("+00:00","Z")


def https_url(value):
    if not isinstance(value,str) or len(value)>2000:
        return None
    try:
        url=urlsplit(value)
    except ValueError:
        return None
    return value if url.scheme=="https" and bool(url.hostname) and not url.username and not url.password else None


def geo_note(value):
    g=value if isinstance(value,dict) else {}
    return {
        "label":as_string(g.get("label") or "Location not verified",180),
        "scope_key":as_string(g.get("key"),180) if g.get("key") else None,
        "precision":as_string(g.get("precision") or "not_geocoded",180),
        "verified_iso":g.get("verified_iso") is True,
    }


def read_bounded(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_BYTES:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError,RecursionError):
        return None


def embed(site):
    root=Path(site)/"behavior"
    raw=read_bounded(root/"behavioral_fusion.json")
    if not isinstance(raw,dict) or raw.get("schema")!=SCHEMA:
        return empty("missing_or_invalid_behavioral_fusion")
    stamp=iso(raw.get("generated_at"))
    groups=raw.get("review_groups")
    leads=raw.get("new_single_source_leads")
    health=raw.get("collection_coverage")
    if (not stamp or not isinstance(groups,list) or len(groups)>MAX_GROUPS or
        not isinstance(leads,list) or len(leads)>MAX_LEADS or
        not isinstance(health,dict) or len(health)>MAX_PROVIDERS):
        return empty("invalid_or_oversized_behavioral_snapshot")
    if (raw.get("approved_warning_count",0)!=0 or
        raw.get("automated_severity_changes",0)!=0 or
        raw.get("forecast_probability") is not None or
        raw.get("prediction_horizon") is not None):
        return empty("source_contains_unreviewed_promotion_or_forecast")
    def count(key,minimum):
        value=raw.get(key)
        return value if type(value) is int and minimum<=value<=100000 else None
    total_groups=count("review_groups_count_total",len(groups))
    total_leads=count("new_single_source_count_total",len(leads))
    if total_groups is None or total_leads is None:
        return empty("inconsistent_behavioral_counts")
    safe_groups=[]
    for row in groups:
        if not isinstance(row,dict) or row.get("status")!="cross_family_cooccurrence_unreviewed" or row.get("warning_level_change") is not False:
            return empty("unexpected_behavioral_group_promotion")
        families=row.get("distinct_source_families")
        links=row.get("source_links")
        if not isinstance(families,list) or len(families)<2 or not isinstance(links,list):
            return empty("invalid_behavioral_group_evidence")
        safe_groups.append({
            "id":as_string(row.get("id"),100),
            "geography":geo_note(row.get("geography")),
            "source_family_count":row.get("source_family_count") if type(row.get("source_family_count")) is int else len(families),
            "distinct_source_families":[as_string(x,100) for x in families[:12]],
            "distinct_provider_count":row.get("distinct_provider_count"),
            "source_root_count":row.get("source_root_count"),
            "assessment":as_string(row.get("assessment"),800),
            "status":"cross_family_cooccurrence_unreviewed",
            "first_observed_at":iso(row.get("first_observed_at")),
            "last_observed_at":iso(row.get("last_observed_at")),
            "source_links":[{
                "url":https_url(x.get("url")), "provider":as_string(x.get("provider"),120),
                "family":as_string(x.get("family"),120),
                "first_observed_at":iso(x.get("first_observed_at")),
                "published_at":iso(x.get("published_at"))
            } for x in links[:MAX_SOURCES_PER_GROUP] if isinstance(x,dict)],
            "warning_level_change":False,
        })
    safe_leads=[]
    for row in leads:
        if not isinstance(row,dict) or row.get("status")!="single_source_unreviewed":
            return empty("unexpected_source_lead_status")
        safe_leads.append({
            "observation_id":as_string(row.get("observation_id"),140),
            "title":as_string(row.get("title"),250),
            "source_family":as_string(row.get("source_family"),120),
            "source_url":https_url(row.get("source_url")),
            "first_observed_at":iso(row.get("first_observed_at")),
            "source_published_at":iso(row.get("source_published_at")),
            "geography":geo_note(row.get("geography")),
            "requires_geolocation":row.get("requires_geolocation") is True,
            "status":"single_source_unreviewed",
        })
    safe_health={}
    for name,row in sorted(health.items()):
        if not isinstance(name,str) or not isinstance(row,dict):
            return empty("invalid_source_coverage")
        safe_health[as_string(name,80)]={
            "status":as_string(row.get("status") or "unknown",100),
            "missingness":as_string(row.get("missingness") or "unknown",160),
            "source_scope":as_string(row.get("source_scope") or "unverified scope",400),
            "snapshot_at":iso(row.get("snapshot_at")),
        }
    baseline=read_bounded(root/"behavioral_baselines.json")
    provider_baselines={}
    if isinstance(baseline,dict) and baseline.get("schema")=="aiba.behavioral-provider-baseline.v1":
        for name,row in list((baseline.get("sources") or {}).items())[:MAX_PROVIDERS]:
            if isinstance(name,str) and isinstance(row,dict):
                days=row.get("comparable_provider_snapshot_days")
                provider_baselines[as_string(name,80)]={
                    "status":as_string(row.get("status") or "unknown",80),
                    "comparable_days":days if type(days) is int else None,
                    "median_records":row.get("median_daily_source_snapshot_records")
                        if type(row.get("median_daily_source_snapshot_records")) in (int,float) else None,
                }
    return {
        "schema":SCHEMA,
        "status":"read_only_shadow_evidence",
        "reason":None,
        "source_generated_at":stamp,
        "site_snapshot_fresh":raw.get("site_snapshot_fresh") is True,
        "cross_family_count_total":total_groups,
        "single_source_count_total":total_leads,
        "review_groups":safe_groups,
        "new_single_source_leads":safe_leads,
        "collection_coverage":safe_health,
        "provider_baselines":provider_baselines,
        "approved_warning_count":0,
        "automated_severity_changes":0,
        "source_continuity_proven":False,
        "forecast_probability":None,
        "map_coordinates_inferred":False,
    }
