#!/usr/bin/env python3
"""Bounded ADSB.lol archive-input experiment; no anomaly scoring or scheduling.

Reads a prefix of the first production tar part and summarizes complete trace
members only. Never extracts archive paths or publishes individual positions.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import resource
import subprocess
import sys
import tarfile
import tempfile
import time


DEFAULT_BYTES = 262144
MAX_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ROWS = 250000
TRACE_NAME = re.compile(r"traces/[0-9a-f]{2}/trace_full_(~?[0-9a-f]{6})\.json(?:\.gz)?", re.I)
COUNT_KEYS = (
    "aircraft_files", "position_rows", "valid_position_rows", "invalid_position_rows",
    "source_marked_stale_rows", "source_leg_start_markers", "rows_with_callsign_metadata",
    "rows_with_ground_altitude",
)


class ProbeError(ValueError):
    """Input, transport or resource bound prevents a usable sample."""


def source_url(day):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ProbeError("Source date must be YYYY-MM-DD")
    try:
        date = dt.date.fromisoformat(day)
    except ValueError as exc:
        raise ProbeError("Invalid source date") from exc
    tag = f"v{date:%Y.%m.%d}-planes-readsb-prod-0"
    return f"https://github.com/adsblol/globe_history_{date.year}/releases/download/{tag}/{tag}.tar.aa"


def download_prefix(url, size, timeout):
    """curl honors proxy/CA settings; refuse servers ignoring the byte range.

    Both curl's transfer deadline and maximum file size apply before parsing.
    Redirects remain HTTPS. No credentials or arbitrary URL override are used.
    """
    with tempfile.TemporaryDirectory(prefix="aiba-aircraft-") as directory:
        output, headers = Path(directory) / "prefix", Path(directory) / "headers"
        command = [
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--proto", "=https", "--proto-redir", "=https",
            "--max-time", str(timeout), "--max-filesize", str(size),
            "--range", f"0-{size - 1}", "--dump-header", str(headers),
            "--output", str(output), "--write-out", "%{http_code}", url,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=timeout + 5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProbeError("Download unavailable: curl missing or transfer timed out") from exc
        if result.returncode:
            # Do not copy request diagnostics, proxy details or credential URLs.
            raise ProbeError(f"Download failed (curl exit {result.returncode})")
        if result.stdout.strip() != "206":
            raise ProbeError("Source did not honor the byte range (HTTP 206 required)")
        raw_headers = headers.read_text().replace("\r\n", "\n").strip().split("\n\n")[-1]
        fields = {k.lower().strip(): v.strip() for line in raw_headers.splitlines()
                  if ":" in line for k, v in [line.split(":", 1)]}
        content_range = fields.get("content-range", "")
        match = re.fullmatch(r"bytes 0-(\d+)/(\d+)", content_range)
        with output.open("rb") as stream:
            data = stream.read(size + 1)
        if (not match or len(data) != size or int(match[1]) != size - 1
                or int(match[2]) < size):
            raise ProbeError("Incomplete or inconsistent range response")
        return data, {"http_status": 206, "content_range": content_range}


def finite(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def summarize(data, max_files=25):
    if not 512 <= len(data) <= MAX_BYTES:
        raise ProbeError("Input prefix must be between 512 bytes and 16 MiB")
    if not 1 <= max_files <= 100:
        raise ProbeError("File limit must be between 1 and 100")
    counts = Counter({key: 0 for key in COUNT_KEYS})
    seen, members, next_header = set(), 0, 0
    stop_reason = "tar_end_in_sample"
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            while True:
                if len(data) - next_header < 512:
                    stop_reason = "prefix_boundary"
                    break
                header = data[next_header:next_header + 512]
                if header == b"\0" * 512:
                    break
                # tarfile can otherwise treat a damaged later header as EOF.
                # Verify every visible header, not just the first member.
                tarfile.TarInfo.frombuf(header, "utf-8", "surrogateescape")
                member = archive.next()
                if member is None:
                    raise ProbeError("Unexpected end of archive metadata")
                next_header = archive.offset
                members += 1
                if members > 10000:
                    raise ProbeError("Archive member limit exceeded")
                if member.size < 0:
                    raise ProbeError("Invalid member size")
                if member.offset_data + member.size > len(data):
                    stop_reason = "incomplete_member_at_prefix_boundary"
                    break
                name = member.name.removeprefix("./")
                if name.startswith("/") or ".." in name.split("/"):
                    raise ProbeError("Unsafe archive member path")
                match = TRACE_NAME.fullmatch(name)
                if not match:
                    continue
                if not member.isfile() or member.issparse():
                    raise ProbeError("Trace member is not an ordinary file")
                identity = match[1].lower()
                if identity in seen:
                    raise ProbeError("Duplicate aircraft member in sample")
                seen.add(identity)
                if member.size > MAX_JSON_BYTES:
                    raise ProbeError("Trace member exceeds size limit")
                raw = archive.extractfile(member).read(MAX_JSON_BYTES + 1)
                if raw.startswith(b"\x1f\x8b"):
                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                        raw = compressed.read(MAX_JSON_BYTES + 1)
                if len(raw) > MAX_JSON_BYTES:
                    raise ProbeError("Expanded trace exceeds size limit")
                trace = json.loads(raw)
                if (not isinstance(trace, dict) or trace.get("icao", "").lower() != identity
                        or not finite(trace.get("timestamp")) or trace["timestamp"] <= 0
                        or not isinstance(trace.get("trace"), list)):
                    raise ProbeError("Unsupported aircraft trace envelope")
                rows = trace["trace"]
                if counts["position_rows"] + len(rows) > MAX_ROWS:
                    raise ProbeError("Position-row limit exceeded")
                counts["aircraft_files"] += 1
                counts["position_rows"] += len(rows)
                for row in rows:
                    if (not isinstance(row, list) or len(row) < 9
                            or not all(finite(row[i]) for i in (0, 1, 2))
                            or row[0] < 0 or not -90 <= row[1] <= 90 or not -180 <= row[2] <= 180
                            or not isinstance(row[6], int) or isinstance(row[6], bool) or row[6] < 0):
                        counts["invalid_position_rows"] += 1
                        continue
                    counts["valid_position_rows"] += 1
                    counts["source_marked_stale_rows"] += bool(row[6] & 1)
                    counts["source_leg_start_markers"] += bool(row[6] & 2)
                    counts["rows_with_ground_altitude"] += row[3] == "ground"
                    counts["rows_with_callsign_metadata"] += bool(
                        isinstance(row[8], dict) and isinstance(row[8].get("flight"), str)
                        and row[8]["flight"].strip())
                if counts["aircraft_files"] >= max_files:
                    stop_reason = "file_limit"
                    break
    except ProbeError:
        raise
    except (tarfile.TarError, ValueError, UnicodeError, OSError,
            EOFError, RecursionError, AttributeError) as exc:
        raise ProbeError("Malformed archive or trace data") from exc
    if not counts["valid_position_rows"]:
        raise ProbeError("No usable complete aircraft traces in prefix; sample is not a valid empty day")
    return {"counts": dict(counts), "stop_reason": stop_reason}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Source day, YYYY-MM-DD")
    parser.add_argument("--archive-prefix", type=Path, help="Read a local prefix instead of downloading")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_BYTES)
    parser.add_argument("--max-files", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=30, help="Network deadline in seconds (1–120)")
    parser.add_argument("--output", type=Path, required=True, help="Local summary receipt, not raw positions")
    args = parser.parse_args(argv)
    started, cpu_started = time.monotonic(), time.process_time()
    report = {"schema": "aiba.aircraft-archive-probe.v1", "status": "unavailable",
              "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source_date": args.date, "sample_only": True,
              "coverage": "archive_order_prefix_not_worldwide_monitoring",
              "anomaly_scoring": "not_implemented", "license": "ODbL-1.0",
              "attribution": "ADSB.lol contributors"}
    exit_code = 1
    try:
        url = source_url(args.date)
        if not 512 <= args.max_bytes <= MAX_BYTES or not 1 <= args.timeout <= 120:
            raise ProbeError("Byte limit must be 512–16777216; timeout must be 1–120 seconds")
        if not 1 <= args.max_files <= 100:
            raise ProbeError("File limit must be between 1 and 100")
        report["source_asset"] = url
        report["limits"] = {"prefix_bytes": args.max_bytes, "aircraft_files": args.max_files,
                            "json_bytes_per_file": MAX_JSON_BYTES, "position_rows": MAX_ROWS,
                            "download_seconds": args.timeout}
        if args.archive_prefix:
            # Reading remains bounded even if the file changes after stat().
            with args.archive_prefix.open("rb") as stream:
                data = stream.read(args.max_bytes + 1)
            if len(data) > args.max_bytes:
                raise ProbeError("Local prefix exceeds configured byte limit")
            report["transport"] = {"mode": "local_prefix", "source_provenance": "caller_supplied"}
        else:
            data, transport = download_prefix(url, args.max_bytes, args.timeout)
            report["transport"] = {"mode": "https_range", **transport}
        report.update(summarize(data, args.max_files))
        report["input_bytes"] = len(data)
        report["prefix_sha256"] = hashlib.sha256(data).hexdigest()
        report["status"] = "input_sample_readable"
        exit_code = 0
    except (ProbeError, OSError) as exc:
        report["error"] = str(exc) if isinstance(exc, ProbeError) else "Local input/output unavailable"
    usage = resource.getrusage(resource.RUSAGE_SELF)
    report["measurement"] = {
        "wall_seconds": round(time.monotonic() - started, 6),
        "python_cpu_seconds": round(time.process_time() - cpu_started, 6),
        "python_peak_rss_kib": usage.ru_maxrss,
        "measurement_scope": "Linux Python process; curl child CPU/RSS and network headers excluded",
    }
    # Replace a previous success with an explicit failure receipt; never leave a
    # successful zero-anomaly report behind after input failure.
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=args.output.parent,
                                         prefix=".aircraft-probe-", delete=False) as staged:
            temporary = Path(staged.name)
            json.dump(report, staged, indent=2, allow_nan=False)
            staged.write("\n")
        temporary.replace(args.output)
    except OSError:
        print("Cannot write probe receipt", file=sys.stderr)
        return 1
    print(f"{report['status']}: {args.output}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
