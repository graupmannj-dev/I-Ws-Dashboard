#!/usr/bin/env python3
"""Combine bounded PR17 GDELT backfills; replay calendar-correct baselines in shadow mode.

No historical result is promoted to the operational threat engine automatically.
"""
import argparse
import datetime as dt
import gzip
import json
import math
from pathlib import Path
from statistics import median

SOURCE_PROFILE = "GDELT-v1 EventRootCode 17/18/19/20, selected-event denominator"
MIN_HISTORY = 28
WINDOW_DAYS = 90


def unpack_date(value):
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise ValueError("Expected YYYYMMDD calendar date")
    return dt.datetime.strptime(value, "%Y%m%d").date()


def validate_record(obj):
    if not isinstance(obj, dict):
        raise ValueError("Daily record must be an object")
    day = unpack_date(obj.get("day"))
    counts = obj.get("counts")
    selected, rows = obj.get("selected"), obj.get("rows")
    if not isinstance(counts, dict) or not isinstance(selected, int) or selected <= 0:
        raise ValueError(f"Invalid selected counts for {day}")
    if not isinstance(rows, int) or rows < selected:
        raise ValueError(f"Invalid row count for {day}")
    if any(not isinstance(k, str) or not k.startswith(("BILAT:", "DOMESTIC:"))
           or not isinstance(v, int) or isinstance(v, bool) or v < 0
           for k, v in counts.items()):
        raise ValueError(f"Invalid case count for {day}")
    if sum(counts.values()) != selected:
        raise ValueError(f"Selected denominator does not equal summed counts on {day}")
    return day


def collect_inputs(paths):
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file() and path.name == "daily.jsonl":
            found.append(path)
        elif path.is_dir():
            found.extend(path.rglob("daily.jsonl"))
        else:
            raise ValueError(f"No readable daily.jsonl found in {path}")
    if not found:
        raise ValueError("No daily.jsonl inputs; workflow artifacts must be downloaded first")
    return sorted(set(found))


def merge(inputs):
    by_day, sources = {}, {}
    for path in collect_inputs(inputs):
        with path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    day = validate_record(rec)
                except (ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"{path}:{line_no}: {exc}") from exc
                previous = by_day.get(day)
                if previous is not None and previous != rec:
                    raise ValueError(f"Conflicting observations for {day} in {sources[day]} and {path}")
                by_day[day] = rec
                sources.setdefault(day, str(path))
    if not by_day:
        raise ValueError("No daily records available")
    return by_day


def pct95(values):
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)]


def candidates(by_day, start, end, top_per_day=25):
    """No look-ahead. No interpolation. Missing calendar dates interrupt the minimum baseline."""
    first = min(by_day)
    all_candidates = []
    analyzed = 0
    insufficient = 0
    for offset in range((end - start).days + 1):
        day = start + dt.timedelta(days=offset)
        current = by_day.get(day)
        if current is None:
            continue
        window_start = max(first, day - dt.timedelta(days=WINDOW_DAYS))
        expected = [window_start + dt.timedelta(days=i)
                    for i in range((day - window_start).days)]
        prior = [by_day[d] for d in expected if d in by_day]
        last28 = [day - dt.timedelta(days=i) for i in range(1, MIN_HISTORY + 1)]
        if (len(prior) < MIN_HISTORY
                or not all(d in by_day for d in last28)
                or len(prior) / max(1, len(expected)) < 0.9):
            insufficient += 1
            continue
        analyzed += 1
        prev_selected = sum(r["selected"] for r in prior)
        dated = []
        for case, count in current["counts"].items():
            if count < 5:
                continue
            past = [r["counts"].get(case, 0) / r["selected"] for r in prior]
            today_share = count / current["selected"]
            historical_share = sum(r["counts"].get(case, 0) for r in prior) / prev_selected
            ratio = ((count + .5) / (current["selected"] + 1)) / (
                (sum(r["counts"].get(case, 0) for r in prior) + .5) / (prev_selected + 1))
            upper = pct95(past)
            # Screening heuristic only; zero-heavy / correlated GDELT media data
            # can create extreme ratios. This does not justify a risk alert.
            if ratio < 2 or today_share <= max(1.5 * upper, 0.00005):
                continue
            dated.append({
                "day": day.isoformat(), "case": case, "today_events": count,
                "today_share": round(today_share, 8),
                "prior_days": len(prior), "prior_90_weighted_share": round(historical_share, 8),
                "prior_90_median_share": round(median(past), 8),
                "prior_90_p95_share": round(upper, 8),
                "ratio_to_prior_90": round(ratio, 3),
                "baseline_method": "prior 90 calendar days; >=90% day coverage and complete preceding 28 days",
                "status": "shadow_candidate_not_predictive",
            })
        dated.sort(key=lambda r: (-r["ratio_to_prior_90"], -r["today_events"], r["case"]))
        all_candidates.extend(dated[:top_per_day])
    return all_candidates, {"analyzed_days": analyzed, "insufficient_baseline_days": insufficient}


def build(inputs, output, start=None, end=None, top_per_day=25):
    by_day = merge(inputs)
    first, last = min(by_day), max(by_day)
    start = start or first
    end = end or last
    if end < start:
        raise ValueError("Start after end")
    missing = [(start + dt.timedelta(days=i)).isoformat()
               for i in range((end - start).days + 1)
               if start + dt.timedelta(days=i) not in by_day]
    shadow, status = candidates(by_day, start, end, top_per_day)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "merged_daily.jsonl.gz", "wt", encoding="utf-8") as f:
        for day in sorted(by_day):
            if start <= day <= end:
                f.write(json.dumps(by_day[day], sort_keys=True) + "\n")
    with (out / "shadow_candidates.jsonl").open("w", encoding="utf-8") as f:
        for item in shadow:
            f.write(json.dumps(item, sort_keys=True) + "\n")
    manifest = {
        "source_profile": SOURCE_PROFILE,
        "requested_range": [start.isoformat(), end.isoformat()],
        "first_available_day": first.isoformat(),
        "last_available_day": last.isoformat(),
        "requested_days": (end - start).days + 1,
        "complete_days": (end - start).days + 1 - len(missing),
        "missing_days": missing, "shadow_candidates": len(shadow),
        **status,
        "warning": "Not joined to production GDELT 13/16/17/18/19/20 profile; not a war probability or accuracy evaluation.",
        "approved_for_production_thresholds": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", nargs="+", required=True, help="Artifact directories or daily.jsonl files")
    p.add_argument("--output", default="historical-merged")
    p.add_argument("--start", help="YYYY-MM-DD inclusive; defaults to oldest input day")
    p.add_argument("--end", help="YYYY-MM-DD inclusive; defaults to newest input day")
    p.add_argument("--top-per-day", type=int, default=25)
    args = p.parse_args()
    if args.top_per_day < 1 or args.top_per_day > 500:
        p.error("--top-per-day must be 1..500")
    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None
    print(json.dumps(build(args.inputs, args.output, start, end, args.top_per_day), indent=2))


if __name__ == "__main__":
    main()
