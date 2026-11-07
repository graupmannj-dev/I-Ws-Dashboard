#!/usr/bin/env python3
"""AIBA operational collectors. Public OSINT leads, never validated war predictions.

Writes immutable timestamped observations to a separate Git data branch.
The observation clock and the reporting/publication clock are distinct.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UTC = dt.timezone.utc
USER_AGENT = "AIBA-OSINT-Watch/6 (public-source historical monitoring; GitHub graupmannj-dev/I-Ws-Dashboard)"
SCENARIOS = {
    "Iran / Gulf": ("iran", "hormuz", "qeshm", "persian gulf", "tehran"),
    "Taiwan Strait": ("taiwan", "taipei", "china invade", "south china sea", "pla "),
    "Russia / NATO": ("russia", "nato", "poland", "ukraine", "kaliningrad", "baltic"),
    "Korean Peninsula": ("north korea", "south korea", "pyongyang", "seoul"),
    "Horn of Africa": ("ethiopia", "eritrea", "tigray", "sudan", "moyale", "kenya"),
    "Afghanistan / Pakistan": ("afghanistan", "pakistan", "taliban"),
    "DRC / Rwanda": ("congo", "rwanda", "m23"),
    "Thailand / Cambodia": ("thailand", "cambodia"),
}
QUERY_TERMS = ("Taiwan", "Iran", "Ukraine", "North Korea", "Ethiopia", "Pakistan", "Rwanda")
ACTION_WORDS = re.compile(r"\b(airline|flight|shipping|vessel|insur|evacuat|border closure|suspend|rerout|war.risk|embassy|airspace|mobiliz|withdraw)\w*", re.I)

def now_utc():
    return dt.datetime.now(UTC).replace(microsecond=0)

def parse_time(value):
    """Parse common ISO/GDELT/RSS timestamps into aware UTC datetime, or None."""
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(value / (1000 if value > 1e11 else 1), UTC)
        raw = str(value).strip()
        if re.fullmatch(r"\d{14}", raw):
            return dt.datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        t = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        try:
            from email.utils import parsedate_to_datetime
            t = parsedate_to_datetime(str(value))
            return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
        except (ValueError, TypeError, IndexError):
            return None

def iso(t):
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z") if t else None

def scenario(text):
    s = (text or "").lower()
    hits = [key for key, terms in SCENARIOS.items() if any(term in s for term in terms)]
    return hits if hits else ["Unassigned / global"]

def digest(*parts):
    return hashlib.sha256("||".join(str(x) for x in parts).encode()).hexdigest()[:20]

def fetch_json(url, fetch=None):
    if fetch:
        return fetch(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.load(response)

def fetch_xml(url, fetch=None):
    if fetch:
        return fetch(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/rss+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return ET.fromstring(response.read(3_000_000))

def as_number(x):
    try:
        n = float(x)
        return n if n == n and abs(n) != float("inf") else None
    except (TypeError, ValueError):
        return None

def json_or_list(value):
    if isinstance(value, list):
        return value
    try:
        return json.loads(value) if isinstance(value, str) else []
    except (TypeError, ValueError):
        return []

def collect_markets(fetch=fetch_json, clock=now_utc):
    """Discovery of public market candidates; never outcome-match by keywords."""
    at = iso(clock())
    rows, errors = [], []
    for term in QUERY_TERMS:
        params = urllib.parse.urlencode({"term": term, "filter": "open", "contractType": "BINARY", "sort": "liquidity", "limit": 8})
        url = "https://api.manifold.markets/v0/search-markets?" + params
        try:
            records = fetch(url)
            if not isinstance(records, list):
                raise ValueError("Unexpected Manifold schema")
            for item in records:
                if item.get("outcomeType") not in ("BINARY", None) or item.get("isResolved"):
                    continue
                price = as_number(item.get("probability"))
                title = str(item.get("question", ""))[:400]
                if price is None or not 0 <= price <= 1 or not title or scenario(title) == ["Unassigned / global"]:
                    continue
                market_id = str(item.get("id", ""))
                if not market_id:
                    continue
                rows.append({"id": "manifold:" + market_id, "provider": "Manifold", "title": title,
                             "price": round(price, 6), "observed_at": at,
                             "market_url": item.get("url") or "https://manifold.markets/",
                             "end_at": iso(parse_time(item.get("closeTime"))),
                             "liquidity": as_number(item.get("totalLiquidity")),
                             "volume": as_number(item.get("volume")),
                             "scenario_tags": scenario(title), "source_query": term,
                             "status": "candidate_market_not_outcome_verified"})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"source": "Manifold:" + term, "error": str(exc)[:240]})
    # Targeted Gamma search avoids unsupported event sort fields and
    # still requires exact contract ID and the Yes outcome price.
    for term in QUERY_TERMS:
        url = "https://gamma-api.polymarket.com/public-search?" + urllib.parse.urlencode(
            {"q": term, "limit_per_type": 5, "keep_closed_markets": 0})
        try:
            result = fetch(url)
            if not isinstance(result, dict) or not isinstance(result.get("events"), list):
                raise ValueError("Unexpected Polymarket search schema")
            for event in result["events"]:
                for item in event.get("markets", []):
                    title = str(item.get("question") or event.get("title") or "")[:400]
                    if not title or scenario(title) == ["Unassigned / global"]:
                        continue
                    outcomes = json_or_list(item.get("outcomes"))
                    prices = json_or_list(item.get("outcomePrices"))
                    normalized = [str(x).lower() for x in outcomes]
                    if "yes" not in normalized or len(outcomes) != len(prices):
                        continue
                    price = as_number(prices[normalized.index("yes")])
                    if price is None or not 0 <= price <= 1 or item.get("closed"):
                        continue
                    market_id = str(item.get("id", ""))
                    if not market_id:
                        continue
                    rows.append({"id": "polymarket:" + market_id, "provider": "Polymarket", "title": title,
                                 "price": round(price, 6), "observed_at": at,
                                 "market_url": "https://polymarket.com/event/" + str(event.get("slug", "")),
                                 "end_at": iso(parse_time(item.get("endDate"))),
                                 "liquidity": as_number(item.get("liquidityNum") or item.get("liquidity")),
                                 "volume": as_number(item.get("volumeNum") or item.get("volume")),
                                 "scenario_tags": scenario(title), "source_query": term,
                                 "status": "candidate_market_not_outcome_verified"})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append({"source": "Polymarket:" + term, "error": str(exc)[:240]})
    dedup = {r["id"]: r for r in rows}
    return list(dedup.values())[:120], errors, len(QUERY_TERMS) * 2

def xml_child_text(node, names):
    for name in names:
        item = node.find(name)
        if item is not None and item.text:
            return item.text.strip()
    return ""

def collect_official(fetch=fetch_xml, clock=now_utc):
    """Publishers' notices, not independently confirmed conflict intent."""
    at = iso(clock())
    feeds = [
        ("US State Department", "https://travel.state.gov/_res/rss/TAsTWs.xml", "rss"),
        ("UK FCDO", "https://www.gov.uk/foreign-travel-advice.atom", "atom"),
    ]
    rows, errors = [], []
    atom = "{http://www.w3.org/2005/Atom}"
    for publisher, url, kind in feeds:
        try:
            root = fetch(url)
            if not isinstance(root, ET.Element):
                raise ValueError("Expected XML element")
            items = root.findall(".//item") if kind == "rss" else root.findall(".//" + atom + "entry")
            if not items:
                raise ValueError("No RSS/Atom entries")
            for item in items[:240]:
                if kind == "rss":
                    title = xml_child_text(item, ["title"])
                    link = xml_child_text(item, ["link"])
                    published = xml_child_text(item, ["pubDate", "dc:date"]) if False else xml_child_text(item, ["pubDate"])
                else:
                    title = xml_child_text(item, [atom + "title"])
                    ln = item.find(atom + "link")
                    link = ln.get("href", "") if ln is not None else ""
                    published = xml_child_text(item, [atom + "updated", atom + "published"])
                title = re.sub(r"\s+", " ", html.unescape(title))[:400]
                published_at = iso(parse_time(published))
                if not title or not link.startswith("https://"):
                    continue
                rows.append({"id": digest(publisher, link), "publisher": publisher, "title": title,
                             "source_url": link, "published_at": published_at,
                             "observed_at": at, "scenario_tags": scenario(title),
                             "kind": "official_travel_security_notice",
                             "assessment": "protective_advisory_not_military_preparation"})
        except (OSError, ValueError, ET.ParseError, TypeError) as exc:
            errors.append({"source": publisher, "error": str(exc)[:240]})
    return list({r["id"]: r for r in rows}.values()), errors, len(feeds)

def collect_commercial(fetch=fetch_xml, clock=now_utc):
    """Maritime and air-cargo trade-press headline leads, not direct activity data."""
    at = iso(clock())
    feeds = [
        ("The Maritime Executive", "https://www.maritime-executive.com/articles.rss"),
        ("Air Cargo News", "https://www.aircargonews.net/feed/"),
    ]
    rows, errors = [], []
    for publisher, url in feeds:
        try:
            root = fetch(url)
            if not isinstance(root, ET.Element):
                raise ValueError("Expected RSS XML element")
            items = root.findall(".//item")
            if not items:
                raise ValueError("No RSS items")
            for item in items[:120]:
                title = re.sub(r"\s+", " ", html.unescape(xml_child_text(item, ["title"])))[:400]
                link = xml_child_text(item, ["link"])
                if not title or not link.startswith("https://") or not ACTION_WORDS.search(title):
                    continue
                rows.append({"id": digest(link), "title": title, "source_url": link,
                             "publisher_domain": publisher,
                             "published_at": iso(parse_time(xml_child_text(item, ["pubDate"]))),
                             "observed_at": at, "scenario_tags": scenario(title),
                             "kind": "trade_press_commercial_behavior_lead",
                             "assessment": "media_mention_unverified_not_independent_actor_behavior"})
        except (OSError, ValueError, TypeError, ET.ParseError) as exc:
            errors.append({"source": publisher, "error": str(exc)[:240]})
    return list({r["id"]: r for r in rows}.values())[:100], errors, len(feeds)

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

def ingest_mode(state, mode, collectors=None, clock=now_utc):
    collectors = collectors or {"markets": collect_markets, "official": collect_official, "commercial": collect_commercial}
    if mode not in collectors:
        raise ValueError("Invalid collection mode")
    observed = clock()
    try:
        rows, errors, requested = collectors[mode]()
    except Exception as exc:
        rows, errors, requested = [], [{"source": mode, "error": str(exc)[:240]}], 1
    ok = max(0, requested - len(errors))
    status = "collected" if ok == requested else ("partial" if ok else "unavailable")
    health = {"mode": mode, "checked_at": iso(observed), "status": status,
              "source_queries_ok": ok, "source_queries_attempted": requested, "record_count": len(rows),
              "errors": errors,
              "caveat": "Data are source observations or investigatory leads; no likelihood of conflict is inferred."}
    write_json(Path(state) / "health" / (mode + ".json"), health)
    if ok:
        snap = {"mode": mode, "observed_at": iso(observed), "status": status, "records": rows, "health": health}
        path = Path(state) / "history" / mode / (observed.strftime("%Y%m%dT%H%M%SZ") + ".json")
        write_json(path, snap)
        write_json(Path(state) / "latest" / (mode + ".json"), snap)
    return health

def historical_snapshots(state, mode, limit=50):
    paths = sorted((Path(state) / "history" / mode).glob("*.json"))
    return [x for x in (load_json(p) for p in paths[-limit:]) if isinstance(x, dict)]

def update_fusion(state, clock=now_utc):
    """Surface candidate divergences, without promoting any threat level."""
    at = clock()
    latest = {mode: load_json(Path(state) / "latest" / (mode + ".json"), {}) for mode in ("markets", "official", "commercial")}
    health = {mode: load_json(Path(state) / "health" / (mode + ".json"), {"status": "not_collected"}) for mode in ("markets", "official", "commercial")}
    market_hist = historical_snapshots(state, "markets", 36)
    market_asof = parse_time(latest["markets"].get("observed_at"))
    # Failed collection must not replay old changes as new leads.
    market_current = bool(market_asof and dt.timedelta(0) <= (at - market_asof) <= dt.timedelta(hours=12))
    current = ({r["id"]: r for r in latest["markets"].get("records", [])} if market_current else {})
    moves = []
    for key, market in current.items():
        now_p = as_number(market.get("price"))
        current_time = parse_time(market.get("observed_at"))
        if now_p is None or not current_time:
            continue
        past = []
        for snap in market_hist:
            stamp = parse_time(snap.get("observed_at"))
            if not stamp or not dt.timedelta(hours=36) >= (current_time - stamp) >= dt.timedelta(hours=18):
                continue
            for old in snap.get("records", []):
                if old.get("id") == key and as_number(old.get("price")) is not None:
                    past.append((stamp, as_number(old["price"])))
        if not past:
            continue
        old_time, old_price = min(past, key=lambda x: abs((current_time - x[0]).total_seconds() - 86400))
        change = round(now_p - old_price, 4)
        if abs(change) >= .12:
            moves.append({"id": key, "title": market["title"], "scenario_tags": market["scenario_tags"],
                          "change_24h_approx": change, "previous_at": iso(old_time), "current_at": iso(current_time),
                          "url": market.get("market_url"), "classification": "market_repricing_investigation_only",
                          "limitation": "Market question direction may differ from escalation; event definition not cross-validated."})
    # Treat official notices as independently published records, not validation of press headlines.
    fresh_official = []
    official_asof = parse_time(latest["official"].get("observed_at"))
    official_current = bool(official_asof and dt.timedelta(0) <= (at - official_asof) <= dt.timedelta(hours=12))
    for record in (latest["official"].get("records", []) if official_current else []):
        t = parse_time(record.get("published_at"))
        if t and dt.timedelta(0) <= (at - t) <= dt.timedelta(hours=36):
            fresh_official.append(record)
    # Commercial items are media leads and cannot be counted as proof of a commercial decision.
    fresh_commercial = []
    commercial_asof = parse_time(latest["commercial"].get("observed_at"))
    commercial_current = bool(commercial_asof and dt.timedelta(0) <= (at - commercial_asof) <= dt.timedelta(hours=48))
    for record in (latest["commercial"].get("records", []) if commercial_current else []):
        t = parse_time(record.get("published_at")) or parse_time(record.get("observed_at"))
        if t and dt.timedelta(0) <= (at - t) <= dt.timedelta(hours=36):
            fresh_commercial.append(record)
    leads = []
    for move in moves:
        matching = [r for r in fresh_official if set(r.get("scenario_tags", [])) & set(move.get("scenario_tags", []))
                    and "Unassigned / global" not in r.get("scenario_tags", [])]
        leads.append({"scenario_tags": move["scenario_tags"], "market": move,
                      "related_official_notices": [{"title": r["title"], "url": r["source_url"], "published_at": r["published_at"]} for r in matching[:5]],
                      "kind": "cross_source_overlap" if matching else "quiet_discrepancy_candidate",
                      "meaning": "An investigatory lead only: neither a war probability nor proof of advance knowledge."})
    result = {"generated_at": iso(at), "models": ["same-contract roughly-24h repricing", "dated notice/media comparison"],
              "warnings": ["No validated conflict event posterior", "No automatic escalation status",
                           "Official advisories are often reactive", "Media commercial mentions are not independent commercial verification"],
              "health": health, "market_moves": moves[:30], "new_official_notices": fresh_official[:70],
              "commercial_media_leads": fresh_commercial[:70], "preconvergence_leads": leads[:30],
              "source_asof": {m: latest[m].get("observed_at") for m in latest}}
    write_json(Path(state) / "latest" / "fusion.json", result)
    return result

def audit(state, clock=now_utc):
    counts = {}
    for mode in ("markets", "official", "commercial"):
        snapshots = historical_snapshots(state, mode, 500)
        times = [parse_time(s.get("observed_at")) for s in snapshots]
        counts[mode] = {"snapshots": len(snapshots), "first": iso(min(x for x in times if x)) if any(times) else None,
                        "last": iso(max(x for x in times if x)) if any(times) else None}
    result = {"generated_at": iso(clock()), "source_history_coverage": counts,
              "warning_performance": "NOT ESTIMABLE: no event-outcome annotation series or matched non-event controls",
              "next": "Add independent outcome labels and walk-forward forecast snapshots before reporting sensitivity or false-alarm rates."}
    write_json(Path(state) / "latest" / "weekly_audit.json", result)
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("markets", "official", "commercial", "audit", "fusion"), required=True)
    p.add_argument("--state", type=Path, required=True)
    args = p.parse_args()
    if args.mode == "audit":
        result = audit(args.state)
    elif args.mode == "fusion":
        result = update_fusion(args.state)
    else:
        result = ingest_mode(args.state, args.mode)
        update_fusion(args.state)
    print(json.dumps(result, indent=2)[:3000])

if __name__ == "__main__":
    main()
