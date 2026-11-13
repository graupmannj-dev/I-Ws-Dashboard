#!/usr/bin/env python3
"""Compare old title matching versus new evidence-spanned claim nomination.

Requires adjudicated pairs; results are only as good as supplied corpus and
labels. No full text is printed or returned in the comparison report.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from behavioral_claim_extraction import extract_report
from behavioral_event_resolution import match_pair
from scripts.aiba_extracted_claim_graph import evaluate_pair
from scripts.aiba_real_report_eval import read_jsonl, validate_reports, validate_pairs


def wilson(success, total):
    if not total:
        return None
    if not 0 <= success <= total:
        raise ValueError("invalid confidence interval inputs")
    import math
    z = 1.95996398454
    p = success / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total))/denominator
    half = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denominator
    return {"low": round(max(0, center-half), 4),
            "high": round(min(1, center+half), 4),
            "n": total, "method": "descriptive_unclustered_wilson_95"}


def _old_nomination(a, b):
    result = match_pair(a, b)
    return bool(result and result["status"] == "possible_same_event_unreviewed")


def _new_nomination(a, b, ca, cb):
    result = evaluate_pair(a, b, ca, cb)
    return bool(result and result["category"] == "possible_same_event_claims_unreviewed")


def _metric(rows):
    eligible = [r for r in rows if r["truth"] in ("same_event", "different_event")]
    positives = sum(r["truth"] == "same_event" for r in eligible)
    negatives = sum(r["truth"] == "different_event" for r in eligible)
    tp = sum(r["truth"] == "same_event" and r["nomination"] for r in eligible)
    fp = sum(r["truth"] == "different_event" and r["nomination"] for r in eligible)
    fn = positives - tp
    tn = negatives - fp
    return {
        "pairs_scored": len(eligible), "same_event_truth": positives, "different_event_truth": negatives,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(tp/(tp+fp), 4) if (tp+fp) else None,
        "recall": round(tp/positives, 4) if positives else None,
        "false_nomination_rate_on_different_events":
            round(fp/negatives, 4) if negatives else None,
        "false_nomination_wilson95": wilson(fp, negatives),
        "recall_wilson95": wilson(tp, positives),
    }


def compare(reports, pairs, only_heldout=True):
    reports = validate_reports(reports)
    pairs = validate_pairs(reports, pairs)
    by_id = {r["id"]: r for r in reports}
    claims = {r["id"]: extract_report(r)["claims"] for r in reports}
    rows = {"title_baseline": [], "claim_graph": []}
    for p in pairs:
        a, b = by_id[p["a"]], by_id[p["b"]]
        if only_heldout and a["split"] != "heldout":
            continue
        truth = p["label"]
        if truth == "uncertain":
            continue  # uncertain truth is NOT negative
        old = _old_nomination(a, b)
        new = _new_nomination(a, b, claims[a["id"]], claims[b["id"]])
        for key, nominated in (("title_baseline", old), ("claim_graph", new)):
            rows[key].append({"a": p["a"], "b": p["b"], "truth": truth,
                              "nomination": nominated})
    scores = {k: _metric(v) for k, v in rows.items()}
    return {
        "schema": "aiba.claim-graph-comparison.v1",
        "evaluation_split": "heldout" if only_heldout else "both_splits_diagnostic",
        "source_story_lineage_leakage_checked": True,
        "independent_human_truth_verified_by_software": False,
        "operational_validation": False,
        "scores": scores, "case_decisions": rows,
        "automated_event_merges": 0, "warning_level_change": False,
        "limitations": [
            "Ground truth provenance must be independently audited; pair labels alone do not verify independent annotation.",
            "Wilson intervals assume independent pairs, which is false for shared stories; descriptive only.",
            "The baseline is title-matching; the graph uses source body text and should be compared on the same available-body denominator.",
            "A false merge here means a false nomination for human review, not an actual merged incident.",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--development-included", action="store_true")
    args = ap.parse_args()
    result = compare(read_jsonl(args.reports), read_jsonl(args.pairs),
                     only_heldout=not args.development_included)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.output.chmod(0o600)
    print(json.dumps({"evaluation_split": result["evaluation_split"],
                      "scores": result["scores"],
                      "operational_validation": False}, indent=2))


if __name__ == "__main__":
    main()
