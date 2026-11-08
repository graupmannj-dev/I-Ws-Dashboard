#!/usr/bin/env python3
"""AIBA ephemeral-friction collector: bounded, public, source-linked measurements.

Shadow mode. A collection is NOT an intelligence assessment, a verified
military activity, or proof of a cyberattack. Source failure never means zero.
The state branch is public; do not collect personal/sensitive information.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

UTC = dt.timezone.utc
IODA = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events"
NGA = "https://msi.nga.mil/api/publications/broadcast-warn"
USER_AGENT = "AIBA-Public-IW-Friction/1.0 (github.com/graupmannj-dev/I-Ws-Dashboard)"
MAX_BYTES = 3_000_000
MAX_RECORDS = 250
MAX_ARCHIVES = 350
SOURCES = ("ioda", "nga")
CAVEAT = "Source observation only. Does not independently establish military preparations or event attribution."

# Geographic association is explicitly contextual; a national outage cannot
# establish bilateral military activity at the theater anchor.
COUNTRY_CASES = {
    "IR": "iran_gulf", "TW": "taiwan", "KP": "korea", "KR": "korea",
    "PK": "afpak", "AF": "afpak", "ET": "horn_ethiopia_eritrea",
    "ER": "horn_ethiopia_eritrea", "RW": "drc_rwanda", "CD": "drc_rwanda",
    "TH": "thailand_cambodia", "KH": "thailand_cambodia",
}
# Use only unambiguous geographic keywords; plain "Gulf" or "Russia" alone
# cannot justify mapping a source to a more specific military scenario.
MARITIME_CASE_TERMS = {
    "iran_gulf": (r"\bstrait of hormuz\b", r"\bpersian gulf\b", r"\bqeshm\b"),
    "taiwan": (r"\btaiwan strait\b", r"\bkinmen\b"),
    "korea": (r"\bkorean peninsula\b", r"\bsea of japan\b"),
    "thailand_cambodia": (r"\bthai.cambodian\b",),
}
MILITARY = re.compile(r"\b(military exercise|live.?fire|missile|firing|gunnery|naval exercise|weapon testing)\b", re.I)


def utcnow():
    return dt.datetime.now(UTC).replace(microsecond=0)


def iso(value):
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def event_time(value):
    """Accept explicit aware source times and Unix seconds, never guessed local."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)) and math.isfinite(value):
            return dt.datetime.fromtimestamp(value / (1000 if value > 1e11 else 1), UTC)
        if isinstance(value, str):
            txt = value.strip()
            parsed = dt.datetime.fromisoformat(txt.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (OverflowError, ValueError, TypeError):
        pass
    return None


def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write_json(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                 encoding="utf-8")


def fetch(url):
    if not url.startswith("https://"):
        raise ValueError("HTTPS required")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    # IODA currently serves a TLS 1.2-only stack for some clients. Use an
    # authenticated TLS 1.2 connection for IODA only; do not disable CA
    # verification, hostname checking, or downgrade other sources.
    context = None
    if urllib.parse.urlsplit(url).hostname == "api.ioda.inetintel.cc.gatech.edu":
        context = ssl.create_default_context()
        context.maximum_version = ssl.TLSVersion.TLSv1_2
    with urllib.request.urlopen(req, timeout=23, context=context) as reply:
        data = reply.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Response larger than bounded collector limit")
        if reply.headers.get("content-type", "").split(";")[0].strip() in ("text/html", "text/plain"):
            raise ValueError("Unexpected non-JSON source response")
        return json.loads(data)


def extract_records(payload, names):
    """Reject unknown API responses, rather than call them zero events."""
    if isinstance(payload, list):
        return payload, False
    if not isinstance(payload, dict):
        raise ValueError("Unexpected upstream response")
    containers = [payload]
    if isinstance(payload.get("data"), dict):
        containers.insert(0, payload["data"])
    for block in containers:
        for name in names:
            val = block.get(name)
            if isinstance(val, list):
                has_more = bool(block.get("nextPage") or block.get("hasNextPage") or
                                block.get("has_next") or block.get("next"))
                paging = block.get("pagination")
                if isinstance(paging, dict):
                    has_more = has_more or bool(paging.get("nextPage") or paging.get("hasNextPage"))
                return val, has_more
            if isinstance(val, dict):
                for child in ("results", "items", "rows", "data"):
                    if isinstance(val.get(child), list):
                        return val[child], bool(val.get("nextPage") or val.get("hasNextPage"))
    raise ValueError("Unsupported upstream response shape; never label it an empty result")


def safe_text(value, limit=350):
    return str(value or "").strip()[:limit]


def fingerprint(*parts):
    return hashlib.sha256("||".join(str(x) for x in parts).encode()).hexdigest()[:24]


def ioda_records(payload, checked, max_records=MAX_RECORDS):
    entries, more = extract_records(payload, ("events", "outages", "results"))
    result = []
    for row in entries[:max_records]:
        if not isinstance(row, dict):
            continue
        entity = row.get("entity") or {}
        if not isinstance(entity, dict):
            entity = {}
        kind = str(entity.get("type") or row.get("entityType") or "").lower()
        cc = str(entity.get("code") or row.get("entityCode") or "").upper()
        if kind not in ("country", "region", "asn", "geoasn"):
            continue
        start = event_time(row.get("start") or row.get("startTime") or row.get("start_time"))
        end = event_time(row.get("end") or row.get("endTime") or row.get("end_time"))
        # IODA's event onset is not its publication time.
        if start is None or start > checked + dt.timedelta(minutes=5):
            continue
        if start < checked - dt.timedelta(days=7):
            continue
        signals = row.get("datasources") or row.get("sources") or []
        if isinstance(signals, dict):
            signals = list(signals)
        if not isinstance(signals, list):
            signals = []
        signal_names = [safe_text(v, 40) for v in signals if isinstance(v, str)][:8]
        identifier = safe_text(row.get("id"), 100) or fingerprint(kind, cc, iso(start), signal_names)
        case = COUNTRY_CASES.get(cc) if kind == "country" else None
        link = "https://ioda.inetintel.cc.gatech.edu/"
        result.append({
            "id": "ioda:" + fingerprint(identifier, kind, cc),
            "family": "internet_reachability", "source": "IODA / Georgia Tech",
            "source_url": link, "entity_type": kind, "entity_code": cc,
            "case_id": case, "title": f"IODA detected connectivity anomaly: {kind} {cc}",
            "summary": ("Internet outage detection candidate; network measurements are not "
                        "evidence of state attribution or an impending cyber offensive."),
            "kind": "outage_event", "event_at": iso(start),
            "source_published_at": None, "collected_at": iso(checked),
            "end_at": iso(end) if end else None, "signal_types": signal_names,
            "root": f"ioda:{identifier}", "review_level": "measurement_context",
            "location_precision": "Country/region/network context, not incident geolocation.",
        })
    return list({x["id"]: x for x in result}.values()), more or len(entries) >= max_records


def nga_records(payload, checked, max_records=MAX_RECORDS):
    entries, more = extract_records(payload, ("broadcastWarnings", "warnings", "results", "items"))
    result = []
    for row in entries[:max_records]:
        if not isinstance(row, dict):
            continue
        # NGA response fields may differ between API versions. No guessing
        # publication time: if the source doesn't expose it, preserve null.
        title = safe_text(row.get("subject") or row.get("title") or row.get("heading") or "Navigational warning", 250)
        message = safe_text(row.get("text") or row.get("message") or row.get("warningText") or row.get("body"), 1200)
        area = safe_text(row.get("navArea") or row.get("area") or row.get("region"), 50)
        number = safe_text(row.get("msgNumber") or row.get("messageNumber") or row.get("id"), 100)
        year = safe_text(row.get("msgYear") or row.get("year"), 10)
        issue = event_time(row.get("issueDate") or row.get("issueDateTime") or row.get("issuedAt"))
        if issue and issue > checked + dt.timedelta(minutes=5):
            continue
        if not (number or message):
            continue
        content = (title + " " + message).lower()
        matches = [case for case, terms in MARITIME_CASE_TERMS.items()
                   if any(re.search(pattern, content) for pattern in terms)]
        case = matches[0] if len(matches) == 1 else None
        identifier = (f"{area}:{year}:{number}" if number else fingerprint(area, title, message))
        result.append({
            "id": "nga:" + fingerprint(identifier), "family": "maritime_restriction",
            "source": "NGA Maritime Safety Information", "source_url": "https://msi.nga.mil/NavWarnings",
            "case_id": case, "title": title, "summary": message[:800],
            "kind": "military_hazard_mention" if MILITARY.search(content) else "navigation_safety_notice",
            "event_at": iso(issue) if issue else None, "source_published_at": iso(issue) if issue else None,
            "collected_at": iso(checked), "root": f"nga:{identifier}",
            "area": area, "review_level": "official_notice_not_kinetic_confirmation",
            "location_precision": "Text-associated theater if unique; no warning polygon inferred.",
        })
    return list({x["id"]: x for x in result}.values()), more or len(entries) > max_records


def collect(state, clock=utcnow, fetcher=fetch):
    """Write health for every query; retain previous successful latest on failures."""
    state = Path(state)
    checked = clock()
    # A bounded global 4h event window; source historical backfill can overlap
    # prior runs, and stable event IDs remove overlap.
    start = checked - dt.timedelta(hours=4)
    urls = {
        "ioda": IODA + "?" + urllib.parse.urlencode({
            "from": int(start.timestamp()), "until": int(checked.timestamp()),
            "entityType": "country", "limit": 100, "page": 0, "extendWindowSeconds": 0}),
        "nga": NGA + "?" + urllib.parse.urlencode({"status": "active", "output": "json"}),
    }
    source_rows, health = {}, {}
    for mode in SOURCES:
        try:
            payload = fetcher(urls[mode])
            normalized, truncated = (ioda_records(payload, checked, 100) if mode == "ioda"
                                     else nga_records(payload, checked, MAX_RECORDS))
            status = "partial" if truncated else "collected"
            source_rows[mode] = normalized
            health[mode] = {"status": status, "checked_at": iso(checked),
                            "records": len(normalized), "truncated": truncated,
                            "source_url": urls[mode], "error": None,
                            "caveat": CAVEAT}
        except (OSError, ValueError, KeyError, TypeError, TimeoutError) as exc:
            health[mode] = {"status": "unavailable", "checked_at": iso(checked),
                            "records": None, "truncated": None, "source_url": urls[mode],
                            "error": type(exc).__name__ + ": " + safe_text(str(exc), 120),
                            "caveat": "Upstream unavailable or unsupported; NOT evidence of zero activity."}
        write_json(state / "health" / f"friction_{mode}.json", health[mode])
    records = [row for values in source_rows.values() for row in values]
    if source_rows:
        index_path = state / "index" / "friction_seen.json"
        index = read_json(index_path, {}) or {}
        if not isinstance(index, dict):
            raise ValueError("Invalid previous source identity index")
        # Keep stable identity for 45 days even when a source temporarily stops
        # returning an event, so a reappearance does not create a false new hit.
        kept = {}
        for key, value in index.items():
            prior_time = event_time(value.get("last_seen_at")) if isinstance(value, dict) else None
            if prior_time and checked - dt.timedelta(days=45) <= prior_time <= checked:
                kept[key] = value
        index = kept
        new_records = []
        for row in records:
            old = index.get(row["id"])
            row["first_seen_at"] = old["first_seen_at"] if old else iso(checked)
            if old is None:
                new_records.append(row)
            index[row["id"]] = {"first_seen_at": row["first_seen_at"],
                                "last_seen_at": iso(checked), "family": row["family"]}
        write_json(index_path, index)
        by_case = {}
        for row in records:
            key = row.get("case_id") or "unlocated"
            member = by_case.setdefault(key, {})
            member[row["family"]] = member.get(row["family"], 0) + 1
        result = {"schema_version": 1, "collected_at": iso(checked),
                  "records": records, "health": health, "case_counts": by_case,
                  "coverage": "partial" if any(x["status"] != "collected" for x in health.values())
                              else "collected",
                  "note": "Only successful sources appear in records. Missing sources remain unavailable."}
        # Historical snapshots contain ONLY newly identified event payloads
        # plus aggregates, not repeated full global API dumps. The full latest
        # snapshot and identity index support replay, baselines and dedup.
        historical = {k: v for k, v in result.items() if k != "records"}
        historical["new_records"] = new_records
        historical["record_count"] = len(records)
        write_json(state / "history" / "friction" / (checked.strftime("%Y%m%dT%H%M%SZ") + ".json"), historical)
        write_json(state / "latest" / "friction.json", result)
    else:
        result = {"schema_version": 1, "collected_at": iso(checked),
                  "records": [], "health": health, "coverage": "unavailable",
                  "note": "No updated snapshot; previous successful observations retained."}
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    args = p.parse_args()
    result = collect(args.state)
    print(json.dumps({"collected_at": result["collected_at"],
                      "coverage": result["coverage"],
                      "health": result["health"]}, indent=2))
    # Fail on total unavailability so CI and monitors never show green for no data.
    return 1 if result["coverage"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
