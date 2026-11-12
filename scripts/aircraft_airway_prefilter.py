#!/usr/bin/env python3
"""FAA NASR J/Q airway network proximity screen, NOT assigned-route detection.

No network calls, flight downloads, alerts, deployment or automatic publication.
A nearby published ATS route is NOT evidence an aircraft was assigned it.
Outside a published network is NOT evidence of abnormal or hostile behavior.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aircraft_route_history as flight

NETWORK_SCHEMA = "aiba.faa-published-airway-network.v1"
SCREEN_SCHEMA = "aiba.aircraft-published-airway-screen.v1"
INPUT_SCHEMA = "aiba.aircraft-enroute-legs.v1"
FAA_NASR_URL = "https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/"
ROUTE_RE = re.compile(r"(?:J|Q)\d{1,4}\Z")
MAX_CSV_BYTES = 60 * 1024 * 1024
MAX_NETWORK_BYTES = 12 * 1024 * 1024
MAX_FEATURES = 15000
MAX_SEGMENT_KM = 600
MAX_LEGS = 100
MAX_POINTS = 2000
MIN_VALID_POINTS = 6
MAX_BAND_KM = 35
DEFAULT_BAND_KM = 25
COVERAGE_FRACTION = 0.80
GRID_DEGREES = 2
GRID_MARGIN_DEGREES = 2
# Intentionally CONUS only. FAA's larger FIR/oceanic/Alaska datasets
# cannot be represented as a verified global route coverage polygon here.
CONUS = {"lat_min": 24, "lat_max": 50, "lon_min": -125, "lon_max": -66}


class AirwayError(ValueError):
    pass


def load_csv(path, required):
    if not path.is_file() or path.stat().st_size > MAX_CSV_BYTES or path.is_symlink():
        raise AirwayError("missing_or_oversized_local_csv")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise AirwayError("unsupported_nasr_csv_columns")
        return list(reader)


def point(row):
    try:
        lat = float(row["LAT_DECIMAL"])
        lon = float(row["LONG_DECIMAL"])
    except (ValueError, TypeError, KeyError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return (lat, lon)


def in_conus(p):
    return (CONUS["lat_min"] <= p[0] <= CONUS["lat_max"]
            and CONUS["lon_min"] <= p[1] <= CONUS["lon_max"])


def index_points(fixes, navaids, effective):
    locations = defaultdict(list)
    for rows, name in ((fixes, "FIX_ID"), (navaids, "NAV_ID")):
        for row in rows:
            if row.get("EFF_DATE") != effective:
                raise AirwayError("mixed_nasr_data_cycle")
            p = point(row)
            key = row.get(name, "").strip().upper()
            if p and key:
                locations[key].append(p)
    return locations


def resolve(locations, identifier):
    positions = locations.get(identifier.strip().upper(), [])
    if not positions:
        return None
    first = positions[0]
    if any(flight.haversine(first, item) > 2 for item in positions[1:]):
        return None  # ambiguous same-name FIX/NAVAID; never guess
    return first


def nasr_network(awy_csv, fix_csv, nav_csv, effective_from, effective_until):
    """Build a conservative CONUS high-altitude route SEGMENT reference.

    Skips unresolved, gapped, duplicated and geographically ambiguous
    airway edges; never bridges gaps to manufacture a route.
    """
    start = flight.date_of(effective_from)
    stop = flight.date_of(effective_until)
    if stop <= start or (stop - start).days > 56:
        raise AirwayError("nasr_cycle_window_invalid")
    effective = start.strftime("%Y/%m/%d")
    fixes = load_csv(fix_csv, {"FIX_ID", "EFF_DATE", "LAT_DECIMAL", "LONG_DECIMAL"})
    navs = load_csv(nav_csv, {"NAV_ID", "EFF_DATE", "LAT_DECIMAL", "LONG_DECIMAL"})
    routes = load_csv(awy_csv, {"EFF_DATE", "AWY_ID", "POINT_SEQ", "FROM_POINT",
                                "TO_POINT", "AWY_SEG_GAP_FLAG", "SIGNAL_GAP_FLAG", "MEA_GAP"})
    locations = index_points(fixes, navs, effective)
    counters = Counter()
    features, seen = [], set()
    for item in routes:
        counters["all_awy_rows"] += 1
        if item.get("EFF_DATE") != effective:
            raise AirwayError("mixed_nasr_airway_cycle")
        name = item.get("AWY_ID", "").strip().upper()
        if not ROUTE_RE.fullmatch(name):
            continue
        counters["j_q_rows"] += 1
        sequence = item.get("POINT_SEQ", "").strip()
        if not sequence.isdigit():
            counters["invalid_sequence"] += 1
            continue
        key = (name, int(sequence))
        if key in seen:
            counters["duplicate_sequence"] += 1
            continue
        seen.add(key)
        if (item.get("AWY_SEG_GAP_FLAG") != "N" or item.get("SIGNAL_GAP_FLAG") != "N"
                or item.get("MEA_GAP", "").strip() == "U"):
            counters["flagged_route_or_signal_gap"] += 1
            continue
        a = resolve(locations, item.get("FROM_POINT", ""))
        b = resolve(locations, item.get("TO_POINT", ""))
        if a is None or b is None:
            counters["missing_or_ambiguous_fix"] += 1
            continue
        if not in_conus(a) or not in_conus(b):
            counters["outside_conus_scope"] += 1
            continue
        distance = flight.haversine(a, b)
        if not 1 <= distance <= MAX_SEGMENT_KM:
            counters["implausible_or_long_edge"] += 1
            continue
        features.append({
            "route_id": name, "sequence": int(sequence), "route_class": name[0],
            "from_fix": item["FROM_POINT"].strip().upper(),
            "to_fix": item["TO_POINT"].strip().upper(),
            "geometry_lonlat": [[round(a[1], 7), round(a[0], 7)],
                                [round(b[1], 7), round(b[0], 7)]],
        })
        counters["mapped_segments"] += 1
        if len(features) > MAX_FEATURES:
            raise AirwayError("route_reference_feature_limit")
    if not features:
        raise AirwayError("no_resolved_eligible_j_q_edges")
    fingerprints = {}
    for path in (awy_csv, fix_csv, nav_csv):
        h = hashlib.sha256()
        with path.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        fingerprints[path.name] = h.hexdigest()
    return {
        "schema": NETWORK_SCHEMA, "source": "FAA NASR", "scope": "CONUS_J_Q_published_only",
        "source_page": FAA_NASR_URL, "effective_from": effective_from,
        "effective_until_exclusive": effective_until, "scope_bbox": CONUS,
        "source_dataset_completeness_verified": False,
        "flight_plan_assignment_known": False,
        "note": "Published available ATS routes, not expected or cleared individual trajectories",
        "input_sha256": fingerprints, "counts": dict(counters), "features": features,
    }


def validate_network(network, day):
    d = flight.date_of(day)
    if (not isinstance(network, dict) or network.get("schema") != NETWORK_SCHEMA
            or network.get("source") != "FAA NASR"
            or network.get("scope") != "CONUS_J_Q_published_only"
            or network.get("scope_bbox") != CONUS
            or network.get("source_page") != FAA_NASR_URL
            or network.get("flight_plan_assignment_known") is not False
            or network.get("source_dataset_completeness_verified") is not False):
        raise AirwayError("invalid_or_untrusted_reference_metadata")
    start = flight.date_of(network.get("effective_from"))
    end = flight.date_of(network.get("effective_until_exclusive"))
    if not start <= d < end:
        raise AirwayError("reference_not_effective_on_observation_date")
    features = network.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= MAX_FEATURES:
        raise AirwayError("reference_feature_count_out_of_bounds")
    edges = []
    for feature in features:
        if not isinstance(feature, dict) or not ROUTE_RE.fullmatch(feature.get("route_id", "")):
            raise AirwayError("malformed_reference_feature")
        coords = feature.get("geometry_lonlat")
        if not isinstance(coords, list) or len(coords) != 2:
            raise AirwayError("malformed_reference_geometry")
        converted = []
        for raw in coords:
            if (not isinstance(raw, list) or len(raw) != 2
                    or not all(flight.number(v) for v in raw)):
                raise AirwayError("nonfinite_reference_point")
            p = (raw[1], raw[0])
            if not in_conus(p):
                raise AirwayError("route_reference_outside_scope")
            converted.append(p)
        if not 1 <= flight.haversine(*converted) <= MAX_SEGMENT_KM:
            raise AirwayError("invalid_reference_segment_span")
        edges.append(tuple(converted))
    return edges


def build_index(edges):
    """Conservative 2-degree grids; 2-degree margin protects the curved path.

    Index only the CONUS, with a larger margin than the max comparison band.
    Multiple routes in one tile are not treated as independent confirmations.
    """
    tiles = defaultdict(list)
    for i, (a, b) in enumerate(edges):
        lat_lo = math.floor((min(a[0], b[0]) - GRID_MARGIN_DEGREES) / GRID_DEGREES)
        lat_hi = math.floor((max(a[0], b[0]) + GRID_MARGIN_DEGREES) / GRID_DEGREES)
        lon_lo = math.floor((min(a[1], b[1]) - GRID_MARGIN_DEGREES) / GRID_DEGREES)
        lon_hi = math.floor((max(a[1], b[1]) + GRID_MARGIN_DEGREES) / GRID_DEGREES)
        for x in range(lat_lo, lat_hi + 1):
            for y in range(lon_lo, lon_hi + 1):
                tiles[(x, y)].append(i)
    return tiles


def evaluate_leg(leg, edges, tiles, day, *, width=DEFAULT_BAND_KM):
    if not isinstance(leg, dict) or not flight.ident(leg.get("flight_id")):
        raise AirwayError("missing_or_bad_leg_id")
    result = {"flight_id": leg["flight_id"], "status": "insufficient_observations",
              "reason": None, "evaluated_points": 0, "points_near_any_published_airway": 0,
              "proportion_near": None, "candidate_segment_comparisons": 0,
              "max_distance_to_assigned_route_km": None,
              "route_assignment_known": False, "changes_warning_status": False,
              "requires_historical_validation": False}
    if leg.get("coverage") != "complete" or not isinstance(leg.get("points"), list):
        result["reason"] = "leg_coverage_unverified"
        return result
    positions = leg["points"]
    if len(positions) > MAX_POINTS:
        raise AirwayError("leg_exceeds_bounded_point_limit")
    day_start = dt.datetime.combine(flight.date_of(day), dt.time.min, tzinfo=dt.timezone.utc).timestamp()
    enroute, outscope, other_altitude = [], 0, 0
    for row in positions:
        if not isinstance(row, dict):
            result["reason"] = "invalid_position_record"
            return result
        t, lat, lon, alt = (row.get(v) for v in ("t", "lat", "lon", "altitude_ft"))
        if not all(flight.number(x) for x in (t, lat, lon, alt)) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            result["reason"] = "invalid_or_missing_position_altitude"
            return result
        if not day_start <= t < day_start + 86400:
            result["reason"] = "observation_outside_reference_day"
            return result
        if not in_conus((lat, lon)):
            outscope += 1
            continue
        if not 18000 <= alt <= 45000:
            other_altitude += 1
            continue
        enroute.append((t, lat, lon))
    result["excluded_outside_CONUS"] = outscope
    result["excluded_other_altitudes"] = other_altitude
    if len(enroute) < MIN_VALID_POINTS:
        result["reason"] = "too_few_scope_and_altitude_positions"
        return result
    for a, b in zip(enroute, enroute[1:]):
        if b[0] <= a[0] or b[0] - a[0] > flight.MAX_GAP_S or flight.haversine(a[1:], b[1:]) > flight.MAX_STEP_KM:
            result["reason"] = "gap_or_invalid_track_continuity"
            return result
    if enroute[-1][0] - enroute[0][0] < 900:
        result["reason"] = "insufficient_enroute_observation_time"
        return result
    near, touched = 0, 0
    for t, lat, lon in enroute:
        key = (math.floor(lat / GRID_DEGREES), math.floor(lon / GRID_DEGREES))
        candidates = tiles.get(key, [])
        if candidates:
            touched += 1
        is_near = False
        for i in candidates:
            result["candidate_segment_comparisons"] += 1
            if flight.segment_distance((lat, lon), *edges[i]) <= width:
                is_near = True
                break
        near += int(is_near)
    result["evaluated_points"] = len(enroute)
    result["points_near_any_published_airway"] = near
    result["proportion_near"] = round(near / len(enroute), 4)
    if touched == 0:
        result["status"] = "uncovered_by_local_reference_index"
        result["reason"] = "no_reference_segments_in_spatial_tiles"
    elif near / len(enroute) >= COVERAGE_FRACTION:
        result["status"] = "network_proximity_only"
        result["reason"] = "near_some_published_ats_routes_not_assigned_flight_plan"
    else:
        result["status"] = "needs_route_context_before_history"
        result["reason"] = "outside_some_known_routes_or_direct_routing_possible"
        result["requires_historical_validation"] = True
    return result


def screen(network, input_value, *, width=DEFAULT_BAND_KM):
    if not flight.number(width) or not 1 <= width <= MAX_BAND_KM:
        raise AirwayError("corridor_width_outside_bound")
    if not isinstance(input_value, dict) or input_value.get("schema") != INPUT_SCHEMA:
        raise AirwayError("invalid_leg_input_schema")
    day = input_value.get("day")
    edges = validate_network(network, day)
    legs = input_value.get("legs")
    if not isinstance(legs, list) or not 1 <= len(legs) <= MAX_LEGS:
        raise AirwayError("invalid_leg_count")
    tiles = build_index(edges)
    seen, results = set(), []
    for leg in legs:
        if not isinstance(leg, dict) or leg.get("flight_id") in seen:
            raise AirwayError("duplicate_or_bad_leg")
        seen.add(leg.get("flight_id"))
        results.append(evaluate_leg(leg, edges, tiles, day, width=width))
    return {
        "schema": SCREEN_SCHEMA, "status": "experimental_offline_screen",
        "source": "FAA NASR", "observation_day": day, "route_reference_effective": True,
        "reference_dataset_completeness_verified": False, "individual_clearance_known": False,
        "reference_segments": len(edges), "corridor_km": width,
        "review_candidate_count": sum(r["requires_historical_validation"] for r in results),
        "segments_available_in_index": len(edges),
        "total_actual_comparisons": sum(r["candidate_segment_comparisons"] for r in results),
        "full_scan_upper_bound": len(edges) * sum(r["evaluated_points"] for r in results),
        "alerts_emitted": 0, "changes_aiba_warning_status": False,
        "publication_enabled": False,
        "interpretation": "Proximity to SOME published U.S. ATS route, never assigned-route adherence or abnormality",
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("build", help="Offline authoritative-cycle NASR CSV translation")
    make.add_argument("--awy", type=Path, required=True)
    make.add_argument("--fix", type=Path, required=True)
    make.add_argument("--nav", type=Path, required=True)
    make.add_argument("--effective-from", required=True)
    make.add_argument("--effective-until", required=True)
    make.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("screen", help="Offline broad published-network proximity filter")
    check.add_argument("--network", type=Path, required=True)
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--width-km", type=float, default=DEFAULT_BAND_KM)
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    code = 0
    try:
        if args.command == "build":
            result = nasr_network(args.awy, args.fix, args.nav, args.effective_from, args.effective_until)
        else:
            result = screen(flight.read_json(args.network), flight.read_json(args.input), width=args.width_km)
    except (AirwayError, flight.InputError, OSError, TypeError, OverflowError, RecursionError) as exc:
        code = 1
        result = {"schema": NETWORK_SCHEMA if args.command == "build" else SCREEN_SCHEMA,
                  "status": "unavailable", "reason": str(exc) if isinstance(exc, (AirwayError, flight.InputError))
                  else "input_unavailable", "alerts_emitted": 0, "changes_aiba_warning_status": False,
                  "results": []}
    try:
        flight.write_atomic(args.output, result)
    except OSError:
        return 1
    print(f"{result.get('status', 'network_built_for_offline_review')}: {args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
