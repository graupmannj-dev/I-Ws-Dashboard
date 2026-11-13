#!/usr/bin/env python3
"""FAA NAS systemic disruption sensor — operational effects, never threat attribution.

Official nationwide NAS airport-events JSON covers airport ground stops, ground
delay programs, and arrival/departure delays. It is DIFFERENT from FAA TFRs.
Observed FAA operational restrictions are not pre-event warning or evidence of
malicious/hostile causation. Single issuer and multiple airports are one sensor.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from ops_pipeline import load_json, write_json

UTC = dt.timezone.utc
SCHEMA = "aiba.faa-nas-systemic-disruption.v1"
SOURCE_URL = "https://nasstatus.faa.gov/api/airport-events"
MAX_AIRPORTS = 450
MAX_BYTES = 3_500_000
MAX_REASON = 220
MIN_AIRPORTS = 5
FRESH_MINUTES = 25
NATIONAL = re.compile(r"\b(?:NATIONAL\s+(?:GROUND\s+)?STOP|NATIONWIDE\s+(?:GROUND\s+)?STOP|ALL\s+(?:U\\.S\\.\s+)?AIRPORTS)\b", re.I)
OUTAGE = re.compile(r"\b(?:COMMUNICATION|TELECOM|EQUIPMENT|SYSTEM\s+OUTAGE|ATC\s+OUTAGE|RADAR|FREQUENCY)\b", re.I)
SCOPE = "FAA NAS monitored US airport sample; neither worldwide nor all US airfields"


def clock_iso(t):
    return t.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_json():
    req = urllib.request.Request(
        SOURCE_URL,
        headers={"Accept": "application/json",
                 "User-Agent": "AIBA-Unclassified-NAS-Operational-Sensor/1.0"})
    with urllib.request.urlopen(req, timeout=18) as response:
        if response.status != 200:
            raise ValueError("FAA NAS source did not return HTTP 200")
        content_type = response.headers.get("Content-Type", "").lower()
        if "json" not in content_type:
            raise ValueError("FAA NAS source returned a non-JSON response")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("FAA NAS response exceeds bounded size")
    return json.loads(data)


def reason_for(item):
    if not isinstance(item, dict):
        return None
    fields = ["reason", "simpleText", "type", "message"]
    pieces = [str(item.get(k) or "") for k in fields]
    return re.sub(r"\s+", " ", " ".join(pieces)).strip()[:MAX_REASON]


def analyze(payload, *, collected_at):
    if not isinstance(payload, list) or not MIN_AIRPORTS <= len(payload) <= MAX_AIRPORTS:
        raise ValueError("NAS JSON airport array missing or outside safety bound")
    if not isinstance(collected_at, dt.datetime) or not collected_at.tzinfo:
        raise ValueError("collection timestamp must include UTC timezone")
    examined, affected, national, stops, delays = set(), [], set(), set(), set()
    observed_reason_count = 0
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("NAS event row invalid")
        airport = str(item.get("airportId") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{3,4}", airport) or airport in examined:
            raise ValueError("NAS airport identifiers missing or duplicated")
        examined.add(airport)
        source_mentions = []
        observed = {}
        for key in ("groundStop", "groundDelay", "airportClosure", "departureDelay", "arrivalDelay"):
            value = item.get(key)
            if value is None:
                continue
            if not isinstance(value, dict):
                raise ValueError("NAS event object changed shape: " + key)
            reason = reason_for(value)
            if not reason:
                continue
            observed[key] = reason
            source_mentions.append(reason)
            observed_reason_count += 1
            if key == "groundStop":
                stops.add(airport)
            if key in ("groundDelay", "departureDelay", "arrivalDelay"):
                delays.add(airport)
            if NATIONAL.search(reason):
                national.add(airport)
        if observed:
            affected.append({
                "airport": airport,
                "nas_event_reasons": observed,
                "national_stop_reason_in_source": airport in national,
                "ground_stop_object_present": airport in stops,
            })
    if len(examined) < MIN_AIRPORTS:
        raise ValueError("insufficient observed FAA NAS airports")
    if len(national) >= 2:
        category = "multi_airport_national_stop_language"
    elif len(national) == 1:
        category = "single_airport_national_stop_language"
    elif len(stops) >= 4:
        category = "multiple_airport_ground_stops"
    else:
        category = "no_systemic_disruption_in_monitored_sample"
    # This is not aviation-safety severity, threat severity, or a validated early-warning level.
    feature = {"national_stop_airports": len(national), "active_ground_stop_airports": len(stops),
               "airports_with_any_delay": len(delays), "affected_airport_records": len(affected)}
    state_fingerprint = hashlib.sha256(json.dumps(
        {"category": category, "national": sorted(national), "stops": sorted(stops)},
        sort_keys=True).encode()).hexdigest()[:24]
    now = clock_iso(collected_at)
    return {
        "schema": SCHEMA, "source_provider": "FAA National Airspace System",
        "source_family": "civil_air_traffic_management",
        "source_url": SOURCE_URL, "geographic_scope": "United States",
        "source_scope": SCOPE,
        "checked_at": now, "observed_at": now,
        "status": category,
        "provisional_review_required": category != "no_systemic_disruption_in_monitored_sample",
        "monitored_airport_count": len(examined),
        "airports_with_any_nas_event": len(affected),
        "event_reason_objects_examined": observed_reason_count,
        **feature,
        "airports": affected[:MAX_AIRPORTS],
        "source_family_independence_count": 1,
        "multiple_airports_not_independent_attribution": True,
        "national_event_confirmed_by_explicit_ATCSCC_order": False,
        "event_occurrence_as_reported_by_FAA_only": True,
        "hostile_actor_evidence": False,
        "cyberattack_evidence": False,
        "forecast_probability": None,
        "military_warning_level_change": False,
        "automatic_event_merges": 0,
        "state_fingerprint": state_fingerprint,
        "limitations": [
            "The FAA NAS airport-events feed describes operational effects, not root cause.",
            "The FAA is one issuer; multiple affected airports are correlated, not independent corroboration.",
            "This feed may lag the controlling ATCSCC advisory and does not include all airports.",
            "A non-disruption sampled response does not certify nationwide all-clear.",
            "The sensor makes no inference of hostile intent or cyberattack.",
        ],
    }


def collect(state, *, fetch=fetch_json, clock=None, write=True):
    state = Path(state)
    at = (clock or (lambda: dt.datetime.now(UTC)))().astimezone(UTC)
    previous = load_json(state / "latest" / "faa_nas.json", {}) or {}
    try:
        result = analyze(fetch(), collected_at=at)
        health = {
            "schema": "aiba.faa-nas-health.v1",
            "source_url": SOURCE_URL, "checked_at": clock_iso(at),
            "status": "collected", "records": result["monitored_airport_count"],
            "source_scope": SCOPE, "error": None,
            "freshness_limit_minutes": FRESH_MINUTES,
        }
        result["changed_since_prior_observation"] = (
            not bool(previous) or result["state_fingerprint"] != previous.get("state_fingerprint"))
        if write:
            write_json(state / "latest" / "faa_nas.json", result)
            # Append only if the operational pattern changed. Never overwrite a dated identity.
            if result["changed_since_prior_observation"]:
                path = state / "history" / "faa_nas" / (
                    at.strftime("%Y%m%dT%H%M%SZ") + "-" + result["state_fingerprint"] + ".json")
                if path.exists():
                    raise ValueError("FAA NAS append-only snapshot ID collision")
                write_json(path, result)
            write_json(state / "health" / "faa_nas.json", health)
        return result, health
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        health = {
            "schema": "aiba.faa-nas-health.v1",
            "source_url": SOURCE_URL, "checked_at": clock_iso(at),
            "status": "unavailable", "records": None,
            "source_scope": SCOPE, "error": type(exc).__name__[:70],
            "freshness_limit_minutes": FRESH_MINUTES,
            "missing_not_clear": True,
        }
        # Preserve last valid snapshot; its age still determines freshness.
        if write:
            write_json(state / "health" / "faa_nas.json", health)
        return None, health


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    args = p.parse_args()
    result, health = collect(args.state)
    print(json.dumps({
        "checked_at": health["checked_at"],
        "source_status": health["status"],
        "result": ({
            "category": result["status"],
            "monitored_airports": result["monitored_airport_count"],
            "national_stop_airports": result["national_stop_airports"],
            "active_ground_stop_airports": result["active_ground_stop_airports"],
            "affected_airport_records": result["airports_with_any_nas_event"],
            "changed_since_prior_observation": result["changed_since_prior_observation"],
            "hostile_actor_evidence": False,
        } if result else None),
        "warning_level_change": False,
    }, indent=2))
    if health["status"] != "collected":
        raise SystemExit("FAA NAS provider unavailable; health saved, prior snapshot not overwritten")


if __name__ == "__main__":
    main()
