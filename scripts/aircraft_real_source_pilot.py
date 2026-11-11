#!/usr/bin/env python3
"""Explicitly opted-in, bounded, real-source *quality* sampling pilot.

Archive assets are ephemeral, no aircraft IDs/positions/callsigns leave the
runner, and outputs remain aggregate. No production alert or global coverage.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import shutil
import sys
import tempfile
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import aircraft_one_day_benchmark as benchmark
from scripts import aircraft_real_trace_quality as quality
from scripts import aircraft_route_history as route

SCHEMA = "aiba.aircraft-real-source-day-pilot.v1"
ACK = "YES_SAMPLE_2026_11_07"
DAY = "2026-11-07"
BUFFER_BYTES = 2 * 1024 ** 3


def measure(pin, available_bytes, workdir):
    if pin["source_day"] != DAY:
        raise benchmark.BenchmarkError("sample_day_must_be_predeclared_2026_11_07")
    root = Path(__file__).resolve().parents[1]
    if not workdir.is_dir() or workdir.is_symlink() or workdir.resolve().is_relative_to(root):
        raise benchmark.BenchmarkError("unsafe_ephemeral_workdir")
    if shutil.disk_usage(workdir).free < available_bytes + BUFFER_BYTES:
        raise benchmark.BenchmarkError("insufficient_ephemeral_disk")
    started = time.monotonic()
    downloads = []
    with tempfile.TemporaryDirectory(dir=workdir, prefix="aiba-real-quality-") as scratch:
        paths = []
        for part in pin["assets"]:
            path, record = benchmark.download_one(part, pin, Path(scratch))
            paths.append(path)
            downloads.append(record)
        result = quality.scan_day(paths, DAY)
        # No identity, call sign, coordinate, or selected trace returned.
        return {
            "source_quality": result,
            "download_receipts": downloads,
            "asset_checksums_verified": len(downloads),
            "downloaded_bytes": sum(d["downloaded_bytes"] for d in downloads),
            "total_seconds": round(time.monotonic() - started, 3),
            "raw_archives_deleted": True,
            "status": "quality_audit_review_required"
                      if result["source_archive_complete"] else "unavailable",
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge", default="")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args(argv)
    report = {
        "schema": SCHEMA, "status": "unavailable", "source_date": DAY,
        "sample_is_route_cohort": False, "receiver_coverage_verified": False,
        "historically_prospective_warning": False, "warning_promotion": False,
        "selected_identity_output": False, "raw_geometry_output": False,
        "source_download_executed": False,
    }
    exit_code = 1
    try:
        pin, size = benchmark.load_pin(args.pin)
        if pin["source_day"] != DAY:
            raise benchmark.BenchmarkError("wrong_predeclared_training_day")
        if args.execute and (args.acknowledge != ACK or args.work_dir is None):
            raise benchmark.BenchmarkError("source_download_requires_explicit_acknowledgement")
        report["planned_source_bytes"] = size
        report["release_published_at_utc"] = benchmark.fetch_release(pin)
        if args.execute:
            report["source_download_attempted"] = True
            result = measure(pin, size, args.work_dir)
            report.update(result)
            exit_code = 0 if report["status"] == "quality_audit_review_required" else 1
        else:
            report["status"] = "metadata_verified_without_source_download"
            exit_code = 0
    except (benchmark.BenchmarkError, route.InputError, OSError, TypeError, OverflowError) as exc:
        report["status"] = "unavailable"
        report["reason"] = str(exc) if isinstance(exc, (benchmark.BenchmarkError, route.InputError)) else "pilot_local_or_source_unavailable"
    try:
        route.write_atomic(args.output, report)
    except OSError:
        return 1
    print(f"{report['status']}: {args.output}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
