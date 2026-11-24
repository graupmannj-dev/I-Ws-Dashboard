#!/usr/bin/env python3
"""Incremental, source-hash-gated local Phi sidecar builder.

Separate source publication from model inference. A cached interpretation is
reusable ONLY for an identical evidence_packet, original model/schema and a
bounded age. No automatic directional ACH judgment or warnings are accepted.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path

from dashboard.semantic_ach import digest, evidence_packet
from scripts.cairn_phi_local import MODEL

SCHEMA = "cairn.phi-sidecar.v1"
SOURCE_SCHEMA = "cairn.hypothesis-evidence.v1"
MAX_CASES = 10
DEFAULT_MAX_AGE_HOURS = 24


def _clock(now=None):
    instant = now or dt.datetime.now(dt.timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Clock must be timezone-aware")
    return instant.astimezone(dt.timezone.utc)


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.astimezone(dt.timezone.utc) if value.tzinfo else None
    except ValueError:
        return None


def _load(path):
    if path is None or not Path(path).is_file():
        return {}
    try:
        data = json.loads(Path(path).read_text())
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _source_cases(source, max_cases):
    if (not isinstance(source, dict) or source.get("schema") != SOURCE_SCHEMA
            or not isinstance(source.get("hypotheses"), list)
            or not 1 <= max_cases <= MAX_CASES):
        raise ValueError("Invalid published hypothesis source")
    cases = source["hypotheses"][:max_cases]
    ids = [x.get("id") if isinstance(x, dict) else None for x in cases]
    if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("Invalid or repeated source case IDs")
    return cases


def _valid_provisional(row, case, expected, now, *, max_age_hours):
    """Validate every cache hit independently; source content is not trusted."""
    if not isinstance(row, dict) or row.get("status") != "provisional_complete":
        return False
    if row.get("input_sha256") != expected or row.get("model_family") != MODEL:
        return False
    if (row.get("analyst_approved") is not False
            or row.get("interpretation_only") is not True
            or row.get("source_truth_not_verified") is not True
            or row.get("evaluations") != []):
        return False
    stamp = _date(row.get("model_generated_at"))
    if stamp is None or not 0 <= (now - stamp).total_seconds() <= max_age_hours * 3600:
        return False
    packet = evidence_packet(case)
    known = {x["evidence_key"] for x in packet["evidence_families"]}
    notes = row.get("evidence_notes")
    refs = row.get("source_references")
    interpretations = row.get("interpretations")
    if not isinstance(notes, list) or len(notes) > 6 or not isinstance(refs, list):
        return False
    if (not isinstance(interpretations, list)
            or len(interpretations) != len(packet["hypotheses"])):
        return False
    if any(not isinstance(x, dict) or type(x.get("hypothesis_index")) is not int
           or x["hypothesis_index"] != i
           or not isinstance(x.get("meaning"), str) or len(x["meaning"]) < 12
           or not isinstance(x.get("discriminator"), str)
           or len(x["discriminator"]) < 15
           for i, x in enumerate(interpretations)):
        return False
    ref_keys = {x.get("evidence_key") for x in refs if isinstance(x, dict)}
    if not ref_keys.issubset(known):
        return False
    if any(not isinstance(n, dict) or n.get("evidence_key") not in known
           or n.get("evidence_key") not in ref_keys
           or n.get("status") != "unverified_source_title_lead"
           or not isinstance(n.get("observation"), str)
           or not isinstance(n.get("verification_step"), str)
           for n in notes):
        return False
    return True


def prepare(source, prior, work, *, now=None, max_cases=MAX_CASES,
            max_age_hours=DEFAULT_MAX_AGE_HOURS):
    now = _clock(now)
    cases = _source_cases(source, max_cases)
    old = prior.get("cases", {}) if isinstance(prior, dict) and prior.get("schema") == SCHEMA and prior.get("model") == MODEL else {}
    if not isinstance(old, dict):
        old = {}
    changed, reused, keys = [], [], {}
    for case in cases:
        cid = case["id"]
        expected = digest(evidence_packet(case))
        keys[cid] = expected
        if _valid_provisional(old.get(cid), case, expected, now, max_age_hours=max_age_hours):
            reused.append(cid)
        else:
            changed.append(case)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    # The trusted original source is not modified; a separate tiny batch goes
    # to the loopback-only model runner.
    batch = {"schema": SOURCE_SCHEMA, "hypotheses": changed,
             "reviewed_hypotheses": source.get("reviewed_hypotheses", 0)}
    (work / "hypotheses.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
    manifest = {"schema": "cairn.phi-incremental-manifest.v1",
                "source_generated_at": source.get("generated_at"),
                "prepared_at": now.isoformat().replace("+00:00", "Z"),
                "input_sha256": keys, "changed": [x["id"] for x in changed],
                "reused": reused}
    (work / "phi_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"changed": len(changed), "reused": len(reused),
            "cases": len(cases), "input_sha256": keys}


def assemble(source, prior, work, *, now=None, max_cases=MAX_CASES,
             max_age_hours=DEFAULT_MAX_AGE_HOURS):
    now = _clock(now)
    cases = _source_cases(source, max_cases)
    work = Path(work)
    manifest = _load(work / "phi_manifest.json")
    if manifest.get("schema") != "cairn.phi-incremental-manifest.v1":
        raise ValueError("Missing incremental manifest")
    hashes = {c["id"]: digest(evidence_packet(c)) for c in cases}
    if manifest.get("input_sha256") != hashes:
        raise ValueError("Source changed during Phi inference; abort stale publication")
    prior_rows = prior.get("cases", {}) if prior.get("schema") == SCHEMA and prior.get("model") == MODEL else {}
    if not isinstance(prior_rows, dict):
        prior_rows = {}
    generated = _load(work / "semantic_ach.json")
    fresh = (generated.get("cases", {}) if generated.get("schema") == "cairn.semantic-ach.v1"
             and generated.get("model") == MODEL else {})
    if not isinstance(fresh, dict):
        fresh = {}
    rows, reused, produced, failed = {}, 0, 0, 0
    for c in cases:
        cid = c["id"]
        key = hashes[cid]
        old = prior_rows.get(cid)
        if cid in manifest["reused"] and _valid_provisional(old, c, key, now, max_age_hours=max_age_hours):
            row = copy.deepcopy(old)
            row["cache_status"] = "reused_exact_input"
            reused += 1
        else:
            row = copy.deepcopy(fresh.get(cid, {}))
            row["input_sha256"] = key
            row["model_generated_at"] = generated.get("generated_at")
            if _valid_provisional(row, c, key, now, max_age_hours=max_age_hours):
                row["cache_status"] = "fresh_inference"
                produced += 1
            else:
                code = row.get("error_code")
                if not isinstance(code, str) or not code.replace("_", "").isalpha() or len(code) > 48:
                    code = "phi_runtime_unavailable"
                row = {"status": "model_or_validation_failed",
                       "error_code": code, "interpretations": [], "evaluations": [],
                       "analyst_approved": False, "input_sha256": key,
                       "model_generated_at": None, "cache_status": "unavailable"}
                failed += 1
        rows[cid] = row
    return {"schema": SCHEMA, "model": MODEL,
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "source_build_generated_at": source.get("generated_at"),
            "provisional_only": True, "signed_evidence_modified": False,
            "cases": rows,
            "summary": {"cases": len(cases), "reused": reused,
                        "new_provisional": produced, "failed": failed}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["prepare", "assemble"])
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--prior", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--max-cases", type=int, default=MAX_CASES)
    p.add_argument("--max-age-hours", type=int, default=DEFAULT_MAX_AGE_HOURS)
    args = p.parse_args()
    if not 1 <= args.max_age_hours <= 168:
        p.error("Age must be between one hour and seven days")
    source = json.loads(args.source.read_text())
    prior = _load(args.prior)
    if args.action == "prepare":
        result = prepare(source, prior, args.work, max_cases=args.max_cases,
                         max_age_hours=args.max_age_hours)
    else:
        if args.output is None:
            p.error("assemble requires --output")
        result = assemble(source, prior, args.work, max_cases=args.max_cases,
                          max_age_hours=args.max_age_hours)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result if args.action == "prepare" else result["summary"],
                     sort_keys=True))


if __name__ == "__main__":
    main()
