#!/usr/bin/env python3
"""Audit two independent human pair-label exports; prepare adjudication queue.

Never manufactures gold labels, even when coders agree. Output template must
be completed by a human adjudicator before use by evaluation scorer.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

from scripts.aiba_real_report_eval import read_jsonl

VALID = {"same_event", "different_event", "same_story", "same_document", "uncertain"}


def audit(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        raise ValueError("both annotation lists required")
    def check(rows, coder):
        result = {}
        for r in rows:
            if not isinstance(r, dict) or r.get("annotator_id") != coder:
                raise ValueError("reviewer identity mismatch")
            ident = r.get("pair_id")
            if not isinstance(ident, str) or not ident.startswith("pair-") or ident in result:
                raise ValueError("duplicate or malformed pair ID")
            if not isinstance(r.get("a"), str) or not isinstance(r.get("b"), str):
                raise ValueError("missing report IDs")
            if r.get("label") not in VALID:
                raise ValueError("incomplete reviewer decisions; export and finish both packets")
            result[ident] = r
        return result
    aa, bb = check(a, "A"), check(b, "B")
    if not aa or set(aa) != set(bb):
        raise ValueError("pair coverage mismatch or empty annotation batch")
    out = []
    agree = 0
    agreement = Counter()
    for pair_id in sorted(aa):
        x, y = aa[pair_id], bb[pair_id]
        if sorted((x["a"], x["b"])) != sorted((y["a"], y["b"])):
            raise ValueError("pair IDs refer to mismatched reports")
        same = x["label"] == y["label"]
        agree += same
        agreement[x["label"]] += same
        out.append({
            "pair_id": pair_id, "a": x["a"], "b": x["b"],
            "reviewer_A_label": x["label"], "reviewer_B_label": y["label"],
            "reviewer_A_notes": (x.get("reviewer_notes") or "")[:2000],
            "reviewer_B_notes": (y.get("reviewer_notes") or "")[:2000],
            "reviewers_agree": same, "label": None, "adjudication_id": None,
            "adjudicator_notes": "",
        })
    return out, {
        "schema": "aiba.independent-pair-review-audit.v1",
        "pairs_double_coded": len(out), "exact_agreement_count": agree,
        "exact_agreement_rate": round(agree/len(out), 4),
        "disagreements": len(out) - agree,
        "agreement_counts": dict(sorted(agreement.items())),
        "human_adjudications_completed": 0,
        "uncertain_labels_not_treated_as_negative": True,
        "automatic_event_merges": 0, "automatic_alerts_created": 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reviewer-a", required=True, type=Path)
    p.add_argument("--reviewer-b", required=True, type=Path)
    p.add_argument("--adjudication-template", required=True, type=Path)
    p.add_argument("--audit", required=True, type=Path)
    args = p.parse_args()
    out, summary = audit(read_jsonl(args.reviewer_a), read_jsonl(args.reviewer_b))
    for target in (args.adjudication_template, args.audit):
        target.parent.mkdir(parents=True, exist_ok=True)
    with args.adjudication_template.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    args.adjudication_template.chmod(0o600)
    args.audit.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    args.audit.chmod(0o600)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
