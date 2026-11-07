#!/usr/bin/env python3
"""AIBA decision-focused fusion: changes, evidence limits, and next collection tasks.

This is a deterministic analyst triage product, NOT a model of war probabilities.
No external language model summarizes unchecked source text. Every novel signal
is tied to a snapshot, source and observed/published interval where available.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from ops_pipeline import iso, parse_time, load_json, write_json, now_utc

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "data" / "decision_registry.json"
CURATED = ROOT / "data" / "verified_hotspots.json"
MAX_AGE = {"watchlist": 12, "official": 12, "commercial": 48}

def recent_snapshot(state, mode, now):
    snap = load_json(Path(state) / "latest" / (mode + ".json"), {}) or {}
    health = load_json(Path(state) / "health" / (mode + ".json"), {}) or {}
    stamp = parse_time(snap.get("observed_at"))
    hours = (now - stamp).total_seconds() / 3600 if stamp else None
    current = hours is not None and 0 <= hours <= MAX_AGE[mode]
    return {"snapshot": snap, "health": health, "available": bool(current),
            "last_asof": iso(stamp), "age_hours": round(hours, 1) if hours is not None else None,
            "status": ("current" if current else "stale_or_missing"),
            "checked": health.get("checked_at"), "collection_status": health.get("status", "never_checked")}

def snapshots(state, mode, limit=100):
    folder = Path(state) / "history" / mode
    return [v for v in (load_json(x) for x in sorted(folder.glob("*.json"))[-limit:]) if isinstance(v, dict)]

def previous_snapshot(history, current_at, min_hours=0.2):
    options = []
    for snap in history:
        stamp = parse_time(snap.get("observed_at"))
        diff = (current_at - stamp).total_seconds() / 3600 if stamp else -1
        if diff >= min_hours:
            options.append((diff, snap))
    return min(options, key=lambda x: x[0])[1] if options else None

def normalize(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()

def matches_case(case, record):
    text = str(record.get("title") or record.get("market_question") or "")
    return any(re.search(pattern, text, re.I) for pattern in case.get("patterns", []))

def change_in_notices(state, mode, now, case, current):
    """Only version changes or post-baseline publication count as NEW.
    
    The first snapshot is a baseline and cannot establish whether an item is new.
    Null publication dates never become 'today' merely because we fetched them.
    """
    if not current["available"]:
        return [], {"comparison": "source not current", "baseline": False}
    snap = current["snapshot"]
    observation = parse_time(snap.get("observed_at"))
    prior = previous_snapshot(snapshots(state, mode), observation)
    if not prior:
        return [], {"comparison": "first snapshot / no prior baseline", "baseline": False}
    previous = {r.get("source_url"): r for r in prior.get("records", []) if r.get("source_url")}
    prev_at = parse_time(prior.get("observed_at"))
    changes = []
    for record in snap.get("records", []):
        url = record.get("source_url")
        if not url or not matches_case(case, record):
            continue
        old = previous.get(url)
        pub = parse_time(record.get("published_at"))
        kind = None
        if old is not None and normalize(old.get("title")) != normalize(record.get("title")):
            kind = "revision_observed_between_checks"
        elif old is None and pub and prev_at and prev_at <= pub <= observation:
            kind = "first_seen_with_new_publication_timestamp"
        if not kind:
            continue
        changes.append({
            "source_family": "official_protective" if mode == "official" else "commercial_media",
            "kind": kind, "title": record.get("title"), "source_url": url,
            "publisher": record.get("publisher") or record.get("publisher_domain"),
            "published_at": iso(pub), "observed_at": iso(observation),
            "previous_check_at": iso(prev_at), "root": normalize(url.split("?")[0]),
            "assessment_ceiling": ("Published government notice; not evidence of military preparations"
                                   if mode == "official" else
                                   "Article headline, not independently verified commercial behavior")
        })
    # A syndication feed and the same publisher's RSS are one underlying story,
    # not independent behavior roots or repeated signal confirmation.
    dedup = {}
    for record in changes:
        title_root = normalize(re.sub(r"\s+-\s+[^-]{1,60}$", "", record["title"] or ""))
        key = title_root if mode == "commercial" else record["root"]
        dedup.setdefault(key, record)
    return list(dedup.values())[:15], {"comparison": "prior vs current observations", "baseline": True}

def market_changes(state, current, now):
    """Strict same-contract deltas; 6h and 24h are alternative comparison windows."""
    if not current["available"]:
        return [], {"baseline": False, "reason": "watchlist unavailable/stale"}
    snap = current["snapshot"]
    time_now = parse_time(snap.get("observed_at"))
    history = snapshots(state, "watchlist", 80)
    moves = []
    paired = 0
    eligible = 0
    for record in snap.get("records", []):
        if record.get("status") != "eligible":
            continue
        eligible += 1
        options = []
        for prior in history:
            t = parse_time(prior.get("observed_at"))
            delta_h = (time_now - t).total_seconds() / 3600 if t else -1
            if not (4 <= delta_h <= 36):
                continue
            prior_quote = next((x for x in prior.get("records", [])
                                if x.get("id") == record.get("id") and x.get("status") == "eligible"
                                and x.get("market_question") == record.get("market_question")), None)
            if prior_quote:
                options.append((delta_h, prior_quote, t))
        comparisons = []
        for label, lo, hi, center, threshold in (("6h", 4, 10, 6, .08), ("24h", 18, 36, 24, .12)):
            valid = [o for o in options if lo <= o[0] <= hi]
            if not valid:
                continue
            _, old_quote, old_at = min(valid, key=lambda x: abs(x[0] - center))
            paired += 1
            change = round(float(record["price"]) - float(old_quote["price"]), 5)
            comparisons.append({"window": label, "change": change, "baseline_at": iso(old_at),
                                "threshold": threshold})
        flagged = [c for c in comparisons if abs(c["change"]) >= c["threshold"]]
        if flagged:
            largest = max(flagged, key=lambda x: abs(x["change"]))
            moves.append({
                "id": record["id"], "case_id": record["case_id"], "event": record["event"],
                "exact_question": record["market_question"], "effect": record["effect"],
                "change_pp": round(largest["change"] * 100, 2),
                "window": largest["window"], "previous_at": largest["baseline_at"],
                "observed_at": record["observed_at"], "price_yes": record["price"],
                "end_at": record.get("end_at"), "source_url": record["source_url"],
                "caveat": record["caveat"], "source_family": "matched_public_market",
                "assessment_ceiling": "Market repricing, not forecast verification or attack probability",
                "direction": ("YES price rose" if largest["change"] > 0 else "YES price fell"),
                "threshold_type": "exploratory; not historically optimized"
            })
    moves.sort(key=lambda m: -abs(m["change_pp"]))
    return moves, {"eligible": eligible, "window_comparisons": paired,
                   "reason": "Comparisons need prior same-ID observations 4–10h or 18–36h earlier; insufficient history is not a null signal."}

def status_summary(mode_record):
    return {"collection_status": mode_record["collection_status"], "status": mode_record["status"],
            "latest_observation": mode_record["last_asof"], "age_hours": mode_record["age_hours"],
            "last_check": mode_record["checked"]}

def time_of(date):
    return parse_time(date)

def case_brief(case_cfg, curated, market, official, commercial, coverage, now):
    case_id = case_cfg["id"]
    state = curated.get("state", "No curated baseline")
    asof = curated.get("asof")
    related_moves = [m for m in market if m["case_id"] == case_id]
    dated_official = official
    dated_commercial = commercial
    # Evidence quality is not predictive skill; new commercial/official records
    # remain source observations, NOT independent costly action.
    if related_moves and dated_official:
        priority = "Investigate linked changes"
        headline = "A matched contract repriced alongside a newly observed official advisory change."
        implication = ("Two measurement systems changed, but both may react to the same news. Verify the event dates "
                       "and an independent costly action before inferring preparation.")
    elif related_moves:
        priority = "Investigate market repricing"
        headline = "A scenario-matched contract moved materially before independent confirmation here."
        implication = ("Check exact contract resolution terms, liquidity and trade drivers. No updated advisory in "
                       "these sources does not establish that public officials or military forces were quiet.")
    elif dated_official:
        priority = "Verify policy change"
        headline = "An official protective notice changed relative to the preceding collection."
        implication = ("This demonstrates a public advisory change, often reactive. Investigate whether independent "
                       "actors changed behavior earlier, rather than counting the advisory as attack preparation.")
    elif dated_commercial:
        priority = "Verify reported action"
        headline = "New commercial-disruption reporting requires primary-source confirmation."
        implication = ("Check operator identity, whether a real route/insurance rule changed, and its effective date. "
                       "Reprints and syndicated articles do not constitute independent economic decisions.")
    elif not coverage["watchlist"]["available"] and not coverage["official"]["available"]:
        priority = "Collection gap"
        headline = "Insufficient current monitored evidence for a new-change assessment."
        implication = ("Keep the historical severity baseline, but do not infer stability from missing or stale inputs. "
                       "Restore source coverage before interpreting silence.")
    else:
        priority = "Maintain watch"
        headline = "No reproducible new change established by the currently implemented feeds."
        implication = ("This is not evidence of reduced threat. Longstanding risk and current-period changes are "
                       "separate judgments, and these public feeds do not cover military preparations exhaustively.")
    source_evidence = (
        [{"source_family": "matched_public_market", "title": m["exact_question"],
          "source_url": m["source_url"], "published_at": None, "observed_at": m["observed_at"],
          "change_pp": m["change_pp"], "window": m["window"],
          "assessment_ceiling": m["assessment_ceiling"]} for m in related_moves[:4]]
        + dated_official[:4] + dated_commercial[:4]
    )
    curated_counter = [
        {"title": s.get("title"), "date": s.get("date"), "assessment": s.get("assessment")}
        for s in curated.get("signals", []) if "counter" in str(s.get("assessment", "")).lower()
    ][:3]
    return {
        "id": case_id, "title": curated.get("name", case_id), "question": case_cfg["question"],
        "warning_horizon": case_cfg["horizon"],
        "standing_state": state, "standing_asof": asof,
        "standing_confidence": curated.get("confidence", "Not specified"),
        "collection_priority": priority, "what_changed": headline,
        "so_what": implication, "what_would_change_assessment": case_cfg["next"],
        "alternative_explanation": curated.get("alternatives") or case_cfg["alternative"],
        "source_evidence": source_evidence, "market_repricing_count": len(related_moves),
        "official_change_count": len(dated_official), "commercial_media_change_count": len(dated_commercial),
        "historical_counter_signals": curated_counter,
        "scope_note": "Case-specific; adjacent conflict reports do not automatically establish direct interstate escalation.",
        "verification": ("No automated classification as imminent, critical or independently confirmed. "
                         "Curated dossier is a dated human-supplied baseline, not refreshed by this run.")
    }

def build(state, registry=REGISTRY, curated_file=CURATED, clock=now_utc, write=True):
    now = clock()
    config = json.loads(Path(registry).read_text(encoding="utf-8"))
    original = {x["id"]: x for x in json.loads(Path(curated_file).read_text(encoding="utf-8"))}
    coverage = {mode: recent_snapshot(state, mode, now) for mode in MAX_AGE}
    moves, market_diag = market_changes(state, coverage["watchlist"], now)
    notes = {}
    cases = []
    for case_cfg in config["cases"]:
        key = case_cfg["id"]
        official, official_diag = change_in_notices(state, "official", now, case_cfg, coverage["official"])
        commercial, commercial_diag = change_in_notices(state, "commercial", now, case_cfg, coverage["commercial"])
        notes[key] = {"official": official_diag, "commercial": commercial_diag}
        cases.append(case_brief(case_cfg, original.get(key, {}), moves, official, commercial, coverage, now))
    ranks = ["Investigate linked changes", "Investigate market repricing", "Verify policy change",
             "Verify reported action", "Collection gap", "Maintain watch"]
    cases.sort(key=lambda x: (ranks.index(x["collection_priority"]), x["title"]))
    changed = [x for x in cases if x["source_evidence"]]
    headline = (f"{len(changed)} of {len(cases)} cases have new monitored change leads; "
                "none is automatically a verified conflict warning."
                if changed else
                "No new case-specific change established by the currently implemented feeds; this is not a no-risk assessment.")
    output = {
        "version": 1, "generated_at": iso(now),
        "executive_summary": headline,
        "operational_action": ("Review changed case evidence and seek independent cost-bearing action."
                               if changed else
                               "Prioritize missing coverage and scenario-specific signposts; avoid repeat alerts for static advisories."),
        "cases": cases,
        "source_health": {mode: status_summary(v) for mode, v in coverage.items()},
        "market_diagnostics": market_diag, "new_change_count": len(changed),
        "new_market_moves": len(moves),
        "baseline_comparison": notes,
        "limits": [
            "A source-wide 6h scan is not evidence of comprehensive military, shipping, or insurance coverage.",
            "First successful collection establishes a baseline, not a new warning.",
            "Published_at null cannot be treated as an event occurring at fetched_at.",
            "Market YES prices measure their exact questions and horizons; not probabilities of war.",
            "Government advisories are often reactive and a syndicated media headline is not independent commercial behavior.",
            "Curated hotspot states are historical context; this layer does not update their verified status or estimate conflict probabilities."
        ]
    }
    if write:
        path = Path(state)
        write_json(path / "latest" / "decision_briefs.json", output)
        write_json(path / "history" / "decision_briefs" / now.strftime("%Y%m%dT%H%M%SZ.json"), output)
    return output

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    args = p.parse_args()
    result = build(args.state)
    print(json.dumps({"executive_summary": result["executive_summary"],
                      "new_change_count": result["new_change_count"],
                      "case_priorities": {x["id"]: x["collection_priority"] for x in result["cases"]}},
                     indent=2))
