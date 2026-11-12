#!/usr/bin/env python3
"""Explicit one-day pinned shadow retention audit runner, no track artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aircraft_one_day_benchmark as bench
from scripts import aircraft_retention_shadow_audit as audit
from scripts import aircraft_route_history as route

SCHEMA = "aiba.aircraft-retention-shadow-run.v1"
ACK = "YES_ONE_HELDOUT_3_69_GB"


def measure(pin, size, directory):
    if pin["source_day"] != audit.HOLDOUT_DAY:
        raise bench.BenchmarkError("wrong_pinned_holdout_day")
    root = Path(__file__).resolve().parents[1]
    if (not directory.is_dir() or directory.is_symlink() or
            directory.resolve().is_relative_to(root)):
        raise bench.BenchmarkError("unsafe_ephemeral_work_directory")
    if shutil.disk_usage(directory).free < size + bench.BUFFER_BYTES:
        raise bench.BenchmarkError("insufficient_ephemeral_space")
    started = time.monotonic()
    verified, parts = [], []
    with tempfile.TemporaryDirectory(dir=directory, prefix="aiba-heldout-shadow-") as temp:
        folder=Path(temp)
        for part in pin["assets"]:
            path, receipt=bench.download_one(part,pin,folder)
            parts.append(path)
            verified.append(receipt)
        result = audit.scan_day(parts, pin["source_day"])
    return {
        "source_quality_and_shadow_loss": result,
        "downloaded_bytes": sum(r["downloaded_bytes"] for r in verified),
        "assets_sha256_verified": len(verified),
        "download_receipts": verified,
        "end_to_end_wall_seconds": round(time.monotonic()-started,3),
        "source_archives_deleted_from_ephemeral_runner": True,
        "status": "shadow_audit_review_required"
                  if result["status"] == "shadow_audit_review_required"
                  else "insufficient_data_or_incomplete_source",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--acknowledge",default="")
    parser.add_argument("--work-dir",type=Path)
    args=parser.parse_args(argv)
    report={
        "schema":SCHEMA,"status":"unavailable",
        "source_download_executed":False,
        "receiver_coverage_verified":False,
        "normality_or_landing_verified":False,
        "deletion_authorized":False,
        "source_geometry_published":False,
        "changes_warning_status":False,
    }
    code=1
    try:
        pin,size=bench.load_pin(args.pin)
        if pin["source_day"] != audit.HOLDOUT_DAY:
            raise bench.BenchmarkError("not_predeclared_holdout")
        if args.execute and (args.acknowledge != ACK or args.work_dir is None):
            raise bench.BenchmarkError("full_download_requires_explicit_heldout_ack")
        report["planned_bytes"]=size
        report["source_release_published_at"]=bench.fetch_release(pin)
        if args.execute:
            report["source_download_executed"]=True
            report.update(measure(pin,size,args.work_dir))
            code=0 if report["status"]=="shadow_audit_review_required" else 1
        else:
            report["status"]="metadata_verified_not_downloaded"
            code=0
    except (bench.BenchmarkError, audit.ShadowError, OSError,
            route.InputError, TypeError, OverflowError) as exc:
        report["status"]="unavailable"
        report["reason"]=str(exc) if isinstance(exc,(bench.BenchmarkError,audit.ShadowError,route.InputError)) else "source_or_input_unavailable"
    try:
        route.write_atomic(args.output,report)
    except OSError:
        return 1
    print(f"{report['status']}: {args.output}")
    return code


if __name__=="__main__":
    raise SystemExit(main())
