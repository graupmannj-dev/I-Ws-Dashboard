#!/usr/bin/env python3
"""Retrospective GDELT screening vs provisional UCDP coded violence (SHADOW).

This evaluates a country-exposure proxy for a public lethal-event outcome.
It does NOT validate interstate escalation, actual war onset or probability.
Never use unobserved UCDP release months as negative labels.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.gdelt_shadow_monitor import analyze_day
from scripts.merge_gdelt_history import SOURCE_PROFILE, validate_record

UCDP_VERSION = "26.01.26.09"
UCDP_SOURCE_URL = "https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_01_26_09.csv"
OUTCOME_COVERAGE_START = dt.date(2026, 1, 1)
OUTCOME_COVERAGE_END = dt.date(2026, 9, 30)
HORIZON = 7
MIN_PRIOR_QUIET = 14
REQUIRED = {"id", "country", "type_of_violence", "date_start",
            "date_end", "date_prec", "event_clarity", "code_status", "high"}


def parse_date(value):
    return dt.date.fromisoformat(str(value).strip()[:10])


def iso_day(value):
    return parse_date(value)


def load_history(path):
    """Accept only the verified four-root v1 file; v2 must be evaluated separately."""
    by_day = {}
    source = Path(path).read_bytes()
    for line_num, line in enumerate(source.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            day = validate_record(record)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Historical row {line_num}: {exc}") from exc
        if day in by_day:
            raise ValueError(f"Duplicate historical date {day}")
        by_day[day] = record
    if not by_day:
        raise ValueError("No valid GDELT aggregate records")
    return by_day, hashlib.sha256(source).hexdigest()


def country_crosswalk(path):
    """Ex-ante fixed target universe and exact reviewed UCDP country spellings."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"gdelt_code", "ucdp_country"}.issubset(reader.fieldnames or []):
            raise ValueError("Crosswalk must provide gdelt_code,ucdp_country")
        result = {}
        source_names = set()
        for row in reader:
            code = row["gdelt_code"].strip()
            name = row["ucdp_country"].strip()
            if not (len(code) == 3 and code.isalpha() and code.upper() == code and name):
                raise ValueError("Crosswalk uses invalid GDELT code or blank UCDP name")
            if code in result or name in source_names:
                raise ValueError("Duplicate/ambiguous crosswalk")
            source_names.add(name)
            result[code] = name
    if not result:
        raise ValueError("Crosswalk must select an ex-ante country universe")
    return result


def load_ucdp(path, names):
    """Only exact-date, clear state-based candidate events become positives.

    Imprecise and review-needed events are retained as censoring intervals.
    For any given named country in the source, a future horizon intersecting
    uncertain rows is not coded as a negative.
    """
    src = Path(path).read_bytes()
    try:
        reader = csv.DictReader(io.StringIO(src.decode("utf-8-sig", errors="strict")))
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError(f"UCDP CSV lacks required fields: {sorted(REQUIRED-set(reader.fieldnames or []))}")
        seen = {}
        country_rows = Counter()
        exact = defaultdict(set)
        ambiguous = defaultdict(set)
        reasons = Counter()
        for row in reader:
            uid = row["id"].strip()
            if not uid:
                raise ValueError("UCDP event without persistent id")
            if uid in seen:
                if seen[uid] != row:
                    raise ValueError(f"Contradictory UCDP event ID {uid}")
                continue
            seen[uid] = row
            name = row["country"].strip()
            if name not in names:
                continue
            start, end = parse_date(row["date_start"]), parse_date(row["date_end"])
            if end < start:
                raise ValueError(f"UCDP date interval reversed: event {uid}")
            if end < OUTCOME_COVERAGE_START or start > OUTCOME_COVERAGE_END:
                continue
            country_rows[name] += 1
            if row["type_of_violence"].strip() != "1":
                continue
            high = int(float(row["high"]))
            if high <= 0:
                reasons["nonfatal_or_missing_high"] += 1
                continue
            valid = (row["date_prec"].strip() == "1"
                     and start == end
                     and row["event_clarity"].strip() == "1"
                     and row["code_status"].strip().lower() == "clear")
            if valid:
                exact[name].add(start)
                reasons["qualified_positive_event"] += 1
            else:
                for day in (start + dt.timedelta(days=i) for i in range((end-start).days+1)):
                    if OUTCOME_COVERAGE_START <= day <= OUTCOME_COVERAGE_END:
                        ambiguous[name].add(day)
                reasons["ambiguous_quarantined"] += 1
    except UnicodeError as exc:
        raise ValueError("UCDP source is not UTF-8") from exc
    return {
        "exact": exact, "ambiguous": ambiguous, "source_rows": country_rows,
        "reason_counts": dict(reasons), "sha256": hashlib.sha256(src).hexdigest(),
        "unique_event_ids": len(seen),
    }


def members(case):
    parts = case.split(":")
    if parts[0] == "BILAT" and len(parts) == 3:
        return parts[1:]
    if parts[0] == "DOMESTIC" and len(parts) == 2:
        return parts[1:]
    raise ValueError(f"Invalid GDELT case key: {case}")


def seven_28_candidates(by_day, date):
    """Simple matched-source 7/28 comparator, NOT deployed production model.

    No beta-binomial tail is computed here. It must not be described as
    the production six-root discovery engine.
    """
    preceding = [date - dt.timedelta(days=n) for n in range(7, 35)]
    recent = [date - dt.timedelta(days=n) for n in range(7)]
    if not all(d in by_day for d in preceding+recent):
        return None
    totals0 = sum(by_day[d]["selected"] for d in preceding)
    totals1 = sum(by_day[d]["selected"] for d in recent)
    if not totals0 or not totals1:
        return None
    keys = set().union(*(set(by_day[d]["counts"]) for d in recent))
    candidates = set()
    for key in keys:
        before = sum(by_day[d]["counts"].get(key, 0) for d in preceding)
        now = sum(by_day[d]["counts"].get(key, 0) for d in recent)
        if now < 9:
            continue
        ratio = ((now + 0.5)/(totals1 + 20.0))/((before + 0.5)/(totals0+20.0))
        if ratio >= 1.65:
            candidates.add(key)
    return candidates


def exposure(cases):
    result = set()
    for case in cases:
        result.update(members(case))
    return result


def outcome_window(ledger, name, date, horizon=HORIZON):
    window = [date + dt.timedelta(days=n) for n in range(1, horizon+1)]
    if window[-1] > OUTCOME_COVERAGE_END:
        return None, "beyond_ucdp_release"
    if any(x in ledger["ambiguous"][name] for x in window):
        return None, "imprecise_or_uncertain_ucdp_event"
    return int(any(x in ledger["exact"][name] for x in window)), None


def confusion(rows, prediction_key, subset=None):
    evaluated = [r for r in rows if subset is None or subset(r)]
    tp = sum(r[prediction_key] and r["outcome"] == 1 for r in evaluated)
    fp = sum(r[prediction_key] and r["outcome"] == 0 for r in evaluated)
    fn = sum((not r[prediction_key]) and r["outcome"] == 1 for r in evaluated)
    tn = sum((not r[prediction_key]) and r["outcome"] == 0 for r in evaluated)
    def rate(a, b):
        return round(a/b, 4) if b else None
    n = tp+fp+fn+tn
    return {
        "country_days": n, "positives": tp+fn, "negatives": fp+tn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": rate(tp, tp+fp), "recall": rate(tp, tp+fn),
        "false_positive_rate": rate(fp, fp+tn),
        "alerts_per_100_country_days": round((tp+fp)*100/n, 2) if n else None,
        "event_base_rate": rate(tp+fn, n),
        "note": "Correlated overlapping 7-day country horizons; descriptive only, no skill significance test."
    }


def evaluate(history, crosswalk, ucdp, start=None, end=None):
    by_day, gdelt_hash = load_history(history)
    cases = country_crosswalk(crosswalk)
    ledger = load_ucdp(ucdp, set(cases.values()))
    start = max(start or min(by_day), min(by_day)+dt.timedelta(days=34),
                OUTCOME_COVERAGE_START)
    end = min(end or max(by_day), max(by_day), OUTCOME_COVERAGE_END-dt.timedelta(days=HORIZON))
    records, excluded = [], Counter()
    active = {code: name for code, name in cases.items() if ledger["source_rows"][name]>0}
    for code, name in cases.items():
        if code not in active:
            excluded["country_not_verified_in_source_vocabulary"] += 1
    for day in (start + dt.timedelta(days=n) for n in range(max(0, (end-start).days+1))):
        try:
            screen = analyze_day(by_day, day)
            compare = seven_28_candidates(by_day, day)
        except (ValueError, KeyError):
            excluded["invalid_source_day"] += 1
            continue
        if compare is None or not screen["baseline"]["eligible"]:
            excluded["incomplete_gdelt_lagged_baseline"] += 1
            continue
        n90 = exposure({x["case"] for x in screen["established_leads"]+screen["emerging_leads"]})
        n728 = exposure(compare)
        for code, name in active.items():
            outcome, reason = outcome_window(ledger, name, day)
            if reason:
                excluded[reason] += 1
                continue
            past = [day-dt.timedelta(days=i) for i in range(1, MIN_PRIOR_QUIET+1)]
            past_quiet = (all(p not in ledger["exact"][name] for p in past)
                          and all(p not in ledger["ambiguous"][name] for p in past))
            records.append({
                "day": day.isoformat(), "gdelt_country_code": code,
                "ucdp_country": name, "outcome": outcome,
                "shadow_90d": int(code in n90), "simple_7_28d": int(code in n728),
                "prior_14d_quiet": int(past_quiet),
                "outcome_definition": "any_future_7d_clear_exact_state_based_lethal_ucdp_event",
                "proxy_level": "country_exposure_not_bilateral_case_confirmation",
            })
    totals = {
        "all_country_days": {
            "shadow_90d": confusion(records, "shadow_90d"),
            "simple_7_28d": confusion(records, "simple_7_28d"),
        },
        "quiet_country_days": {
            "shadow_90d": confusion(records, "shadow_90d", lambda r: r["prior_14d_quiet"]),
            "simple_7_28d": confusion(records, "simple_7_28d", lambda r: r["prior_14d_quiet"]),
        },
    }
    coverage = {"start": start.isoformat(), "end": end.isoformat(),
                "ucdp_release_end": OUTCOME_COVERAGE_END.isoformat(),
                "horizon_days": HORIZON, "countries_preselected": list(sorted(cases)),
                "countries_with_recognized_ucdp_rows": list(sorted(active)),
                "unmatched_country_codes": sorted(set(cases)-set(active)),
                "excluded": dict(sorted(excluded.items()))}
    return records, {
        "status": ("exploratory_proxy_only" if records else "insufficient_labeled_coverage"),
        "source_profile": SOURCE_PROFILE,
        "source_gdelt_sha256": gdelt_hash,
        "outcome_dataset": "UCDP Candidate Events",
        "outcome_version": UCDP_VERSION,
        "outcome_source_url": UCDP_SOURCE_URL,
        "ucdp_csv_sha256": ledger["sha256"],
        "ucdp_candidate_event_ids": ledger["unique_event_ids"],
        "ucdp_filter_counts": ledger["reason_counts"],
        "coverage": coverage, "metrics": totals,
        "caveats": [
            "Retrospective backtest generated after outcomes; not a record of predictions issued in advance.",
            "UCDP candidate lethal events are not interstate-war onsets, escalation judgments, or military decisions.",
            "Country association of bilateral GDELT case leads is a proxy, not evidence its named states fought.",
            "Unmapped/uncertain UCDP country names excluded, not assumed negative.",
            "No candidate outcomes after September 30 2026 are scored; candidate data are provisional.",
            "Non-events mean no UCDP-coded qualifying event in covered country-days, not proof of peace.",
            "Source media dependence, label revisions, overlapping horizons, selection of countries, and no external prospective holdout preclude forecast-skill claims.",
            "The comparator is a matched-profile simple 7/28 screen and is not the six-root live production Bayesian-tail implementation.",
        ],
        "approved_for_alert_promotion": False
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history",required=True)
    p.add_argument("--ucdp",required=True)
    p.add_argument("--crosswalk",default="data/validation/ucdp_country_crosswalk_pilot.csv")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--output",default="validation-shadow")
    a=p.parse_args()
    rows, report=evaluate(a.history,a.crosswalk,a.ucdp,
                          start=parse_date(a.start) if a.start else None,
                          end=parse_date(a.end) if a.end else None)
    path=Path(a.output)
    path.mkdir(parents=True,exist_ok=True)
    with (path/"country_day_pilot.csv").open("w",encoding="utf-8",newline="") as f:
        fields=["day","gdelt_country_code","ucdp_country","outcome","shadow_90d",
                "simple_7_28d","prior_14d_quiet","outcome_definition","proxy_level"]
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (path/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
