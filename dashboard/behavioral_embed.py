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
MAX_RECENT_CONTEXT=24
MAX_EVENT_LINK_GROUPS=20
MAX_EVENT_SOURCES=8


def empty(reason="not_collected"):
    return {
        "schema":SCHEMA,"status":"unavailable",
        "reason":reason,"source_generated_at":None,
        "site_snapshot_fresh":False,
        "cross_family_count_total":0,"single_source_count_total":0,
        "review_groups":[],"new_single_source_leads":[],
        "collection_coverage":{},"provider_baselines":{},
        "discovery_visibility":None,"recent_source_observations":[],
        "report_relationships":None,
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
    # Preserve source monitoring evidence separately from candidate alerts.
    # These optional new fields are absent in historical published snapshots.
    vis = raw.get("discovery_visibility")
    contextual = raw.get("recent_source_observations", [])
    if (vis is not None or "recent_source_observations" in raw):
        expected = ("latest_registry_record_count",
                    "latest_registry_newly_observed_count",
                    "recent_unique_record_count_72h",
                    "recent_unlocated_count_72h",
                    "latest_unlocated_record_count",
                    "shared_exact_geography_keys_across_behavior_families",
                    "recent_observations_sampled")
        if (not isinstance(vis, dict) or
                vis.get("schema") != "aiba.behavioral-discovery-visibility.v1" or
                not isinstance(contextual, list) or len(contextual) > MAX_RECENT_CONTEXT or
                any(type(vis.get(key)) is not int or
                    not 0 <= vis[key] <= 100000 for key in expected) or
                vis.get("recent_observations_sampled") != len(contextual) or
                vis.get("source_coverage_is_globally_complete") is not False or
                vis.get("new_or_collocated_not_same_as_verified_threat") is not True):
            return empty("invalid_discovery_visibility_diagnostics")
        safe_vis = {key: vis[key] for key in expected}
        safe_vis["schema"] = vis["schema"]
        safe_vis["exact_geography_match_required_for_cross_family"] = (
            vis.get("exact_geography_match_required_for_cross_family") is True)
        safe_vis["new_this_collection_required_for_cross_family_nomination"] = (
            vis.get("new_this_collection_required_for_cross_family_nomination") is True)
        safe_vis["source_coverage_is_globally_complete"] = False
        safe_recent = []
        for item in contextual:
            if not isinstance(item, dict) or item.get("status") != "recent_source_observation_unreviewed":
                return empty("unexpected_historical_observation_status")
            observed = iso(item.get("first_observed_at"))
            if not observed or observed > stamp:
                return empty("future_or_invalid_source_observation")
            safe_recent.append({
                "observation_id": as_string(item.get("observation_id"), 140),
                "title": as_string(item.get("title"), 250),
                "source_family": as_string(item.get("source_family"), 120),
                "provider": as_string(item.get("provider"), 120),
                "source_url": https_url(item.get("source_url")),
                "first_observed_at": observed,
                "source_published_at": iso(item.get("source_published_at")),
                "geography": geo_note(item.get("geography")),
                "requires_geolocation": item.get("requires_geolocation") is True,
                "status": "recent_source_observation_unreviewed",
            })
    else:
        safe_vis = None
        safe_recent = []
    # Event/report relationship matching is a *separate* investigative lane.
    # Same document = potentially ONE report duplicated across geometries;
    # substantively similar reporting = possible same/related event, NOT
    # verified source independence or military intent.
    matches = raw.get("report_relationships")
    if matches is not None:
        statuses = {
            "shared_source_document_unreviewed",
            "possible_same_source_story_unreviewed",
            "possible_same_event_unreviewed",
            "related_reporting_unreviewed",
        }
        if (not isinstance(matches,dict) or
                matches.get("schema")!="aiba.report-event-resolution-shadow.v1" or
                matches.get("status")!="unreviewed_report_relationships_only" or
                matches.get("reporting_origins_are_not_event_locations") is not True or
                matches.get("source_independence_unverified") is not True or
                matches.get("not_a_preparations_sensor_or_warning") is not True or
                matches.get("automatic_alerts_created")!=0 or
                matches.get("automatic_severity_changes")!=0 or
                matches.get("forecast_probability") is not None or
                not isinstance(matches.get("candidate_groups"),list) or
                len(matches["candidate_groups"])>MAX_EVENT_LINK_GROUPS):
            return empty("invalid_event_resolution_metadata")
        safe_groups=[]
        for item in matches["candidate_groups"]:
            if (not isinstance(item,dict) or item.get("status") not in statuses or
                    item.get("independent_corroboration_established") is not False or
                    item.get("warning_level_change") is not False or
                    item.get("reporting_origin_used_as_event_site") is not False or
                    not isinstance(item.get("source_reports"),list) or
                    not 2<=len(item["source_reports"])<=MAX_EVENT_SOURCES):
                return empty("invalid_event_link_evidence")
            safe_links=[]
            for x in item["source_reports"]:
                if not isinstance(x,dict) or x.get("status")!="unreviewed_source_report":
                    return empty("invalid_event_source_report")
                safe_links.append({
                    "observation_id":as_string(x.get("observation_id"),140),
                    "title":as_string(x.get("title"),240),
                    "source_family":as_string(x.get("source_family"),80),
                    "provider":as_string(x.get("provider"),80),
                    "source_url":https_url(x.get("source_url")),
                    "first_observed_at":iso(x.get("first_observed_at")),
                    "source_published_at":iso(x.get("source_published_at")),
                    "reporting_origin":as_string(x.get("reporting_origin"),100),
                    "geography":geo_note(x.get("geography")),
                    "status":"unreviewed_source_report",
                })
            score=item.get("semantic_similarity")
            km=item.get("reported_event_site_separation_km")
            if score is not None and (type(score) not in (int,float) or not 0<=score<=1):
                return empty("invalid_event_semantic_similarity")
            if km is not None and (type(km) not in (int,float) or not 0<=km<=20020):
                return empty("invalid_event_site_separation")
            safe_groups.append({
                "id":as_string(item.get("id"),100),
                "status":item["status"],
                "match_basis":as_string(item.get("match_basis"),180),
                "semantic_similarity":score,
                "reported_event_site_separation_km":km,
                "reported_event_site_comparison_available":item.get(
                    "reported_event_site_comparison_available") is True,
                "shared_information_root":item.get("shared_information_root") is True,
                "independent_corroboration_established":False,
                "reporting_origin_used_as_event_site":False,
                "warning_level_change":False,
                "source_reports":safe_links,
            })
        examined=matches.get("records_examined")
        eligible=matches.get("eligible_event_reporting_records")
        excluded=matches.get(
            "routine_notice_market_or_measurement_records_excluded_from_text_event_matching")
        if (type(examined) is not int or type(eligible) is not int or
                type(excluded) is not int or examined<0 or eligible<0 or
                excluded<0 or eligible+excluded!=examined):
            return empty("invalid_event_report_denominators")
        safe_matches = {
            "schema":matches["schema"],
            "status":"unreviewed_report_relationships_only",
            "records_examined":examined,
            "eligible_event_reporting_records":eligible,
            "routine_notice_market_or_measurement_records_excluded_from_text_event_matching":
                excluded,
            "input_truncated":matches.get("input_truncated") is True,
            "pairwise_comparisons_capped":matches.get("pairwise_comparisons_capped") is True,
            "same_document_group_count_total":matches.get("same_document_group_count_total"),
            "possible_same_source_story_count_total":matches.get("possible_same_source_story_count_total"),
            "possible_same_event_count_total":matches.get("possible_same_event_count_total"),
            "related_reporting_count_total":matches.get("related_reporting_count_total"),
            "candidate_groups_truncated":matches.get("candidate_groups_truncated") is True,
            "reporting_origins_are_not_event_locations":True,
            "source_independence_unverified":True,
            "not_a_preparations_sensor_or_warning":True,
            "automatic_alerts_created":0,
            "automatic_severity_changes":0,
            "forecast_probability":None,
            "candidate_groups":safe_groups,
        }
    else:
        safe_matches=None
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
        "discovery_visibility":safe_vis,
        "recent_source_observations":safe_recent,
        "report_relationships":safe_matches,
        "collection_coverage":safe_health,
        "provider_baselines":provider_baselines,
        "approved_warning_count":0,
        "automated_severity_changes":0,
        "source_continuity_proven":False,
        "forecast_probability":None,
        "map_coordinates_inferred":False,
    }
