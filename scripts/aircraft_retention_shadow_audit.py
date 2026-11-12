#!/usr/bin/env python3
"""Held-out real-source shadow test of post-flight thinning (never purge).

Uses the training-day frozen hash identity rule on a separately pinned held-out
archive. Only aggregate receipt leaves memory; no identifiers, callsigns,
geometry, raw traces or compacted traces are published.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import resource
import sys
import tarfile
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import aircraft_cohort_archive_scan as archive
from scripts import aircraft_real_trace_quality as qa
from scripts import aircraft_route_history as route
from scripts import aircraft_postlanding_retention as tier

SCHEMA = "aiba.aircraft-retention-shadow-audit.v1"
HOLDOUT_DAY = "2026-11-10"
SOURCE_BYTES_CAP = 4_000_000_000
SCAN_SECONDS = 600
MAX_TAR_MEMBERS = 800000
MAX_SELECT = 150
MAX_DECODED_BYTES = 48 * 1024 * 1024
MIN_LENGTH_KM = 5
TRANSIENT_SPAN_S = 300
# Diagnostic stress probes only, NOT validated AIBA event or warning detectors.
LOCAL_BEND_KM = 1.0
LOCAL_ALT_FT = 750


class ShadowError(ValueError):
    pass


def segment_event_flags(points):
    """Diagnostic triplet-level local bend / altitude peak, not threat labels."""
    bend, altitude = False, False
    for a, b, c in zip(points, points[1:], points[2:]):
        if c[0] - a[0] > TRANSIENT_SPAN_S or not a[0] < b[0] < c[0]:
            continue
        ratio = (b[0] - a[0]) / (c[0] - a[0])
        # Same interpolation convention as the PR42 storage algorithm.
        lon = (a[2] + ratio * ((c[2] - a[2] + 180) % 360 - 180) + 180) % 360 - 180
        lat = a[1] + ratio * (c[1] - a[1])
        bend |= route.haversine((b[1], b[2]), (lat, lon)) >= LOCAL_BEND_KM
        altitude |= abs(b[3] - (a[3] + ratio * (c[3] - a[3]))) >= LOCAL_ALT_FT
    return bend, altitude


def extract_segments(envelope, day, counts):
    """Split on boundaries; do not backfill, join ground gaps or assert landing."""
    anchor = envelope["timestamp"]
    midnight = dt.datetime.combine(route.date_of(day), dt.time.min,
                                   tzinfo=dt.timezone.utc).timestamp()
    active, callsign = [], None

    def review(points):
        if not points:
            return None
        counts["candidate_segments"] += 1
        if len(points) < tier.MIN_POINTS or points[-1][0] - points[0][0] < tier.MIN_DURATION_S:
            counts["rejected_short_segments"] += 1
            return None
        if not midnight <= points[0][0] <= points[-1][0] < midnight + 86400:
            counts["rejected_out_of_day"] += 1
            return None
        if len(points) > tier.MAX_POINTS:
            counts["rejected_long_segments"] += 1
            return None
        distance = sum(route.haversine(a[1:3], b[1:3])
                       for a, b in zip(points, points[1:]))
        if distance < MIN_LENGTH_KM:
            counts["rejected_stationary"] += 1
            return None
        return points

    for row in envelope["trace"]:
        counts["rows_considered"] += 1
        if not qa.valid_raw(row) or not route.number(row[3]):
            counts["invalid_or_ground_rows"] += 1
            part = review(active)
            if part:
                yield part
            active, callsign = [], None
            continue
        t, lat, lon, alt = anchor + row[0], row[1], row[2], row[3]
        call = (row[8].get("flight") or "").strip() if isinstance(row[8], dict) else ""
        flags = row[6]
        if flags & 3:
            counts["source_boundary_rows"] += 1
            part = review(active)
            if part:
                yield part
            active, callsign = [], None
            if flags & 1:
                continue
        if active:
            a = active[-1]
            if ((callsign and call and call != callsign) or
                    t <= a[0] or t - a[0] > tier.MAX_TIME_GAP_S or
                    route.haversine((lat, lon), (a[1], a[2])) > route.MAX_STEP_KM):
                counts["gap_or_callsign_boundaries"] += 1
                part = review(active)
                if part:
                    yield part
                active, callsign = [], None
        if call:
            callsign = call
        active.append((t, lat, lon, alt))
        if len(active) > tier.MAX_POINTS:
            counts["rejected_long_segments"] += 1
            active, callsign = [], None
    part = review(active)
    if part:
        yield part


def compare_leg(points):
    """No normality or landed state is inferred; test just numerical distortion."""
    indices, fidelity = tier.select_positions(points)
    reduced = [points[i] for i in indices]
    full_flags = segment_event_flags(points)
    reduced_flags = segment_event_flags(reduced)
    compact_json = json.dumps(reduced, separators=(",", ":")).encode()
    original_json = json.dumps(points, separators=(",", ":")).encode()
    full_gzip = len(gzip.compress(original_json, compresslevel=6, mtime=0))
    small_gzip = len(gzip.compress(compact_json, compresslevel=6, mtime=0))
    return {
        "original_points": len(points), "retained_points": len(reduced),
        "original_gzip_bytes": full_gzip, "retained_gzip_bytes": small_gzip,
        "max_reconstruction_km": fidelity["max_reconstruction_km"],
        "max_reconstruction_altitude_ft": fidelity["max_reconstruction_altitude_ft"],
        "full_bend_probe": full_flags[0], "reduced_bend_probe": reduced_flags[0],
        "full_alt_probe": full_flags[1], "reduced_alt_probe": reduced_flags[1],
    }


def summarize(sample, count):
    count["eligible_shadow_legs"] += 1
    count["original_positions"] += sample["original_points"]
    count["retained_positions"] += sample["retained_points"]
    count["original_gzip_bytes"] += sample["original_gzip_bytes"]
    count["retained_gzip_bytes"] += sample["retained_gzip_bytes"]
    count["full_bend_probe_positive"] += int(sample["full_bend_probe"])
    count["full_alt_probe_positive"] += int(sample["full_alt_probe"])
    count["lost_bend_probe"] += int(sample["full_bend_probe"] and not sample["reduced_bend_probe"])
    count["lost_alt_probe"] += int(sample["full_alt_probe"] and not sample["reduced_alt_probe"])
    count["new_bend_probe"] += int(not sample["full_bend_probe"] and sample["reduced_bend_probe"])
    count["new_alt_probe"] += int(not sample["full_alt_probe"] and sample["reduced_alt_probe"])


def scan_day(parts, day=HOLDOUT_DAY, *,
             max_bytes=SOURCE_BYTES_CAP, max_seconds=SCAN_SECONDS):
    if day != HOLDOUT_DAY:
        raise ShadowError("only_frozen_heldout_source_day_supported")
    if not 512 <= max_bytes <= SOURCE_BYTES_CAP or not 1 <= max_seconds <= SCAN_SECONDS:
        raise ShadowError("untrusted_scan_budget")
    source_size, _, asset = archive.archive_parts(parts, day)
    reader = archive.BoundedSplitReader(parts, max_bytes, max_seconds)
    counts = Counter()
    status, reason = "unavailable", None
    selected_bytes = 0
    max_horizontal, max_vertical = 0, 0
    started = time.monotonic()
    try:
        while True:
            hdr = reader.read(512)
            if not hdr:
                raise archive.IncompleteScan("missing_tar_terminator")
            if len(hdr) != 512:
                raise archive.IncompleteScan("truncated_tar_header")
            if hdr == b"\0" * 512:
                if reader.exact(512) != b"\0" * 512:
                    raise archive.IncompleteScan("missing_second_tar_terminator")
                while True:
                    tail = reader.read(archive.MAX_READ)
                    if not tail:
                        break
                    if any(tail):
                        raise archive.IncompleteScan("nonzero_after_tar_terminator")
                status = ("shadow_audit_review_required"
                          if counts["eligible_shadow_legs"] > 0 else "insufficient_sample")
                break
            counts["tar_members"] += 1
            if counts["tar_members"] > MAX_TAR_MEMBERS:
                raise archive.BudgetStop("tar_member_limit")
            try:
                member = tarfile.TarInfo.frombuf(hdr, "utf-8", "surrogateescape")
            except (tarfile.TarError, ValueError, OverflowError) as exc:
                raise archive.IncompleteScan("invalid_tar_header") from exc
            if member.size < 0 or member.name.startswith("/") or ".." in member.name.split("/"):
                raise ShadowError("unsafe_tar_member")
            if member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE,
                               tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
                raise ShadowError("unsupported_tar_extension")
            name = member.name.removeprefix("./")
            match = archive.TRACE_PATTERN.fullmatch(name)
            if match:
                counts["source_trace_members"] += 1
            if not match or not qa.hashed_selection(match[1].lower()):
                reader.skip(member.size + (-member.size) % 512)
                continue
            counts["selected_trace_members"] += 1
            if counts["selected_trace_members"] > MAX_SELECT:
                raise archive.BudgetStop("selected_trace_limit")
            if not member.isfile() or member.issparse():
                raise ShadowError("untrusted_selected_tar_member")
            if member.size > qa.MAX_SAMPLE_BYTES:
                counts["selected_oversized_members"] += 1
                reader.skip(member.size + (-member.size) % 512)
                continue
            parts_data = []
            remaining = member.size
            while remaining:
                block = reader.exact(min(remaining, archive.MAX_READ))
                parts_data.append(block)
                remaining -= len(block)
            reader.skip((-member.size) % 512)
            try:
                envelope, expanded = archive.read_selected(
                    b"".join(parts_data), name, match[1].lower()
                )
            except archive.ScanError:
                counts["selected_decode_failures"] += 1
                continue
            selected_bytes += expanded
            if selected_bytes > MAX_DECODED_BYTES:
                raise archive.BudgetStop("decoded_trace_limit")
            counts["selected_decoded_traces"] += 1
            for leg in extract_segments(envelope, day, counts):
                try:
                    sample = compare_leg(leg)
                except tier.RetentionError:
                    counts["rejected_compression_error"] += 1
                    continue
                summarize(sample, counts)
                max_horizontal = max(max_horizontal, sample["max_reconstruction_km"])
                max_vertical = max(max_vertical, sample["max_reconstruction_altitude_ft"])
    except archive.IncompleteScan as exc:
        status, reason = "incomplete_archive", str(exc)
    except (ShadowError, archive.ScanError, OSError, tarfile.TarError,
            MemoryError, OverflowError, ValueError) as exc:
        status = "unavailable"
        reason = str(exc) if isinstance(exc, (ShadowError, archive.ScanError)) else "source_scan_unavailable"
    finally:
        reader.close()
    complete = status in ("shadow_audit_review_required", "insufficient_sample")
    return {
        "schema": SCHEMA, "status": status, "reason": reason,
        "source_date": day, "source_asset": asset, "source": "ADSB.lol",
        "selection_rule": "PR40_frozen_hash_1_in_1024_of_ICAO_ids",
        "selection_made_without_holdout_paths": True,
        "historical_prospective_warning": False, "source_archive_complete": complete,
        "receiver_coverage_verified": False, "reviewed_normal_flights": 0,
        "landed_state_verified": False,
        "actual_alert_detector_comparison": False,
        "unverified_diagnostic_probes_only": True,
        "source_data_deleted": False, "source_geometry_retained": False,
        "destination_geometry_published": False,
        "approved_for_raw_deletion": False, "changes_aiba_warning_status": False,
        "source_file_bytes": source_size, "bytes_read": reader.bytes_read,
        "source_stream_sha256": reader.digest.hexdigest(),
        "source_scan_seconds": round(time.monotonic() - started, 3),
        "python_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "counts": dict(counts) if complete else None,
        "max_reconstruction_km": round(max_horizontal, 6) if complete else None,
        "max_reconstruction_altitude_ft": round(max_vertical, 3) if complete else None,
        "eligibility_note": "Shadow-only, no flight clearance/landing/normality review; cannot authorize actual retention/deletion",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--part", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    exit_code = 1
    try:
        receipt = scan_day(args.part, args.date)
        exit_code = 0 if receipt["status"] == "shadow_audit_review_required" else 1
    except (ShadowError, archive.ScanError, OSError, route.InputError, TypeError) as exc:
        receipt = {
            "schema": SCHEMA, "status": "unavailable",
            "reason": str(exc) if isinstance(exc, (ShadowError, archive.ScanError, route.InputError)) else "invalid_source_files",
            "source_archive_complete": False, "counts": None,
            "source_data_deleted": False, "approved_for_raw_deletion": False,
            "changes_aiba_warning_status": False,
        }
    try:
        route.write_atomic(args.output, receipt)
    except OSError:
        return 1
    print(f"{receipt['status']}: {args.output}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
