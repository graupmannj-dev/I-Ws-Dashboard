"""CAIRN hypothesis-centered analyst evidence: explicit links, review-gated direction.

A topical or geographic association never creates directional evidence.
Evidence may be associated with several hypotheses. Signed evidence balances
are *ordinal review summaries*, never calibrated likelihoods or attack risk.
"""
from __future__ import annotations

from collections import defaultdict
import datetime as dt
import hashlib
from urllib.parse import urlsplit

SCHEMA = "cairn.hypothesis-evidence.v1"
REVIEW_SCHEMA = "cairn.hypothesis-reviews.v1"
DIRECTIONS = {"supports", "contradicts", "context"}
MAX_HYPOTHESES = 40
MAX_FAMILIES = 150
MAX_ALTERNATIVES = 3


def clean(value, cap=240):
    return value.strip()[:cap] if isinstance(value, str) else ""


def safe_url(value):
    if not isinstance(value, str) or len(value) > 1800:
        return None
    try:
        x = urlsplit(value)
        return value if x.scheme == "https" and x.hostname and not x.username and not x.password else None
    except ValueError:
        return None


def iso(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def signal_key(hypothesis_id, root):
    return "dossier:" + hashlib.sha256((hypothesis_id + "\x1f" + root).encode()).hexdigest()[:24]


def reviewed_annotations(config):
    """Validate optional reviewer annotations; reject incompatible score formats."""
    if not config:
        return {}, {}
    if not isinstance(config, dict) or config.get("schema") != REVIEW_SCHEMA:
        raise ValueError("Hypothesis-review contract must be versioned")
    results, alternatives = {}, {}
    reviews = config.get("reviews", [])
    if not isinstance(reviews, list) or len(reviews) > 1000:
        raise ValueError("Invalid hypothesis review record list")
    for row in reviews:
        if not isinstance(row, dict):
            raise ValueError("Review must be a dictionary")
        hid, key = clean(row.get("hypothesis_id"), 100), clean(row.get("evidence_key"), 100)
        direction, reason = row.get("direction"), clean(row.get("rationale"), 600)
        strength, stamp = row.get("strength"), iso(row.get("reviewed_at"))
        if not hid or not key or direction not in DIRECTIONS or not reason or not stamp:
            raise ValueError("Incomplete or invalid directional review")
        if type(strength) is not int or strength not in (1, 2, 3):
            raise ValueError("Review strength must be ordinal 1-3")
        dep = clean(row.get("dependency_group"), 120) or key
        slot = (hid, key)
        if slot in results:
            raise ValueError("Duplicate directional review")
        results[slot] = {
            "direction": direction, "strength": strength, "rationale": reason,
            "reviewed_at": stamp, "dependency_group": dep,
            "evidence_model": "analyst_ordinal_review_not_calibrated_likelihood",
        }
    extras = config.get("alternative_hypotheses", {})
    if not isinstance(extras, dict):
        raise ValueError("Alternative hypothesis definitions must be keyed by case ID")
    for hid, items in extras.items():
        if not isinstance(hid, str) or not isinstance(items, list):
            raise ValueError("Alternative hypotheses must be text lists")
        if len(items) > MAX_ALTERNATIVES:
            raise ValueError("Maximum three alternatives per hypothesis")
        alternatives[hid] = [clean(i, 300) for i in items if clean(i, 300)]
    return results, alternatives


def alternative_ach_annotations(config):
    """Independent ordinal annotations for explicit competing alternatives.

    A signed judgment about the primary claim is NOT transferable to an
    alternative; a source may be consistent with multiple hypotheses.
    """
    if not config:
        return {}
    if config.get("schema") != REVIEW_SCHEMA:
        raise ValueError("Invalid ACH review contract")
    rows = config.get("ach_reviews", [])
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError("Invalid ACH review list")
    results = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("ACH review must be a dictionary")
        hid = clean(row.get("hypothesis_id"), 100)
        key = clean(row.get("evidence_key"), 100)
        index = row.get("alternative_index")
        direction = row.get("direction")
        strength = row.get("strength")
        reason = clean(row.get("rationale"), 600)
        stamp = iso(row.get("reviewed_at"))
        if not hid or not key or type(index) is not int or index not in (1, 2, 3):
            raise ValueError("ACH review needs valid case, evidence and competing index")
        if direction not in DIRECTIONS or type(strength) is not int or strength not in (1, 2, 3) or not reason or not stamp:
            raise ValueError("Invalid alternative ACH direction, strength, rationale or time")
        slot = (hid, key, index)
        if slot in results:
            raise ValueError("Duplicate alternative ACH review")
        results[slot] = {"direction": direction, "strength": strength,
                         "rationale": reason, "reviewed_at": stamp,
                         "dependency_group": clean(row.get("dependency_group"), 120) or key,
                         "evidence_model": "reviewed_ordinal_not_probability"}
    return results


def _health_for(family, health):
    modes = sorted({clean(x.get("collection_mode"), 60)
                    for x in family.get("sources", []) if isinstance(x, dict)
                    and clean(x.get("collection_mode"), 60)})
    if family.get("origin") == "curated_dossier":
        return {"status": "historical_reference_not_live",
                "checked_at": None, "modes": [], "coverage": "manual dated case dossier"}
    if not modes:
        return {"status": "unknown", "checked_at": None, "modes": [],
                "coverage": "no provider status linked"}
    observed = [health.get(mode, {}) for mode in modes]
    statuses = [x.get("status") for x in observed]
    # All contributing source mechanisms must be current before display says current.
    if not statuses or any(st not in ("current", "current_partial") for st in statuses):
        status = "stale_or_unavailable"
    elif any(st == "current_partial" for st in statuses):
        status = "current_partial"
    else:
        status = "current"
    clocks = [x.get("checked_at") for x in observed if iso(x.get("checked_at"))]
    return {"status": status, "checked_at": max(clocks) if clocks else None,
            "modes": modes, "coverage": "provider-specific sampling; not global completeness"}


def _dossier_families(dossier):
    hid = clean(dossier.get("id"), 100)
    grouped = defaultdict(list)
    for index, signal in enumerate((dossier.get("signals") or [])[:100]):
        if not isinstance(signal, dict):
            continue
        link = safe_url(signal.get("url"))
        if not link:
            continue
        root = clean(signal.get("root"), 140) or link
        grouped[root].append((index, signal))
    families = []
    for root, members in grouped.items():
        key = signal_key(hid, root)
        sources = []
        for _, signal in members:
            sources.append({
                "title": clean(signal.get("title"), 240),
                "source_url": safe_url(signal.get("url")),
                "provider": clean(signal.get("source"), 140),
                "observed_at": clean(signal.get("date"), 30),
                "assessment": clean(signal.get("assessment"), 160),
                "category": clean(signal.get("category"), 70),
                "details": clean(signal.get("details"), 500),
            })
        families.append({
            "evidence_key": key, "title": sources[0]["title"] or root,
            "kind": "dated_curated_source_root",
            "origin": "curated_dossier", "source_mechanism": sources[0]["category"] or "dossier reporting",
            "source_root_count": 1, "source_independence_established": False,
            "observation_verified_as_hypothesis": False,
            "sources": sources[:20], "source_count": len(sources),
        })
    return families


def _dynamic_families(hid, dynamic):
    candidates = dynamic.get("families", []) if isinstance(dynamic, dict) else []
    out = []
    for family in candidates[:800]:
        if not isinstance(family, dict) or hid not in (family.get("case_hints") or []):
            continue
        ident = clean(family.get("id"), 100)
        if not ident:
            continue
        sources = []
        for row in (family.get("sources") or [])[:20]:
            if not isinstance(row, dict) or not safe_url(row.get("source_url")):
                continue
            sources.append({
                "title": clean(row.get("title"), 240),
                "source_url": safe_url(row.get("source_url")),
                "provider": clean(row.get("provider"), 140),
                "observed_at": clean(row.get("first_observed_at"), 42),
                "assessment": "unreviewed_observation",
                "category": clean(row.get("source_family"), 90),
                "collection_mode": clean(row.get("collection_mode"), 60),
                "source_dependency_class": clean(row.get("source_dependency_class"), 100),
            })
        out.append({
            "evidence_key": ident, "title": clean(family.get("title"), 240),
            "kind": clean(family.get("kind"), 80),
            "origin": "dynamic_family_case_hint_not_verified_event",
            "source_mechanism": ", ".join(family.get("source_families", [])[:4]),
            "source_root_count": family.get("information_root_count"),
            "source_independence_established": family.get("source_independence_established") is True,
            "observation_verified_as_hypothesis": False,
            "sources": sources, "source_count": len(sources),
        })
    return out


def _balance(families):
    """One maximum ordinal strength per declared dependent root and direction.

    Unknown independence is NOT treated as probabilistically independent.
    Mixed direction in the same declared dependency group is excluded.
    """
    dep = defaultdict(lambda: {"supports": [], "contradicts": []})
    for family in families:
        review = family.get("review")
        if not review or review["direction"] == "context":
            continue
        dep[review["dependency_group"]][review["direction"]].append(review["strength"])
    supports = contradicts = conflicts = 0
    for group in dep.values():
        if group["supports"] and group["contradicts"]:
            conflicts += 1
            continue
        if group["supports"]:
            supports += max(group["supports"])
        if group["contradicts"]:
            contradicts += max(group["contradicts"])
    total = supports + contradicts
    value = round((supports - contradicts) / total, 3) if total else None
    direction = ("not_assessed" if value is None else
                 "mixed" if abs(value) < 0.2 else
                 "leans_support" if value > 0 else "leans_contradict")
    return {"direction": direction, "signed_ordinal_balance": value,
            "support_strength": supports, "contradict_strength": contradicts,
            "conflicting_dependency_groups_excluded": conflicts,
            "reviewed_directional_family_count": sum(bool(f.get("review")) and
                f["review"]["direction"] in ("supports","contradicts") for f in families),
            "calibrated_probability": None,
            "interpretation": "Reviewer-tagged ordinal evidence only; not a probability or live threat score"}


def build(dossiers, dynamic=None, source_health=None, reviews=None, generated_at=None):
    """Build a bounded non-probabilistic hypothesis index from reviewed case IDs.

    A source family can appear under multiple explicit case hints. No text
    similarity, proximity, source counts or collector failure assigns a sign.
    """
    if not isinstance(dossiers, list):
        raise ValueError("Case dossiers must be a list")
    annotations, extras = reviewed_annotations(reviews)
    alternative_annotations = alternative_ach_annotations(reviews)
    health = source_health if isinstance(source_health, dict) else {}
    cases, used_keys = [], set()
    for dossier in dossiers[:MAX_HYPOTHESES]:
        if not isinstance(dossier, dict):
            continue
        hid = clean(dossier.get("id"), 100)
        if not hid or hid in used_keys:
            raise ValueError("Missing or duplicate hypothesis case ID")
        used_keys.add(hid)
        linked = _dossier_families(dossier) + _dynamic_families(hid, dynamic)
        deduplicated = {}
        for family in linked:
            deduplicated.setdefault(family["evidence_key"], family)
        linked = list(deduplicated.values())[:MAX_FAMILIES]
        for family in linked:
            family["health"] = _health_for(family, health)
            family["review"] = annotations.get((hid, family["evidence_key"]))
            family["direction"] = (
                family["review"]["direction"] if family["review"] else "not_assessed")
        alternatives = []
        if clean(dossier.get("alternatives"), 400):
            alternatives.append(clean(dossier["alternatives"], 400))
        for item in extras.get(hid, []):
            if item not in alternatives and len(alternatives) < MAX_ALTERNATIVES:
                alternatives.append(item)
        for family in linked:
            family["ach_reviews"] = {str(index): alternative_annotations[(hid, family["evidence_key"], index)]
                for index in (1, 2, 3) if (hid, family["evidence_key"], index) in alternative_annotations}
        cases.append({
            "id": hid, "title": clean(dossier.get("name"), 180),
            "hypothesis": clean(dossier.get("scenario"), 320),
            "standing_state": clean(dossier.get("state"), 90),
            "dossier_asof": clean(dossier.get("asof"), 30),
            "overview": clean(dossier.get("analysis"), 700),
            "next_discriminators": clean(dossier.get("next"), 450),
            "alternatives": alternatives[:MAX_ALTERNATIVES],
            "families": linked, "family_count": len(linked),
            "reviewed_family_count": sum(f.get("review") is not None for f in linked),
            "balance": _balance(linked),
            "evidence_is_case_associated_not_event_verified": True,
        })
    referenced = {(c["id"], f["evidence_key"]) for c in cases for f in c["families"]}
    stale_ach_reviews = sorted(k for k in alternative_annotations
        if (k[0], k[1]) not in referenced or
        k[2] > len(next((c["alternatives"] for c in cases if c["id"] == k[0]), [])))
    if stale_ach_reviews:
        raise ValueError("Alternative ACH review targets missing hypothesis or evidence: " + str(stale_ach_reviews[:3]))
    stale_reviews = sorted(k for k in annotations if k not in referenced)
    if stale_reviews:
        raise ValueError("Review refers to missing hypothesis/evidence key: " + str(stale_reviews[:3]))
    crosslinks = defaultdict(list)
    for case in cases:
        for family in case["families"]:
            crosslinks[family["evidence_key"]].append(case["id"])
    for case in cases:
        for family in case["families"]:
            family["linked_hypotheses"] = sorted(crosslinks[family["evidence_key"]])
    return {"schema": SCHEMA, "generated_at": generated_at,
            "status": "review_gated_hypothesis_workspace",
            "warning_probability_estimated": False,
            "hypotheses": cases, "hypothesis_count": len(cases),
            "reviewed_hypotheses": sum(c["reviewed_family_count"] > 0 for c in cases),
            "directional_review_required": True,
            "method": "explicit_case_hint_links_and_reviewed_ordinal_evidence_only",
            "limitations": [
                "Case dossiers are dated historical references, not current verified assessments.",
                "Case-hint association and shared source roots do not establish corroboration.",
                "Ordinal direction is assigned only by timestamped analyst review.",
                "Collection failures, missingness and contextual anomalies never imply zero risk.",
                "A signed ordinal balance is not a conflict probability or calibrated likelihood.",
                "Evidence can relate to more than one hypothesis without being duplicated as independent confirmation.",
            ]}
