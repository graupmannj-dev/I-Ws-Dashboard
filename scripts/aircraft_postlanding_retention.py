#!/usr/bin/env python3
"""Conservative post-landing aircraft track archival copy (offline pilot).

No source deletion, public track publication, scheduling, network, alert change
or inference that a route near an airway is a confirmed normal flight.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aircraft_route_history as route

INPUT_SCHEMA = "aiba.aircraft-retention-candidate.v1"
ARCHIVE_SCHEMA = "aiba.aircraft-postlanding-archive.v1"
RECEIPT_SCHEMA = "aiba.aircraft-postlanding-retention-receipt.v1"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_POINTS = 12000
MAX_TIME_GAP_S = 600
MAX_POSITION_ERROR_KM = 2.0
MAX_ALTITUDE_ERROR_FT = 500.0
COMPRESS_LEVEL = 9
MIN_POINTS = 6
MIN_DURATION_S = 900
OUTPUT_SUFFIX = ".json.gz"
# These are conservative engineering defaults, not calibrated to rare-event loss.
# Retention remains copy-only until independent heldout loss audits.


class RetentionError(ValueError):
    pass


def load_input(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_INPUT_BYTES:
        raise RetentionError("missing_untrusted_or_oversized_input")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError, OSError) as exc:
        raise RetentionError("invalid_source_json") from exc


def epoch(value):
    return route.number(value) and 0 < value < 5000000000


def validate_gate(doc):
    if not isinstance(doc, dict) or doc.get("schema") != INPUT_SCHEMA:
        raise RetentionError("wrong_retention_input_schema")
    if doc.get("source") != "ADSB.lol" or not route.ident(doc.get("flight_id")):
        raise RetentionError("invalid_source_or_flight_identity")
    g = doc.get("gate")
    if not isinstance(g, dict):
        raise RetentionError("missing_postflight_review_gate")
    # Automatic published-airway proximity is NOT equivalent to verified
    # normality. Historical context AND an explicit review are prerequisites.
    prerequisites = (
        ("landed_verified", True),
        ("leg_closed", True),
        ("source_coverage", "complete"),
        ("screening_complete", True),
        ("historical_status", "within_reference"),
        ("airway_status", "network_proximity_only"),
        ("analyst_review", "normal_reviewed"),
        ("retention_approved", True),
        ("unresolved_indicators", 0),
        ("open_tippers", 0),
    )
    for field, expected in prerequisites:
        if type(g.get(field)) is not type(expected) or g.get(field) != expected:
            raise RetentionError("retention_gate_not_met_" + field)
    reviewer = g.get("reviewer_id")
    if not isinstance(reviewer, str) or not route.ident(reviewer):
        raise RetentionError("missing_named_reviewer_provenance")
    if not isinstance(g.get("review_note"), str) or len(g["review_note"].strip()) < 20:
        raise RetentionError("missing_review_reason_and_context")
    landing = g.get("landing_ground_observed_at")
    closed = g.get("flight_closed_asof")
    reviewed = g.get("reviewed_asof")
    if not all(epoch(value) for value in (landing, closed, reviewed)):
        raise RetentionError("missing_landing_or_review_times")
    if not landing <= closed <= reviewed:
        raise RetentionError("review_or_closure_precedes_landing")
    return g


def validate_positions(doc):
    points = doc.get("points")
    if not isinstance(points, list) or not MIN_POINTS <= len(points) <= MAX_POINTS:
        raise RetentionError("invalid_position_count")
    cleaned = []
    for p in points:
        if not isinstance(p, dict):
            raise RetentionError("invalid_position_row")
        if set(p) != {"t", "lat", "lon", "altitude_ft"}:
            # Undocumented ADS-B metadata and event flags must not silently
            # disappear. Introduce an audited converter before accepting them.
            raise RetentionError("unsupported_position_fields_may_be_evidence")
        t, lat, lon, alt = (p.get(name) for name in ("t", "lat", "lon", "altitude_ft"))
        if (not epoch(t) or not all(route.number(x) for x in (lat, lon, alt))
                or not -90 <= lat <= 90 or not -180 <= lon <= 180
                or not -1500 <= alt <= 65000):
            raise RetentionError("nonfinite_or_implausible_position")
        cleaned.append((t, lat, lon, alt))
    for a, b in zip(cleaned, cleaned[1:]):
        if b[0] <= a[0] or b[0] - a[0] > MAX_TIME_GAP_S:
            raise RetentionError("source_gap_or_nonmonotonic_track")
        if route.haversine((a[1], a[2]), (b[1], b[2])) > route.MAX_STEP_KM:
            raise RetentionError("implausible_position_jump")
    if cleaned[-1][0] - cleaned[0][0] < MIN_DURATION_S:
        raise RetentionError("inadequate_flight_duration")
    g = doc["gate"]
    if not cleaned[-1][0] <= g["landing_ground_observed_at"]:
        raise RetentionError("last_position_after_verified_ground_time")
    if g["reviewed_asof"] <= cleaned[-1][0]:
        raise RetentionError("review_precedes_last_position")
    return cleaned


def interpolation_residual(p, a, b):
    if not a[0] < b[0]:
        raise RetentionError("invalid_interpolation_order")
    fraction = (p[0] - a[0]) / (b[0] - a[0])
    # Unwrap only the local longitude delta; safe across antimeridian.
    lon_delta = (b[2] - a[2] + 180) % 360 - 180
    interpolated_lon = (a[2] + fraction * lon_delta + 180) % 360 - 180
    position_error = route.haversine((p[1], p[2]), (
        a[1] + fraction * (b[1] - a[1]), interpolated_lon))
    altitude_error = abs(p[3] - (a[3] + fraction * (b[3] - a[3])))
    return position_error, altitude_error


def select_positions(points, *, interval_s=MAX_TIME_GAP_S,
                     max_error_km=MAX_POSITION_ERROR_KM,
                     max_alt_error_ft=MAX_ALTITUDE_ERROR_FT):
    if (not isinstance(interval_s, int) or isinstance(interval_s, bool)
            or not 30 <= interval_s <= MAX_TIME_GAP_S):
        raise RetentionError("invalid_max_sample_interval")
    if not route.number(max_error_km) or not 0 < max_error_km <= 2:
        raise RetentionError("invalid_position_error_bound")
    if not route.number(max_alt_error_ft) or not 0 < max_alt_error_ft <= 500:
        raise RetentionError("invalid_altitude_error_bound")
    # 10-minute time anchors guarantee no compressed sample gap >600 s
    # (unlike pure RDP). Preserve both endpoints and additional turning
    # or altitude-transition points via iterative bounded-error splitting.
    anchors = [0]
    for index in range(1, len(points) - 1):
        if points[index][0] - points[anchors[-1]][0] >= interval_s:
            anchors.append(index)
    if anchors[-1] != len(points) - 1:
        anchors.append(len(points) - 1)
    selected = set(anchors)
    stack = list(zip(anchors, anchors[1:]))
    while stack:
        first, last = stack.pop()
        if last - first <= 1:
            continue
        worst_index, worst_ratio = None, 1.0
        for i in range(first + 1, last):
            horizontal, vertical = interpolation_residual(points[i], points[first], points[last])
            ratio = max(horizontal / max_error_km, vertical / max_alt_error_ft)
            if ratio > worst_ratio:
                worst_ratio, worst_index = ratio, i
        if worst_index is not None:
            selected.add(worst_index)
            stack.append((first, worst_index))
            stack.append((worst_index, last))
    retained = sorted(selected)
    max_seen_km, max_seen_ft, largest_gap = 0.0, 0.0, 0.0
    for a, b in zip(retained, retained[1:]):
        largest_gap = max(largest_gap, points[b][0] - points[a][0])
        for index in range(a + 1, b):
            horizontal, vertical = interpolation_residual(points[index], points[a], points[b])
            max_seen_km = max(max_seen_km, horizontal)
            max_seen_ft = max(max_seen_ft, vertical)
    if max_seen_km > max_error_km + 1e-9 or max_seen_ft > max_alt_error_ft + 1e-9 or largest_gap > interval_s:
        raise RetentionError("reconstructed_path_exceeds_declared_error_budget")
    return retained, {"max_reconstruction_km": round(max_seen_km, 6),
                      "max_reconstruction_altitude_ft": round(max_seen_ft, 3),
                      "max_retained_gap_seconds": largest_gap}


def compact(doc, *, interval_s=MAX_TIME_GAP_S):
    gate = validate_gate(doc)
    points = validate_positions(doc)
    indices, fidelity = select_positions(points, interval_s=interval_s)
    archived = {
        "schema": ARCHIVE_SCHEMA, "source": "ADSB.lol",
        "retention_tier": "postlanding_normal_reviewed_copy",
        "flight_id": doc["flight_id"],
        "original_point_count": len(points),
        "review_provenance": {
            "reviewer_id": gate["reviewer_id"],
            "review_note": gate["review_note"],
            "reviewed_asof": gate["reviewed_asof"],
            "historical_status": gate["historical_status"],
            "airway_status": gate["airway_status"],
            "landing_ground_observed_at": gate["landing_ground_observed_at"],
        },
        "fidelity": {"max_allowed_position_error_km": MAX_POSITION_ERROR_KM,
                     "max_allowed_altitude_error_ft": MAX_ALTITUDE_ERROR_FT,
                     "target_max_interval_seconds": interval_s, **fidelity},
        "points": [doc["points"][i] for i in indices],
        "original_data_preserved": True,
        "warning_status_unchanged": True,
        "alerts_generated": 0,
    }
    return archived


def write_gzip_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = None
    try:
        encoded = json.dumps(data, separators=(",", ":"), allow_nan=False,
                             ensure_ascii=True).encode("utf-8")
        payload = gzip.compress(encoded, compresslevel=COMPRESS_LEVEL, mtime=0)
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".aiba-retention-",
                                         delete=False) as handle:
            stage = Path(handle.name)
            handle.write(payload)
        stage.replace(path)
        return len(payload), hashlib.sha256(payload).hexdigest()
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path,
                        help="Aggregate receipt; no ID or geometry")
    parser.add_argument("--copy", type=Path,
                        help="Optional PRIVATE .json.gz copy outside the Git checkout")
    parser.add_argument("--interval-seconds", type=int, default=MAX_TIME_GAP_S)
    args = parser.parse_args(argv)
    receipt = {
        "schema": RECEIPT_SCHEMA, "status": "not_eligible",
        "original_data_deleted": False, "source_mutated": False,
        "automatic_deletion_enabled": False,
        "published": False, "changes_aiba_warning_status": False,
        "analyst_review_required": True,
        "compressed_copy_created": False,
    }
    exit_code = 1
    try:
        checkout = Path(__file__).resolve().parents[1]
        if args.copy is not None:
            if args.copy.suffixes[-2:] != [".json", ".gz"]:
                raise RetentionError("private_archive_output_must_end_json_gz")
            if args.copy.resolve().is_relative_to(checkout):
                raise RetentionError("private_archive_must_be_outside_checkout")
            if args.input.resolve() == args.copy.resolve():
                raise RetentionError("cannot_overwrite_original_source")
        if args.input.resolve() == args.receipt.resolve():
            raise RetentionError("receipt_must_not_overwrite_original_source")
        if args.copy is not None and args.copy.resolve() == args.receipt.resolve():
            raise RetentionError("receipt_cannot_replace_private_archive")
        doc = load_input(args.input)
        archive = compact(doc, interval_s=args.interval_seconds)
        receipt["source_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
        receipt["input_bytes"] = args.input.stat().st_size
        receipt["original_points"] = archive["original_point_count"]
        receipt["retained_points"] = len(archive["points"])
        receipt["retained_fraction"] = round(len(archive["points"]) / archive["original_point_count"], 6)
        receipt["geometry_error_bounds"] = archive["fidelity"]
        if args.copy is not None:
            length, digest = write_gzip_atomic(args.copy, archive)
            receipt["compressed_copy_bytes"] = length
            receipt["compressed_copy_sha256"] = digest
            receipt["compressed_copy_created"] = True
        receipt["status"] = "copy_created_original_preserved" if args.copy else "eligible_dry_run_original_preserved"
        exit_code = 0
    except (RetentionError, route.InputError, OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        receipt["status"] = "not_eligible"
        receipt["reason"] = str(exc) if isinstance(exc, (RetentionError, route.InputError)) else "invalid_or_unavailable_input"
    try:
        route.write_atomic(args.receipt, receipt)
    except OSError:
        return 1
    print(f"{receipt['status']}: {args.receipt}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
