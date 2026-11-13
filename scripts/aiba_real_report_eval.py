#!/usr/bin/env python3
"""Offline, provenance-first evaluation for real AIBA event reports.

Never fetches URLs, publishes source bodies, or changes operational warning
scores. Real performance requires independently annotated held-out source data.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from behavioral_claim_extraction import extract_report
from behavioral_event_resolution import match_pair, report_document

SCHEMA = "aiba.real-report-corpus.v1"
ANNOTATION_SCHEMA = "aiba.real-report-labels.v1"
PAIR_SCHEMA = "aiba.real-report-pairs.v1"
ALLOWED_RIGHTS = {"public_domain", "licensed_for_internal_evaluation", "permission_granted", "short_permitted_excerpt"}
CLAIM_FIELDS = ("actor_text", "action", "object_text", "assertion_status")
ALLOWED_PAIR_LABELS = {"same_event", "different_event", "same_story", "same_document", "uncertain"}
MAX_ROWS = 5000
MAX_PAIR_ROWS = 10000


def read_jsonl(path):
    data = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            data.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{i}: invalid JSON: {e}") from e
    return data


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_reports(rows):
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("invalid or oversized report corpus")
    ids = set()
    result = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("invalid report shape")
        rid = r.get("id")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", rid) or rid in ids:
            raise ValueError("missing/duplicate/invalid report ID")
        ids.add(rid)
        url = r.get("source_url")
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError(f"{rid}: invalid URL")
        try:
            u = urlsplit(url)
        except ValueError as e:
            raise ValueError(f"{rid}: invalid URL") from e
        if u.scheme != "https" or not u.hostname or u.username or u.password:
            raise ValueError(f"{rid}: require source-specific HTTPS URL")
        body = r.get("source_text")
        if not isinstance(body, str) or not body.strip() or len(body) > 12000:
            raise ValueError(f"{rid}: missing or oversized body text")
        lineage = r.get("story_lineage_id")
        if not isinstance(lineage, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", lineage):
            raise ValueError(f"{rid}: missing source-story lineage ID")
        if r.get("rights_basis") not in ALLOWED_RIGHTS:
            raise ValueError(f"{rid}: missing allowable rights basis")
        if not isinstance(r.get("retrieved_at"), str) or not re.fullmatch(
            r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["retrieved_at"]
        ):
            raise ValueError(f"{rid}: missing UTC retrieval provenance")
        if r.get("source_family") != "commercial_media" and r.get("source_kind") not in (
            "field_event_report", "primary_event_report", "eyewitness_event_report", "source_event_report"
        ):
            raise ValueError(f"{rid}: not event-report eligible")
        if r.get("split") not in ("development", "heldout"):
            raise ValueError(f"{rid}: split must be development or heldout")
        result.append(r)
    splits = defaultdict(set)
    for r in result:
        splits[r["story_lineage_id"]].add(r["split"])
    leaked = sorted(key for key, v in splits.items() if len(v) > 1)
    if leaked:
        raise ValueError("source-story lineage leak across splits: " + ", ".join(leaked[:5]))
    return result


def validate_labels(reports, labels):
    if not isinstance(labels, list):
        raise ValueError("annotations must be list")
    by_id = {r["id"]: r for r in reports}
    seen = set()
    for lab in labels:
        rid = lab.get("report_id")
        coder = lab.get("annotator_id")
        if rid not in by_id or not isinstance(coder, str) or not coder:
            raise ValueError("annotation references unknown report or annotator")
        if (rid, coder) in seen:
            raise ValueError("duplicate annotator/report annotation")
        seen.add((rid, coder))
        claims = lab.get("claims")
        if not isinstance(claims, list):
            raise ValueError("missing annotation claims list (empty list means no event)")
        text = by_id[rid]["source_text"]
        for c in claims:
            span = c.get("evidence_span")
            if not isinstance(span, dict) or type(span.get("start")) is not int or type(span.get("end")) is not int:
                raise ValueError("missing integer evidence offsets")
            start, end = span["start"], span["end"]
            if not 0 <= start < end <= len(text) or text[start:end] != span.get("text"):
                raise ValueError(f"{rid}: annotation evidence span mismatch")
            if not all(isinstance(c.get(k), str) and c[k] for k in CLAIM_FIELDS):
                raise ValueError("missing claim label fields")
    return labels


def validate_pairs(reports, pairs):
    if not isinstance(pairs, list) or len(pairs) > MAX_PAIR_ROWS:
        raise ValueError("invalid or oversized pair corpus")
    by_id = {r["id"]: r for r in reports}
    seen = set()
    for row in pairs:
        a, b = row.get("a"), row.get("b")
        if a not in by_id or b not in by_id or a == b:
            raise ValueError("invalid report pair IDs")
        key = tuple(sorted((a, b)))
        if key in seen:
            raise ValueError("duplicate pair labels")
        seen.add(key)
        if by_id[a]["split"] != by_id[b]["split"]:
            raise ValueError("cross-split pair: evaluation leakage")
        if row.get("label") not in ALLOWED_PAIR_LABELS:
            raise ValueError("unknown pair truth label")
        if not row.get("adjudication_id"):
            raise ValueError("pair requires documented adjudication")
    return pairs


def assignment(reports):
    """Return two independent annotator packets WITHOUT parser predictions."""
    rows = validate_reports(reports)
    packets = {}
    for reviewer in ("A", "B"):
        packets[reviewer] = [
            {"report_id": r["id"], "source_url": r["source_url"], "source_text": r["source_text"],
             "rights_basis": r["rights_basis"], "retrieved_at": r["retrieved_at"],
             "claims": [], "annotator_id": reviewer}
            for r in rows
        ]
    return packets


def _key(c):
    return tuple(c.get(k) for k in CLAIM_FIELDS)


def _ratio(n, d):
    return round(n / d, 4) if d else None


def score_claims(reports, adjudicated):
    """Exact structured labels + exact evidence span; never compare on title alone."""
    by_id = {r["id"]: r for r in reports}
    labels = {x["report_id"]: x for x in adjudicated}
    if len(labels) != len(adjudicated) or set(labels) != set(by_id):
        raise ValueError("one adjudicated label record required for each report")
    tp = fp = fn = zero = negative = abstentions = 0
    cases = []
    for rid, row in sorted(by_id.items()):
        out = extract_report(row)
        if out.get("warning_level_change") or out.get("independent_corroboration_established"):
            raise ValueError("unsafe extraction status")
        predicted = list(out.get("claims", []))
        expected = list(labels[rid]["claims"])
        if not expected:
            negative += 1
            zero += not predicted
        abstentions += out["status"] == "abstained"
        remaining = [(_key(c), c["evidence_span"]["start"], c["evidence_span"]["end"]) for c in expected]
        matched = 0
        for c in predicted:
            k = (_key(c), c["evidence_span"]["start"], c["evidence_span"]["end"])
            if k in remaining:
                remaining.remove(k)
                matched += 1
        tp += matched
        fp += len(predicted) - matched
        fn += len(expected) - matched
        cases.append({"report_id": rid, "split": row["split"], "source_hostname": urlsplit(row["source_url"]).hostname,
                      "tp": matched, "fp": len(predicted) - matched, "fn": len(expected) - matched,
                      "abstained": out["status"] == "abstained"})
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "exact_precision": _ratio(tp, tp + fp),
        "exact_recall": _ratio(tp, tp + fn),
        "exact_f1": _ratio(2 * tp, 2 * tp + fp + fn),
        "negative_reports": negative, "correct_negative_abstentions": zero,
        "negative_report_specificity": _ratio(zero, negative),
        "abstentions": abstentions, "cases": cases,
    }


def score_pairs(reports, pairs):
    lookup = {r["id"]: r for r in reports}
    counts = Counter()
    cases = []
    for pair in pairs:
        a, b = lookup[pair["a"]], lookup[pair["b"]]
        da, db = report_document(a), report_document(b)
        if da and da == db:
            predicted = "same_document"
        else:
            result = match_pair(a, b)
            if result and (result.get("warning_level_change") or
                           result.get("independent_corroboration_established")):
                raise ValueError("unsafe relationship status")
            predicted = {
                "possible_same_event_unreviewed": "same_event",
                "possible_same_source_story_unreviewed": "same_story",
                "related_reporting_unreviewed": "related",
            }.get(result.get("status") if result else None, "no_match")
        gold = pair["label"]
        if gold == "uncertain":
            counts["uncertain_truth_excluded"] += 1
            continue
        counts["scored"] += 1
        if gold == "same_event":
            counts["same_event_truth"] += 1
            counts["same_event_hit"] += predicted == "same_event"
        if predicted == "same_event":
            counts["same_event_nominations"] += 1
            counts["false_same_event_nominations"] += gold != "same_event"
        acceptable = gold == predicted or (gold == "different_event" and predicted in ("no_match", "related"))
        counts["acceptable"] += acceptable
        cases.append({"a": pair["a"], "b": pair["b"], "gold": gold, "predicted": predicted,
                      "acceptable": bool(acceptable),
                      "false_same_event_nomination": predicted == "same_event" and gold != "same_event"})
    return {"scored_pairs": counts["scored"], "uncertain_truth_excluded": counts["uncertain_truth_excluded"],
            "same_event_truth": counts["same_event_truth"],
            "true_same_event_nominations": counts["same_event_hit"],
            "false_same_event_nominations": counts["false_same_event_nominations"],
            "same_event_precision": _ratio(counts["same_event_hit"], counts["same_event_nominations"]),
            "same_event_recall": _ratio(counts["same_event_hit"], counts["same_event_truth"]),
            "acceptable_relationship_rate": _ratio(counts["acceptable"], counts["scored"]),
            "cases": cases}


def score(reports, adjudicated, pairs):
    validate_reports(reports)
    validate_labels(reports, adjudicated)
    validate_pairs(reports, pairs)
    # Prevent accidentally substituting one of the two blinded annotation packets
    # for final labels. Every report must be recorded as adjudicated.
    if any(l.get("annotator_id") != "ADJUDICATED" or not l.get("adjudication_id")
           for l in adjudicated):
        raise ValueError("adjudicated gold required, not a single coder's judgments")
    return {"schema": "aiba.real-report-evaluation-results.v1",
            "kind": "real_report_evaluation_requires_independent_annotations",
            "operational_validation": False, "report_count": len(reports),
            "claim_metrics": score_claims(reports, adjudicated),
            "pair_metrics": score_pairs(reports, pairs),
            "limitations": [
                "Precision, recall and false-merge rates require a representative held-out corpus.",
                "Unreviewed claims and links do not authorize automated military warning decisions.",
                "This evaluator measures only the supplied source sample, never global detection coverage.",
            ]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reports", required=True, type=Path)
    p.add_argument("--mode", choices=("prepare", "score"), required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--adjudicated", type=Path)
    p.add_argument("--pairs", type=Path)
    a = p.parse_args()
    reports = validate_reports(read_jsonl(a.reports))
    if a.mode == "prepare":
        packets = assignment(reports)
        a.output.mkdir(parents=True, exist_ok=True)
        for coder, rows in packets.items():
            with (a.output / f"reviewer_{coder}.jsonl").open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        write_json(a.output / "packet_manifest.json",
                   {"schema": ANNOTATION_SCHEMA, "report_count": len(reports),
                    "independent_reviewer_packets": ["A", "B"],
                    "predictions_excluded": True, "split_leakage_checked": True})
    else:
        if a.adjudicated is None or a.pairs is None:
            p.error("--adjudicated and --pairs are required for score")
        results = score(reports, read_jsonl(a.adjudicated), read_jsonl(a.pairs))
        write_json(a.output, results)
        print(json.dumps({"report_count": results["report_count"],
                          "claim_metrics": {k: v for k, v in results["claim_metrics"].items() if k != "cases"},
                          "pair_metrics": {k: v for k, v in results["pair_metrics"].items() if k != "cases"}},
                         indent=2))


if __name__ == "__main__":
    main()
