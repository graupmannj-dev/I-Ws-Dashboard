#!/usr/bin/env python3
"""Collect explicitly registered, outcome-matched public forecast markets.

Discovery market search is NOT the monitoring universe: exact IDs ensure that a
market remains observable after it drops out of top-search results.
No market price is treated as a calibrated probability of military conflict.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import urllib.parse
from pathlib import Path
from ops_pipeline import now_utc, fetch_json, parse_time, as_number, iso, write_json

REGISTRY = Path(__file__).resolve().parent / "data" / "decision_registry.json"

def normalize(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text).lower())).strip()

def list_value(item):
    if isinstance(item, list):
        return item
    if isinstance(item, str):
        try:
            val = json.loads(item)
            return val if isinstance(val, list) else []
        except (ValueError, TypeError):
            return []
    return []

def market_url(contract):
    provider, market_id = contract["id"].split(":", 1)
    quoted = urllib.parse.quote(market_id, safe="")
    if provider == "manifold":
        return "https://api.manifold.markets/v0/market/" + quoted
    if provider == "polymarket":
        return "https://gamma-api.polymarket.com/markets/" + quoted
    raise ValueError("Unknown registry provider")

def parse_contract(contract, payload, when):
    if not isinstance(payload, dict):
        raise ValueError("Unexpected market response")
    provider, identifier = contract["id"].split(":", 1)
    actual_id = str(payload.get("id", ""))
    if actual_id != identifier:
        raise ValueError("Market ID changed; refuse re-assignment")
    title = str(payload.get("question") or "")[:500]
    if normalize(contract["expected"]) not in normalize(title):
        raise ValueError("Question changed or unexpected contract definition")
    if provider == "manifold":
        if payload.get("outcomeType") != "BINARY":
            raise ValueError("Not a binary market")
        price = as_number(payload.get("probability"))
        closed = bool(payload.get("isResolved")) or bool(payload.get("isClosed"))
        end_at = parse_time(payload.get("closeTime"))
        liquid = as_number(payload.get("totalLiquidity"))
        source_url = payload.get("url")
    else:
        outcomes = [str(x).lower() for x in list_value(payload.get("outcomes"))]
        prices = list_value(payload.get("outcomePrices"))
        if len(outcomes) != len(prices) or "yes" not in outcomes:
            raise ValueError("Missing unambiguous YES outcome")
        price = as_number(prices[outcomes.index("yes")])
        closed = bool(payload.get("closed"))
        end_at = parse_time(payload.get("endDate"))
        liquid = as_number(payload.get("liquidityNum") or payload.get("liquidity"))
        slug = payload.get("slug", "")
        source_url = "https://polymarket.com/event/" + urllib.parse.quote(str(slug), safe="-") if slug else market_url(contract)
    if price is None or price < 0 or price > 1:
        raise ValueError("Invalid YES price")
    status = "eligible"
    if closed or (end_at and end_at <= when):
        status = "expired_or_closed"
    elif liquid is None:
        status = "liquidity_unreported"
    elif liquid < contract["min_liquidity"]:
        status = "thin_market"
    # Different providers' liquidity units are not comparable.
    return {"id": contract["id"], "case_id": contract["case_id"],
            "event": contract["event"], "effect": contract["effect"],
            "market_question": title, "expected_question": contract["expected"],
            "source_url": source_url, "provider": provider, "price": round(price, 6),
            "liquidity": liquid, "liquidity_unit": "Manifold play units" if provider == "manifold" else "Polymarket market units",
            "end_at": iso(end_at), "observed_at": iso(when), "status": status,
            "caveat": contract["caveat"], "date_horizon": contract["horizon"],
            "interpretation": "Single-contract YES quote; not a calibrated 7/30-day military-attack probability."}

def collect_watchlist(state, registry=REGISTRY, fetch=fetch_json, clock=now_utc):
    when = clock()
    cfg = json.loads(Path(registry).read_text(encoding="utf-8"))
    records, failures = [], []
    for contract in cfg["markets"]:
        try:
            record = parse_contract(contract, fetch(market_url(contract)), when)
            records.append(record)
        except Exception as exc:
            failures.append({"id": contract["id"], "error": f"{type(exc).__name__}: {exc}"[:210]})
    attempted = len(cfg["markets"])
    ok = len(records)
    status = "collected" if ok == attempted else ("partial" if ok else "unavailable")
    health = {"mode": "watchlist", "checked_at": iso(when), "status": status,
              "source_queries_ok": ok, "source_queries_attempted": attempted,
              "record_count": len(records), "errors": failures, "registry_version": cfg["version"],
              "caveat": "Exact contract questions, not event probabilities or interchangeable outcomes."}
    state = Path(state)
    write_json(state / "health" / "watchlist.json", health)
    if ok:
        snapshot = {"mode": "watchlist", "observed_at": iso(when), "status": status,
                    "registry_version": cfg["version"], "records": records, "health": health}
        write_json(state / "history" / "watchlist" / when.strftime("%Y%m%dT%H%M%SZ.json"), snapshot)
        write_json(state / "latest" / "watchlist.json", snapshot)
    return health

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(collect_watchlist(args.state), indent=2))
