#!/usr/bin/env python3
"""Incremental six-root GDELT history, independently versioned in private GCS.

Requires exact day-by-day projection parity with pre-existing four-root history.
Never mutates production discovery thresholds, old four-root objects or site.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
import time

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.gdelt_event_profile import (
    PROFILE, PREFIX, SCHEMA, crosscheck_v1, parse_archive, validate
)
from scripts.gdelt_gcs_history import (
    PROJECT, PREFIX as FOUR_PREFIX, canonical, dates_between, existing_dates,
    read_days, safe_prefix, write_immutable
)
from scripts.gdelt_shadow_monitor import analyze_day

MAX_BATCH = 14
SEED_DATE = dt.date(2026, 7, 11)
API_ROOT = "https://data.gdeltproject.org/events/"


def daily_key(prefix, day):
    return f"{prefix}/daily/{day:%Y%m%d}.json"


def fetch_source(day):
    url = f"{API_ROOT}{day:%Y%m%d}.export.CSV.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "AIBA-SixRoot-History/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            transient = not isinstance(exc, urllib.error.HTTPError) or exc.code in (404, 408, 429, 500, 502, 503, 504)
            if attempt == 2 or not transient:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("No source response after three attempts")


def stored_v2(bucket, names, day):
    obj = json.loads(bucket.blob(names[day]).download_as_bytes())
    if obj.get("schema") != SCHEMA or obj.get("profile") != PROFILE:
        raise ValueError(f"Stored six-root envelope profile mismatch {day}")
    record = obj["record"]
    validate(record, day)
    if canonical(obj) != bucket.blob(names[day]).download_as_bytes():
        raise ValueError(f"Noncanonical immutable six-root object {day}")
    return record


def eligible_dates(bucket, mode, first, last, existing, four, max_batch=MAX_BATCH):
    if max_batch < 1 or max_batch > MAX_BATCH:
        raise ValueError("Maximum allowed GDELT daily source archives per run is 14")
    if mode == "backfill":
        if first is None or last is None:
            raise ValueError("Backfill requires both --start and --end")
        if first < SEED_DATE or last < first or (last - first).days >= MAX_BATCH:
            raise ValueError("Bounded backfill must be 1–14 days from July 11, 2026")
        selected = [d for d in dates_between(first, last) if d not in existing]
    elif mode == "update":
        if last is None:
            last = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
        if last < SEED_DATE:
            raise ValueError("UTC last day precedes six-root source period")
        missing = [d for d in dates_between(SEED_DATE, last) if d not in existing]
        # Always test newest available date, then repair the earliest gaps.
        selected = ([missing[-1]] + missing[:-1][:max_batch - 1]) if missing else []
    else:
        raise ValueError("Mode must be backfill or update")
    deferred = [d for d in dates_between(SEED_DATE, last) if d not in existing and d not in selected]
    # Only download dates already present in verified four-root GCS store;
    # this prevents hidden source-profile drift and makes parity mandatory.
    blocked = [d for d in selected if d not in four]
    ready = [d for d in selected if d in four]
    return ready, blocked, deferred, last


def execute(bucket, mode, output, start=None, end=None, through=None, run_id="local",
            batch_limit=MAX_BATCH, fetcher=None):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    v1 = existing_dates(bucket, FOUR_PREFIX)
    if not v1:
        raise ValueError("Four-root reference bucket is empty; seed it before six-root migration")
    v2 = existing_dates(bucket, PREFIX)
    today = dt.datetime.now(dt.timezone.utc).date()
    target = end if mode == "backfill" else (through or today - dt.timedelta(days=1))
    if target >= today:
        raise ValueError("Only fully closed historical UTC calendar days are eligible")
    planned, blocked, deferred, target = eligible_dates(
        bucket, mode, start, target, v2, v1, max_batch=batch_limit
    )
    get = fetcher or fetch_source
    created, failed, checks, scored = [], [], [], []
    for day in planned:
        # Unlike the four-root profile, count ALL six roots in denominator.
        try:
            raw = get(day)
            v2_record = parse_archive(raw, f"{day:%Y%m%d}")
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            failed.append({"date": day.isoformat(), "type": "provider_or_source_failure",
                           "error": type(exc).__name__, "message": str(exc)[:200]})
            continue
        # A changed historical archive, altered actor pairing, or silent parser
        # difference must stop the migration and trigger an investigator audit.
        four = read_days(bucket, v1, [day])[day]
        crosscheck_v1(v2_record, four)
        checks.append(day)
        envelope = canonical({"schema": SCHEMA, "profile": PROFILE, "record": v2_record})
        write_immutable(bucket, daily_key(PREFIX, day), envelope)
        created.append(day)

    updated = existing_dates(bucket, PREFIX)
    # Score only newly added six-root dates with strict lagged history,
    # using a matched six-root denominator; dates without 28 previous
    # complete days are explicitly INELIGIBLE.
    if created:
        # Read each immutable object at most once per run, avoiding repeated
        # network fetches when 14 backfill days share the same 90-day history.
        first_needed = min(created) - dt.timedelta(days=90)
        last_needed = max(created)
        needed = [d for d in updated if first_needed <= d <= last_needed]
        by_day = {d: stored_v2(bucket, updated, d) for d in needed}
        for day in sorted(created):
            scored.append(analyze_day(by_day, day, profile=PROFILE))
    with (out / "comparisons.jsonl").open("w", encoding="utf-8") as handle:
        for row in scored:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    missing = [d for d in dates_between(SEED_DATE, target) if d not in updated]
    health = "complete" if not (missing or failed or blocked or deferred) else "partial"
    report = {
        "schema": "aiba.gdelt.sixroot-run.v1",
        "mode": mode, "project": PROJECT, "profile": PROFILE, "prefix": PREFIX,
        "four_root_parity_required": True,
        "checked_parity": [x.isoformat() for x in checks],
        "created_days": [x.isoformat() for x in created],
        "missing_v1_dependency": [x.isoformat() for x in blocked],
        "deferred_days": [x.isoformat() for x in deferred],
        "source_failures": failed,
        "missing_sixroot_days": [x.isoformat() for x in missing],
        "first_stored_day": min(updated).isoformat() if updated else None,
        "latest_stored_day": max(updated).isoformat() if updated else None,
        "evaluated": [x["day"] for x in scored],
        "eligible_evaluations": [x["day"] for x in scored if x["baseline"]["eligible"]],
        "established_leads": sum(x.get("established_lead_count", 0) for x in scored),
        "emerging_leads": sum(x.get("emerging_lead_count", 0) for x in scored),
        "status": health,
        "executive_eligible": False,
        "production_thresholds_modified": False,
    }
    raw_report = canonical(report)
    (out / "manifest.json").write_bytes(raw_report)
    write_immutable(bucket, f"{PREFIX}/runs/{run_id}/manifest.json", raw_report)
    if scored:
        write_immutable(bucket, f"{PREFIX}/runs/{run_id}/comparisons.jsonl",
                        (out/"comparisons.jsonl").read_bytes())
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=["backfill", "update"])
    p.add_argument("--project", default=PROJECT)
    p.add_argument("--bucket", required=True)
    p.add_argument("--start", help="Backfill first UTC YYYY-MM-DD")
    p.add_argument("--end", help="Backfill last UTC YYYY-MM-DD")
    p.add_argument("--through", help="Update through last fully completed UTC YYYY-MM-DD")
    p.add_argument("--batch-limit", default=MAX_BATCH, type=int)
    p.add_argument("--output", default="gdelt-sixroot-audit")
    p.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "manual"))
    a = p.parse_args()
    if a.project != PROJECT:
        p.error("Wrong GCP project; do not migrate to an unrelated bucket")
    if not a.bucket or a.bucket.startswith("gs://") or any(ch.isspace() for ch in a.bucket):
        p.error("Specify private bucket name only, no gs://")
    from google.cloud import storage
    bucket = storage.Client(project=a.project).bucket(a.bucket)
    bucket.reload()
    if not bucket.versioning_enabled:
        p.error("Object Versioning disabled; refusing to migrate history")
    dates = {k: dt.date.fromisoformat(getattr(a, k))
             for k in ("start", "end", "through") if getattr(a, k)}
    result = execute(bucket, a.mode, a.output, start=dates.get("start"), end=dates.get("end"),
                     through=dates.get("through"), run_id=f"{a.run_id}-{os.getenv('GITHUB_RUN_ATTEMPT', '1')}",
                     batch_limit=a.batch_limit)
    print(json.dumps(result, indent=2))
    if result["status"] == "partial":
        print("::warning::Six-root history is still partial; no operational promotion.")


if __name__ == "__main__":
    main()
