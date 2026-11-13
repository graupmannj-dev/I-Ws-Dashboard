#!/usr/bin/env python3
"""Reproducible synthetic smoke benchmark for AIBA candidate claims and report links.

A synthetic hand-authored benchmark is NOT an independently labeled field test.
Outputs are performance diagnostics and cannot authorize warning escalation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from behavioral_claim_extraction import extract_report
from behavioral_event_resolution import build as build_relationships, match_pair, report_document

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "aiba_claim_benchmark_v1.json"
STATUS_EVENT = "possible_same_event_unreviewed"
STATUS_STORY = "possible_same_source_story_unreviewed"
STATUS_RELATED = "related_reporting_unreviewed"


def safe_ratio(n, d):
    return round(n / d, 4) if d else None


def _event_location(coord):
    if coord is None:
        return None
    return {"role": "reported_event_site", "basis": "source_declared",
            "lat": coord[0], "lon": coord[1]}


def claim_case(row):
    candidate = {
        "id": row["id"],
        "source_url": "https://benchmark.example.org/report/" + row["id"],
        "source_family": "commercial_media",
        "source_text": row["text"],
    }
    result = extract_report(candidate)
    claims = result["claims"]
    gold = [] if row.get("none") else [{
        "actor_text": row["actor"], "action": row["action"],
        "object_text": row["object"], "assertion_status": row["status"]
    }]
    def exact(c):
        return {k: c.get(k) for k in ("actor_text", "action", "object_text", "assertion_status")}
    pred = [exact(c) for c in claims]
    # One-to-one exact multiset evaluation; no duplicate credit.
    remaining = list(gold)
    tp = 0
    for p in pred:
        if p in remaining:
            remaining.remove(p)
            tp += 1
    for c in claims:
        span = c["evidence_span"]
        if candidate["source_text"][span["start"]:span["end"]] != span["text"]:
            raise ValueError("evidence-span corruption: " + row["id"])
        if c.get("warning_level_change") is True:
            raise ValueError("unexpected warning promotion")
    if result["independent_corroboration_established"] or result["warning_level_change"]:
        raise ValueError("unsafe evidence promotion: " + row["id"])
    return {
        "id": row["id"], "expected_claims": len(gold), "predicted_claims": len(pred),
        "tp": tp, "fp": len(pred) - tp, "fn": len(gold) - tp,
        "predicted": pred, "gold": gold,
        "abstained": result["status"] == "abstained",
    }


def relationship_case(row):
    stamp = "2026-11-13T12:00:00Z"
    def report(suffix, title):
        result = {
            "id": row["id"] + suffix, "provider": "benchmark",
            "source_family": "commercial_media", "title": title,
            "first_observed_at": stamp, "source_published_at": stamp,
            "information_root": "benchmark:" + row["id"] + suffix,
            "source_url": row.get("url" + suffix.upper(),
                                  "https://benchmark.example.org/story/" + row["id"] + suffix),
            "reporting_origin": row.get("origin" + suffix.upper()),
        }
        site = _event_location(row.get("location" + suffix.upper()))
        if site is not None:
            result["reported_event_location"] = site
        return result
    a, b = report("a", row["a"]), report("b", row["b"])
    doc_shared = bool(report_document(a) and report_document(a) == report_document(b))
    if doc_shared:
        predicted = "same_document"
    else:
        matched = match_pair(a, b)
        status = matched.get("status") if matched else None
        predicted = ({
            STATUS_EVENT: "same_event", STATUS_STORY: "same_story",
            STATUS_RELATED: "related", None: "no_match",
        }).get(status, "unknown")
        if matched and (matched.get("warning_level_change") or
                        matched.get("independent_corroboration_established")):
            raise ValueError("unsafe relationship promotion: " + row["id"])
    truth = row["truth"]
    return {"id": row["id"], "truth": truth, "predicted": predicted,
            "correct": predicted == truth,
            "false_event_merge": predicted == "same_event" and truth != "same_event",
            "missed_same_event": truth == "same_event" and predicted != "same_event"}


def evaluate(fixture):
    if fixture.get("schema") != "aiba.claim-extraction-benchmark.synthetic.v1":
        raise ValueError("unsupported benchmark schema")
    if fixture.get("dataset_kind") != "hand_authored_synthetic_not_real_world":
        raise ValueError("benchmark provenance missing")
    cases = fixture["claim_cases"]
    pairs = fixture["relationship_cases"]
    if len({x["id"] for x in cases}) != len(cases) or len({x["id"] for x in pairs}) != len(pairs):
        raise ValueError("duplicate benchmark case IDs")
    claims = [claim_case(c) for c in cases]
    relationships = [relationship_case(c) for c in pairs]
    tp, fp, fn = (sum(c[key] for c in claims) for key in ("tp", "fp", "fn"))
    positives = sum(c["expected_claims"] > 0 for c in claims)
    negatives = len(claims) - positives
    true_empty = sum(c["expected_claims"] == 0 and c["predicted_claims"] == 0 for c in claims)
    event_positive = sum(c["truth"] == "same_event" for c in relationships)
    event_true_positive = sum(c["truth"] == "same_event" and c["predicted"] == "same_event" for c in relationships)
    false_merge = sum(c["false_event_merge"] for c in relationships)
    result = {
        "schema": "aiba.claim-benchmark-results.v1",
        "dataset_kind": fixture["dataset_kind"],
        "operational_validation": False,
        "claim_metrics": {
            "examples": len(claims), "labeled_positive_examples": positives,
            "labeled_negative_examples": negatives,
            "exact_true_positives": tp, "exact_false_positives": fp,
            "exact_false_negatives": fn,
            "exact_precision": safe_ratio(tp, tp + fp),
            "exact_recall": safe_ratio(tp, tp + fn),
            "exact_f1": safe_ratio(2 * tp, 2 * tp + fp + fn),
            "negative_example_correct_abstentions": true_empty,
            "negative_example_specificity": safe_ratio(true_empty, negatives),
        },
        "relationship_metrics": {
            "examples": len(relationships), "labeled_same_event_pairs": event_positive,
            "true_same_event_nominations": event_true_positive,
            "false_event_merges": false_merge,
            "same_event_nomination_recall": safe_ratio(event_true_positive, event_positive),
            "same_event_nomination_precision": safe_ratio(
                event_true_positive, event_true_positive + false_merge),
            "exact_relation_accuracy": safe_ratio(
                sum(c["correct"] for c in relationships), len(relationships)),
        },
        "claim_cases": claims, "relationship_cases": relationships,
        "limitations": [
            "Hand-authored synthetic cases are developer-visible; no blind annotation.",
            "Small examples cannot estimate real-world base rates, false-alarm burden or calibration.",
            "Candidate same-event nominations are not automatic merges or corroboration.",
            "All warnings and alert scores remain unchanged.",
        ]
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-false-merge", action="store_true",
                        help="Optional strict regression gate on synthetic known-different pairs")
    args = parser.parse_args()
    data = json.loads(args.fixture.read_text(encoding="utf-8"))
    result = evaluate(data)
    print(json.dumps({k: v for k, v in result.items() if k not in ("claim_cases", "relationship_cases")},
                     indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.fail_on_false_merge and result["relationship_metrics"]["false_event_merges"]:
        raise SystemExit("Synthetic known-different event pairs were falsely merged")


if __name__ == "__main__":
    main()
