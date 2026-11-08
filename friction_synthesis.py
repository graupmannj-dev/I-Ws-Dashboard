#!/usr/bin/env python3
"""Deterministic, source-traceable AIBA friction synthesis for a 10-minute read.

This is triage, not an LLM-produced intelligence assessment and not a
calibrated probability of conflict. Scores never modify watch severity.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from friction_pipeline import event_time, iso, read_json, utcnow, write_json

ROOT = Path(__file__).resolve().parent
FAMILIES = {"ioda": "internet_reachability", "nga": "maritime_restriction",
            "amsa": "maritime_restriction"}
MAX_HISTORY = 850  # >14 days of half-hour historical samples plus scheduling jitter
RECENT_HOURS = 36
BASELINE_DAYS = 14
MIN_BASELINE = 8
MIN_SPAN_HOURS = 24


def source_status(state, mode, at):
    health = read_json(Path(state) / "health" / f"friction_{mode}.json", {}) or {}
    checked = event_time(health.get("checked_at"))
    hours = round((at - checked).total_seconds() / 3600, 2) if checked else None
    ok = (health.get("status") in ("collected", "partial")
          and hours is not None and 0 <= hours <= 3)
    label = ("fresh" if ok else
             "unavailable" if health.get("status") == "unavailable" else
             "stale" if checked else "not_collected")
    return {"status": label, "collector_status": health.get("status", "not_collected"),
            "age_hours": hours, "checked_at": health.get("checked_at"),
            "observed_records": health.get("records"),
            "coverage": "partial" if health.get("status") == "partial" else
                        "complete" if health.get("status") == "collected" else "unknown",
            "error": health.get("error") if label == "unavailable" else None}


def historical(state, at):
    paths = sorted((Path(state) / "history" / "friction").glob("*.json"))[-MAX_HISTORY:]
    result = []
    for path in paths:
        item = read_json(path)
        when = event_time(item.get("collected_at")) if isinstance(item, dict) else None
        if not when or when > at or when < at - dt.timedelta(days=BASELINE_DAYS):
            continue
        if not isinstance(item.get("case_counts"), dict):
            continue
        result.append(item)
    return result


def robust_change(current, prior):
    """Conservative count anomaly, not an estimated risk probability."""
    if len(prior) < MIN_BASELINE:
        return {"status": "insufficient_baseline", "samples": len(prior),
                "current": current, "median": None, "robust_z": None}
    center = statistics.median(prior)
    mad = statistics.median(abs(x - center) for x in prior)
    # A flat historical series cannot imply infinite significance from +1.
    sigma = max(1.0, 1.4826 * mad)
    z = round((current - center) / sigma, 2)
    anomalous = current >= center + 4 * sigma and current >= center * 2 + 2
    return {"status": "unusual_count" if anomalous else "within_observed_range",
            "samples": len(prior), "current": current, "median": center,
            "robust_z": z, "threshold": round(center + 4 * sigma, 1)}


def baseline(state, history, case, family, at):
    sources = [mode for mode, name in FAMILIES.items() if name == family]
    now_health = (history[-1].get("health") or {}) if history else {}
    active_sources = {mode for mode in sources
                      if (now_health.get(mode) or {}).get("status") in ("collected", "partial")
                      and not (now_health.get(mode) or {}).get("truncated")}
    if not active_sources:
        return {"status": "insufficient_baseline", "samples": 0,
                "current": None, "median": None, "robust_z": None}
    pairs = []
    for snap in history[:-1]:
        moment = event_time(snap.get("collected_at"))
        old_health = snap.get("health") or {}
        old_sources = {mode for mode in sources
                       if (old_health.get(mode) or {}).get("status") in ("collected", "partial")
                       and not (old_health.get(mode) or {}).get("truncated")}
        if (not moment or not 0 < (at - moment).total_seconds() <= BASELINE_DAYS * 86400
                or old_sources != active_sources):
            continue
        val = (snap.get("case_counts") or {}).get(case, {}).get(family, 0)
        if isinstance(val, int) and not isinstance(val, bool):
            pairs.append((moment, val))
    # Compare neighboring UTC hours to control for any diurnal schedules.
    matched = [(time, count) for time, count in pairs
               if abs(((time.hour - at.hour + 12) % 24) - 12) <= 3]
    if (len(matched) >= MIN_BASELINE and
        (max(x[0] for x in matched) - min(x[0] for x in matched)).total_seconds() >= MIN_SPAN_HOURS * 3600):
        pairs = matched
    # Otherwise do not pretend that unmatched hours control for diurnal effects.
    else:
        return {"status": "insufficient_baseline", "samples": len(matched),
                "current": None, "median": None, "robust_z": None}
    current_snap = history[-1] if history else {}
    value = (current_snap.get("case_counts") or {}).get(case, {}).get(family, 0)
    return robust_change(value, [c for _, c in pairs])


def unique_recent(history, at):
    """Only records first observed after an established previous source sample."""
    seen, recent = set(), []
    for i, snap in enumerate(history):
        when = event_time(snap.get("collected_at"))
        if when is None or when < at - dt.timedelta(hours=RECENT_HOURS):
            continue
        for row in snap.get("new_records", []):
            if not isinstance(row, dict) or row.get("id") in seen:
                continue
            seen.add(row["id"])
            src = row.get("provider")
            if src not in FAMILIES:
                continue
            # The first observation of a source establishes its baseline,
            # regardless of how many apparent events appear on the first pull.
            prior = [v for v in history[:i]
                     if (v.get("health") or {}).get(src, {}).get("status") in ("collected", "partial")]
            if not prior or src is None:
                continue
            original = event_time(row.get("event_at"))
            if original and not dt.timedelta(0) <= at - original <= dt.timedelta(days=7):
                continue
            recent.append(row)
    return recent


def matched_legacy(state, case_id, at):
    brief = read_json(Path(state) / "latest" / "decision_briefs.json", {}) or {}
    produced = event_time(brief.get("generated_at"))
    if not produced or not dt.timedelta(0) <= at - produced <= dt.timedelta(hours=18):
        return []
    case = next((c for c in brief.get("cases", []) if c.get("id") == case_id), {})
    rows = []
    for rec in case.get("source_evidence", [])[:6]:
        if not isinstance(rec, dict):
            continue
        url = rec.get("source_url", "")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        rows.append({"title": str(rec.get("title", ""))[:250], "url": url,
                     "family": str(rec.get("source_family", "traditional_source"))[:60],
                     "observed_at": rec.get("observed_at"),
                     "note": "Existing decision brief context, not independently re-confirmed here."})
    return rows


def build(state, clock=utcnow, registry=ROOT / "data" / "decision_registry.json",
          curated=ROOT / "data" / "verified_hotspots.json", write=True):
    at = clock()
    state = Path(state)
    config = read_json(registry, {"cases": []})
    curated_cases = {x["id"]: x for x in (read_json(curated, []) or []) if isinstance(x, dict) and "id" in x}
    current = read_json(state / "latest" / "friction.json", {}) or {}
    history = historical(state, at)
    health = {mode: source_status(state, mode, at) for mode in FAMILIES}
    snap_time = event_time(current.get("collected_at"))
    current_fresh = bool(snap_time and dt.timedelta(0) <= at - snap_time <= dt.timedelta(hours=3))
    all_records = current.get("records", []) if current_fresh else []
    incoming = unique_recent(history, at)
    recent_by_case = defaultdict(list)
    for row in incoming:
        recent_by_case[row.get("case_id") or "unlocated"].append(row)
    active_by_case = defaultdict(list)
    for row in all_records:
        # An older source event can still be operationally active and must
        # not become "new" just because it was fetched today.
        if row.get("case_id"):
            active_by_case[row["case_id"]].append(row)
    cases = []
    for case_cfg in config.get("cases", []):
        cid = case_cfg.get("id")
        if not cid:
            continue
        standing = curated_cases.get(cid, {})
        new = recent_by_case[cid]
        ongoing = active_by_case[cid]
        by_root = {}
        for row in new:
            by_root.setdefault(row.get("root") or row["id"], row)
        new = list(by_root.values())[:16]
        distinct = sorted({r["family"] for r in new})
        overlaps = len(distinct) >= 2
        traditional = matched_legacy(state, cid, at)
        baselines = {family: baseline(state, history, cid, family, at)
                     for family in FAMILIES.values()}
        anomalous = [family for family, val in baselines.items()
                     if val["status"] == "unusual_count"]
        gap = [name for name, info in health.items()
               if info["status"] != "fresh" or info["coverage"] == "partial"]
        if overlaps:
            triage = "multi_stream_review"
            changed = "Distinct maritime and connectivity source families have newly reported observations."
        elif new:
            triage = "source_review"
            changed = "New source-specific structural-friction observation warrants contextual review."
        elif anomalous:
            triage = "baseline_review"
            changed = "Observed source counts differ from the matched-hour historical baseline."
        else:
            triage = "collection_gap" if len(gap) == len(FAMILIES) else "maintain"
            changed = "No qualifying new structural-friction change established from available observations."
        subject = " and ".join(distinct) if distinct else "current monitored feeds"
        so_what = (f"{len(new)} newly observed unique roots across {subject}. "
                   "Co-occurrence does not establish a common cause or an impending operation."
                   if new else
                   f"{len(ongoing)} current source records provide context; repeated pulls are not new alerts.")
        alternative = case_cfg.get("alternative") or standing.get("alternatives") or "Routine activity or reporting coverage shift."
        cases.append({
            "id": cid, "title": standing.get("name") or cid,
            "standing_state": standing.get("state") or "Standing watch",
            "triage": triage, "what_changed": changed, "so_what": so_what,
            "alternative": alternative, "next_signpost": case_cfg.get("next") or standing.get("next"),
            "new_sources": len(new), "new_families": distinct, "current_source_records": len(ongoing),
            "source_evidence": [{"id": r["id"], "title": r["title"],
                                 "family": r["family"], "kind": r["kind"],
                                 "url": r["source_url"], "event_at": r.get("event_at"),
                                 "first_seen_at": r.get("first_seen_at"),
                                 "root": r.get("root"), "assessment": r["review_level"]}
                                for r in new],
            "traditional_changes": traditional, "anomaly_baselines": baselines,
            "coverage_gaps": gap,
            "confidence": ("Review priority, not confidence in escalation. "
                           "No source-independence or causal attribution is assumed."),
            "warnings": [
                "Existing war severity is not evidence of a new phase.",
                "A national network disruption is not evidence of interstate military preparation.",
                "Concurrent restrictions and outages can share a public, routine, or accidental cause.",
            ],
        })
    rank = {"multi_stream_review": 0, "baseline_review": 1,
            "source_review": 2, "collection_gap": 3, "maintain": 4}
    cases.sort(key=lambda x: (rank[x["triage"]], x["title"]))
    review = [c for c in cases if c["triage"] in ("multi_stream_review", "baseline_review", "source_review")]
    unlocated = recent_by_case["unlocated"]
    out = {
        "schema_version": 1, "generated_at": iso(at),
        "fresh_snapshot": current_fresh, "latest_source_snapshot": current.get("collected_at"),
        "shadow_mode": True, "health": health,
        "executive_summary": (
            f"{len(review)} theaters have investigatory source anomalies in shadow mode; "
            f"{len(unlocated)} recent unlocated source leads. "
            "No automated change to standing threat categories."
            if review else
            "No qualifying novel structural-friction lead in the collected evidence. "
            "This is not an all-clear; verify coverage and established watch states."),
        "cases": cases,
        "unlocated_leads": [{"title": str(r.get("title", ""))[:250],
                            "family": r.get("family"), "event_at": r.get("event_at"),
                            "url": r.get("source_url")} for r in unlocated[:25]],
        "coverage_gaps": [mode for mode, h in health.items()
                          if h["status"] != "fresh" or h["coverage"] == "partial"],
        "alert_count": 0,  # No automatic threats or notifications from a shadow model.
        "uncalibrated_review_count": len(review),
        "limits": [
            "Data feeds are partial, not a global exhaustive sensor network.",
            "Collection timestamp does not establish source event or publication time.",
            "Anomalies and matched-hour count comparisons do not estimate war probability.",
            "IODA BGP-related measurements do not prove a BGP hijack or state cyberattack.",
            "NAVAREA restrictions, even if paired with an outage, do not prove a blockade.",
            "No false-alarm rate can be computed without labeled outcomes and non-event windows.",
        ],
    }
    if write:
        write_json(state / "latest" / "friction_briefs.json", out)
        # Compact immutable alert-decision trace for future walk-forward audits.
        trace = {"asof": iso(at), "shadow_mode": True,
                 "review_case_ids": [c["id"] for c in review],
                 "triage": {c["id"]: c["triage"] for c in cases},
                 "sources_available": {k: v["status"] for k, v in health.items()},
                 "outcomes_labeled": False}
        write_json(state / "history" / "friction_triage" /
                   (at.strftime("%Y%m%dT%H%M%SZ") + ".json"), trace)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True, type=Path)
    args = p.parse_args()
    output = build(args.state)
    print(json.dumps({"generated_at": output["generated_at"],
                      "executive_summary": output["executive_summary"],
                      "coverage_gaps": output["coverage_gaps"],
                      "case_count": len(output["cases"])}, indent=2))


if __name__ == "__main__":
    main()
