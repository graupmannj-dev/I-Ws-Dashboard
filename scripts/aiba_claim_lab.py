#!/usr/bin/env python3
"""AIBA offline claim lab: intake, extraction, candidate pairs and review packets.

This prepares a *private* evaluation workspace from pre-approved source text.
It never downloads articles, publishes source texts, creates alerts, or writes
into the deployed dashboard or observations branch.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from behavioral_claim_extraction import build as extract_claims
from scripts.aiba_extracted_claim_graph import build as build_graph
from scripts.aiba_real_report_eval import assignment, read_jsonl
from scripts.aiba_source_text_intake import ingest

MAX_REPORTS = 250


def private_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def private_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def prepare(input_rows, existing_manifest=None):
    reports, manifest, intake = ingest(input_rows, existing_manifest)
    if len(reports) > MAX_REPORTS:
        raise ValueError("one claim-lab batch may contain at most 250 documents")
    claims = extract_claims(reports)
    graph = build_graph(reports)
    packets = assignment(reports)
    receipt = {
        "schema": "aiba.claim-lab-receipt.v1",
        "mode": "private_offline_evaluation_only",
        "reports": len(reports),
        "source_text_present": len(reports),
        "candidate_claims": claims["candidate_claim_count"],
        "claim_abstentions": claims["abstention_count"],
        "candidate_relationships": graph["candidate_count_total"],
        "candidate_relationship_types": graph["categories"],
        "blinded_packets_generated": 2,
        "intake_summary": intake,
        "operational_validation": False,
        "automatic_event_merges": 0,
        "automatic_alerts_created": 0,
        "warning_level_change": False,
    }
    return reports, manifest, claims, graph, packets, receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True, help="Operator-approved article text JSONL")
    p.add_argument("--workspace", type=Path, required=True, help="Private writable directory")
    args = p.parse_args()
    if args.workspace.resolve().is_relative_to(Path.cwd().resolve()) and ".github" in args.workspace.parts:
        raise ValueError("do not write evaluation corpus into GitHub workflow paths")
    manifest_path = args.workspace / "lineage_splits.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    reports, manifest, claims, graph, packets, receipt = prepare(read_jsonl(args.input), manifest)
    private_jsonl(args.workspace / "reports.jsonl", reports)
    private_write(manifest_path, manifest)
    private_write(args.workspace / "candidate_claims.json", claims)
    private_write(args.workspace / "candidate_relationships.json", graph)
    for coder in ("A", "B"):
        private_jsonl(args.workspace / f"reviewer_{coder}.jsonl", packets[coder])
    private_write(args.workspace / "receipt.json", receipt)
    # Do not print source prose, coordinates, or asset-specific URLs.
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
