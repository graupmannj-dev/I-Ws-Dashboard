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



def executive_materiality(case_id, question, new, overlaps, anomalous, baselines, reviews, at):
    """Screen significance, not mere novelty, and retain uncorroborated early signals."""
    comp = []
    for family, v in baselines.items():
        if v["status"] == "unusual_count":
            comp.append(f"{family}: current {v['current']}, 14-day matched-hour median "
                        f"{v['median']}, {v['samples']} valid samples, screening "
                        f"threshold {v['threshold']}, robust z {v['robust_z']}.")
        elif v["status"] == "insufficient_baseline":
            comp.append(f"{family}: insufficient matched-hour baseline "
                        f"({v.get('samples', 0)} samples); rarity cannot be quantified.")
    context = " ".join(comp) or "No statistically characterized source anomaly."
    for r in reviews:
        if not isinstance(r, dict) or r.get("status") != "approved" or r.get("case_id") != case_id:
            continue
        when = event_time(r.get("reviewed_at"))
        if not when or not dt.timedelta(0) <= at - when <= dt.timedelta(days=7):
            continue
        if not any(e.get("root") == r.get("root") and
                   e.get("source_url") == r.get("source_url") for e in new):
            continue
        fields = ("materiality_basis", "why_it_matters", "baseline_comparison",
                  "alternative_evidence", "next_signpost")
        if not all(isinstance(r.get(k), str) and len(r[k].strip()) >= 25 for k in fields):
            continue
        return {"executive_eligible": True, "publication_basis": "reviewed_single_root",
                "baseline_context": r["baseline_comparison"],
                "so_what": r["why_it_matters"],
                "materiality_rationale": r["materiality_basis"],
                "counter_evidence": r["alternative_evidence"],
                "next_signpost_override": r["next_signpost"]}
    if anomalous:
        relevance = ("Abnormal network disruptions may impede local communications "
                     "and independent reporting; they do not imply state involvement."
                     if "internet_reachability" in anomalous else
                     "Above-baseline navigational restrictions may constrain "
                     "commercial movement or indicate unusual maritime activity, "
                     "but exercises are a common alternative.")
        return {"executive_eligible": True, "publication_basis": "matched_hour_anomaly",
                "baseline_context": context, "so_what": relevance+" Case: "+question,
                "materiality_rationale": "Observed count exceeds an explicit short-window screening threshold.",
                "counter_evidence": "Count deviations alone provide no causal attribution.",
                "next_signpost_override": None}
    if overlaps:
        return {"executive_eligible": True, "publication_basis": "dated_multi_family_overlap",
                "baseline_context": context,
                "so_what": ("Six-hour overlap of different source families may indicate "
                            "operational friction; unrelated or shared routine causes "
                            "remain plausible. Case: "+question),
                "materiality_rationale": "Distinct source families have source-dated proximity, not proven independent causes.",
                "counter_evidence": "Exercises, weather, or shared reporting effects remain possible.",
                "next_signpost_override": None}
    return {"executive_eligible": False, "publication_basis": "investigatory_only",
            "baseline_context": context,
            "so_what": "Novel observation retained; deviation and scenario consequence not yet established.",
            "materiality_rationale": "Source novelty alone does not warrant executive prominence.",
            "counter_evidence": "No demonstrated departure, timed overlap, or reviewed exceptional single indicator.",
            "next_signpost_override": None}


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
            provider_health = (snap.get("health") or {}).get(src) or {}
            if provider_health.get("status") not in ("collected", "partial") or provider_health.get("truncated"):
                # An incomplete page cannot honestly establish a new-event
                # population or reliable numerator for surge detection.
                continue
            # The first observation of a source establishes its baseline,
            # regardless of how many apparent events appear on the first pull.
            prior = [v for v in history[:i]
                     if (v.get("health") or {}).get(src, {}).get("status") in ("collected", "partial")]
            if not prior or src is None:
                continue
            original = event_time(row.get("event_at"))
            # New-to-collector is not necessarily new-to-world. Without a
            # source event date, a warning is retained as context only and
            # cannot qualify for the recent-change queue.
            if not original or not dt.timedelta(0) <= at - original <= dt.timedelta(days=7):
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
          curated=ROOT / "data" / "verified_hotspots.json", write=True,
          executive_registry=ROOT / "data" / "executive_signal_reviews.json"):
    at = clock()
    state = Path(state)
    config = read_json(registry, {"cases": []})
    curated_cases = {x["id"]: x for x in (read_json(curated, []) or []) if isinstance(x, dict) and "id" in x}
    reviews_cfg = read_json(executive_registry, {"reviews": []}) or {}
    reviews = reviews_cfg.get("reviews", []) if isinstance(reviews_cfg, dict) else []
    if not isinstance(reviews, list):
        reviews = []
    current = read_json(state / "latest" / "friction.json", {}) or {}
    validation = read_json(state / "latest" / "friction_validation.json", {}) or {}
    history = historical(state, at)
    health = {mode: source_status(state, mode, at) for mode in FAMILIES}
    snap_time = event_time(current.get("collected_at"))
    current_fresh = bool(snap_time and dt.timedelta(0) <= at - snap_time <= dt.timedelta(hours=3))
    all_records = current.get("records", []) if current_fresh else []
    ris = read_json(state / "latest" / "ris_sampling.json", {}) or {}
    ris_ended = event_time(ris.get("ended_at"))
    ris_age = round((at - ris_ended).total_seconds() / 3600, 2) if ris_ended else None
    ris_current = (ris_age is not None and 0 <= ris_age <= 3
                   and ris.get("status") == "collected"
                   and not ris.get("truncated"))
    routing_sample = {
        "status": ("fresh_scoped_sample" if ris_current else
                   "stale_sample" if ris_ended else "not_configured"),
        "ended_at": ris.get("ended_at"),
        "coverage_seconds": ris.get("coverage_seconds"),
        "scoped_prefixes": (ris.get("prefixes", [])[:8] if ris_current else []),
        "scope_note": "Optional scoped BGP UPDATE context, not a hijack diagnosis, "
                      "country attribution or an independent escalation signal.",
    }
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
        # A multi-source *time sequence* needs temporal proximity. Two
        # unrelated observations on different days are not corroboration.
        overlaps = any(
            first.get("family") != second.get("family")
            and event_time(first.get("event_at")) is not None
            and event_time(second.get("event_at")) is not None
            and abs((event_time(first["event_at"]) -
                     event_time(second["event_at"])).total_seconds()) <= 6 * 3600
            for i, first in enumerate(new) for second in new[i + 1:]
        )
        traditional = matched_legacy(state, cid, at)
        if new and traditional:
            contrast = ("Traditional case-specific change evidence and nontraditional "
                        "observations are both present. Investigate shared causes, "
                        "reporting delays, and whether either actually preceded the other.")
        elif new:
            contrast = ("Nontraditional-source change without new corroborating evidence "
                        "from the latest case-specific traditional brief. This may "
                        "reflect stale or incomplete conventional coverage, not secrecy.")
        elif traditional:
            contrast = ("Traditional-source change without newly detected structural "
                        "friction in the monitored feeds. Missing sources limit "
                        "inferences from apparent quiet.")
        else:
            contrast = ("No new matched source change across these monitored families; "
                        "the standing watch and unmeasured activity remain unresolved.")
        baselines = {family: baseline(state, history, cid, family, at)
                     for family in FAMILIES.values()}
        anomalous = [family for family, val in baselines.items()
                     if val["status"] == "unusual_count"]
        gap = [name for name, info in health.items()
               if info["status"] != "fresh" or info["coverage"] == "partial"]
        counts = {family: sum(r["family"] == family for r in new)
                  for family in distinct}
        readable = {
            "internet_reachability": "public network-reachability detections",
            "maritime_restriction": "official maritime safety notices",
        }
        summary = " and ".join(
            f"{counts[family]} new {readable.get(family, family)}"
            for family in distinct)
        if overlaps:
            triage = "multi_stream_review"
            changed = (summary + " within a six-hour source-event window. "
                       "Joint timing merits review, not an assumption of common intent.")
        elif new:
            triage = "source_review"
            changed = (summary + ". Source-specific materiality and baseline "
                       "still require analyst verification.")
        elif anomalous:
            triage = "baseline_review"
            changed = "Observed source counts differ from their matched-hour historical baselines."
        else:
            triage = "collection_gap" if len(gap) == len(FAMILIES) else "maintain"
            changed = "No qualifying new structural-friction change established from available observations."
        assessment = executive_materiality(
            cid, case_cfg.get("question") or cid, new, overlaps,
            anomalous, baselines, reviews, at)
        so_what = assessment["so_what"]
        alternative = case_cfg.get("alternative") or standing.get("alternatives") or "Routine activity or reporting coverage shift."
        cases.append({
            "id": cid, "title": standing.get("name") or cid,
            "standing_state": standing.get("state") or "Standing watch",
            "triage": triage, "what_changed": changed, "so_what": so_what,
            "executive_eligible": assessment["executive_eligible"],
            "publication_basis": assessment["publication_basis"],
            "baseline_context": assessment["baseline_context"],
            "materiality_rationale": assessment["materiality_rationale"],
            "counter_evidence": assessment["counter_evidence"],
            "alternative": alternative,
            "next_signpost": assessment["next_signpost_override"] or case_cfg.get("next") or standing.get("next"),
            "traditional_contrast": contrast,
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
    executive = [c for c in review if c["executive_eligible"]]
    unlocated = recent_by_case["unlocated"]
    out = {
        "schema_version": 1, "generated_at": iso(at),
        "routing_sample": routing_sample,
        "validation": {"status": validation.get("status", "not_estimable"),
                       "labeled_windows": validation.get("labels_finalized", 0)},
        "fresh_snapshot": current_fresh, "latest_source_snapshot": current.get("collected_at"),
        "shadow_mode": True, "health": health,
        "executive_summary": (
            f"{len(executive)} early indicators qualify for executive assessment; "
            f"{len(review)-len(executive)} other investigatory leads remain. "
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
        "executive_case_ids": [c["id"] for c in executive],
        "executive_review_count": len(executive),
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
                 "executive_case_ids": [c["id"] for c in executive],
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
