"""CAIRN hypothesis discriminator workbench: explicit, reproducible *nominations*.

Primary H (new escalation) is compared to case-specific alternative
explanations. Sources are associated by an explicit case hint or a distinctive
case cue, then checked for observable signpost phrases. These are hypotheses
about the reports, NOT validated events or military decisions. No probability,
warning, confidence, posterior or signed reviewer weight is inferred.

All output is reproducible from the versioned discriminator registry and dated
archival inputs. Provider-wide historical baselines are never mislabeled as
case-specific baseline measurements.
"""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlsplit

try:
    from .hypothesis_auto_review import _match_case, _parse_time, _safe_url
except ImportError:  # Direct script invocation of dashboard/build_atlas.py
    from hypothesis_auto_review import _match_case, _parse_time, _safe_url

SCHEMA = "cairn.competing-hypothesis-screen.v1"
CONFIG_SCHEMA = "cairn.hypothesis-discriminators.v1"
ARCHIVE_SCHEMA = "aiba.family-archive.v1"
REGISTRY_SCHEMA = "aiba.behavioral-observations.v1"
BASELINE_SCHEMA = "aiba.behavioral-provider-baseline.v1"
MAX_SOURCE_INPUT = 20000
MAX_SOURCE_PER_RULE = 5
MAX_SOURCE_PER_CASE = 14
QUOTED_CLAIM = re.compile(
    r"\b(?:alleg(?:ed|es|ation)|claim(?:s|ed)?|report(?:s|ed|edly)?|"
    r"suspect(?:s|ed)?|unconfirm(?:ed)?|den(?:y|ied|ies)|disput(?:ed|es)|"
    r"rumou?r(?:s|ed)?)\b", re.I)
NEGATED = re.compile(r"\b(?:no|not|without|false|hoax|den(?:ied|ies|y))\b", re.I)
CONFOUNDERS = re.compile(
    r"\b(?:routine|scheduled|planned|exercis(?:e|es)|drill(?:s)?|"
    r"training|weather|storm|cyclone|typhoon|earthquake|flood(?:ing)?|"
    r"wildfire|volcan(?:o|ic))\b", re.I)
HAZARD_FAMILIES = {"environmental_context"}
HAZARD_MODES = {"usgs", "eonet", "nws", "swpc", "bmkg_quake",
                "bmkg_nowcast", "inmet_br", "imd_in", "saws_za"}


def _when(value):
    return _parse_time(value)


def _utc(value):
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value, n=250):
    return str(value or "").strip()[:n]


def _scope(row):
    # Archives have normalized 'geography_label' rather than a nested
    # 'geography' object. The geographic association remains unverified.
    geo = row.get("geography_label")
    if not geo:
        obj = row.get("geography")
        geo = obj.get("label") if isinstance(obj, dict) else obj
    return _clean(geo, 160)


def _record_key(row, url):
    """Document identity, not a claim that publishers are independent."""
    u = urlsplit(url)
    mode = _clean(row.get("collection_mode"), 80)
    concrete_document = (u.path not in ("", "/") and not
                         u.path.lower().endswith((".xml", ".rss", ".json")))
    # A Niord hash fragment contains the actual notice ID.
    if "/message/" in u.fragment or "/message/" in u.path:
        concrete_document = True
    if concrete_document:
        return "url:" + url.rstrip("/")
    return "root:" + mode + ":" + _clean(row.get("information_root"), 230)


def _sources(registry, archive, now, window_days):
    archive_ok = (isinstance(archive, dict) and archive.get("schema") == ARCHIVE_SCHEMA
                  and isinstance(archive.get("records"), list))
    registry_ok = (isinstance(registry, dict) and registry.get("schema") == REGISTRY_SCHEMA
                   and isinstance(registry.get("records"), list))
    records = archive["records"] if archive_ok else registry["records"] if registry_ok else []
    end = now - dt.timedelta(days=window_days)
    # Prefer the newest source version, but count each independent document
    # ID only once within each hypothesis and discriminator.
    items = []
    for row in records:
        if not isinstance(row, dict):
            continue
        first = _when(row.get("first_observed_at"))
        url = _safe_url(row.get("source_url"))
        if (first is None or first > now or first < end or not url
                or row.get("registry_novelty") == "initial_provider_baseline"):
            continue
        items.append((first, row, url, _record_key(row, url)))
    items.sort(key=lambda item: (item[0], item[3]), reverse=True)
    return items[:MAX_SOURCE_INPUT], {
        "archive_used": archive_ok, "registry_used": registry_ok,
        "source_records_in_window": len(items),
        "candidate_input_truncated": len(items) > MAX_SOURCE_INPUT,
        "source_lookback_days": window_days,
    }


def _status(row, provider_health):
    mode = _clean(row.get("collection_mode"), 80)
    if mode == "analyst" or _clean(row.get("origin")) == "analyst":
        return "unverified_source_submission"
    health = provider_health.get(mode) if isinstance(provider_health, dict) else None
    value = health.get("status") if isinstance(health, dict) else None
    return ("current_provider_not_event_verified" if value in ("current", "current_partial")
            else "provider_current_health_unavailable")


def _source_metadata(first, row, url, key, association, kind, reason):
    return {
        "record_id": _clean(row.get("id"), 128),
        "source_document_key": key[:320],
        "title": _clean(row.get("title"), 240),
        "source_url": url,
        "source_mode": _clean(row.get("collection_mode"), 80),
        "source_family": _clean(row.get("source_family"), 100),
        "first_observed_at": _utc(first),
        "case_association": association,
        "candidate_class": kind,
        "reason": reason,
        "event_verification": "not_verified",
        "independent_observation_confirmed": False,
        "analyst_approved": False,
    }


def _baseline(mode, provider_baselines, provider_health):
    """Provider-wide comparability diagnostic, NEVER a geographic comparator."""
    if (not isinstance(provider_baselines, dict)
            or provider_baselines.get("schema") != BASELINE_SCHEMA):
        return {"mode": mode, "status": "provider_history_unavailable",
                "comparable_days": None, "case_specific": False}
    b = provider_baselines.get("sources", {}).get(mode, {})
    h = provider_health.get(mode, {}) if isinstance(provider_health, dict) else {}
    days = b.get("comparable_provider_snapshot_days")
    minimum = provider_baselines.get("minimum_comparable_days", 14)
    ready = (isinstance(days, int) and days >= minimum
             and b.get("status") not in ("insufficient_comparable_source_days", None)
             and b.get("median_daily_first_seen_records") is not None
             and h.get("status") in ("current", "current_partial"))
    return {
        "mode": mode, "status": "provider_descriptive_baseline_available" if ready
        else "baseline_inadequate_or_source_unavailable",
        "comparable_days": days if isinstance(days, int) else None,
        "minimum_days": minimum,
        "provider_scope": _clean(h.get("source_scope"), 240) or "source scope not established",
        "current_source_status": _clean(h.get("status"), 80) or "unknown",
        "median_daily_first_seen_records": b.get("median_daily_first_seen_records") if ready else None,
        "case_specific": False,
        "baseline_direction_inferred": False,
    }


def _check_config(config):
    if not isinstance(config, dict) or config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("Incorrect discriminator contract")
    templates = config.get("templates")
    cases = config.get("cases")
    if not isinstance(templates, dict) or not isinstance(cases, dict) or len(cases) < 1:
        raise ValueError("Discriminator templates and cases required")
    for key, spec in templates.items():
        if (not isinstance(spec, dict) or spec.get("role") not in
                ("escalation_candidate", "alternative_candidate", "context_candidate")):
            raise ValueError("Invalid discriminator role for " + key)
        re.compile(spec["pattern"])
    for cid, c in cases.items():
        if not isinstance(c, dict):
            raise ValueError("Invalid case " + cid)
        ids = c.get("escalation", []) + c.get("alternatives", [])
        if not ids or any(name not in templates for name in ids):
            raise ValueError("Unrecognized discriminator in " + cid)
        if (any(templates[name]["role"] != "escalation_candidate"
                for name in c.get("escalation", [])) or
                any(templates[name]["role"] == "escalation_candidate"
                    for name in c.get("alternatives", []))):
            raise ValueError("Discriminator placed on wrong competing theory")
    return templates, cases


def assess(dossiers, registry, archive, gdelt_trends, provider_baselines, config, *, at=None):
    """Return case-by-case machine evidence comparisons without updating reviews."""
    templates, case_specs = _check_config(config)
    now = _when(at) if isinstance(at, str) else at
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Assessment clock must have UTC offset")
    now = now.astimezone(dt.timezone.utc)
    window_days = config.get("window_days", 7)
    if not isinstance(window_days, int) or not 1 <= window_days <= 28:
        raise ValueError("Invalid discriminator window")
    rows, intake = _sources(registry, archive, now, window_days)
    provider_health = registry.get("source_health", {}) if isinstance(registry, dict) else {}
    if not isinstance(provider_health, dict):
        provider_health = {}
    gdelt_ok = (isinstance(gdelt_trends, dict)
                and gdelt_trends.get("schema") == "cairn.gdelt-case-trends.v1"
                and isinstance(gdelt_trends.get("cases"), dict))
    dossier_map = {r.get("id"): r for r in dossiers if isinstance(r, dict)}
    case_outputs = {}
    for cid, spec in case_specs.items():
        rules = list(dict.fromkeys(spec["escalation"] + spec["alternatives"]))
        per_rule = {rule: {"id": rule, "label": _clean(templates[rule].get("label")),
                           "role": templates[rule]["role"],
                           "discriminator": _clean(templates[rule].get("discriminator"), 450),
                           "candidate_count": 0, "ambiguous_count": 0,
                           "context_count": 0, "sources": [], "status": "no_candidate_observed"}
                    for rule in rules}
        seen_by_rule = {rule: set() for rule in rules}
        case_seen = set()
        case_record_count = 0
        observed_modes = set()
        evidence_modes = {"escalation_candidate": set(), "alternative_candidate": set()}
        for first, row, url, key in rows:
            # Reshape archive geographical label as expected by case linker.
            association = _match_case(cid, {
                "title": row.get("title"),
                "case_hint": row.get("case_hint"),
                "geography": _scope(row),
            })
            if not association:
                continue
            if key not in case_seen:
                case_seen.add(key)
                case_record_count += 1
            title = _clean(row.get("title"), 240)
            if not title:
                continue
            mode = _clean(row.get("collection_mode"), 80)
            kind = _status(row, provider_health)
            for rule in rules:
                cfg = templates[rule]
                if key in seen_by_rule[rule] or not re.search(cfg["pattern"], title, re.I):
                    continue
                seen_by_rule[rule].add(key)
                role = cfg["role"]
                hazard = (row.get("source_family") in HAZARD_FAMILIES or
                          mode in HAZARD_MODES)
                qualifies = bool(QUOTED_CLAIM.search(title) or NEGATED.search(title)
                                 or (role != "context_candidate" and
                                     kind != "current_provider_not_event_verified")
                                 or (role == "escalation_candidate" and
                                     (CONFOUNDERS.search(title) or hazard)))
                # A media headline remains an unverified source claim, even
                # when it is specific. Qualifiers downgrade interpretability.
                if qualifies:
                    outcome = "ambiguous_count"
                    reason = ("Provisional or unverified source provenance, or an attributed, negated, "
                              "routine or hazard qualifier; original source and alternatives require review")
                elif role == "context_candidate" or hazard:
                    outcome = "context_count"
                    reason = "Context only: no military attribution or causal link established"
                else:
                    outcome = "candidate_count"
                    reason = "Source-title signpost requires source reading and competing-explanation checks"
                result = per_rule[rule]
                result[outcome] += 1
                if len(result["sources"]) < MAX_SOURCE_PER_RULE:
                    details = _source_metadata(first, row, url, key, association, kind, reason)
                    details["screening_bucket"] = outcome.removesuffix("_count")
                    result["sources"].append(details)
                if outcome == "candidate_count" and role in evidence_modes:
                    evidence_modes[role].add(mode or "unknown")
                observed_modes.add(mode or "unknown")
        for rule in per_rule.values():
            rule["status"] = ("candidate_observed" if rule["candidate_count"] else
                              "ambiguous_only" if rule["ambiguous_count"] else
                              "context_only" if rule["context_count"] else
                              "no_candidate_observed_not_negative")
        esc = sum(per_rule[r]["candidate_count"] for r in spec["escalation"])
        alt = sum(per_rule[r]["candidate_count"] for r in spec["alternatives"]
                  if templates[r]["role"] == "alternative_candidate")
        ambig = sum(per_rule[r]["ambiguous_count"] for r in rules)
        interpretation = ("competing_candidates_present" if esc and alt
                          else "escalation_signposts_nominated" if esc
                          else "alternative_signposts_nominated" if alt
                          else "ambiguous_or_context_only" if ambig or case_record_count
                          else "no_matching_case_records_in_window")
        g = gdelt_trends.get("cases", {}).get(cid, {}) if gdelt_ok else {}
        gstatus = g.get("status") if isinstance(g, dict) else None
        coverage = [_baseline(mode, provider_baselines, provider_health)
                    for mode in spec.get("priority_modes", [])]
        summary = {
            "competing_pattern": interpretation,
            "escalation_signpost_nominations": esc,
            "alternative_signpost_nominations": alt,
            "ambiguous_signpost_nominations": ambig,
            "source_documents_case_associated": case_record_count,
            "nominating_collection_modes": sorted(observed_modes),
            "modes_with_escalation_signposts": sorted(evidence_modes["escalation_candidate"]),
            "modes_with_alternative_signposts": sorted(evidence_modes["alternative_candidate"]),
            "source_independence_established": False,
            "source_text_fully_read": False,
            "direction_of_armed_conflict_hypothesis": "not_estimated",
            "warning_promoted": False,
        }
        case_outputs[cid] = {
            "status": "screened" if intake["archive_used"] or intake["registry_used"]
                      else "source_evidence_unavailable",
            "id": cid, "title": _clean(spec.get("name")),
            "hypothesis": _clean(dossier_map.get(cid, {}).get("scenario"), 450),
            "alternative_explanation": _clean(
                dossier_map.get(cid, {}).get("alternatives"), 650),
            "evaluated_at": _utc(now),
            "summary": summary,
            "discriminators": [per_rule[rule] for rule in rules],
            "source_baseline_readiness": coverage,
            "gdelt_context": {
                "status": gstatus or "unavailable",
                "media_coded_share_trend": g.get("trend") if gstatus == "measured" else None,
                "media_share_ratio": g.get("media_share_ratio") if gstatus == "measured" else None,
                "baseline_days": gdelt_trends.get("baseline_days") if gdelt_ok else None,
                "recent_days": gdelt_trends.get("window_days") if gdelt_ok else None,
                "not_independent_evidence": True,
                "not_a_directional_military_assessment": True,
            },
            "assessment_limits": [
                "A matched keyword is a nomination for verification, not confirmation of an event or decision.",
                "Different collection modes may cite the same event or underlying source. Independence unverified.",
                "Provider-wide baselines cannot be transported to case-specific threat probability or rates.",
                "GDELT coded-coverage trends describe reporting, not verified intent or a likelihood of war.",
                "No matching observations or missing source coverage cannot count against a hypothesis.",
            ],
        }
    return {
        "schema": SCHEMA, "status": "screened" if (intake["archive_used"] or intake["registry_used"])
                  else "source_evidence_unavailable",
        "evaluated_at": _utc(now),
        "config_schema": CONFIG_SCHEMA,
        "hypothesis_count": len(case_outputs),
        **intake,
        "analyst_approved_directions": 0,
        "automated_warnings": 0,
        "probability_of_conflict": None,
        "cases": case_outputs,
    }
