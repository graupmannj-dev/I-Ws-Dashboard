#!/usr/bin/env python3
"""Read-only reconstruction of a private AIBA prospective monitoring frame.

Recomputes exact source hashes and checks both the original local ledger
chain prefix and its private archive. Never claims external timestamp proof.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aiba_private_pilot_capture as capture
from scripts import aiba_prospective_shadow as shadow
from scripts import aiba_tipper_ledger as ledger

SCHEMA = "aiba.private-prospective-source-reconstruction.v1"


class ReconstructionError(ValueError):
    pass


def private_json(path):
    if (not path.is_file() or path.is_symlink()
            or path.stat().st_mode & 0o077
            or path.stat().st_size > ledger.MAX_PAYLOAD_BYTES):
        raise ReconstructionError("private_manifest_or_receipt_unavailable")
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=ledger.object_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ReconstructionError("nonfinite_private_metadata")))
    except (ValueError, UnicodeError, OSError, RecursionError) as exc:
        raise ReconstructionError("invalid_private_manifest_or_receipt") from exc


def reconstruct(private_root, frame_id):
    ledger.clean_id(frame_id, "frame_id")
    root = Path(private_root)
    if (root.is_symlink() or not root.is_dir() or capture.within_repo(root)
            or root.stat().st_mode & 0o077):
        raise ReconstructionError("restricted_off_repo_private_root_required")
    entries, current_head = ledger.read_ledger(root / "tippers.jsonl")
    matches = [entry for entry in entries
               if entry["kind"] == "frame"
               and entry["payload"]["frame_id"] == frame_id]
    if len(matches) != 1:
        raise ReconstructionError("frame_missing_or_duplicate_in_ledger")
    original = matches[0]
    p = original["payload"]
    folder = root / "frames" / frame_id
    if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode & 0o077:
        raise ReconstructionError("private_frame_archive_missing_or_insecure")
    registry, rh = shadow.read_snapshot(folder / capture.FILES["registry"])
    fusion, fh = shadow.read_snapshot(folder / capture.FILES["fusion"])
    hashes = {"registry": rh, "fusion": fh}
    if hashes != p["source_sha256"]:
        raise ReconstructionError("archived_source_hash_does_not_match_issued_frame")
    manifest = private_json(folder / "manifest.json")
    receipt = private_json(folder / "local-freeze-receipt.json")
    if (not isinstance(manifest, dict) or
            manifest.get("schema") != "aiba.private-shadow-source-manifest.v1" or
            manifest.get("frame_id") != frame_id or
            manifest.get("input_sha256") != hashes or
            manifest.get("source_completeness_verified") is not False or
            manifest.get("event_outcomes_verified") is not False or
            manifest.get("original_source_asof") != {
                "registry": p["registry_asof"], "fusion": p["fusion_asof"]
            }):
        raise ReconstructionError("private_source_manifest_inconsistent")
    if (not isinstance(receipt, dict) or receipt.get("schema") != capture.SCHEMA or
            receipt.get("status") != "private_frame_frozen_not_independently_time_witnessed" or
            receipt.get("frame_id") != frame_id or
            receipt.get("source_sha256") != hashes or
            receipt.get("ledger_entry_count") != original["seq"] or
            receipt.get("ledger_head_sha256") != original["entry_hash"] or
            receipt.get("local_recorded_at_untrusted") != original["recorded_at"] or
            receipt.get("issued_tipper") is not False or
            receipt.get("independent_time_witness_verified") is not False):
        raise ReconstructionError("private_freeze_receipt_inconsistent")
    if registry.get("generated_at") != p["registry_asof"] or (
            fusion.get("generated_at") != p["fusion_asof"] or
            fusion.get("registry_asof") != p["registry_asof"] or
            registry.get("source_health") != fusion.get("collection_coverage")):
        raise ReconstructionError("archived_input_provenance_mismatch")
    # As-of-issuance validation uses the original ledger time, not today's
    # date: historical preservation should remain reconstructible indefinitely.
    regenerated, _ = shadow.prepare(
        registry, fusion, hashes,
        now=ledger.iso_time(original["recorded_at"]))
    if (regenerated["sensor_coverage"] != p["sensor_coverage"] or
            regenerated["single_source_review_count"] != p["single_source_review_count"] or
            regenerated["cross_family_review_count"] != p["cross_family_review_count"]):
        raise ReconstructionError("archived_behavioral_counts_or_coverage_mismatch")
    return {
        "schema": SCHEMA, "status": "local_source_and_ledger_prefix_reconstructed",
        "frame_id": frame_id, "frame_sequence": original["seq"],
        "frame_entry_hash_sha256": original["entry_hash"],
        "source_sha256": hashes,
        "ledger_entries_now": len(entries),
        "current_local_ledger_head": current_head,
        "exact_private_source_bytes_verified": True,
        "local_hash_chain_prefix_verified": True,
        "independent_sigstore_witness_verified": False,
        "verified_pre_news_issuance": False,
        "actual_geopolitical_forecast_issued_by_frame": False,
        "no_event_outcome_established": False,
        "worldwide_coverage_ascertained": False,
        "interpretation": (
            "Historical source archive and local ledger chain match; "
            "only independent Sigstore witness verification and separate "
            "event/publication adjudication can establish prospective skill."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--frame-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = reconstruct(args.private_root, args.frame_id)
        print(json.dumps(result, indent=2))
        return 0
    except (ReconstructionError, capture.CaptureError, shadow.ShadowError,
            ledger.LedgerError, ValueError, TypeError, OSError,
            OverflowError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, (ReconstructionError, capture.CaptureError,
                                             shadow.ShadowError, ledger.LedgerError)) else "unavailable"
        print(json.dumps({"schema": SCHEMA, "status": "unavailable",
                          "reason": reason,
                          "independent_sigstore_witness_verified": False,
                          "verified_pre_news_issuance": False,
                          "no_event_outcome_established": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
