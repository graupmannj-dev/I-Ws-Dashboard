#!/usr/bin/env python3
"""Offline, rights-gated import of operator-supplied full-text/short-excerpt reports.

Input is JSONL of explicit source records. Never fetches URLs or assumes
that a publicly accessible URL authorizes copying its body. No live writes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from scripts.aiba_real_report_eval import (
    ALLOWED_RIGHTS, read_jsonl, validate_reports,
)

MAX_INPUT = 5000
MAX_BODY = 12000
MAX_URL = 2000
REQUIRED = ("id", "source_url", "source_text", "rights_basis",
            "retrieved_at", "story_lineage_id", "source_family")
ALLOWED_KIND = {"commercial_media", "official_media", "field_event_report",
                "primary_event_report", "eyewitness_event_report",
                "source_event_report"}


def canonical_url(raw):
    if not isinstance(raw, str) or len(raw) > MAX_URL:
        raise ValueError("source URL invalid")
    p = urlsplit(raw)
    if (p.scheme != "https" or not p.hostname or p.username or p.password
            or not p.path.strip("/") or len(p.path.strip("/")) < 5):
        raise ValueError("source-specific HTTPS document URL required")
    return p.hostname.lower() + p.path.rstrip("/") + ("?" + p.query if p.query else "")


def to_record(record):
    if not isinstance(record, dict):
        raise ValueError("invalid input row")
    missing = [k for k in REQUIRED if k not in record]
    if missing:
        raise ValueError("missing fields: " + ",".join(missing))
    if record["rights_basis"] not in ALLOWED_RIGHTS:
        raise ValueError("unknown or missing rights attestation")
    if record["source_family"] not in ALLOWED_KIND:
        raise ValueError("unsupported text record family")
    if not isinstance(record["source_text"], str) or not record["source_text"].strip():
        raise ValueError("missing original text")
    if len(record["source_text"]) > MAX_BODY:
        raise ValueError("body too long; manually select authorized excerpt")
    if not isinstance(record.get("rights_note"), str) or len(record["rights_note"].strip()) < 8:
        raise ValueError("specific rights_note required, flag alone is insufficient")
    if not isinstance(record.get("content_type"), str) or record["content_type"] not in ("full_body", "source_excerpt"):
        raise ValueError("content_type must identify full_body versus source_excerpt")
    canonical_url(record["source_url"])
    # Refuse article prose which is claimed to be an event site without typed provenance.
    if "reported_event_location" in record:
        from behavioral_claim_extraction import _site
        if _site(record) is None:
            raise ValueError("invalid source declared event site")
    item = {k: record[k] for k in (
        "id", "source_url", "source_text", "rights_basis", "retrieved_at",
        "story_lineage_id", "source_family")}
    item["rights_note"] = record["rights_note"].strip()
    item["content_type"] = record["content_type"]
    item["source_kind"] = record.get("source_kind")
    item["title"] = record.get("title")
    item["source_published_at"] = record.get("source_published_at")
    item["event_at"] = record.get("event_at")
    item["reported_event_location"] = record.get("reported_event_location")
    item["reporting_origin"] = record.get("reporting_origin")
    # A content hash detects changed excerpts, but not independence of reporting.
    item["source_text_sha256"] = hashlib.sha256(item["source_text"].encode()).hexdigest()
    return item


def _split(lineage):
    # Group-preserving deterministic split; freezes only when the local manifest
    # is retained. Do not call this a truly blinded random evaluation sample.
    value = int(hashlib.sha256(("aiba-corpus-v1:" + lineage).encode()).hexdigest()[:8], 16)
    return "heldout" if value % 5 == 0 else "development"


def ingest(rows, manifest=None):
    if not isinstance(rows, list) or len(rows) > MAX_INPUT:
        raise ValueError("invalid or oversized batch")
    manifest = dict(manifest or {})
    existing = manifest.get("lineage_splits", {})
    if not isinstance(existing, dict):
        raise ValueError("invalid frozen split manifest")
    assigned = dict(existing)
    output = []
    seen = set()
    docs = set()
    for r in rows:
        item = to_record(r)
        ident = item["id"]
        if ident in seen:
            raise ValueError("duplicate report identity")
        seen.add(ident)
        doc = canonical_url(item["source_url"])
        if doc in docs:
            raise ValueError("duplicate document: use one row per original report")
        docs.add(doc)
        lineage = item["story_lineage_id"]
        split = assigned.setdefault(lineage, _split(lineage))
        if split not in ("development", "heldout"):
            raise ValueError("invalid preexisting split")
        if r.get("split") and r["split"] != split:
            raise ValueError("incoming split conflicts with frozen lineage")
        item["split"] = split
        output.append(item)
    validate_reports(output)
    # Stop if existing splits unexpectedly change.
    for lineage, split in existing.items():
        if assigned[lineage] != split:
            raise ValueError("frozen lineage split modified")
    receipt = {
        "schema": "aiba.source-text-intake-receipt.v1",
        "source_kind": "operator_supplied_permission_attested_not_independently_verified",
        "record_count": len(output),
        "distinct_lineages": len({r["story_lineage_id"] for r in output}),
        "full_bodies": sum(r["content_type"] == "full_body" for r in output),
        "excerpts": sum(r["content_type"] == "source_excerpt" for r in output),
        "development_records": sum(r["split"] == "development" for r in output),
        "heldout_records": sum(r["split"] == "heldout" for r in output),
        "rights_verified_by_software": False,
        "automatic_alerts_created": 0,
        "production_ingested": False,
        "text_copied_to_public_repository": False,
    }
    return output, {"schema": "aiba.lineage-split-manifest.v1",
                    "lineage_splits": assigned}, receipt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--private-output", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    rows = read_jsonl(args.input)
    existing = json.loads(args.manifest.read_text()) if args.manifest.exists() else {}
    output, manifest, receipt = ingest(rows, existing)
    for p in (args.private_output, args.manifest, args.receipt):
        p.parent.mkdir(parents=True, exist_ok=True)
    # Restrict file creation in local environments that honor POSIX chmod.
    with args.private_output.open("w", encoding="utf-8") as f:
        for row in output:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    args.private_output.chmod(0o600)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
