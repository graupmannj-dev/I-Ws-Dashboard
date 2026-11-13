#!/usr/bin/env python3
"""Prepare blinded source-pair judgments from real texts, without labels.

Candidates combine claim-graph nominations with deliberate non-nominated and
same-context comparison pairs. Sampling categories are hidden from coders.
No generated pair is a ground-truth event identity or negative.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from itertools import combinations
from pathlib import Path

from scripts.aiba_extracted_claim_graph import build as claim_graph
from scripts.aiba_real_report_eval import read_jsonl, validate_reports

MAX_PAIRS = 120
MAX_ALL_PAIRS = 20000


def _fingerprint(a, b):
    x, y = sorted([a, b])
    return hashlib.sha256((x + "\x1f" + y).encode()).hexdigest()[:20]


def _pair(a, b):
    first, second = sorted([a, b], key=lambda r: r["id"])
    return {"pair_id": "pair-" + _fingerprint(first["id"], second["id"]),
            "a": first["id"], "b": second["id"],
            "split": first["split"]}


def generate(reports, max_pairs=MAX_PAIRS):
    validate_reports(reports)
    if not 0 < max_pairs <= MAX_PAIRS:
        raise ValueError("invalid pair cap")
    if len(reports) > 250:
        raise ValueError("pair packet batch source cap exceeded")
    by_id = {r["id"]: r for r in reports}
    graph = claim_graph(reports)
    nominations = {}
    for item in graph["candidates"]:
        a, b = item["report_a"], item["report_b"]
        p = _pair(by_id[a], by_id[b])
        nominations[p["pair_id"]] = p

    potential = []
    comparisons = 0
    for a, b in combinations(reports, 2):
        if a["split"] != b["split"]:
            continue
        comparisons += 1
        if comparisons > MAX_ALL_PAIRS:
            raise ValueError("pair pool comparison safety cap exceeded")
        p = _pair(a, b)
        if p["pair_id"] in nominations:
            continue
        # Review a mixture of similar official context and unrelated reports.
        # This is NOT a known-negative label: the annotator decides.
        near = a.get("sampling_stratum") == b.get("sampling_stratum")
        same_episode = bool(a.get("evaluation_group_id") and
                            a["evaluation_group_id"] == b.get("evaluation_group_id"))
        stage = ("same_episode_unreviewed" if same_episode else
                 "same_sampling_stratum_unreviewed" if near else
                 "cross_sampling_stratum_unreviewed")
        potential.append((stage, p))
    # Deterministic, non-learned pair selection; preserves an audit trail.
    potential.sort(key=lambda v: (v[0], v[1]["pair_id"]))
    selected = []
    counts = Counter()
    for p in sorted(nominations.values(), key=lambda x: x["pair_id"]):
        if len(selected) >= max_pairs:
            break
        selected.append((p, "claim_graph_nominated_unreviewed"))
        counts["claim_graph_nominated_unreviewed"] += 1
    if len(selected) < max_pairs:
        staged = {}
        for kind, p in potential:
            staged.setdefault(kind, []).append(p)
        for kind in ("same_episode_unreviewed", "same_sampling_stratum_unreviewed",
                     "cross_sampling_stratum_unreviewed"):
            choices = staged.get(kind, [])
            # Round-robin quota leaves room for unrelated, potentially negative
            # comparisons in the review set.
            target = max(1, (max_pairs - len(nominations)) // 3)
            for p in choices[:target]:
                if len(selected) >= max_pairs:
                    break
                selected.append((p, kind))
                counts[kind] += 1
        # Refill unused slots deterministically from all non-nominations.
        chosen = {x["pair_id"] for x, _ in selected}
        for kind, p in potential:
            if len(selected) >= max_pairs:
                break
            if p["pair_id"] not in chosen:
                selected.append((p, kind))
                chosen.add(p["pair_id"])
                counts[kind] += 1

    packets = {}
    for coder in ("A", "B"):
        rows = []
        for p, _ in selected:
            a, b = by_id[p["a"]], by_id[p["b"]]
            def source(r):
                return {
                    "report_id": r["id"], "title": r.get("title"),
                    "source_url": r["source_url"], "source_text": r["source_text"],
                    "source_published_at": r.get("source_published_at"),
                }
            rows.append({
                "pair_id": p["pair_id"], "annotator_id": coder,
                "a": source(a), "b": source(b),
                "label": None, "reviewer_notes": "",
            })
        packets[coder] = rows
    audit = {
        "schema": "aiba.blind-pair-review-pool.v1",
        "source_report_count": len(reports), "eligible_within_split_comparisons": comparisons,
        "selected_pair_count": len(selected),
        "selection_strata_counts": dict(sorted(counts.items())),
        "candidate_graph_total": graph["candidate_count_total"],
        "sampling_strata_are_not_event_truth": True,
        "predictions_hidden_from_annotators": True,
        "human_ground_truth_completed": 0,
        "automatic_event_merges": 0, "automatic_alerts_created": 0,
    }
    return packets, audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", required=True, type=Path)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--max-pairs", type=int, default=MAX_PAIRS)
    args = ap.parse_args()
    packets, audit = generate(read_jsonl(args.reports), args.max_pairs)
    args.workspace.mkdir(parents=True, exist_ok=True)
    for coder, rows in packets.items():
        p = args.workspace / ("blind_pair_reviewer_" + coder + ".jsonl")
        with p.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        p.chmod(0o600)
    path = args.workspace / "blind_pair_pool_audit.json"
    path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
