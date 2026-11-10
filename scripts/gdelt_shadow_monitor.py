#!/usr/bin/env python3
"""Source-matched GDELT 17-20 daily baseline, shadow screening only.

Consumes PR17 daily aggregates. Adds optional next UTC daily archives without
mixing root scopes or silently converting a missing archive into zero events.
No production warning score, severity change or predictive probability.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import statistics
import sys
import urllib.error
import urllib.request

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.historical_gdelt_baseline import URL, daily_counts
from scripts.merge_gdelt_history import merge, validate_record, SOURCE_PROFILE

WINDOW_DAYS = 90
MIN_DAYS = 28
MIN_COVERAGE = 0.9
MAX_FORWARD_DAYS = 14


def iso_day(day):
    return day.strftime("%Y%m%d")


def percentiles(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def prior_window(by_day, day):
    """Pre-observation calendar days only: never use the current/future event."""
    history_start = min(by_day)
    first = max(history_start, day - dt.timedelta(days=WINDOW_DAYS))
    wanted = [first + dt.timedelta(days=x) for x in range((day - first).days)]
    available = [by_day[d] for d in wanted if d in by_day]
    recent = [day - dt.timedelta(days=d) for d in range(1, MIN_DAYS + 1)]
    eligible = (len(wanted) >= MIN_DAYS
                and all(d in by_day for d in recent)
                and len(available) >= MIN_DAYS
                and len(available) / len(wanted) >= MIN_COVERAGE)
    return available, {
        "eligible": eligible,
        "start": first.isoformat(),
        "end": (day - dt.timedelta(days=1)).isoformat(),
        "expected_days": len(wanted),
        "valid_days": len(available),
        "coverage": round(len(available) / len(wanted), 4) if wanted else 0,
        "complete_last_28_days": all(d in by_day for d in recent),
        "reason": None if eligible else "Insufficient calendar coverage; do not score missing days as zero",
    }


def analyze_day(by_day, date, profile=SOURCE_PROFILE):
    """Descriptive volume-normalized baseline with sparse-key separate routing.

    Caller MUST ensure every source record shares the declared profile and
    denominator. Six-root GCS migration independently validates this.
    """
    current = by_day.get(date)
    if current is None:
        raise ValueError(f"No valid daily aggregate for {date}")
    prior, health = prior_window(by_day, date)
    result = {
        "day": date.isoformat(),
        "profile": profile,
        "selected_events": current["selected"],
        "all_events": current["rows"],
        "baseline": health,
        "screen_status": "shadow_only_not_predictive",
        "established_leads": [],
        "emerging_leads": [],
        "observed_cases": 0,
        "eligible_established_cases": 0,
        "eligible_sparse_cases": 0,
    }
    if not health["eligible"]:
        return result
    prior_events = sum(r["selected"] for r in prior)
    if prior_events <= 0:
        raise ValueError("Historical denominator is zero")
    keys = set(current["counts"])
    result["observed_cases"] = len(keys)
    for key in keys:
        count = current["counts"][key]
        if count < 5:
            continue
        hcounts = [r["counts"].get(key, 0) for r in prior]
        observed_days = sum(v > 0 for v in hcounts)
        p = [v / r["selected"] for v, r in zip(hcounts, prior)]
        now_share = count / current["selected"]
        p95 = percentiles(p, .95)
        cumulative = sum(hcounts)
        base_share = cumulative / prior_events
        # Use a bounded ratio only if the baseline has enough actual evidence.
        # An unsampled case is not "thousands of times more threatening."
        established = observed_days >= 28 and cumulative >= 50
        if established:
            result["eligible_established_cases"] += 1
        else:
            result["eligible_sparse_cases"] += 1
        if established:
            candidate = (now_share > 1.5 * p95 and
                         now_share > 2 * base_share and count >= 5)
        else:
            candidate = (count >= 10 and now_share > max(1.5 * p95, .0001))
        if not candidate:
            continue
        item = {
            "case": key, "day": date.isoformat(), "current_count": count,
            "current_event_share": round(now_share, 8),
            "baseline_90_p50_share": round(statistics.median(p), 8),
            "baseline_90_p95_share": round(p95, 8),
            "baseline_90_pooled_share": round(base_share, 8),
            "baseline_nonzero_days": observed_days,
            "baseline_event_count": cumulative,
            "baseline_valid_days": len(prior),
            "ratio_to_baseline": round(now_share / base_share, 2) if established and base_share else None,
            "baseline_kind": "established" if established else "sparse_or_new",
            "interpretation": (
                "Above descriptive established-case reference; investigative lead only."
                if established else
                "Sparse/unobserved case history; novelty is not evidence of escalation."
            ),
            "executive_eligible": False,
        }
        result["established_leads" if established else "emerging_leads"].append(item)
    for field in ("established_leads", "emerging_leads"):
        result[field].sort(key=lambda x: (-x["current_count"], -x["current_event_share"], x["case"]))
    result["established_lead_count"] = len(result["established_leads"])
    result["emerging_lead_count"] = len(result["emerging_leads"])
    result["established_leads"] = result["established_leads"][:50]
    result["emerging_leads"] = result["emerging_leads"][:50]
    return result


def collect_forward(by_day, through, fetcher=None, max_days=MAX_FORWARD_DAYS):
    """Bounded forward-only daily archive retrieval from the last backfill day."""
    fetcher = fetcher or (lambda url: urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "AIBA-GDELT-Shadow-Monitor/1.0"}),
        timeout=90).read())
    last = max(by_day)
    if through < last:
        raise ValueError(f"through {through} precedes last historical day {last}")
    dates = [last + dt.timedelta(days=n) for n in range(1, (through - last).days + 1)]
    if len(dates) > max_days:
        raise ValueError(f"Forward gap {len(dates)} days exceeds {max_days}; update the retained baseline in bounded batches")
    failures, added = [], []
    for day in dates:
        stamp = iso_day(day)
        try:
            record = daily_counts(fetcher(URL.format(day=stamp)), stamp)
            validate_record(record)
            by_day[day] = record
            added.append(day)
        except (OSError, ValueError, RuntimeError, KeyError, TimeoutError) as exc:
            failures.append({"day": day.isoformat(), "error": type(exc).__name__,
                             "detail": str(exc)[:150]})
    return added, failures


def run(history, out_dir, through=None, fetcher=None):
    by_day = merge(history)
    original_end = max(by_day)
    first = min(by_day)
    added = failures = []
    if through is not None:
        added, failures = collect_forward(by_day, through, fetcher=fetcher)
    current = max(by_day)
    # Forward evaluations only; if nothing new was ingested, backtest the
    # final historical day and identify it as a REPLAY, not a current alert.
    scored_days = added if added else [original_end]
    reports = [analyze_day(by_day, day) for day in scored_days]
    latest = reports[-1]
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "daily_aggregates.jsonl").open("w", encoding="utf-8") as f:
        for day in sorted(by_day):
            f.write(json.dumps(by_day[day], sort_keys=True) + "\n")
    with (output / "shadow_comparisons.jsonl").open("w", encoding="utf-8") as f:
        for record in reports:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    (output / "latest_shadow_comparison.json").write_text(
        json.dumps(latest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "profile": SOURCE_PROFILE,
        "historical_start": first.isoformat(),
        "historical_end": original_end.isoformat(),
        "available_end": current.isoformat(),
        "requested_through": through.isoformat() if through else None,
        "freshly_collected_days": [x.isoformat() for x in added],
        "failed_days": failures,
        "total_valid_days": len(by_day),
        "mode": "forward_shadow" if added else "historical_replay_only",
        "latest_comparison_date": latest["day"],
        "latest_comparison_eligible": latest["baseline"]["eligible"],
        "latest_established_leads_total": latest.get("established_lead_count", 0),
        "latest_emerging_leads_total": latest.get("emerging_lead_count", 0),
        "approved_for_production": False,
        "warning": "GDELT news-coded event-share departures, not conflict forecasts. Do not join to 13/16/17/18/19/20 denominators or auto-promote to executive alerts.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", nargs="+", required=True, help="Downloaded backfill artifact folder(s) or daily.jsonl")
    parser.add_argument("--output", default="gdelt-shadow-baseline")
    parser.add_argument("--through", help="Optional last UTC date to fetch, YYYY-MM-DD; max 14 forward days")
    args = parser.parse_args()
    day = dt.date.fromisoformat(args.through) if args.through else None
    print(json.dumps(run(args.history, args.output, through=day), indent=2))


if __name__ == "__main__":
    main()
