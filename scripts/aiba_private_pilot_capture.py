#!/usr/bin/env python3
"""Manual private-source capture for a *real prospective* AIBA shadow window.

No network fetch, external upload, scheduling, threat forecast or Atlas update.
No source snapshots or tipper ledger ever written to the Git checkout.
An independently signed timestamp is still needed after a successful freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aiba_prospective_shadow as shadow
from scripts import aiba_tipper_ledger as ledger

SCHEMA = "aiba.private-prospective-capture-receipt.v1"
REPO = Path(__file__).resolve().parents[1]
MAX_INPUT_BYTES = shadow.MAX_SOURCE_BYTES
FILES = {"registry": "registry.json", "fusion": "fusion.json"}


class CaptureError(ValueError):
    pass


def within_repo(path):
    return Path(path).resolve().is_relative_to(REPO)


def ensure_private_root(path):
    path = Path(path)
    if path.is_symlink() or within_repo(path):
        raise CaptureError("private_root_must_be_outside_repo_and_not_symlink")
    if path.exists():
        if not path.is_dir() or path.stat().st_mode & 0o077:
            raise CaptureError("private_root_permissions_must_be_0700")
    else:
        path.mkdir(parents=True, mode=0o700)
        if path.stat().st_mode & 0o077:
            raise CaptureError("private_root_permissions_must_be_0700")
    return path


def write_exclusive(path, content):
    if not isinstance(content, bytes):
        raise CaptureError("raw_source_bytes_required")
    if path.exists() or path.is_symlink():
        raise CaptureError("refuse_overwrite_private_evidence")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(content):
            written = os.write(fd, content[offset:])
            if not written:
                raise CaptureError("short_private_evidence_write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)
    if path.stat().st_mode & 0o077:
        raise CaptureError("private_evidence_permissions_invalid")


def read_consistent(path):
    path = Path(path)
    value, digest = shadow.read_snapshot(path)
    # Check again when copying: an updated latest file must never be
    # silently archived with an earlier snapshot's digest.
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest or not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise CaptureError("source_mutated_during_preflight")
    return value, digest, raw


def create_capture(registry_path, fusion_path, *, private_root=None,
                   freeze=False, accept_unverified_coverage=False,
                   now=None, append_fn=None):
    """Freeze a bounded private 24h frame and exact source bytes when opt-in.

    The private ledger append uses its actual machine clock. The local clock
    itself is not trusted; user must externally sign the resulting head.
    """
    if freeze != bool(accept_unverified_coverage):
        raise CaptureError("freeze_requires_explicit_unverified_coverage_acceptance")
    if freeze and private_root is None:
        raise CaptureError("private_root_required_for_freeze")
    registry, rh, rbytes = read_consistent(registry_path)
    fusion, fh, fbytes = read_consistent(fusion_path)
    frame, preflight = shadow.prepare(registry, fusion,
                                      {"registry": rh, "fusion": fh}, now=now)
    receipt = {
        "schema": SCHEMA,
        "status": "preflight_only_not_frozen",
        "frame_id": frame["frame_id"],
        "window_start": frame["window_start"],
        "window_end": frame["window_end"],
        "source_asof": {"registry": frame["registry_asof"],"fusion":frame["fusion_asof"]},
        "source_sha256": {"registry": rh, "fusion": fh},
        "source_count": preflight["providers_checked"],
        "source_adapters_bounded_or_degraded": preflight["providers_with_missingness"],
        "new_single_source_leads": frame["single_source_review_count"],
        "cross_family_review_groups": frame["cross_family_review_count"],
        "source_complete": False,
        "issued_tipper": False,
        "negative_event_inferred": False,
        "independent_time_witness_verified": False,
        "warning_skill_estimated": False,
        "private_source_copies_saved": False,
        "ledger_head_sha256": None,
        "ledger_entry_count": None,
    }
    if not freeze:
        return receipt
    root = ensure_private_root(private_root)
    if Path(registry_path).resolve().is_relative_to(root.resolve()) or Path(
            fusion_path).resolve().is_relative_to(root.resolve()):
        raise CaptureError("source_inputs_must_not_be_archived_into_themselves")
    archive = root / "frames"
    if archive.is_symlink():
        raise CaptureError("private_archive_dir_symlink_not_allowed")
    if archive.exists():
        if not archive.is_dir() or archive.stat().st_mode & 0o077:
            raise CaptureError("private_archive_dir_must_be_0700")
    else:
        archive.mkdir(mode=0o700)
    folder = archive / frame["frame_id"]
    folder.mkdir(mode=0o700)  # existing frame / replay fails closed
    write_exclusive(folder / FILES["registry"], rbytes)
    write_exclusive(folder / FILES["fusion"], fbytes)
    manifest = {
        "schema": "aiba.private-shadow-source-manifest.v1",
        "frame_id": frame["frame_id"], "status": "copied_not_yet_independently_witnessed",
        "input_sha256": {"registry": rh, "fusion": fh},
        "original_source_asof": {"registry": frame["registry_asof"],
                                 "fusion": frame["fusion_asof"]},
        "source_completeness_verified": False,
        "event_outcomes_verified": False,
    }
    write_exclusive(folder / "manifest.json",
                    ledger.json_bytes(manifest) + b"\n")
    # Verify the exact archived bytes before accepting a linked ledger entry.
    if (hashlib.sha256((folder / FILES["registry"]).read_bytes()).hexdigest() != rh
        or hashlib.sha256((folder / FILES["fusion"]).read_bytes()).hexdigest() != fh):
        raise CaptureError("archived_source_hash_mismatch")
    path = root / "tippers.jsonl"
    appender = append_fn or ledger.append
    result = appender(path, "frame", frame)
    entries, head = ledger.read_ledger(path)
    if head != result["entry_hash"] or entries[-1]["payload"]["frame_id"] != frame["frame_id"]:
        raise CaptureError("private_chain_post_append_verification_failed")
    receipt.update({
        "status": "private_frame_frozen_not_independently_time_witnessed",
        "private_source_copies_saved": True,
        "ledger_head_sha256": head,
        "ledger_entry_count": len(entries),
        "local_recorded_at_untrusted": result["recorded_at"],
    })
    # Commit marker lives privately and is never treated as a Sigstore witness.
    write_exclusive(folder / "local-freeze-receipt.json",
                    ledger.json_bytes(receipt) + b"\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--fusion", type=Path, required=True)
    parser.add_argument("--mode", choices=("check", "freeze"), default="check")
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--accept-unverified-coverage", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = create_capture(
            args.registry, args.fusion, private_root=args.private_root,
            freeze=args.mode == "freeze",
            accept_unverified_coverage=args.accept_unverified_coverage)
        print(json.dumps(output, indent=2, allow_nan=False))
        if args.mode == "freeze":
            print(
                "\nNEXT MANUAL STEP: Go to GitHub Actions > "
                "Manual AIBA signed private-ledger hash witness and enter "
                "ledger_head_sha256 and ledger_entry_count from above. "
                "The timestamp must be independently verified BEFORE "
                "the earliest credible relevant public report. "
                "DO NOT upload the ledger or source archive."
            )
        return 0
    except (CaptureError, shadow.ShadowError, ledger.LedgerError,
            OSError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, (CaptureError, shadow.ShadowError,
                                            ledger.LedgerError)) else "capture_unavailable"
        print(json.dumps({
            "schema": SCHEMA, "status": "unavailable", "reason": reason,
            "issued_tipper": False, "negative_event_inferred": False,
            "independent_time_witness_verified": False,
            "warning_skill_estimated": False,
        }))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
