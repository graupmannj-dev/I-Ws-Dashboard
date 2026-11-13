#!/usr/bin/env python3
"""Evidence-grounded, conservative pair nomination across extracted source claims.

Not an incident ontology, source independence proof, or alert. Similar actors,
actions and objects may nominate human review; contradictions and mismatched
explicit event sites keep the pair separate. Never geocode narrative text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
from itertools import combinations
import json
from pathlib import Path
import re

from behavioral_claim_extraction import extract_report
from behavioral_event_resolution import reported_site, kilometers
from scripts.aiba_real_report_eval import read_jsonl, validate_reports

MAX_REPORTS = 500
MAX_PAIR_COMPARISONS = 50000
MAX_REVIEW_PAIRS = 200
STOP = {"the", "and", "with", "near", "into", "over", "from", "that", "were",
        "this", "after", "before", "their", "there", "overnight", "reports",
        "official", "officials", "reportedly", "allegedly", "said", "will"}
PRONOUNS = {"they", "their", "the", "an", "a"}


def terms(s):
    return {x for x in re.findall(r"[a-z0-9]{3,}", s.lower()) if x not in STOP}


def overlap(a, b):
    a, b = terms(a), terms(b)
    if not a or not b:
        return 0
    return len(a & b) / len(a | b)


def claim_pair(a, b):
    if a.get("action") != b.get("action"):
        return None
    actors = overlap(a.get("actor_text", ""), b.get("actor_text", ""))
    objects = overlap(a.get("object_text", ""), b.get("object_text", ""))
    if actors < 0.5 or objects < 0.5:
        return None
    return {"actor_overlap": round(actors, 3), "object_overlap": round(objects, 3),
            "action": a["action"], "claim_a": a["claim_id"], "claim_b": b["claim_id"],
            "evidence_a": a["evidence_span"], "evidence_b": b["evidence_span"]}


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def evaluate_pair(a, b, ac, bc):
    if a.get("story_lineage_id") == b.get("story_lineage_id"):
        return {"category": "possible_shared_story_lineage", "reason": "same_source_story_lineage"}
    if a.get("source_url") == b.get("source_url"):
        return {"category": "possible_shared_document", "reason": "same_exact_source_url"}
    evidence = [m for x in ac for y in bc if (m := claim_pair(x, y)) is not None]
    if not evidence:
        return None
    pa, pb = reported_site(a), reported_site(b)
    distance = kilometers(pa, pb) if pa and pb else None
    ta, tb = _time(a.get("event_at")), _time(b.get("event_at"))
    declared_time_gap_h = abs((ta - tb).total_seconds()) / 3600 if ta and tb else None
    if declared_time_gap_h is not None and declared_time_gap_h > 72:
        cat = "related_claims_conflicting_event_times"
        reason = "source_declared_event_times_more_than_72h_apart"
    elif distance is not None and distance > 150:
        cat = "related_claims_conflicting_event_sites"
        reason = "source_declared_sites_more_than_150km_apart"
    else:
        # Even perfect text and proximate points are not verified event identity.
        cat = "possible_same_event_claims_unreviewed"
        reason = "same_action_substantive_actor_object_overlap"
    return {
        "category": cat, "reason": reason,
        "event_site_distance_km": round(distance, 1) if distance is not None else None,
        "source_declared_event_time_gap_h": round(declared_time_gap_h, 1) if declared_time_gap_h is not None else None,
        "event_site_comparison_available": distance is not None,
        "matched_claims": evidence[:5],
    }


def build(reports):
    validate_reports(reports)
    if len(reports) > MAX_REPORTS:
        raise ValueError("claim graph source cap exceeded")
    # Do not join across evaluation splits; heldout is evaluation data.
    pairs = []
    num_comparisons = 0
    claims_by_id = {r["id"]: extract_report(r)["claims"] for r in reports}
    for a, b in combinations(reports, 2):
        if a["split"] != b["split"]:
            continue
        num_comparisons += 1
        if num_comparisons > MAX_PAIR_COMPARISONS:
            raise ValueError("claim graph comparison cap exceeded")
        result = evaluate_pair(a, b, claims_by_id[a["id"]], claims_by_id[b["id"]])
        if result is None:
            continue
        pairs.append({
            "report_a": a["id"], "report_b": b["id"],
            "source_url_a": a["source_url"], "source_url_b": b["source_url"],
            "split": a["split"], **result,
            "independent_corroboration_established": False,
            "event_identity_confirmed": False, "warning_level_change": False,
        })
    counts = Counter(r["category"] for r in pairs)
    return {
        "schema": "aiba.extracted-claim-relationship-shadow.v1",
        "status": "unreviewed_review_candidates_only",
        "report_count": len(reports), "comparisons": num_comparisons,
        "candidate_count_total": len(pairs), "categories": dict(sorted(counts.items())),
        "candidates": pairs[:MAX_REVIEW_PAIRS],
        "display_truncated": len(pairs) > MAX_REVIEW_PAIRS,
        "automatic_event_merges": 0, "automatic_alerts_created": 0,
        "warning_level_change": False, "independence_verified": False,
        "limitations": [
            "Same actor/action/object language may refer to different events.",
            "The source-reported event site is optional, not inferred from prose.",
            "Source lineage may be incomplete or incorrect.",
            "No source story/candidate alone proves a physical incident occurred.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reports", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = build(read_jsonl(args.reports))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "candidates"}, indent=2))


if __name__ == "__main__":
    main()
