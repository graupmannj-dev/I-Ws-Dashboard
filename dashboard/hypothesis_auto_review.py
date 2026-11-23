"""Deterministic, provenance-preserving preliminary hypothesis screening.

Runs on the current durable evidence snapshot during each publication triggered by
collection. It NEVER amends human reviews, assigns ordinal weights, or issues warnings.
Lexical signposts only nominate observations for analyst examination.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlsplit

SCHEMA = "cairn.hypothesis-auto-screen.v1"
REGISTRY_SCHEMA = "aiba.behavioral-observations.v1"
ARCHIVE_SCHEMA = "aiba.family-archive.v1"
LOOKBACK_HOURS = 9
MAX_RECORDS = 12000
MAX_MATCHES_PER_CASE = 12
HISTORY_HOURS = 168
MAX_HISTORY_PER_CASE = 15

# Explicit, distinctive location/actor cues; a generic country or publisher
# dateline must not silently link an observation to an interstate scenario.
CASE_CUES = {
    "horn_ethiopia_eritrea": ("eritrea", "tigray", "ethiopia–eritrea", "ethiopia-eritrea"),
    "horn_ethiopia_sudan": ("al fashaga", "al-fashaga", "ethiopia–sudan", "ethiopia-sudan"),
    "horn_ethiopia_kenya_moyale": ("moyale", "ethiopia–kenya", "ethiopia-kenya"),
    "afpak": ("torkham", "durand line", "spin boldak", "afghanistan–pakistan", "afghanistan-pakistan"),
    "drc_rwanda": ("north kivu", "goma", "m23", "drc–rwanda", "drc-rwanda", "rwanda–congo"),
    "thailand_cambodia": ("thailand–cambodia", "thailand-cambodia", "preah vihear", "ta moan"),
    "russia_nato": ("nato", "baltic sea", "kaliningrad", "suwalki"),
    "iran_gulf": ("strait of hormuz", "hormuz", "persian gulf", "iran–us", "iran-us"),
    "taiwan": ("taiwan", "taiwan strait", "kinmen", "matsu islands"),
    "korea": ("north korea", "south korea", "korean peninsula", "demilitarized zone", "dmz korea"),
}

# These are *candidate signposts*, not confirmed hostile acts or likelihood ratios.
# Restrict support triggers to concrete observable changes, not generic terms
# such as 'military', 'risk', 'crisis', 'tension', 'anomaly', or 'exercise'.
SUPPORT_CUES = (
    ("evacuation order", r"\b(?:ordered|mandatory|emergency|mass) evacuations?\b|\bevacuations? order(?:ed|s)?\b"),
    ("new border closure", r"\b(?:border|crossing|frontier) (?:has been |was )?(?:closed|sealed|shut)\b|\bclosed (?:the )?(?:border|border crossing)\b"),
    ("airspace restriction", r"\b(?:airspace|flight corridor) (?:closure|closed|restricted|shutdown)\b|\bno.fly zone\b"),
    ("maritime exclusion", r"\b(?:maritime|shipping|navigation|sea) exclusion (?:zone|area)\b|\bshipping (?:halted|suspended)\b"),
    ("force concentration", r"\b(?:troop|force|armou?red|naval) (?:build.?up|concentration|mobilization)\b|\b(?:mass|large.scale) deployment\b"),
    ("cross-border attack", r"\b(?:cross.border|border) (?:attack|strike|shelling|incursion|firing)\b"),
)
COUNTER_CUES = (
    ("restriction reportedly lifted", r"\b(?:restriction|closure|ban) (?:was |has been )?(?:lifted|rescinded)\b"),
    ("border reportedly reopened", r"\b(?:border|crossing) (?:has been |was )?reopened\b"),
    ("service reportedly restored", r"\b(?:service|traffic|transit) (?:was |has been )?restored\b"),
)
CONTEXT_ONLY_MODES = {"usgs", "eonet", "nws", "swpc", "bmkg_quake", "jma_weather",
                      "metservice_nz", "bom_au", "imd_in", "metoffice_uk"}
NEGATED = re.compile(r"\b(?:no|not|false|denied|denies|unconfirmed|rumou?r(?:ed|s)?)\b", re.I)


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _safe_url(value):
    if not isinstance(value, str) or len(value) > 1800:
        return None
    try:
        u = urlsplit(value)
        return value if u.scheme == "https" and u.hostname and not u.username and not u.password else None
    except ValueError:
        return None


def _excerpt(value, size=260):
    return str(value or "").strip()[:size]


def _match_case(case_id, record):
    hint = record.get("case_hint")
    if isinstance(hint, str) and hint == case_id:
        return "explicit_case_hint"
    cues = CASE_CUES.get(case_id, ())
    if not cues:
        return None
    # The provider's reported geography is useful context; the publisher
    # location, URL and domain are deliberately NOT geographic matches.
    geography = record.get("geography")
    # Registry geography is normally a structured provider-reported object.
    # Only its reported geographic label is a candidate for case matching:
    # never match object metadata, collector origins or dateline URLs.
    place = geography.get("label") if isinstance(geography, dict) else geography
    reported = (" " + _excerpt(record.get("title"), 240) + " " +
                _excerpt(place, 180) + " ").casefold()
    return "distinctive_case_cue" if any(cue in reported for cue in cues) else None


def _directional_hint(record):
    mode = record.get("collection_mode")
    if mode in CONTEXT_ONLY_MODES or record.get("source_family") == "environmental_context":
        return "context", "Environmental or hazard observation; not evidence of hostile preparation"
    title = _excerpt(record.get("title"), 240).lower()
    support = [name for name, rx in SUPPORT_CUES if re.search(rx, title, re.I)]
    counter = [name for name, rx in COUNTER_CUES if re.search(rx, title, re.I)]
    if NEGATED.search(title):
        return "requires_interpretation", "Negation, denial or uncertainty requires source reading"
    if support and counter:
        return "requires_interpretation", "Both action and reversal phrases present"
    if support:
        return "possible_support", "Candidate observable signpost: " + ", ".join(support)
    if counter:
        return "possible_counter", "Possible relaxation of a signpost: " + ", ".join(counter)
    return "context", "No discriminating observable signpost recognized in source title"


def screen(dossiers, registry, archive=None, *, at=None, lookback_hours=LOOKBACK_HOURS):
    """Screen newly first-observed source records for distinctive case cues.

    The record's first-observed UTC timestamp is the ingestion clock, *not* an
    incident or publication date. Missing provider health is not negative evidence.
    A matching cue is not validated source independence or a direction decision.
    """
    if not 1 <= lookback_hours <= 72:
        raise ValueError("Lookback must be 1..72 hours")
    now = (_parse_time(at) if isinstance(at, str) else at) or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Screen time must be timezone aware")
    now = now.astimezone(dt.timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")
    valid_registry = (isinstance(registry, dict) and
                      registry.get("schema") == REGISTRY_SCHEMA and
                      isinstance(registry.get("records"), list))
    valid_archive = (isinstance(archive, dict) and archive.get("schema") == ARCHIVE_SCHEMA
                     and isinstance(archive.get("records"), list))
    records = (archive["records"] if valid_archive else registry.get("records", [])) if valid_registry else []
    snapshot_time = _parse_time(registry.get("generated_at")) if valid_registry else None
    current_snapshot = bool(snapshot_time and dt.timedelta(0) <= now - snapshot_time
                            <= dt.timedelta(hours=lookback_hours))
    status = ("screened" if valid_registry and current_snapshot else
              "source_snapshot_stale" if valid_registry else "source_snapshot_unavailable")
    health = registry.get("source_health", {}) if valid_registry else {}
    if not isinstance(health, dict):
        health = {}
    all_cases = {d.get("id"): d for d in dossiers if isinstance(d, dict) and isinstance(d.get("id"), str)}
    cases = {cid: {"status": status,
                   "screened_at": stamp if status == "screened" else None,
                   "new_matching_records": 0, "possible_support": 0,
                   "possible_counter": 0, "context": 0, "requires_interpretation": 0,
                   "unavailable_source_matches": 0, "candidates": [],
                   "history_window_hours": HISTORY_HOURS,
                   "historical_case_roots": 0, "historical_sources": [],
                   "historical_sources_truncated": False}
             for cid in all_cases}
    seen = {cid: set() for cid in all_cases}
    recent_rows = []
    if status == "screened":
        for row in records:
            if not isinstance(row, dict):
                continue
            first = _parse_time(row.get("first_observed_at"))
            if (first is None or first > now or
                    now - first > dt.timedelta(hours=lookback_hours) or
                    row.get("registry_novelty") == "initial_provider_baseline"):
                continue
            url = _safe_url(row.get("source_url"))
            if url:
                recent_rows.append((first, row, url))
    # A durable archive may be ordered oldest-first. Cap *after* selecting
    # new records, newest first; otherwise recent evidence can be starved.
    recent_rows.sort(key=lambda item: item[0], reverse=True)
    limited = len(recent_rows) > MAX_RECORDS
    recent = len(recent_rows)
    for first, row, url in recent_rows[:MAX_RECORDS]:
        for cid, result in cases.items():
            basis = _match_case(cid, row)
            if not basis:
                continue
            # Duplicate updates from the same information root count only once.
            root = _excerpt(row.get("information_root"), 230) or url
            identity = (str(row.get("collection_mode") or ""), root)
            if identity in seen[cid]:
                continue
            seen[cid].add(identity)
            mode = row.get("collection_mode")
            provider_status = health.get(mode, {}).get("status") if isinstance(health.get(mode), dict) else None
            if provider_status not in ("current", "current_partial"):
                result["unavailable_source_matches"] += 1
                continue
            direction, reason = _directional_hint(row)
            result["new_matching_records"] += 1
            result[direction] += 1
            result["candidates"].append({
                "record_id": _excerpt(row.get("id"), 120),
                "title": _excerpt(row.get("title"), 240) or "Untitled source observation",
                "source_url": url, "provider": _excerpt(row.get("provider"), 120),
                "source_mode": _excerpt(mode, 80),
                "source_family": _excerpt(row.get("source_family"), 100),
                "first_observed_at": first.isoformat().replace("+00:00", "Z"),
                "match_basis": basis, "preliminary_direction": direction,
                "rationale": reason, "source_health": provider_status,
                "claim_level": _excerpt(row.get("claim_level"), 120),
                "analyst_approved": False, "warning_approved": False,
            })
    # An independent, rolling source-linked investigation history. The nine-
    # hour latest-ingest screen above must not make older relevant evidence
    # disappear from the interface. Intake reports have no live collector
    # health contract: label them explicitly, never treat as approved.
    history_rows = []
    if valid_registry:
        for row in records:
            if not isinstance(row, dict):
                continue
            first = _parse_time(row.get("first_observed_at"))
            url = _safe_url(row.get("source_url"))
            if (not first or first > now or
                    now - first > dt.timedelta(hours=HISTORY_HOURS) or not url):
                continue
            if row.get("registry_novelty") == "initial_provider_baseline":
                continue
            history_rows.append((first, row, url))
    history_rows.sort(key=lambda item: item[0], reverse=True)
    history_seen = {cid: set() for cid in all_cases}
    for first, row, url in history_rows[:MAX_RECORDS]:
        for cid, result in cases.items():
            basis = _match_case(cid, row)
            if not basis:
                continue
            mode = row.get("collection_mode")
            root = _excerpt(row.get("information_root"), 230) or url
            key = (_excerpt(mode, 80), root)
            if key in history_seen[cid]:
                continue
            history_seen[cid].add(key)
            result["historical_case_roots"] += 1
            provider_status = health.get(mode, {}).get("status") if isinstance(health.get(mode), dict) else None
            if mode == "analyst":
                provenance = "public_analyst_intake_not_independently_verified"
                direction = "requires_interpretation"
                reason = "Source-linked public intake; no independent provider-health validation"
            elif provider_status not in ("current", "current_partial"):
                provenance = "current_provider_health_unavailable"
                direction = "requires_interpretation"
                reason = "Archived observation; provider health unavailable at this build"
            else:
                provenance = "source_collected_not_event_verified"
                direction, reason = _directional_hint(row)
            if len(result["historical_sources"]) < MAX_HISTORY_PER_CASE:
                result["historical_sources"].append({
                    "record_id": _excerpt(row.get("id"), 120),
                    "title": _excerpt(row.get("title"), 240) or "Untitled source record",
                    "source_url": url, "source_mode": _excerpt(mode, 80),
                    "provider": _excerpt(row.get("provider"), 120),
                    "first_observed_at": first.isoformat().replace("+00:00", "Z"),
                    "case_match_basis": basis, "provenance": provenance,
                    "preliminary_direction": direction, "rationale": reason,
                    "analyst_approved": False, "warning_approved": False,
                })
    for result in cases.values():
        result["historical_sources_truncated"] = (
            result["historical_case_roots"] > MAX_HISTORY_PER_CASE)
    for result in cases.values():
        result["candidates"].sort(key=lambda x: (x["first_observed_at"], x["record_id"]), reverse=True)
        result["candidates_truncated"] = len(result["candidates"]) > MAX_MATCHES_PER_CASE
        result["candidates"] = result["candidates"][:MAX_MATCHES_PER_CASE]
    return {
        "schema": SCHEMA, "status": status,
        "screened_at": stamp if status == "screened" else None,
        "source_snapshot_at": registry.get("generated_at") if valid_registry else None,
        "window_hours": lookback_hours, "new_source_records_in_window": recent,
        "durable_archive_used": valid_archive, "source_records_truncated": limited,
        "history_window_hours": HISTORY_HOURS,
        "history_records_truncated": len(history_rows) > MAX_RECORDS,
        "method": "distinctive_case_cue_plus_source_title_signposts_without_attribution",
        "analyst_direction_overridden": False, "operational_warnings_issued": 0,
        "cases": cases,
        "limitations": [
            "New means first ingested within the lookback window; it is not the event occurrence time.",
            "Seven-day case-linked historical observations remain visible but are never automatically approved.",
            "Lexical signposts nominate observations for investigation and can contain false positives.",
            "Reported geography is not incident geolocation. A case cue is not corroboration.",
            "Unavailable, partial, omitted or old source records are never considered contradicting evidence.",
            "No automated finding changes the human-reviewed ordinal balance, case severity or warning status.",
        ],
    }
