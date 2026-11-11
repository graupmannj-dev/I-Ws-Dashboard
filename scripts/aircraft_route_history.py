#!/usr/bin/env python3
"""Offline, predeclared-cohort aircraft corridor comparison (experimental).

No network access, archive downloads, recurring jobs, dashboard writes or
severity changes. Input is explicitly curated, not a global ADS-B sample.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
import tempfile

INPUT_SCHEMA = "aiba.aircraft-route-flights.v1"
COHORT_SCHEMA = "aiba.aircraft-route-cohort.v1"
OUTPUT_SCHEMA = "aiba.aircraft-route-retrospective.v1"
WINDOW_DAYS = 28
MIN_HISTORY_FLIGHTS = 4
MIN_HISTORY_DAYS = 3
MIN_POINTS = 6
MIN_DURATION_S = 900
MAX_GAP_S = 600
MAX_STEP_KM = 300
MAX_REFERENCE_DISPERSION_KM = 80
MIN_CORRIDOR_KM = 10
CORRIDOR_MARGIN_KM = 10
EXCESS_THRESHOLD_KM = 25
SUSTAINED_S = 300
SUSTAINED_POINTS = 3
SAMPLES = 21
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_FLIGHTS = 500
MAX_POINTS = 2000
MAX_COHORTS = 20
MAX_OUTPUT_POINTS = 128
RADIUS_KM = 6371.0088
ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,63}\Z")
ICAO_PATTERN = re.compile(r"~?[0-9a-f]{6}\Z")


class InputError(ValueError):
    """An input cannot support a trustworthy offline result."""


def date_of(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise InputError("Expected a YYYY-MM-DD date")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise InputError("Invalid date") from exc


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def ident(value):
    return isinstance(value, str) and bool(ID_PATTERN.fullmatch(value))


def read_json(path):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise InputError("Input exceeds 8 MiB offline limit")
    with path.open("r", encoding="utf-8") as stream:
        try:
            return json.load(stream, parse_constant=lambda _: (_ for _ in ()).throw(InputError("Nonfinite JSON")))
        except (ValueError, RecursionError, UnicodeError) as exc:
            raise InputError("Invalid input JSON") from exc


def validate_manifest(value, target):
    if not isinstance(value, dict) or value.get("schema") != COHORT_SCHEMA:
        raise InputError("Wrong cohort manifest schema")
    frozen = date_of(value.get("frozen_before"))
    if frozen >= target:
        raise InputError("Cohort must be frozen before evaluation day")
    groups = value.get("cohorts")
    if not isinstance(groups, list) or not 1 <= len(groups) <= MAX_COHORTS:
        raise InputError("Cohort manifest must have 1–20 groups")
    selected = {}
    for group in groups:
        if not isinstance(group, dict) or not ident(group.get("id")) or group["id"] in selected:
            raise InputError("Duplicate or invalid cohort ID")
        aircraft = group.get("aircraft_ids")
        if (not isinstance(aircraft, list) or not aircraft or len(aircraft) > 100
                or any(not isinstance(a, str) or not ICAO_PATTERN.fullmatch(a) for a in aircraft)
                or len(set(aircraft)) != len(aircraft)):
            raise InputError("Preselected cohort requires unique ICAO identities")
        if not ident(group.get("direction")) or not isinstance(group.get("label"), str) or not group["label"].strip():
            raise InputError("Cohort needs a label and explicit direction")
        selected[group["id"]] = {**group, "aircraft_set": set(aircraft)}
    return selected, frozen


def validate_input(value, selected, target):
    if not isinstance(value, dict) or value.get("schema") != INPUT_SCHEMA:
        raise InputError("Wrong flight input schema")
    if value.get("collection_scope") != "preselected_cohort_offline":
        raise InputError("Only explicitly preselected offline observations supported")
    if value.get("source") != "ADSB.lol":
        raise InputError("Only ADSB.lol source label is supported by this pilot")
    days = value.get("days")
    flights = value.get("flights")
    if not isinstance(days, list) or not isinstance(flights, list) or len(flights) > MAX_FLIGHTS:
        raise InputError("Invalid day coverage or flight count")
    coverage = {}
    for day in days:
        if not isinstance(day, dict):
            raise InputError("Malformed source-day coverage")
        d = date_of(day.get("date"))
        if d in coverage or day.get("status") not in ("complete", "partial", "unknown"):
            raise InputError("Duplicate day or unknown day coverage status")
        coverage[d] = day["status"]
    if target not in coverage:
        coverage[target] = "unknown"
    seen = set()
    for flight in flights:
        if not isinstance(flight, dict):
            raise InputError("Malformed flight record")
        fid, gid = flight.get("flight_id"), flight.get("cohort_id")
        if not ident(fid) or fid in seen or gid not in selected:
            raise InputError("Duplicate flight ID or non-predeclared cohort")
        seen.add(fid)
        d = date_of(flight.get("day"))
        if d not in coverage:
            raise InputError("Flight day lacks an explicit source-day coverage entry")
        if flight.get("direction") != selected[gid]["direction"]:
            raise InputError("Flight direction differs from predeclared cohort")
        icao = flight.get("aircraft_id")
        if not isinstance(icao, str) or icao not in selected[gid]["aircraft_set"]:
            raise InputError("Flight aircraft not in predeclared cohort")
        if flight.get("coverage") not in ("complete", "partial", "unknown"):
            raise InputError("Flight coverage must be complete, partial or unknown")
        if ("points" in flight) == ("readsb" in flight):
            raise InputError("Flight requires exactly one of points or readsb trace")
        if "points" in flight:
            if not isinstance(flight["points"], list) or len(flight["points"]) > MAX_POINTS:
                raise InputError("Flight points exceed limit or invalid")
        else:
            envelope = flight["readsb"]
            if (not isinstance(envelope, dict) or envelope.get("icao") != icao
                    or not number(envelope.get("timestamp")) or envelope["timestamp"] <= 0
                    or not isinstance(envelope.get("trace"), list)
                    or len(envelope["trace"]) > MAX_POINTS):
                raise InputError("Invalid readsb trace envelope")
        flight["_day"] = d
    return coverage, flights


def haversine(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = (lon2 - lon1 + math.pi) % (2 * math.pi) - math.pi
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def bearing(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta = (lon2 - lon1 + math.pi) % (2 * math.pi) - math.pi
    return math.atan2(math.sin(delta) * math.cos(lat2),
                      math.cos(lat1) * math.sin(lat2) -
                      math.sin(lat1) * math.cos(lat2) * math.cos(delta))


def segment_distance(point, a, b):
    seg = haversine(a, b)
    if seg < 1e-9:
        return haversine(point, a)
    delta = haversine(a, point) / RADIUS_KM
    angle = bearing(a, point) - bearing(a, b)
    cross = math.asin(max(-1.0, min(1.0, math.sin(delta) * math.sin(angle))))
    along = math.atan2(math.sin(delta) * math.cos(angle), math.cos(delta))
    if along < 0:
        return haversine(point, a)
    if along > seg / RADIUS_KM:
        return haversine(point, b)
    return abs(cross) * RADIUS_KM


def polyline_distance(point, polyline):
    return min(segment_distance(point, a, b) for a, b in zip(polyline, polyline[1:]))


def unwrap_lons(coords):
    result = [coords[0][1]]
    for _, lon in coords[1:]:
        result.append(result[-1] + (lon - result[-1] + 180) % 360 - 180)
    return result


def resample(coords):
    """Interpolate by traveled distance, not timestamp, with dateline continuity."""
    lengths = [0.0]
    for a, b in zip(coords, coords[1:]):
        lengths.append(lengths[-1] + haversine(a, b))
    if lengths[-1] == 0:
        raise InputError("Stationary historical flight")
    lons = unwrap_lons(coords)
    result, segment = [], 0
    for i in range(SAMPLES):
        target = lengths[-1] * i / (SAMPLES - 1)
        while segment < len(lengths) - 2 and lengths[segment + 1] < target:
            segment += 1
        den = lengths[segment + 1] - lengths[segment]
        fraction = (target - lengths[segment]) / den if den else 0
        lat = coords[segment][0] + fraction * (coords[segment + 1][0] - coords[segment][0])
        lon = lons[segment] + fraction * (lons[segment + 1] - lons[segment])
        result.append((lat, lon))
    return result


def decode_points(flight):
    if "points" in flight:
        raw = flight["points"]
    else:
        source = flight["readsb"]
        raw = []
        for row in source["trace"]:
            if (not isinstance(row, list) or len(row) < 9 or not number(row[0])
                    or not isinstance(row[6], int) or isinstance(row[6], bool)):
                return None, "invalid_readsb_row", 0
            raw.append({"t": source["timestamp"] + row[0], "lat": row[1],
                        "lon": row[2], "flags": row[6], "ground": row[3] == "ground",
                        "callsign": row[8].get("flight", "").strip()
                        if isinstance(row[8], dict) and isinstance(row[8].get("flight"), str) else ""})
    if len(raw) > MAX_POINTS:
        raise InputError("Point count exceeds bound")
    points, removed, callsigns = [], 0, set()
    for raw_point in raw:
        if not isinstance(raw_point, dict):
            return None, "invalid_position", removed
        t, lat, lon = (raw_point.get(key) for key in ("t", "lat", "lon"))
        flags = raw_point.get("flags", 0)
        if (not all(number(x) for x in (t, lat, lon)) or not -90 <= lat <= 90
                or not -180 <= lon <= 180 or not isinstance(flags, int)
                or isinstance(flags, bool) or flags < 0):
            return None, "invalid_position", removed
        label = raw_point.get("callsign", "")
        if label:
            if not isinstance(label, str):
                return None, "invalid_callsign", removed
            callsigns.add(label.strip())
        if flags & 1 or raw_point.get("ground", False):
            removed += 1
            continue
        if (flags & 2) and points:
            return None, "multiple_legs", removed
        if points:
            gap = t - points[-1][0]
            if gap <= 0:
                return None, "unordered_or_duplicate_timestamps", removed
            if gap > MAX_GAP_S:
                return None, "observation_gap", removed
            if haversine((lat, lon), points[-1][1]) > MAX_STEP_KM:
                return None, "implausible_step_or_gap", removed
        points.append((t, (lat, lon)))
    if len(callsigns) > 1:
        return None, "callsign_change", removed
    if len(points) < MIN_POINTS or points[-1][0] - points[0][0] < MIN_DURATION_S:
        return None, "too_few_positions_or_short_leg", removed
    return points, None, removed


def median(values):
    sorted_values = sorted(values)
    n = len(sorted_values)
    return (sorted_values[(n - 1) // 2] + sorted_values[n // 2]) / 2


def percentile90(values):
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def corridor(history):
    samples = [resample([coord for _, coord in points]) for points in history]
    first_lon = samples[0][0][1]
    for path in samples[1:]:
        adjust = round((first_lon - path[0][1]) / 360) * 360
        for i, (lat, lon) in enumerate(path):
            path[i] = (lat, lon + adjust)
    line = [(median([path[i][0] for path in samples]),
             median([path[i][1] for path in samples])) for i in range(SAMPLES)]
    residuals = [haversine(point, line[i]) for path in samples for i, point in enumerate(path)]
    dispersion = percentile90(residuals)
    return [(lat, (lon + 180) % 360 - 180) for lat, lon in line], dispersion


def small_path(points):
    indices = list(range(len(points)))
    if len(indices) > MAX_OUTPUT_POINTS:
        indices = sorted({round(i * (len(points) - 1) / (MAX_OUTPUT_POINTS - 1))
                          for i in range(MAX_OUTPUT_POINTS)})
    return [[round(points[i][1][0], 5), round(points[i][1][1], 5)] for i in indices]


def score(points, center, width):
    run_start, run_count, peak, most_excess = None, 0, 0.0, 0.0
    candidate = False
    for t, position in points:
        excess = max(0.0, polyline_distance(position, center) - width)
        most_excess = max(most_excess, excess)
        if excess >= EXCESS_THRESHOLD_KM:
            if run_start is None:
                run_start, run_count, peak = t, 1, excess
            else:
                run_count += 1
                peak = max(peak, excess)
            if run_count >= SUSTAINED_POINTS and t - run_start >= SUSTAINED_S:
                candidate = True
        else:
            run_start, run_count, peak = None, 0, 0.0
    return candidate, most_excess


def analyze(manifest, data, target_day):
    target = date_of(target_day)
    selected, frozen = validate_manifest(manifest, target)
    day_status, flights = validate_input(data, selected, target)
    results = []
    for gid, group in selected.items():
        cohort_flights = [f for f in flights if f["cohort_id"] == gid]
        previous = [f for f in cohort_flights if target - dt.timedelta(days=WINDOW_DAYS) <= f["_day"] < target]
        history, eligible_dates, excluded = [], set(), 0
        for flight in previous:
            if day_status.get(flight["_day"]) != "complete" or flight["coverage"] != "complete":
                excluded += 1
                continue
            coordinates, reason, _ = decode_points(flight)
            if reason:
                excluded += 1
                continue
            history.append(coordinates)
            eligible_dates.add(flight["_day"])
        eval_flights = [f for f in cohort_flights if f["_day"] == target]
        if not eval_flights:
            eval_flights = [None]
        center, spread = None, None
        if len(history) >= MIN_HISTORY_FLIGHTS and len(eligible_dates) >= MIN_HISTORY_DAYS:
            center, spread = corridor(history)
            if spread > MAX_REFERENCE_DISPERSION_KM:
                center = None
        for flight in eval_flights:
            entry = {
                "cohort_id": gid, "cohort_label": group["label"], "direction": group["direction"],
                "flight_id": flight["flight_id"] if flight else None,
                "evaluation_date": target_day, "status": "insufficient_coverage",
                "reason": None, "history_window_days": WINDOW_DAYS,
                "reference_flights": len(history), "reference_days": len(eligible_dates),
                "excluded_history_flights": excluded,
                "source_day_coverage": day_status[target], "geometry": None,
                "max_excess_km": None, "experimental": True,
            }
            if day_status[target] != "complete":
                entry["reason"] = "source_day_not_complete"
            elif flight is None:
                entry["reason"] = "no_evaluation_flight_in_cohort"
            elif flight["coverage"] != "complete":
                entry["reason"] = "flight_coverage_not_complete"
            else:
                points, reason, removed = decode_points(flight)
                entry["dropped_stale_or_ground_positions"] = removed
                if reason:
                    entry["reason"] = reason
                elif center is None:
                    entry["status"] = "insufficient_history"
                    entry["reason"] = ("too_few_comparable_historical_flights_or_days"
                                       if len(history) < MIN_HISTORY_FLIGHTS or len(eligible_dates) < MIN_HISTORY_DAYS
                                       else "incoherent_reference_routes")
                else:
                    width = max(MIN_CORRIDOR_KM, spread + CORRIDOR_MARGIN_KM)
                    anomalous, excess = score(points, center, width)
                    entry["status"] = "deviation_candidate" if anomalous else "within_reference"
                    entry["reason"] = "sustained_outside_reference" if anomalous else "no_sustained_excess"
                    entry["max_excess_km"] = round(excess, 2)
                    entry["geometry"] = {
                        "actual_path_latlon": small_path(points),
                        "historical_center_latlon": [[round(a, 5), round(b, 5)] for a, b in center],
                        "corridor_half_width_km": round(width, 2),
                        "historical_p90_spread_km": round(spread, 2),
                    }
            results.append(entry)
    counts = {name: sum(r["status"] == name for r in results)
              for name in ("within_reference", "deviation_candidate",
                           "insufficient_history", "insufficient_coverage")}
    return {
        "schema": OUTPUT_SCHEMA, "status": "experimental_offline_report",
        "evaluation_date": target_day, "cohort_frozen_before": str(frozen),
        "collection_scope": "preselected_cohort_not_worldwide",
        "comparison": "prior_28_days_only", "calibrated_accuracy": None,
        "changes_aiba_warning_status": False, "publishing_enabled": False,
        "source": "ADSB.lol", "attribution": "ADSB.lol contributors",
        "source_license": "ODbL-1.0", "results": results, "counts": counts,
    }


def write_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    staged_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".aiba-aircraft-", delete=False) as stream:
            staged_path = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
        staged_path.replace(path)
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path, help="Frozen cohort manifest")
    parser.add_argument("--input", required=True, type=Path, help="Offline curated flight/day JSON")
    parser.add_argument("--date", required=True, help="Evaluation date UTC YYYY-MM-DD")
    parser.add_argument("--output", required=True, type=Path, help="Local-only report JSON")
    args = parser.parse_args(argv)
    try:
        output = analyze(read_json(args.cohort), read_json(args.input), args.date)
        code = 0
    except (InputError, OSError, TypeError, OverflowError) as exc:
        output = {"schema": OUTPUT_SCHEMA, "status": "unavailable",
                  "evaluation_date": args.date, "reason": str(exc) if isinstance(exc, InputError)
                  else "Local input unavailable", "results": [],
                  "changes_aiba_warning_status": False, "publishing_enabled": False}
        code = 1
    try:
        write_atomic(args.output, output)
    except OSError:
        return 1
    print(f"{output['status']}: {args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
