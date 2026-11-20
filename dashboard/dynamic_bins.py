"""Bounded source-grounded evidence-family candidate index for public Atlas.

Family visibility does not require corroboration. A source information root is
one family; an independently constructed possible-event relationship may link
several roots, without claiming they describe a verified single event.
No fabricated event locations, measured anomaly scores, warning elevations,
or inferred source independence.
"""
from __future__ import annotations

from collections import defaultdict
import datetime as dt
import hashlib
from urllib.parse import urlsplit

UTC = dt.timezone.utc
SCHEMA = "aiba.dynamic-evidence-bins.v1"
REGISTRY_SCHEMA = "aiba.behavioral-observations.v1"
MAX_RECORDS = 2500
MAX_ANALYST = 500
MAX_OUTPUT = 800
MAX_SOURCES = 12
MAX_RELATIONSHIPS = 20
NEW_HOURS = 36
MONITOR_DAYS = 14
RELATION_STATUSES = {"possible_same_event_unreviewed", "related_reporting_unreviewed"}


def when(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
        return stamp.astimezone(UTC)
    except ValueError:
        return None


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        x = urlsplit(value)
    except ValueError:
        return None
    return value if x.scheme == "https" and x.hostname and not x.username and not x.password else None


def stable_id(label, source):
    return "family:" + hashlib.sha256((label + ":" + source).encode()).hexdigest()[:20]


def clean(value, limit=220):
    return value.strip()[:limit] if isinstance(value, str) else ""


def normalize_registry(registry):
    if not isinstance(registry, dict) or registry.get("schema") != REGISTRY_SCHEMA:
        return [], "unavailable"
    rows = registry.get("records")
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        return [], "invalid_or_oversized"
    result = []
    for record in rows:
        if not isinstance(record, dict) or not safe_url(record.get("source_url")):
            continue
        stamp = when(record.get("first_observed_at"))
        root = clean(record.get("information_root"), 220)
        ident = clean(record.get("id"), 150)
        if not stamp or not root or not ident:
            continue
        geo = record.get("geography") if isinstance(record.get("geography"), dict) else {}
        result.append({
            "id": ident,
            "information_root": root,
            "first_observed_at": stamp.isoformat(),
            "published_at": record.get("source_published_at"),
            "event_at": record.get("event_at"),
            "source_url": safe_url(record["source_url"]),
            "title": clean(record.get("title"), 270),
            "provider": clean(record.get("provider"), 100),
            "source_family": clean(record.get("source_family"), 120),
            "source_kind": clean(record.get("source_kind"), 120),
            "origin": "behavioral_registry",
            "geography_label": clean(geo.get("label"), 160) or None,
            "geography_key": clean(geo.get("key"), 160) or None,
            "geography_precision": clean(geo.get("precision"), 160) or "not_verified",
            "case_hint": clean(record.get("case_hint"), 150) or None,
            "direct_measurement": record.get("direct_observed_behavior") is True,
            "claim_level": clean(record.get("claim_level"), 140),
        })
    return result, "available"


def normalize_analyst(analyst):
    if not isinstance(analyst, dict):
        return []
    rows = analyst.get("records")
    if not isinstance(rows, list):
        return []
    result = []
    for record in rows[:MAX_ANALYST]:
        if not isinstance(record, dict) or not safe_url(record.get("source_url")):
            continue
        stamp = when(record.get("first_collected_at"))
        root = clean(record.get("information_root"), 220)
        ident = clean(record.get("observation_id"), 150)
        if not stamp or not root or not ident:
            continue
        result.append({
            "id": "analyst:" + ident,
            "information_root": root,
            "first_observed_at": stamp.isoformat(),
            "published_at": record.get("published_at"),
            "event_at": None,
            "source_url": record["source_url"],
            "title": clean(record.get("title"), 270),
            "provider": clean(record.get("publisher"), 100) or "Analyst intake",
            "source_family": clean(record.get("evidence_class"), 120) or "analyst_report",
            "source_kind": "unreviewed_analyst_report",
            "origin": "analyst_intake",
            "geography_label": None,
            "geography_key": None,
            "geography_precision": "case_hint_not_source_geolocation",
            "case_hint": clean(record.get("case_id"), 150) or None,
            "direct_measurement": False,
            "claim_level": "unreviewed_source_submission",
        })
    return result


def state_for(stamp, now):
    age = now - stamp
    if age < dt.timedelta(0):
        return None
    if age <= dt.timedelta(hours=NEW_HOURS):
        return "emerging"
    if age <= dt.timedelta(days=MONITOR_DAYS):
        return "monitoring"
    return "quiet"


def build(registry, analyst, relationships=None, now=None):
    """Index all accepted source roots, including uncorroborated anomalies.

    Chronology is based on *first* collection, never a routine re-poll of old
    evidence. Existing registry history retains old roots while available.
    """
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Generation clock requires UTC offset")
    now = now.astimezone(UTC)
    source_rows, status = normalize_registry(registry)
    source_rows += normalize_analyst(analyst)
    roots = defaultdict(dict)
    by_observation = {}
    for row in source_rows:
        stamp = when(row["first_observed_at"])
        if stamp is None or stamp > now:
            continue
        by_observation[row["id"]] = row
        roots[row["information_root"]][row["id"]] = row
    families = []
    for root, member_map in roots.items():
        members = sorted(member_map.values(), key=lambda v: (v["first_observed_at"], v["id"]), reverse=True)
        if not members:
            continue
        first = min(when(x["first_observed_at"]) for x in members)
        last = max(when(x["first_observed_at"]) for x in members)
        lifecycle = state_for(last, now)
        if lifecycle is None:
            continue
        sample = members[0]
        family_names = sorted({x["source_family"] for x in members if x["source_family"]})
        providers = sorted({x["provider"] for x in members if x["provider"]})
        cases = sorted({x["case_hint"] for x in members if x["case_hint"]})
        families.append({
            "id": stable_id("root", root),
            "kind": "source_root_candidate",
            "title": sample["title"] or sample["source_family"] or "Unreviewed observation",
            "state": lifecycle,
            "new_activity": lifecycle == "emerging",
            "last_observed_at": last.isoformat(),
            "first_observed_at": first.isoformat(),
            "information_root_count": 1,
            "source_record_count": len(members),
            "source_families": family_names,
            "providers": providers,
            "case_hints": cases,
            "geography_label": sample["geography_label"],
            "geography_precision": sample["geography_precision"],
            "map_eligible": False,  # Source-notice sites are not incident sites.
            "source_independence_established": False,
            "event_occurrence_verified": False,
            "warning_approved": False,
            "anomaly_metric": {"status": "not_calibrated", "z_score": None},
            "corroboration": {"status": "unreviewed", "independent_roots": 1},
            "sources": members[:MAX_SOURCES],
            "sources_truncated": len(members) > MAX_SOURCES,
            "reason": "Distinct original source information root; report novelty is not statistical abnormality.",
        })
    # Explicit candidate links from the separately tested semantic resolver.
    # Never cluster entire countries or two unrelated stories merely because
    # their analysts assigned the same standing case_id.
    candidate_groups = relationships.get("candidate_groups", []) if isinstance(relationships, dict) else []
    for candidate in candidate_groups[:MAX_RELATIONSHIPS]:
        if not isinstance(candidate, dict) or candidate.get("status") not in RELATION_STATUSES:
            continue
        refs = candidate.get("source_reports", [])
        if not isinstance(refs, list) or len(refs) < 2:
            continue
        members = {row["id"]: row for ref in refs if isinstance(ref, dict)
                   for row in [by_observation.get(ref.get("observation_id"))] if row}
        distinct_roots = {x["information_root"] for x in members.values()}
        if len(distinct_roots) < 2:
            continue
        rows = sorted(members.values(), key=lambda v: v["first_observed_at"], reverse=True)
        last = when(rows[0]["first_observed_at"])
        lifecycle = state_for(last, now)
        if lifecycle is None:
            continue
        families.append({
            "id": stable_id("relation", clean(candidate.get("id"), 180)),
            "kind": "possible_related_reporting",
            "title": rows[0]["title"] or "Possible related reports",
            "state": lifecycle,
            "new_activity": lifecycle == "emerging",
            "last_observed_at": last.isoformat(),
            "first_observed_at": min(x["first_observed_at"] for x in rows),
            "information_root_count": len(distinct_roots),
            "source_record_count": len(rows),
            "source_families": sorted({x["source_family"] for x in rows}),
            "providers": sorted({x["provider"] for x in rows}),
            "case_hints": sorted({x["case_hint"] for x in rows if x["case_hint"]}),
            "geography_label": None,
            "geography_precision": "relationship_not_event_site",
            "map_eligible": False,
            "source_independence_established": False,
            "event_occurrence_verified": False,
            "warning_approved": False,
            "anomaly_metric": {"status": "not_calibrated", "z_score": None},
            "corroboration": {"status": "possible_related_reporting", "independent_roots": None},
            "sources": rows[:MAX_SOURCES],
            "sources_truncated": len(rows) > MAX_SOURCES,
            "reason": clean(candidate.get("match_basis"), 220) or "Candidate report association requiring analyst review.",
        })
    ordering = {"emerging": 0, "monitoring": 1, "quiet": 2}
    families.sort(key=lambda f: (ordering[f["state"]], -when(f["last_observed_at"]).timestamp(), f["id"]))
    return {
        "schema": SCHEMA,
        "status": "source_observations_not_verified_events",
        "generated_at": now.isoformat(),
        "registry_status": status,
        "candidate_count_total": len(families),
        "candidate_count_displayed": min(len(families), MAX_OUTPUT),
        "truncated": len(families) > MAX_OUTPUT,
        "emerging_count": sum(f["state"] == "emerging" for f in families),
        "monitoring_count": sum(f["state"] == "monitoring" for f in families),
        "quiet_count": sum(f["state"] == "quiet" for f in families),
        "unverified_map_points_count": 0,
        "automatic_warning_count": 0,
        "default_order": "recent_first_per_lifecycle_no_unvalidated_anomaly_scores",
        "families": families[:MAX_OUTPUT],
    }
