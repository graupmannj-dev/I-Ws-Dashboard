"""ADSB.lol public geographic aircraft adapter for AIBA Atlas.

Public data: ODbL 1.0, https://www.adsb.lol/docs/open-data/api
This collector uses ONE bounded geographic lookup per permitted refresh; it
does not use the global /mil endpoint, tail-number searches or live airspace
surveillance alerts. Database affiliation and platform types are *not* a
verified flight mission, an order of battle, or evidence of hostile action.

No collection occurs unless AIBA_AIRCRAFT_PROVIDER=adsb_lol and a center
and radius are explicitly configured. Use only where provider terms permit.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import re
import time

BASE = "https://api.adsb.lol"
SOURCE = "https://www.adsb.lol/docs/open-data/api"
MAX_RADIUS_NM = 250
DEFAULT_RADIUS_NM = 100
MAX_RESPONSE_AIRCRAFT = 2500
MAX_POSITION_AGE = 120
EARTH_RADIUS_NM = 3440.065
UTC = dt.timezone.utc

# This mapping is intentionally small and auditable. It describes an
# airframe/platform family, not the purpose of the aircraft's current flight.
MILITARY_PLATFORM = {
    "combat": {"F16", "F15", "F18", "F22", "F35", "A10", "EF2K", "EUFI", "TOR", "AV8B",
               "M29", "SU27", "SU30", "SU35", "RAFL"},
    "tanker": {"KC10", "KC46", "K35R", "KC35", "A330MRTT"},
    "transport": {"C130", "C17", "C5", "C5M", "C27J", "A400", "C295", "C160"},
    "surveillance": {"RC135", "R135", "E3", "E3CF", "E737", "E7", "P8", "P8A", "P3", "E8", "U2", "RQ4"},
    "training": {"T38", "T6", "T6A", "T1", "PC21", "PC9", "H25B"},
    "helicopter": {"H60", "H47", "H53", "H64", "UH60", "CH47", "S70"},
}

PASSENGER_TYPES = {
    "A318", "A319", "A320", "A321", "A20N", "A21N", "A332", "A333", "A339",
    "A343", "A346", "A359", "A35K", "A388", "B737", "B738", "B739",
    "B37M", "B38M", "B39M", "B744", "B748", "B752", "B753", "B763",
    "B764", "B772", "B773", "B77W", "B788", "B789", "B78X", "E170",
    "E175", "E190", "E195", "E290", "E295", "CRJ2", "CRJ7", "CRJ9",
    "AT72", "AT75", "DH8D",
}
CARGO_ONLY_TYPES = {"B74F", "B77F", "A33F", "B752F", "B763F", "MD11F", "AN124"}
GENERAL_AVIATION_TYPES = {
    "C172", "C182", "C206", "C208", "PA28", "PA32", "SR20", "SR22",
    "DA40", "DA42", "PC12", "BE20", "BE35", "BE36", "BE58",
    "GLF4", "GLF5", "GLF6", "LJ45", "LJ60", "CL60", "C25A", "C56X",
}
HELICOPTER_TYPES = {"R22", "R44", "R66", "EC35", "EC45", "EC55", "A109", "A139",
                    "S76", "S92", "B06", "B407", "H125", "H145"}
CARGO_OPERATOR = re.compile(r"\b(CARGO|FREIGHT|FEDEX|FEDERAL EXPRESS|UPS|DHL|CARGOLUX|AIRBRIDGE CARGO)\b", re.I)
CIVIL_OPERATOR = re.compile(
    r"\b(AIRLINES|AIRWAYS|AIR LINE|AIR TRANSPORT|JETBLUE|SOUTHWEST|CARGOLUX|"
    r"FEDEX|FEDERAL EXPRESS|DHL|CARGO|FREIGHT|NASA|NOAA|DLR|RESEARCH)\b", re.I)
SCIENCE_OPERATOR = re.compile(r"\b(NASA|NOAA|DLR|RESEARCH|SCIENTIFIC|GEOPHYSICS)\b", re.I)

VALID_GROUPS = ("military", "civilian", "unknown")
VALID_CATEGORIES = ("combat", "transport", "tanker", "surveillance", "training",
                    "passenger", "cargo", "scientific", "helicopter", "general_aviation",
                    "unclassified")


def coordinate(lon, lat):
    return (all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in (lon, lat)) and -180 <= lon <= 180 and -90 <= lat <= 90)


def bounded_query(env=None):
    """Require center; no silently selected operational theater or global query."""
    env = env or os.environ
    if "AIBA_ADSB_LAT" not in env or "AIBA_ADSB_LON" not in env:
        raise ValueError("Set AIBA_ADSB_LAT and AIBA_ADSB_LON explicitly")
    try:
        lat = float(env["AIBA_ADSB_LAT"])
        lon = float(env["AIBA_ADSB_LON"])
        radius = int(env.get("AIBA_ADSB_RADIUS_NM", str(DEFAULT_RADIUS_NM)))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid ADSB.lol geographic settings") from exc
    if not coordinate(lon, lat) or not 1 <= radius <= MAX_RADIUS_NM:
        raise ValueError("ADSB.lol center or radius invalid (1–250 NM)")
    # Only static, strictly validated numeric URL segments. No arbitrary URLs.
    return f"{BASE}/v2/point/{lat:.5f}/{lon:.5f}/{radius}", (lat, lon, radius)


def distance_nm(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    delta_lat=b-a
    delta_lon=math.radians(lon2-lon1)
    value=math.sin(delta_lat/2)**2+math.cos(a)*math.cos(b)*math.sin(delta_lon/2)**2
    return 2*EARTH_RADIUS_NM*math.asin(min(1.0, math.sqrt(max(0.0, value))))


def classify(aircraft):
    """Positive evidence only. No dbFlags military bit does NOT prove civilian."""
    flags = aircraft.get("dbFlags")
    if not isinstance(flags, int) or isinstance(flags, bool) or flags < 0:
        flags = 0
    typ = str(aircraft.get("t") or "").strip().upper()[:16]
    op = str(aircraft.get("ownOp") or "").strip()[:120]
    military = bool(flags & 1)
    civil_positive = bool(CIVIL_OPERATOR.search(op))
    group = "military" if military else "civilian" if civil_positive else "unknown"
    basis = ("Provider database military flag (not mission verification)"
             if military else "Provider operator text suggests civil use (not verified registration)"
             if civil_positive else "No positive military or civil affiliation evidence")

    if group == "military":
        category = next((role for role, types in MILITARY_PLATFORM.items() if typ in types),
                        "unclassified")
    elif SCIENCE_OPERATOR.search(op):
        category = "scientific"
    elif CARGO_OPERATOR.search(op) or typ in CARGO_ONLY_TYPES:
        category = "cargo"
    elif typ in PASSENGER_TYPES:
        category = "passenger"
    elif typ in HELICOPTER_TYPES:
        category = "helicopter"
    elif typ in GENERAL_AVIATION_TYPES:
        category = "general_aviation"
    else:
        category = "unclassified"
    return group, category, basis


def parse_response(payload, center, collected_at=None):
    """Normalize source-coherent, non-stale regional positional observations.

    Keep row-level provider classification evidence, but NEVER make mission
    claims. Reject unknown response structures rather than reporting zero.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("ac"), list):
        raise ValueError("Unexpected ADSB.lol API envelope")
    items = payload["ac"]
    if len(items) > MAX_RESPONSE_AIRCRAFT:
        raise ValueError("ADSB.lol response exceeds bounded aircraft limit")
    collected_at = collected_at or dt.datetime.now(UTC)
    if collected_at.tzinfo is None:
        raise ValueError("Collection clock must include UTC offset")
    collected_at = collected_at.astimezone(UTC)
    raw_time = payload.get("now")
    if not isinstance(raw_time, (int, float)) or isinstance(raw_time, bool) or not math.isfinite(raw_time):
        raise ValueError("ADSB.lol missing source clock")
    server_time = raw_time / 1000 if raw_time > 1e11 else raw_time
    try:
        asof = dt.datetime.fromtimestamp(server_time, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("ADSB.lol invalid source clock") from exc
    if abs((collected_at-asof).total_seconds()) > 300:
        raise ValueError("ADSB.lol source clock differs by over five minutes")
    lat0, lon0, radius = center
    rows, excluded, seen_ids = [], 0, set()
    for item in items:
        if not isinstance(item, dict) or not coordinate(item.get("lon"), item.get("lat")):
            excluded += 1
            continue
        hex_id = item.get("hex")
        if not isinstance(hex_id, str) or not re.fullmatch(r"~?[0-9a-fA-F]{6}", hex_id):
            excluded += 1
            continue
        # Provider sometimes includes stale aircraft with recently received
        # transponder data but no recent position. Do not plot estimated lastPosition.
        age = item.get("seen_pos")
        if not isinstance(age, (int, float)) or isinstance(age, bool) or not math.isfinite(age) or not 0 <= age <= MAX_POSITION_AGE:
            excluded += 1
            continue
        if distance_nm(lat0, lon0, item["lat"], item["lon"]) > radius + 3:
            excluded += 1
            continue
        identity = hex_id.lower()
        if identity in seen_ids:
            excluded += 1
            continue
        seen_ids.add(identity)
        group, category, basis = classify(item)
        observed = asof - dt.timedelta(seconds=age)
        flight = item.get("flight")
        flight = flight.strip().upper()[:16] if isinstance(flight, str) else ""
        if not re.fullmatch(r"[A-Z0-9 -]{1,16}", flight):
            flight = ""
        airframe = str(item.get("t") or "").strip().upper()[:16]
        if not re.fullmatch(r"[A-Z0-9 -]{0,16}", airframe):
            airframe = ""
        callout = flight or airframe or "Aircraft position"
        rows.append({
            "id": identity, "title": callout,
            "lon": float(item["lon"]), "lat": float(item["lat"]),
            "observed_at": observed.isoformat(), "heading": item.get("track")
                if isinstance(item.get("track"), (int,float))
                and not isinstance(item.get("track"),bool)
                and math.isfinite(item["track"]) and 0 <= item["track"] < 360 else None,
            "source": "ADSB.lol", "url": SOURCE,
            "affiliation": group, "role_category": category,
            "classification_basis": basis,
            "aircraft_type": airframe or None,
            "detail": ("Source-observed position. Affiliation and airframe role are provisional "
                       "database classifications, not evidence of this flight's mission. "
                       "ADSB.lol data © contributors, ODbL 1.0."),
            "license": "ODbL-1.0",
            "date": asof.isoformat(),
        })
    return {"records": rows, "skipped": excluded, "source_total": len(items),
            "coverage": ("regional_position_sample_not_global" if items else
                         "empty_regional_sample_not_global")}


def collect_region(fetcher, environ=None, clock=None):
    """One non-retrying HTTPS query. Failure is handled by Collector.update."""
    env = environ or os.environ
    url, center = bounded_query(env)
    current = clock or dt.datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("Collection clock must be timezone-aware")
    headers = {
        "Accept": "application/json",
        "User-Agent": env.get("AIBA_ADSB_USER_AGENT", "AIBA-Research/1.0 (github.com/graupmannj-dev/I-Ws-Dashboard)")[:180],
    }
    # A key is not required for the current public API. No secrets are
    # accepted in browser URLs and no key is embedded in public snapshots.
    return parse_response(json.loads(fetcher(url, headers=headers)), center, current)
