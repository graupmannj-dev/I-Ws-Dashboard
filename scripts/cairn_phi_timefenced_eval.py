#!/usr/bin/env python3
"""Make honest, time-fenced CAIRN historical assessment packets.

The output is source-visibility material for human/LLM comparison, NOT event
truth, prediction outcome labels, or time-travel copies of current articles.
A case is a case-day; repeated days of one case are correlated observations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from dashboard.hypothesis_auto_review import _match_case, _parse_time
from scripts.cairn_historical_replay import snapshots

SCHEMA = "cairn.phi-timefenced-evaluation-packets.v1"
MAX_CASE_DAYS = 100
MAX_DAYS = 10
MAX_SOURCES_PER_CASE_DAY = 8
GENERIC_HYPOTHESES = (
    "The case region is experiencing preparatory activity for a new military escalation.",
    "The available observations reflect routine, localized, or non-hostile activity instead.",
)
CONTROL_CUES = ("firing exercise", "training exercise", "routine drill",
                "scheduled exercise", "recruitment", "military housing")


def _iso(clock):
    if not isinstance(clock, dt.datetime) or clock.tzinfo is None:
        raise ValueError("Historical sample clock must be timezone aware")
    return clock.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _url(value):
    if not isinstance(value, str) or len(value) > 1800:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        return value
    except ValueError:
        return None


def _pick_days(source_snapshots, limit=MAX_DAYS):
    if not 1 <= limit <= MAX_DAYS:
        raise ValueError("Day count outside 1..10")
    unique = {}
    for when, record, filename in source_snapshots:
        if isinstance(record, dict):
            unique[when.date().isoformat()] = (when, record, filename)
    byday = sorted(unique.values(), key=lambda t: t[0])
    if len(byday) <= limit:
        return byday
    # Stratify across the *actual* observation span, not a retrospective
    # archive copied to fictitious historical collection timestamps.
    indices = [round(i * (len(byday) - 1) / (limit - 1))
               for i in range(limit)] if limit > 1 else [0]
    return [byday[i] for i in indices]


def _sources_at(registry, case_id, asof):
    candidates = []
    for rec in registry.get("records", []):
        if not isinstance(rec, dict):
            continue
        stamp = _parse_time(rec.get("first_observed_at"))
        if not stamp or stamp > asof:
            continue
        link = _url(rec.get("source_url"))
        if not link:
            continue
        # Explicit case_hint may encode an analyst's future knowledge.
        # Hide it, and rely on the text/geographic cue only. This is still
        # merely a case association, NOT verification of event geography.
        masked = {**rec, "case_hint": None}
        basis = _match_case(case_id, masked)
        if not basis:
            continue
        title = str(rec.get("title") or "").strip()
        if not title:
            continue
        root = str(rec.get("information_root") or link)[:300]
        mode = str(rec.get("collection_mode") or "unknown")[:70]
        claim = {
            "record_id": str(rec.get("id") or "")[:120],
            "evidence_key": "asof:" + hashlib.sha256(
                (case_id + "\x1f" + mode + "\x1f" + root).encode()
            ).hexdigest()[:24],
            "title": title[:240],
            "source_url": link,
            "source_mode": mode,
            "source_family": str(rec.get("source_family") or "")[:90],
            "first_observed_at": _iso(stamp),
            "reported_geography": (
                str(rec.get("geography", {}).get("label") or "")[:160]
                if isinstance(rec.get("geography"), dict)
                else str(rec.get("geography") or "")[:160]
            ),
            "geography_match_basis": basis,
            "information_root_fingerprint": hashlib.sha256(root.encode()).hexdigest(),
            "independent_source_confirmed": False,
            "source_body_asof_inspected": False,
            "event_occurrence_verified": False,
        }
        candidates.append((stamp, claim))
    # Source fingerprint prevents duplicate syndication roots from inflating
    # the case packet. No assertion that two different fingerprints are
    # independently corroborating a military event.
    candidates.sort(key=lambda x: (x[0], x[1]["evidence_key"]), reverse=True)
    unique = {}
    for when, item in candidates:
        unique.setdefault(item["evidence_key"], item)
    result = list(unique.values())
    return result[:MAX_SOURCES_PER_CASE_DAY], len(result)


def build(source_snapshots, *, case_ids, days=MAX_DAYS,
          source_cap=MAX_SOURCES_PER_CASE_DAY):
    if not 1 <= source_cap <= MAX_SOURCES_PER_CASE_DAY:
        raise ValueError("Source cap outside 1..8")
    if not isinstance(case_ids, (list, tuple)) or not case_ids:
        raise ValueError("Explicit case list required")
    if len(case_ids) > 10 or len(set(case_ids)) != len(case_ids):
        raise ValueError("At most ten unique case IDs allowed")
    selected = _pick_days(source_snapshots, limit=days)
    packets = []
    for asof, registry, snapshot_filename in selected:
        if registry.get("schema") != "aiba.behavioral-observations.v1":
            continue
        asof_stamp = _iso(asof)
        for case_id in case_ids:
            all_candidates, n = _sources_at(registry, case_id, asof)
            matched = all_candidates[:source_cap]
            controlled = sum(any(cue in x["title"].lower() for cue in CONTROL_CUES)
                             for x in matched)
            pid = "case-day:" + hashlib.sha256(
                (case_id + "\x1f" + asof_stamp).encode()).hexdigest()[:24]
            packets.append({
                "packet_id": pid,
                "case_id": case_id,
                "asof": asof_stamp,
                "actual_source_snapshot_filename": snapshot_filename,
                "hypotheses": list(GENERIC_HYPOTHESES),
                "source_claims": matched,
                "all_case_associated_roots_before_cap": n,
                "source_list_truncated": n > len(matched),
                "nominal_training_or_routine_title_controls": controlled,
                "negative_event_truth_established": False,
                "source_independence_established": False,
                "actual_event_outcome": None,
                "expert_evidence_direction": None,
                "historically_observed_source_body_versions": False,
                "no_collected_matches_is_not_evidence_of_no_event": True,
                "case_label_from_future_reporting_used": False,
                "claim_match_is_not_ground_truth": True,
            })
    if len(packets) > MAX_CASE_DAYS:
        raise AssertionError("Packet construction exceeded agreed size")
    counts = Counter()
    by_case = Counter()
    for packet in packets:
        by_case[packet["case_id"]] += 1
        counts["case_days"] += 1
        counts["source_rows_visible"] += len(packet["source_claims"])
        counts["case_days_with_candidates"] += bool(packet["source_claims"])
        counts["nominal_training_or_routine_title_controls"] += (
            packet["nominal_training_or_routine_title_controls"])
    return {
        "schema": SCHEMA,
        "status": "unadjudicated_historical_source_visibility_packets",
        "sampling": {
            "requested_days": days, "actual_days": len(selected),
            "case_count": len(case_ids),
            "packet_count": len(packets),
            "case_days_by_case": dict(sorted(by_case.items())),
            "mode": "chronological_source_snapshot_asof_no_case_hint",
            "event_truth_labels_available": False,
            "independent_true_negative_events_available": False,
            "future_source_bodies_backfilled": False,
        },
        "summary": dict(counts),
        "packets": packets,
        "quality_limits": [
            "Source title and provider geography are assertions, not verified event locations.",
            "Absence of a captured report is not evidence a conflict did not occur.",
            "Training/exercise/recruitment titles are lexical controls, not adjudicated non-events.",
            "Reconstructed daily source snapshots omit initial provider baselines.",
            "The generic pair of hypotheses was specified after some snapshots and cannot establish real historic forecasts.",
            "Repeated case-days are correlated: do not compute event precision from packet count.",
            "Predictive false-positive rate, true negatives, recall, and lead time require independent dated outcomes.",
        ],
    }


def check_model_outputs(dataset, outputs):
    """Audit model source-key discipline; defer semantic truth to reviewers."""
    if dataset.get("schema") != SCHEMA:
        raise ValueError("Wrong dataset")
    if not isinstance(outputs, dict):
        raise ValueError("Model output rows must be keyed by packet ID")
    stats = Counter()
    flags = []
    for p in dataset.get("packets", []):
        pid = p["packet_id"]
        out = outputs.get(pid)
        if out is None:
            stats["not_evaluated"] += 1
            continue
        stats["model_attempted"] += 1
        if not isinstance(out, dict) or out.get("evaluations") != [] or (
                out.get("analyst_approved") is not False):
            stats["unusable_or_unauthorized"] += 1
            flags.append({"packet_id": pid, "error": "unauthorized_or_malformed"})
            continue
        known = {x["evidence_key"] for x in p["source_claims"]}
        notes = out.get("evidence_notes")
        interpretations = out.get("interpretations")
        if (not isinstance(notes, list) or not isinstance(interpretations, list)
                or len(interpretations) != len(p["hypotheses"])):
            stats["unusable_or_unauthorized"] += 1
            flags.append({"packet_id": pid, "error": "incomplete_interpretations"})
            continue
        if any(not isinstance(x, dict) or x.get("evidence_key") not in known
               for x in notes):
            stats["invented_or_off_packet_reference"] += 1
            flags.append({"packet_id": pid, "error": "invalid_evidence_key"})
            continue
        stats["structurally_usable"] += 1
    return {
        "schema": "cairn.phi-timefenced-structural-evaluation.v1",
        "candidate_packets": len(dataset["packets"]),
        "attempted_packets": stats["model_attempted"],
        "structurally_usable": stats["structurally_usable"],
        "not_evaluated": stats["not_evaluated"],
        "unusable_or_unauthorized": stats["unusable_or_unauthorized"],
        "invented_or_off_packet_reference": stats["invented_or_off_packet_reference"],
        "review_flags": flags,
        "original_source_trueness_assessed": False,
        "event_precision": None, "event_recall": None,
        "event_false_positive_rate": None,
        "warning_lead_time_hours": None,
        "expert_adjudication_required": True,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, required=True)
    p.add_argument("--config", type=Path, default=Path("data/hypothesis_discriminators.json"))
    p.add_argument("--days", type=int, default=10)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model-outputs", type=Path)
    p.add_argument("--eval-out", type=Path)
    args = p.parse_args()
    src, valid_files = snapshots(args.history)
    config = json.loads(args.config.read_text())
    if config.get("schema") != "cairn.hypothesis-discriminators.v1":
        raise ValueError("Unexpected version of case configuration")
    result = build(src, case_ids=list(config["cases"]), days=args.days)
    result["original_snapshot_files_valid"] = valid_files
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("Time-fenced candidate packets:", len(result["packets"]),
          "actual source snapshot days:", result["sampling"]["actual_days"])
    if args.model_outputs:
        output = json.loads(args.model_outputs.read_text())
        audit = check_model_outputs(result, output)
        if not args.eval_out:
            raise ValueError("--eval-out required with --model-outputs")
        args.eval_out.write_text(json.dumps(audit, indent=2) + "\n")
        print("Model structural audit:", audit["structurally_usable"],
              "/", audit["attempted_packets"],
              "(not event precision)")


if __name__ == "__main__":
    main()
