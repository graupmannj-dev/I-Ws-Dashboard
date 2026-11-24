#!/usr/bin/env python3
"""Aggregate real CAIRN Phi publication receipts without laundering accuracy.

Counts per-case *schema-valid provisional outputs*, not confirmed events,
decision quality, predictive power or independently validated source claims.
Do not count a copied publication artifact more than once.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCHEMA = "cairn.semantic-ach.v1"
MODEL = "phi-4-mini-instruct-q4km-local"
VALID_STATUSES = {"provisional_complete", "model_or_validation_failed",
                  "not_selected_in_bounded_run", "not_configured"}
ERROR_RE = re.compile(r"[a-z_]{3,48}\Z")


def summarize(receipts, *, minimum_cases=50, minimum_runs=5, threshold=0.98):
    if not 0 < threshold <= 1:
        raise ValueError("Threshold outside (0,1]")
    if minimum_cases < 1 or minimum_runs < 1:
        raise ValueError("Minimum denominators must be positive")
    seen, by_run, failures = set(), [], {}
    successes = attempts = recovered = 0
    for obj in receipts:
        if not isinstance(obj, dict) or obj.get("schema") != SCHEMA:
            raise ValueError("Invalid semantic receipt schema")
        if obj.get("model") != MODEL:
            raise ValueError("Receipt is not a local Phi model publication")
        timestamp = obj.get("generated_at")
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError("Missing generation timestamp")
        if timestamp in seen:
            # Re-downloading the same publication cannot inflate reliability.
            continue
        seen.add(timestamp)
        cases = obj.get("cases")
        if not isinstance(cases, dict) or not cases:
            raise ValueError("Missing per-case model results")
        run_succeeded = run_attempted = run_recovered = 0
        for case_id, row in cases.items():
            if not isinstance(case_id, str) or not isinstance(row, dict):
                raise ValueError("Invalid case record")
            status = row.get("status")
            if status not in VALID_STATUSES:
                raise ValueError("Unexpected case status")
            if status in {"not_configured", "not_selected_in_bounded_run"}:
                continue
            run_attempted += 1
            attempts += 1
            if status == "model_or_validation_failed":
                if row.get("evaluations") not in ([], None):
                    raise ValueError("Failed Phi output must not contain evidence directions")
                code = row.get("error_code", "unclassified")
                if not isinstance(code, str) or not ERROR_RE.fullmatch(code):
                    raise ValueError("Invalid public failure category")
                failures[code] = failures.get(code, 0) + 1
                continue
            # Schema-valid output is NOT independently verified source truth.
            if (row.get("analyst_approved") is not False
                    or row.get("interpretation_only") is not True
                    or row.get("source_truth_not_verified") is not True
                    or row.get("model_family") != MODEL):
                raise ValueError("Model output crossed the analyst authority boundary")
            if row.get("evaluations") != []:
                raise ValueError("Local Phi must not publish ACH evidence directions")
            interpretations = row.get("interpretations")
            if not isinstance(interpretations, list) or not interpretations:
                raise ValueError("Missing provisional hypothesis interpretations")
            if any(not isinstance(x, dict)
                   or type(x.get("hypothesis_index")) is not int
                   or x["hypothesis_index"] != index
                   or not isinstance(x.get("meaning"), str)
                   or not isinstance(x.get("discriminator"), str)
                   or len(x["meaning"]) < 12
                   or len(x["discriminator"]) < 15
                   for index, x in enumerate(interpretations)):
                raise ValueError("Unusable or mismatched hypothesis interpretations")
            if row.get("format_retry_succeeded") is True and row.get("attempts") != 2:
                raise ValueError("Inconsistent format retry accounting")
            references = row.get("source_references")
            notes = row.get("evidence_notes")
            if not isinstance(references, list) or not isinstance(notes, list):
                raise ValueError("Missing source provenance structures")
            keys = {f["evidence_key"] for f in references if isinstance(f, dict)
                    and isinstance(f.get("evidence_key"), str)}
            if any(not isinstance(n, dict) or n.get("evidence_key") not in keys
                   or n.get("status") != "unverified_source_title_lead"
                   or not isinstance(n.get("observation"), str)
                   or len(n["observation"]) < 15
                   or not isinstance(n.get("verification_step"), str)
                   or len(n["verification_step"]) < 15
                   for n in notes):
                raise ValueError("Accepted model note lacks provenance or verification")
            successes += 1
            run_succeeded += 1
            if row.get("format_retry_succeeded") is True:
                recovered += 1
                run_recovered += 1
        by_run.append({"generated_at": timestamp, "attempted": run_attempted,
                       "valid": run_succeeded, "format_retries_recovered": run_recovered})
    ratio = successes / attempts if attempts else None
    sufficient = len(by_run) >= minimum_runs and attempts >= minimum_cases
    return {
        "schema": "cairn.phi-structural-reliability-audit.v1",
        "model": MODEL, "distinct_publication_runs": len(by_run),
        "attempted_case_runs": attempts, "schema_valid_case_runs": successes,
        "failed_case_runs": attempts - successes,
        "valid_fraction": ratio, "format_retries_recovered": recovered,
        "failure_codes": dict(sorted(failures.items())),
        "minimum_cases": minimum_cases, "minimum_runs": minimum_runs,
        "threshold": threshold, "sufficient_denominator": sufficient,
        "structural_validity_gate_met": bool(sufficient and ratio is not None
                                              and ratio >= threshold),
        "independent_real_world_event_accuracy_measured": False,
        "source_truth_independently_verified": False,
        "note": "Correlated repeated case-runs measure output structure, not intelligence accuracy.",
        "runs": sorted(by_run, key=lambda row: row["generated_at"]),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts", nargs="+", type=Path,
                   help="Downloaded per-run semantic_ach.json receipts (JSON, not ZIP)")
    p.add_argument("--out", type=Path)
    p.add_argument("--minimum-cases", type=int, default=50)
    p.add_argument("--minimum-runs", type=int, default=5)
    p.add_argument("--threshold", type=float, default=0.98)
    args = p.parse_args()
    report = summarize([json.loads(f.read_text()) for f in args.receipts],
                       minimum_cases=args.minimum_cases,
                       minimum_runs=args.minimum_runs,
                       threshold=args.threshold)
    result = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
