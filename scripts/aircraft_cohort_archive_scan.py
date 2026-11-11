#!/usr/bin/env python3
"""Bounded, offline, selective scan of locally supplied split ADSB.lol TARs.

This does not download archives, infer flight routes, authorize completeness
of ADS-B reception, publish geometry, or create detector-ready observations.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import tarfile
import time
import sys

# Support both 'python -m scripts.module' and documented direct script invocation.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import aircraft_archive_probe as probe
from scripts import aircraft_route_history as route

REPORT_SCHEMA = "aiba.aircraft-cohort-archive-scan.v1"
CANDIDATE_SCHEMA = "aiba.aircraft-cohort-review-input.v1"
DEFAULT_SCAN_BYTES = 64 * 1024 * 1024
HARD_SCAN_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_SECONDS = 60
MAX_SECONDS = 600
MAX_MEMBERS = 800000
MAX_SELECTED_TRACES = 100
MAX_SELECTED_JSON = 2 * 1024 * 1024
MAX_SELECTED_TOTAL = 24 * 1024 * 1024
MAX_READ = 1024 * 1024
PART_PATTERN = re.compile(
    r"v(\d{4})\.(\d{2})\.(\d{2})-planes-readsb-(prod-[01]|staging-0)\.tar\.([a-z]{2})\Z"
)
TRACE_PATTERN = probe.TRACE_NAME


class ScanError(ValueError):
    pass


class IncompleteScan(ScanError):
    """A valid full-archive claim is not supported."""


class BudgetStop(IncompleteScan):
    pass


class BoundedSplitReader:
    """Small-chunk sequential reader; no concatenated archive materialization."""

    def __init__(self, parts, limit, deadline):
        self.parts = parts
        self.limit = limit
        self.deadline = time.monotonic() + deadline
        self.index = 0
        self.handle = None
        self.bytes_read = 0
        self.digest = hashlib.sha256()

    def read(self, count):
        if count < 0 or count > MAX_READ:
            raise ScanError("Invalid bounded reader request")
        if time.monotonic() >= self.deadline:
            raise BudgetStop("scan_time_budget_exhausted")
        if self.bytes_read + count > self.limit:
            raise BudgetStop("scan_byte_budget_exhausted")
        result = bytearray()
        while len(result) < count:
            if time.monotonic() >= self.deadline:
                raise BudgetStop("scan_time_budget_exhausted")
            if self.handle is None:
                if self.index >= len(self.parts):
                    break
                self.handle = self.parts[self.index].open("rb")
                self.index += 1
            block = self.handle.read(count - len(result))
            if block:
                result.extend(block)
            else:
                self.handle.close()
                self.handle = None
        payload = bytes(result)
        self.digest.update(payload)
        self.bytes_read += len(payload)
        return payload

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def exact(self, count):
        data = self.read(count)
        if len(data) != count:
            raise IncompleteScan("truncated_archive_member_or_header")
        return data

    def skip(self, count):
        while count:
            n = min(count, MAX_READ)
            self.exact(n)
            count -= n


def archive_parts(paths, day):
    """Only one sequential set of same-date split production/staging parts."""
    if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
        raise ScanError("Specify 1–32 local TAR split parts")
    date = route.date_of(day)
    expected_prefix, sequence, names = None, [], set()
    total = 0
    for part in paths:
        if not part.is_file() or part.is_symlink():
            raise ScanError("Source archive part missing or symlinked")
        match = PART_PATTERN.fullmatch(part.name)
        if not match or (int(match[1]), int(match[2]), int(match[3])) != (
            date.year, date.month, date.day
        ):
            raise ScanError("Archive part name does not match requested source date")
        prefix = part.name[:-2]
        if expected_prefix is None:
            expected_prefix = prefix
        if prefix != expected_prefix or part.name in names:
            raise ScanError("Mixed or duplicated archive parts")
        names.add(part.name)
        sequence.append(match[5])
        total += part.stat().st_size
    for i, suffix in enumerate(sequence):
        desired = chr(97 + i // 26) + chr(97 + i % 26)
        if suffix != desired:
            raise ScanError("Archive parts must be supplied in contiguous aa, ab order")
    return total, sequence[0], expected_prefix[:-5]  # remove '.tar.'


def selected_ids(manifest, day):
    target = route.date_of(day)
    groups, _ = route.validate_manifest(manifest, target)
    selected = {icao for group in groups.values() for icao in group["aircraft_set"]}
    if len(selected) > MAX_SELECTED_TRACES:
        raise ScanError("Selected ICAO set exceeds 100 identities")
    return selected, len(groups)


def read_selected(data, name, identity):
    if len(data) > MAX_SELECTED_JSON:
        raise ScanError("Selected trace member exceeds 2 MiB limit")
    if name.endswith(".gz") or data.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                data = stream.read(MAX_SELECTED_JSON + 1)
        except (OSError, EOFError) as exc:
            raise ScanError("Malformed compressed selected trace") from exc
    if len(data) > MAX_SELECTED_JSON:
        raise ScanError("Expanded selected trace exceeds 2 MiB limit")
    try:
        envelope = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ScanError("Malformed selected JSON") from exc
    if (not isinstance(envelope, dict) or envelope.get("icao") != identity
            or not probe.finite(envelope.get("timestamp"))
            or envelope["timestamp"] <= 0
            or not isinstance(envelope.get("trace"), list)
            or len(envelope["trace"]) > probe.MAX_ROWS):
        raise ScanError("Unsupported selected readsb trace envelope")
    return envelope, len(data)


def scan(parts, manifest, date, max_bytes=DEFAULT_SCAN_BYTES,
         max_seconds=DEFAULT_SECONDS, *, clock=time.monotonic):
    if not 512 <= max_bytes <= HARD_SCAN_BYTES or not 1 <= max_seconds <= MAX_SECONDS:
        raise ScanError("Invalid scan byte/time limits")
    selected, groups = selected_ids(manifest, date)
    available_bytes, _, asset = archive_parts(parts, date)
    reader = BoundedSplitReader(parts, max_bytes, max_seconds)
    report = {
        "schema": REPORT_SCHEMA, "status": "unavailable",
        "source_date": date, "source": "ADSB.lol",
        "asset": asset, "license": "ODbL-1.0",
        "attribution": "ADSB.lol contributors",
        "scope": "preselected_cohort_offline_not_global",
        "archive_complete": False, "receiver_coverage_verified": False,
        "input_provenance": "caller_supplied_local_parts",
        "parts_supplied": len(parts),
        "input_file_bytes": available_bytes,
        "max_scan_bytes": max_bytes, "max_scan_seconds": max_seconds,
        "selected_aircraft_count": len(selected), "cohort_groups": groups,
        "scanned_tar_members": 0, "scanned_trace_members": 0,
        "selected_trace_members": 0, "selected_expanded_bytes": 0,
    }
    selected_traces, seen = [], set()
    started = clock()
    try:
        while True:
            header = reader.read(512)
            if not header:
                raise IncompleteScan("missing_two_block_tar_terminator")
            if len(header) != 512:
                raise IncompleteScan("truncated_archive_header")
            if header == b"\0" * 512:
                if reader.exact(512) != b"\0" * 512:
                    raise IncompleteScan("missing_second_tar_terminator")
                # An early zero marker followed by additional nonzero bytes is
                # not the end of a trustworthy complete TAR.
                while True:
                    trailing = reader.read(MAX_READ)
                    if not trailing:
                        break
                    if any(trailing):
                        raise IncompleteScan("nonzero_bytes_after_tar_terminator")
                report["archive_complete"] = True
                report["status"] = "archive_scanned_review_required"
                break
            report["scanned_tar_members"] += 1
            if report["scanned_tar_members"] > MAX_MEMBERS:
                raise BudgetStop("archive_member_budget_exhausted")
            try:
                member = tarfile.TarInfo.frombuf(header, "utf-8", "surrogateescape")
            except (tarfile.TarError, ValueError, OverflowError) as exc:
                raise IncompleteScan("invalid_tar_header_or_checksum") from exc
            if (member.size < 0 or member.name.startswith("/")
                    or ".." in member.name.split("/")):
                raise ScanError("Unsafe or unsupported TAR member")
            if member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE,
                               tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
                raise ScanError("Extended TAR metadata requires explicit parser support")
            name = member.name.removeprefix("./")
            match = TRACE_PATTERN.fullmatch(name)
            if match:
                report["scanned_trace_members"] += 1
            if match and match[1].lower() in selected:
                identity = match[1].lower()
                if not member.isfile() or member.issparse():
                    raise ScanError("Selected TAR member is not a regular file")
                if identity in seen:
                    raise ScanError("Duplicate selected aircraft trace")
                seen.add(identity)
                if member.size > MAX_SELECTED_JSON:
                    raise ScanError("Selected trace exceeds member limit")
                # Selected JSON may be up to 2 MiB while each individual
                # reader operation is capped at 1 MiB. Read in bounded chunks.
                remaining, chunks = member.size, []
                while remaining:
                    chunk = reader.exact(min(remaining, MAX_READ))
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
                envelope, decoded_size = read_selected(raw, name, identity)
                if report["selected_expanded_bytes"] + decoded_size > MAX_SELECTED_TOTAL:
                    raise BudgetStop("selected_output_budget_exhausted")
                selected_traces.append({"aircraft_id": identity, "readsb": envelope,
                                        "flight_leg_review": "required",
                                        "receiver_coverage": "unverified"})
                report["selected_trace_members"] += 1
                report["selected_expanded_bytes"] += decoded_size
                padding = (-member.size) % 512
                reader.skip(padding)
            else:
                reader.skip(member.size + (-member.size) % 512)
    except IncompleteScan as exc:
        report["status"] = "incomplete_archive"
        report["reason"] = str(exc)
        report["archive_complete"] = False
        selected_traces = []  # Cannot release an apparently complete cohort.
    except (OSError, tarfile.TarError, ScanError, OverflowError, MemoryError) as exc:
        report["status"] = "unavailable"
        report["reason"] = str(exc) if isinstance(exc, ScanError) else "Local archive unreadable"
        report["archive_complete"] = False
        selected_traces = []
    finally:
        reader.close()
        report["scanned_bytes"] = reader.bytes_read
        report["scanned_sha256"] = reader.digest.hexdigest()
        report["elapsed_seconds"] = round(clock() - started, 6)
        report["python_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["measurement_scope"] = "local TAR bytes read, process wall time and Python peak RSS; network and storage costs excluded"
    candidate = {
        "schema": CANDIDATE_SCHEMA, "status": "review_required" if report["archive_complete"] else report["status"],
        "source_date": date, "source": "ADSB.lol",
        "archive_scanned_complete": report["archive_complete"],
        "detector_input_ready": False, "coverage": "unverified",
        "license": "ODbL-1.0", "attribution": "ADSB.lol contributors",
        "aircraft_traces": selected_traces if report["archive_complete"] else [],
    }
    return report, candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--part", action="append", required=True, type=Path,
                        help="Local part in ordered .tar.aa, .tar.ab sequence; repeat")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_SCAN_BYTES)
    parser.add_argument("--max-seconds", type=int, default=DEFAULT_SECONDS)
    parser.add_argument("--report", type=Path, required=True,
                        help="Aggregate local measurement receipt (no track points)")
    parser.add_argument("--candidates-output", type=Path,
                        help="Optional local raw selected traces for human leg/route review")
    args = parser.parse_args(argv)
    status, code = "unavailable", 1
    report = {"schema": REPORT_SCHEMA, "status": "unavailable", "source_date": args.date,
              "archive_complete": False}
    candidate = {"schema": CANDIDATE_SCHEMA, "status": "unavailable",
                 "detector_input_ready": False, "aircraft_traces": []}
    candidate_path_allowed = False
    try:
        root = Path(__file__).resolve().parents[1]
        candidate_path_allowed = (
            args.candidates_output is None
            or not args.candidates_output.resolve().is_relative_to(root)
        )
        if not candidate_path_allowed:
            raise ScanError("Raw selected traces must be written outside the Git checkout")
        manifest = route.read_json(args.cohort)
        report, candidate = scan(args.part, manifest, args.date,
                                 args.max_bytes, args.max_seconds)
        status = report["status"]
        code = 0 if report["archive_complete"] else 1
    except (ScanError, route.InputError, OSError, TypeError, OverflowError) as exc:
        report["reason"] = str(exc) if isinstance(exc, (ScanError, route.InputError)) else "Local input unavailable"
    try:
        route.write_atomic(args.report, report)
        if args.candidates_output and candidate_path_allowed:
            route.write_atomic(args.candidates_output, candidate)
    except OSError:
        print("Cannot write local scan receipts")
        return 1
    print(f"{status}: {args.report}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
