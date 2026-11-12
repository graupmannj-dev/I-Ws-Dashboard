#!/usr/bin/env python3
"""One-day deterministic sampled aircraft trace quality audit; no alerts.

The fixed selection is independent of aircraft paths, event outcomes, callsigns,
target geography or historical test days. Aggregate receipt contains no ICAO,
flight paths or callsigns. This is not a vetted route cohort.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import resource
import sys
import tarfile
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import aircraft_archive_probe as probe
from scripts import aircraft_cohort_archive_scan as archive
from scripts import aircraft_route_history as route

SCHEMA = "aiba.aircraft-real-trace-quality-audit.v1"
SAMPLE_SALT = "AIBA-fixed-hash-v1-2026-11-07-no-outcome-selection"
HASH_MODULUS = 1024
HASH_SELECTED = 0
MAX_SAMPLE_BYTES = 2 * 1024 * 1024
MAX_DECODED_BYTES = 48 * 1024 * 1024
MAX_SAMPLE_TRACES = 150
MAX_ROWS_PER_TRACE = 250000
MAX_SEGS_PER_TRACE = 1000
MAX_RUN_S = 600
MAX_SCAN_BYTES = 4_000_000_000
MAX_TAR_MEMBERS = 800000
REASONS = (
    "short_or_sparse", "timestamp_outside_day", "invalid_or_nonfinite_row",
    "stale", "ground", "new_source_leg", "callsign_change",
    "gap_or_nonmonotonic", "implausible_jump", "valid_leg_candidate",
)


class AuditError(ValueError):
    pass


def hashed_selection(icao):
    """Precommitted path-independent rule; NOT a security/privacy hash."""
    if not isinstance(icao, str) or not route.ICAO_PATTERN.fullmatch(icao):
        return False
    digest = hashlib.sha256((SAMPLE_SALT + "|" + icao).encode()).digest()
    return int.from_bytes(digest[:8], "big") % HASH_MODULUS == HASH_SELECTED


def valid_raw(row):
    if (not isinstance(row, list) or len(row) < 9
            or not all(route.number(x) for x in (row[0], row[1], row[2]))
            or row[0] < 0 or not -90 <= row[1] <= 90 or not -180 <= row[2] <= 180
            or not isinstance(row[6], int) or isinstance(row[6], bool)
            or row[6] < 0):
        return False
    if row[8] is not None and not isinstance(row[8], dict):
        return False
    if isinstance(row[8], dict) and "flight" in row[8] and not isinstance(row[8]["flight"], str):
        return False
    return True


def audit_trace(envelope, day):
    """Split, never stitch: bounded source legs, stale and ground boundaries."""
    reasons = Counter()
    metrics = Counter()
    segments = []
    segment = []
    last_call = None
    source_time = envelope["timestamp"]
    def flush():
        nonlocal segment, last_call
        if segment:
            segments.append(segment)
            segment = []
            last_call = None

    for raw in envelope["trace"]:
        metrics["rows_seen"] += 1
        if not valid_raw(raw):
            reasons["invalid_or_nonfinite_row"] += 1
            flush()
            continue
        t, lat, lon = source_time + raw[0], raw[1], raw[2]
        flags = raw[6]
        call = (raw[8].get("flight") or "").strip() if isinstance(raw[8], dict) else ""
        if flags & 2:
            if segment:
                reasons["new_source_leg"] += 1
            flush()
        if flags & 1:
            reasons["stale"] += 1
            flush()
            continue
        if raw[3] == "ground":
            reasons["ground"] += 1
            flush()
            continue
        if segment:
            last_t, last_lat, last_lon = segment[-1]
            if call and last_call and call != last_call:
                reasons["callsign_change"] += 1
                flush()
            elif t <= last_t or t - last_t > route.MAX_GAP_S:
                reasons["gap_or_nonmonotonic"] += 1
                flush()
            elif route.haversine((last_lat, last_lon), (lat, lon)) > route.MAX_STEP_KM:
                reasons["implausible_jump"] += 1
                flush()
        if call:
            last_call = call
        segment.append((t, lat, lon))
        if len(segment) > route.MAX_POINTS:
            # Original comparator refuses >2000 points per leg.
            reasons["short_or_sparse"] += 1
            flush()
        if len(segments) > MAX_SEGS_PER_TRACE:
            raise AuditError("selected_trace_excessive_fragmentation")
    flush()
    midnight = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc).timestamp()
    for points in segments:
        metrics["candidate_segments"] += 1
        if points[0][0] < midnight or points[-1][0] >= midnight + 86400:
            reasons["timestamp_outside_day"] += 1
            continue
        if len(points) < route.MIN_POINTS or points[-1][0] - points[0][0] < route.MIN_DURATION_S:
            reasons["short_or_sparse"] += 1
            continue
        distance = sum(route.haversine((a[1], a[2]), (b[1], b[2]))
                       for a, b in zip(points, points[1:]))
        if distance < 5:
            reasons["short_or_sparse"] += 1
            continue
        metrics["valid_leg_candidates"] += 1
        reasons["valid_leg_candidate"] += 1
    return metrics, reasons


def scan_day(parts, day, *, max_bytes=MAX_SCAN_BYTES, max_seconds=MAX_RUN_S):
    """Read full local split TAR with precommitted selection and fail-closed QA."""
    target = route.date_of(day)
    if not 512 <= max_bytes <= MAX_SCAN_BYTES or not 1 <= max_seconds <= MAX_RUN_S:
        raise AuditError("invalid_scan_budget")
    source_size, _, asset = archive.archive_parts(parts, day)
    reader = archive.BoundedSplitReader(parts, max_bytes, max_seconds)
    counts, reasons = Counter(), Counter()
    start = time.monotonic()
    status, failure, selected_bytes = "unavailable", None, 0
    tar_complete = False
    try:
        while True:
            header = reader.read(512)
            if not header:
                raise archive.IncompleteScan("missing_tar_end_marker")
            if len(header) != 512:
                raise archive.IncompleteScan("truncated_tar_header")
            if header == b"\0" * 512:
                if reader.exact(512) != b"\0" * 512:
                    raise archive.IncompleteScan("missing_second_end_marker")
                while True:
                    tail = reader.read(archive.MAX_READ)
                    if not tail:
                        break
                    if any(tail):
                        raise archive.IncompleteScan("nonzero_tail_after_end_marker")
                tar_complete = True
                status = ("source_sample_audited_review_required"
                          if counts["sampled_decoded_traces"] > 0 else "insufficient_sample")
                break
            counts["tar_members"] += 1
            if counts["tar_members"] > MAX_TAR_MEMBERS:
                raise archive.BudgetStop("tar_member_limit_exceeded")
            try:
                member = tarfile.TarInfo.frombuf(header, "utf-8", "surrogateescape")
            except (tarfile.TarError, ValueError, OverflowError) as exc:
                raise archive.IncompleteScan("invalid_tar_header") from exc
            if (member.size < 0 or member.name.startswith("/")
                    or ".." in member.name.split("/")):
                raise AuditError("unsafe_tar_member")
            if member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME,
                               tarfile.GNUTYPE_LONGLINK):
                raise AuditError("unsupported_tar_extension")
            name = member.name.removeprefix("./")
            match = archive.TRACE_PATTERN.fullmatch(name)
            if match:
                counts["source_trace_members"] += 1
            if not match or not hashed_selection(match[1].lower()):
                reader.skip(member.size + (-member.size) % 512)
                continue
            counts["selected_trace_members"] += 1
            if counts["selected_trace_members"] > MAX_SAMPLE_TRACES:
                raise archive.BudgetStop("sample_trace_count_limit")
            if not member.isfile() or member.issparse():
                raise AuditError("sampled_trace_not_regular_file")
            if member.size > MAX_SAMPLE_BYTES:
                counts["sampled_oversized_members"] += 1
                reader.skip(member.size + (-member.size) % 512)
                continue
            remaining, blocks = member.size, []
            while remaining:
                block = reader.exact(min(remaining, archive.MAX_READ))
                remaining -= len(block)
                blocks.append(block)
            reader.skip((-member.size) % 512)
            try:
                envelope, decoded_size = archive.read_selected(
                    b"".join(blocks), name, match[1].lower()
                )
            except (archive.ScanError, MemoryError, OverflowError) as exc:
                counts["sampled_decode_failures"] += 1
                continue
            selected_bytes += decoded_size
            if selected_bytes > MAX_DECODED_BYTES:
                raise archive.BudgetStop("sample_decoded_byte_limit")
            if len(envelope["trace"]) > MAX_ROWS_PER_TRACE:
                counts["sampled_oversized_row_counts"] += 1
                continue
            counts["sampled_decoded_traces"] += 1
            quality, exclusions = audit_trace(envelope, target)
            counts.update(quality)
            reasons.update(exclusions)
    except archive.IncompleteScan as exc:
        status, failure = "incomplete_archive", str(exc)
    except (AuditError, archive.ScanError, OSError, tarfile.TarError, MemoryError, OverflowError) as exc:
        status, failure = "unavailable", str(exc) if isinstance(exc, (AuditError, archive.ScanError)) else "unreadable_local_archive"
    finally:
        reader.close()
    complete = tar_complete
    # Partial readings may be indicative of cost but never yield a success count.
    return {
        "schema": SCHEMA, "status": status, "reason": failure,
        "source_date": day, "source": "ADSB.lol",
        "source_asset": asset, "source_license": "ODbL-1.0",
        "attribution": "ADSB.lol contributors",
        "selection_rule": "sha256_fixed_salt_mod_1024_eq_0",
        "selection_rule_frozen_before_this_scan": True,
        "historically_prospective_warning": False,
        "selection_target_day_independent": True,
        "sample_fraction_design": "1/1024_of_icao_identities",
        "decoded_sample_adequate": complete and counts["sampled_decoded_traces"] > 0,
        "source_archive_complete": complete,
        "receiver_coverage_verified": False,
        "route_classification_verified": False,
        "sample_is_usable_route_cohort": False,
        "changes_warning_status": False, "raw_geometry_saved": False,
        "selected_identities_released": False,
        "input_file_bytes": source_size,
        "bytes_read": reader.bytes_read,
        "stream_sha256": reader.digest.hexdigest(),
        "wall_seconds": round(time.monotonic() - start, 4),
        "python_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "measurement_scope": "local scan process; download costs excluded",
        "counts": dict(counts) if complete else None,
        "leg_exclusions": {reason: reasons[reason] for reason in REASONS} if complete else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--part", type=Path, action="append", required=True)
    parser.add_argument("--max-bytes", type=int, default=MAX_SCAN_BYTES)
    parser.add_argument("--max-seconds", type=int, default=MAX_RUN_S)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report, result = None, 1
    try:
        report = scan_day(args.part, args.date, max_bytes=args.max_bytes,
                          max_seconds=args.max_seconds)
        result = 0 if report["source_archive_complete"] else 1
    except (AuditError, archive.ScanError, route.InputError, OSError, TypeError, OverflowError) as exc:
        report = {
            "schema": SCHEMA, "status": "unavailable",
            "reason": str(exc) if isinstance(exc, (AuditError, archive.ScanError, route.InputError))
                      else "invalid_local_input",
            "source_date": args.date, "source_archive_complete": False,
            "receiver_coverage_verified": False, "counts": None,
            "raw_geometry_saved": False, "changes_warning_status": False,
        }
    try:
        route.write_atomic(args.output, report)
    except OSError:
        return 1
    print(f"{report['status']}: {args.output}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
