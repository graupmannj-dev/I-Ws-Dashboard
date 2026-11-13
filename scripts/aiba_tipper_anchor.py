#!/usr/bin/env python3
"""Private AIBA ledger head digest export for external signed time anchoring.

Exports NO source details, actors, geography, evidence or tipper hypothesis.
A signed witness later proves the exact ledger hash was present no later
than signing time, NOT that a user-supplied or local issuance time is true.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aiba_tipper_ledger as ledger

SCHEMA = "aiba.ledger-private-head-export.v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ANCHOR_SCHEMA = "aiba.external-ledger-head-anchor.v1"


class AnchorError(ValueError):
    pass


def export_head(path, expected_hash=None):
    path = Path(path)
    repo = Path(__file__).resolve().parents[1]
    if path.resolve().is_relative_to(repo):
        raise AnchorError("private_ledger_must_not_be_inside_public_repository")
    entries, head = ledger.read_ledger(path)
    if not entries:
        raise AnchorError("cannot_anchor_empty_ledger")
    if expected_hash is not None and expected_hash != head:
        raise AnchorError("ledger_head_changed_before_anchor")
    assert HEX64.fullmatch(head)
    return {
        "schema": SCHEMA,
        "ledger_head_sha256": head,
        "ledger_entry_count": len(entries),
        "local_last_recorded_at_untrusted": entries[-1]["recorded_at"],
        "chain_verified_locally": True,
        "external_signed_timestamp_verified": False,
        "public_tip_payload_included": False,
        "source_evidence_included": False,
        "trusted_issuance_time_proven": False,
        "interpretation": "Hash chain is internally consistent; only a separately verified Sigstore witness can give an independently witnessed upper-bound time."
    }


def create_public_anchor(head_hash, entry_count, *, run_id, source_sha):
    if not isinstance(head_hash, str) or not HEX64.fullmatch(head_hash):
        raise AnchorError("invalid_ledger_head_hash")
    if type(entry_count) is not int or not 1 <= entry_count <= ledger.MAX_ENTRIES:
        raise AnchorError("invalid_ledger_entry_count")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{5,20}",run_id):
        raise AnchorError("invalid_github_run_id")
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}",source_sha):
        raise AnchorError("invalid_github_source_commit")
    return {
        "schema": ANCHOR_SCHEMA,
        "subject_kind": "private_aiba_ledger_head_hash_only",
        "hash_algorithm": "sha256",
        "ledger_head_sha256": head_hash,
        "ledger_entry_count": entry_count,
        "github_run_id": run_id,
        "github_source_commit": source_sha,
        "raw_ledger_uploaded": False,
        "tipper_content_uploaded": False,
        "analyst_identity_uploaded": False,
        "first_news_timestamp_proven": False,
        "source_independence_proven": False,
        "verified_issuing_time_proven": False,
        "signed_witness_time_interpretation": "If Sigstore GitHub attestation is cryptographically verified, its witness timestamp bounds when this hash-committed private ledger existed. It does not prove that the local recorded_at was true, or that the content was accurate."
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    local=sub.add_parser("export",help="Inspect existing private ledger, no network")
    local.add_argument("--ledger",type=Path,required=True)
    local.add_argument("--expected-head")
    local.add_argument("--output",required=True,type=Path)
    public=sub.add_parser("public-anchor",help="Construct hash-only attestation subject")
    public.add_argument("--head-hash",required=True)
    public.add_argument("--entry-count",required=True,type=int)
    public.add_argument("--github-run-id",required=True)
    public.add_argument("--source-sha",required=True)
    public.add_argument("--output",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        if args.command=="export":
            if args.ledger.resolve()==args.output.resolve():
                raise AnchorError("cannot_overwrite_private_ledger")
            result=export_head(args.ledger,args.expected_head)
        else:
            result=create_public_anchor(args.head_hash,args.entry_count,
                                        run_id=args.github_run_id,
                                        source_sha=args.source_sha)
        if args.output.exists() or args.output.is_symlink():
            raise AnchorError("refuse_to_overwrite_existing_anchor")
        if args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
            raise AnchorError("never_write_anchor_exports_into_public_repo_checkout")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as out:
            json.dump(result,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({"status":"prepared_hash_only_export",
                          "head_sha256":result.get("ledger_head_sha256"),
                          "entry_count":result.get("ledger_entry_count"),
                          "external_timestamp_verified":False}))
        return 0
    except (AnchorError,ledger.LedgerError,OSError,ValueError,TypeError) as exc:
        print(json.dumps({"status":"unavailable","reason":str(exc) if isinstance(
            exc,(AnchorError,ledger.LedgerError)) else "invalid_anchor_source_or_output"}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
