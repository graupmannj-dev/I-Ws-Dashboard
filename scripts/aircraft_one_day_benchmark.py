#!/usr/bin/env python3
"""Pinned, opt-in, one-day ADSB.lol source benchmark; never a flight warning.

Default mode checks release metadata only. Full source acquisition must be
explicitly acknowledged and remains manual. Results contain no raw aircraft
identities or geometry. No scheduled workflow, cloud resource or publication.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

# Support both 'python -m scripts.module' and documented direct script invocation.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import aircraft_cohort_archive_scan as archive
from scripts import aircraft_route_history as routes

SCHEMA = "aiba.aircraft-one-day-benchmark.v1"
PIN_SCHEMA = "aiba.aircraft-one-day-source-pin.v1"
SOURCE_REPO = "adsblol/globe_history_2026"
HARD_DOWNLOAD_LIMIT = 4_000_000_000
SCAN_LIMIT = 4_000_000_000
MAX_ASSET_SECONDS = 600
SCAN_SECONDS = 600
BUFFER_BYTES = 2 * 1024**3
MAX_PIN_BYTES = 64 * 1024
MAX_RELEASE_BYTES = 256 * 1024
ACK = "YES_ONE_DAY_3_69_GB"


class BenchmarkError(ValueError):
    def __init__(self, reason, partial=None):
        super().__init__(reason)
        self.partial = partial or {}


def load_pin(path):
    if not path.is_file() or path.stat().st_size > MAX_PIN_BYTES:
        raise BenchmarkError("source_pin_missing_or_too_large")
    try:
        pin = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise BenchmarkError("source_pin_not_json") from exc
    if not isinstance(pin, dict) or pin.get("schema") != PIN_SCHEMA:
        raise BenchmarkError("unsupported_source_pin")
    if pin.get("source_repo") != SOURCE_REPO or pin.get("selection") != "production_only_no_staging_or_mlat":
        raise BenchmarkError("source_repo_or_variant_not_allowed")
    day = routes.date_of(pin.get("source_day"))
    tag = f"v{day:%Y.%m.%d}-planes-readsb-prod-0"
    if pin.get("release_tag") != tag or day.year != 2026:
        raise BenchmarkError("source_date_or_tag_mismatch")
    assets = pin.get("assets")
    if not isinstance(assets, list) or len(assets) != 2:
        raise BenchmarkError("expected_exactly_two_source_parts")
    total = 0
    for idx, part in enumerate(assets):
        if not isinstance(part, dict):
            raise BenchmarkError("invalid_asset_entry")
        suffix = "aa" if idx == 0 else "ab"
        if part.get("name") != f"{tag}.tar.{suffix}":
            raise BenchmarkError("asset_name_or_order_mismatch")
        size = part.get("size_bytes")
        digest = part.get("sha256")
        if (not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= 2_000_000_000
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise BenchmarkError("invalid_asset_size_or_digest")
        total += size
    if total > HARD_DOWNLOAD_LIMIT:
        raise BenchmarkError("source_exceeds_single_day_download_cap")
    return pin, total


def validate_release(pin, metadata):
    if (not isinstance(metadata, dict) or metadata.get("tag_name") != pin["release_tag"]
            or metadata.get("draft") is True
            or not isinstance(metadata.get("published_at"), str)):
        raise BenchmarkError("release_metadata_not_published_or_wrong_tag")
    actual = metadata.get("assets")
    if not isinstance(actual, list):
        raise BenchmarkError("release_missing_assets")
    by_name = {a["name"]: a for a in actual
               if isinstance(a, dict) and isinstance(a.get("name"), str)}
    for expected in pin["assets"]:
        asset = by_name.get(expected["name"])
        if (not asset or asset.get("size") != expected["size_bytes"]
                or asset.get("digest") != f"sha256:{expected['sha256']}"
                or asset.get("state") != "uploaded"):
            raise BenchmarkError("release_asset_size_digest_or_state_mismatch")
    return metadata["published_at"]


def fetch_release(pin, opener=urllib.request.urlopen):
    url = f"https://api.github.com/repos/{SOURCE_REPO}/releases/tags/{pin['release_tag']}"
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "AIBA-offline-source-benchmark/1.0"}
    )
    try:
        with opener(request, timeout=20) as response:
            raw = response.read(MAX_RELEASE_BYTES + 1)
        if len(raw) > MAX_RELEASE_BYTES:
            raise BenchmarkError("source_metadata_too_large")
        data = json.loads(raw)
        return validate_release(pin, data)
    except (OSError, urllib.error.URLError, ValueError, UnicodeError, TimeoutError) as exc:
        if isinstance(exc, BenchmarkError):
            raise
        raise BenchmarkError("source_release_metadata_unavailable") from exc


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def download_one(part, pin, folder, *, max_seconds=MAX_ASSET_SECONDS,
                 runner=subprocess.run):
    """TLS-verified fixed GitHub release URL; never accept caller URL/host."""
    if not 1 <= max_seconds <= MAX_ASSET_SECONDS:
        raise BenchmarkError("invalid_asset_download_deadline")
    tag = pin["release_tag"]
    destination = folder / part["name"]
    url = (f"https://github.com/{SOURCE_REPO}/releases/download/{tag}/"
           f"{part['name']}")
    argv = [
        "curl", "--fail", "--silent", "--show-error", "--location",
        "--proto", "=https", "--proto-redir", "=https",
        "--max-filesize", str(part["size_bytes"]),
        "--max-time", str(max_seconds), "--speed-limit", "10240",
        "--speed-time", "120", "--retry", "0", "--output",
        str(destination), "--write-out", "%{http_code}", url,
    ]
    started = time.monotonic()
    try:
        result = runner(argv, capture_output=True, text=True,
                        timeout=max_seconds + 5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError("asset_download_unavailable_or_timeout") from exc
    if result.returncode or result.stdout.strip() != "200":
        raise BenchmarkError(f"asset_download_failed_code_{result.returncode}")
    if destination.stat().st_size != part["size_bytes"]:
        raise BenchmarkError("asset_download_length_mismatch")
    if file_sha256(destination) != part["sha256"]:
        raise BenchmarkError("asset_download_digest_mismatch")
    return destination, {"asset": part["name"], "downloaded_bytes": part["size_bytes"],
                         "sha256_verified": True,
                         "download_seconds": round(time.monotonic() - started, 3)}


def run_benchmark(pin, source_bytes, cohort, work_dir,
                  *, max_asset_seconds=MAX_ASSET_SECONDS):
    if source_bytes > HARD_DOWNLOAD_LIMIT:
        raise BenchmarkError("download_budget_exceeded")
    if not work_dir.is_dir() or work_dir.is_symlink():
        raise BenchmarkError("missing_safe_ephemeral_workdir")
    root = Path(__file__).resolve().parents[1]
    if work_dir.resolve().is_relative_to(root):
        raise BenchmarkError("ephemeral_archive_location_must_be_outside_checkout")
    free_bytes = shutil.disk_usage(work_dir).free
    if free_bytes < source_bytes + BUFFER_BYTES:
        raise BenchmarkError("insufficient_ephemeral_disk_for_complete_archive")
    started = time.monotonic()
    progress = {"downloaded_bytes": 0, "verified_asset_count": 0, "downloads": [],
                "full_day_download_attempted": False, "raw_source_retained": False}
    with tempfile.TemporaryDirectory(prefix="aiba-archive-one-day-", dir=work_dir) as temp:
        scratch = Path(temp)
        paths = []
        for part in pin["assets"]:
            progress["full_day_download_attempted"] = True
            try:
                path, record = download_one(part, pin, scratch, max_seconds=max_asset_seconds)
            except BenchmarkError as exc:
                raise BenchmarkError(str(exc), progress.copy()) from exc
            progress["downloads"].append(record)
            progress["verified_asset_count"] += 1
            progress["downloaded_bytes"] += record["downloaded_bytes"]
            paths.append(path)
        scan_receipt, _candidate = archive.scan(
            paths, cohort, pin["source_day"], max_bytes=SCAN_LIMIT,
            max_seconds=SCAN_SECONDS
        )
        progress["scan"] = scan_receipt
        progress["total_wall_seconds"] = round(time.monotonic() - started, 3)
        # Discard any private selected trace geometry, even if scan fails.
        if not scan_receipt["archive_complete"]:
            raise BenchmarkError("full_day_tar_scan_failed_" +
                                 scan_receipt.get("reason", "unknown"), progress.copy())
        return {"status": "archive_scanned_review_required",
                "full_day_download_executed": True,
                "receiver_coverage_verified": False, "detector_input_ready": False,
                **progress}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly download and scan one full pinned day")
    parser.add_argument("--acknowledge", default="",
                        help=f"Exact opt-in phrase {ACK} required for full download")
    parser.add_argument("--cohort", type=Path,
                        help="Synthetic negative-control fixture for throughput only")
    parser.add_argument("--work-dir", type=Path,
                        help="Ephemeral disk; required for full download")
    args = parser.parse_args(argv)
    started = time.monotonic()
    report = {"schema": SCHEMA, "status": "unavailable",
              "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "full_day_download_executed": False,
              "source_metadata_verified": False,
              "receiver_coverage_verified": False,
              "detector_input_ready": False,
              "worldwide_monitoring": False,
              "publishing_enabled": False, "automated_warning_promotion": False,
              "raw_source_retained": False}
    result_code = 1
    try:
        pin, planned_bytes = load_pin(args.pin)
        report["source_date"] = pin["source_day"]
        report["release_tag"] = pin["release_tag"]
        report["source_repo"] = SOURCE_REPO
        report["planned_asset_sizes"] = [p["size_bytes"] for p in pin["assets"]]
        report["planned_bytes"] = planned_bytes
        if args.execute and (args.acknowledge != ACK or not args.cohort or not args.work_dir):
            raise BenchmarkError("full_download_requires_explicit_acknowledgement_cohort_and_workdir")
        published_at = fetch_release(pin)
        report["source_metadata_verified"] = True
        report["published_at_utc"] = published_at
        if args.execute:
            report["full_day_benchmark_requested"] = True
            cohort = routes.read_json(args.cohort)
            report.update(run_benchmark(pin, planned_bytes, cohort, args.work_dir))
        else:
            report["status"] = "metadata_verified_not_downloaded"
        result_code = 0
    except (BenchmarkError, routes.InputError, OSError, TypeError, OverflowError) as exc:
        report["status"] = "unavailable"
        if isinstance(exc, BenchmarkError):
            report.update(exc.partial)
        report["reason"] = str(exc) if isinstance(exc, (BenchmarkError, routes.InputError)) else "benchmark_input_or_transport_unavailable"
    report["elapsed_process_seconds"] = round(time.monotonic() - started, 3)
    try:
        routes.write_atomic(args.output, report)
    except OSError:
        print("Unable to write benchmark receipt")
        return 1
    print(f"{report['status']}: {args.output}")
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
