#!/usr/bin/env python3
"""Keyless, versioned GCS store for source-matched GDELT 17/18/19/20 history.

Explicit seed from verified historical artifact; thereafter bounded daily
updates and recovery of missed UTC dates. No operational AIBA alert promotion.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.historical_gdelt_baseline import URL, daily_counts
from scripts.gdelt_shadow_monitor import analyze_day
from scripts.merge_gdelt_history import SOURCE_PROFILE, unpack_date, validate_record

PROJECT = "aiba-514120"
PREFIX = "aiba/gdelt/roots-17-18-19-20/v1"
SCHEMA = "aiba.gdelt.daily.v1"
MAX_PER_RUN = 14
EXPECTED_SEED_FIRST = dt.date(2026, 7, 11)
EXPECTED_SEED_LAST = dt.date(2026, 11, 9)
EXPECTED_SEED_DAYS = 122


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def day_key(prefix, day):
    return f"{prefix}/daily/{day:%Y%m%d}.json"


def safe_prefix(value):
    value = value.strip("/")
    if not value or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_-]*", value) or "//" in value or ".." in value:
        raise ValueError("Unsafe GCS prefix")
    return value


def source_record(record):
    day = validate_record(record)
    # Only validated source-specific daily aggregates may enter this dataset.
    payload = {"schema": SCHEMA, "source_profile": SOURCE_PROFILE, "record": record}
    return day, canonical(payload)


def restore_record(payload, expected_day):
    obj = json.loads(payload)
    if obj.get("schema") != SCHEMA or obj.get("source_profile") != SOURCE_PROFILE:
        raise ValueError(f"Source profile/schema mismatch for {expected_day}")
    record = obj["record"]
    if validate_record(record) != expected_day:
        raise ValueError(f"GCS object key and record date disagree for {expected_day}")
    if canonical(obj) != payload:
        raise ValueError(f"Noncanonical or modified stored record for {expected_day}")
    return record


def write_immutable(bucket, object_name, content):
    """Never silently overwrite existing history; retries are byte-identical."""
    blob = bucket.blob(object_name)
    if blob.exists():
        old = blob.download_as_bytes()
        if old != content:
            raise ValueError(f"Conflicting GCS object {object_name}; manual integrity review required")
        return "verified_existing"
    try:
        blob.upload_from_string(content, content_type="application/json", if_generation_match=0)
    except Exception as exc:
        # Race: another collector may have created an identical immutable object.
        # Do not hide network, authentication or service failures.
        if type(exc).__name__ != "PreconditionFailed":
            raise
        if not blob.exists() or blob.download_as_bytes() != content:
            raise ValueError(f"Concurrent conflicting write at {object_name}") from exc
        return "verified_existing"
    return "created"


def existing_dates(bucket, prefix):
    result = {}
    for blob in bucket.list_blobs(prefix=f"{prefix}/daily/"):
        suffix = blob.name.removeprefix(f"{prefix}/daily/")
        if not re.fullmatch(r"\d{8}\.json", suffix):
            raise ValueError(f"Unexpected historical object under daily/: {blob.name}")
        day = unpack_date(suffix[:-5])
        result[day] = blob.name
    return result


def read_days(bucket, names, days):
    by_day = {}
    for day in sorted(days):
        if day not in names:
            continue
        payload = bucket.blob(names[day]).download_as_bytes()
        by_day[day] = restore_record(payload, day)
    return by_day


def parse_seed(file, manifest_file):
    manifest = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    if (manifest.get("profile") != SOURCE_PROFILE
        or manifest.get("historical_start") != EXPECTED_SEED_FIRST.isoformat()
        or manifest.get("available_end") != EXPECTED_SEED_LAST.isoformat()
        or manifest.get("total_valid_days") != EXPECTED_SEED_DAYS
        or manifest.get("failed_days")):
        raise ValueError("Source seed manifest is not the verified 122-day GDELT 17-20 artifact")
    by_day = {}
    raw = Path(file).read_bytes()
    for n, line in enumerate(raw.splitlines(), 1):
        if not line:
            continue
        try:
            record = json.loads(line)
            day, _ = source_record(record)
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Seed daily aggregate line {n}: {exc}") from exc
        if day in by_day:
            raise ValueError(f"Duplicate day {day} in seed")
        by_day[day] = record
    expected = [EXPECTED_SEED_FIRST + dt.timedelta(days=i) for i in range(EXPECTED_SEED_DAYS)]
    if sorted(by_day) != expected:
        raise ValueError("Seed missing or out-of-range calendar dates")
    return by_day, {
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "source_days": len(by_day),
        "source_manifest": manifest,
    }


def download_archive(day):
    """Retry transient publication/network failures; do not fabricate a missing day."""
    url = URL.format(day=day.strftime("%Y%m%d"))
    request = urllib.request.Request(url, headers={"User-Agent": "AIBA-GCS-History/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            retriable = not isinstance(exc, urllib.error.HTTPError) or exc.code in (404, 408, 429, 500, 502, 503, 504)
            if attempt == 2 or not retriable:
                raise
            time.sleep((attempt + 1) * 4)
    raise RuntimeError("Archive download exhausted retries")


def classify_source_error(exc):
    if isinstance(exc, (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError)):
        return "provider_unavailable"
    return "source_invalid"


def dates_between(start, end):
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)] if end >= start else []


def choose_missing_dates(existing, through, max_requests=MAX_PER_RUN, trailing_days=120):
    if not existing:
        raise ValueError("GCS history is empty: run seed mode first")
    if max_requests < 1 or max_requests > 14:
        raise ValueError("At most 14 archival requests per workflow run")
    earliest = max(min(existing), through - dt.timedelta(days=trailing_days-1))
    # Prioritize most recent dates so a stale provider day does not hide new signal;
    # keep an explicit queue for older gaps and retry them on subsequent runs.
    missing = sorted([d for d in dates_between(earliest, through) if d not in existing], reverse=True)
    return missing[:max_requests], missing[max_requests:]


def evaluate(bucket, prefix, available, dates, out):
    latest = max(available)
    first = max(min(available), latest - dt.timedelta(days=180))
    records = read_days(bucket, available, [d for d in available if d >= first])
    reports = [analyze_day(records, day) for day in sorted(dates) if day in records]
    if reports:
        with (out/"shadow_comparisons.jsonl").open("w", encoding="utf-8") as f:
            for r in reports:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    with (out/"rolling_daily.jsonl").open("w", encoding="utf-8") as f:
        for day, record in sorted(records.items()):
            f.write(json.dumps(record, sort_keys=True) + "\n")
    return reports


def execute(bucket, mode, output, through=None, seed_file=None, seed_manifest=None,
            prefix=PREFIX, run_id=None, fetcher=None):
    prefix = safe_prefix(prefix)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    run_id = run_id or "local-manual"
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,90}", run_id):
        raise ValueError("Unsafe run identifier")
    existing = existing_dates(bucket, prefix)
    created, verified, problems, backlog, source_info = [], [], [], [], None
    requested_through = None
    evaluated_days = []
    invalid = False

    if mode == "seed":
        if not seed_file or not seed_manifest:
            raise ValueError("Seed requires both immutable source aggregate and manifest")
        seed, source_info = parse_seed(seed_file, seed_manifest)
        for day, record in sorted(seed.items()):
            _, content = source_record(record)
            status = write_immutable(bucket, day_key(prefix, day), content)
            (created if status == "created" else verified).append(day)
        evaluated_days = [max(seed)]  # historical replay, not fresh lead
    elif mode == "update":
        if not existing:
            raise ValueError("No GCS seed; first dispatch the seed operation")
        yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
        through = through or yesterday
        if through > yesterday:
            raise ValueError(f"Cannot ingest current/future UTC day {through}; latest permissible is {yesterday}")
        if through < min(existing):
            raise ValueError(f"Requested date {through} precedes the seeded history")
        requested_through = through
        wanted, backlog = choose_missing_dates(existing, through)
        fetcher = fetcher or download_archive
        for day in wanted:
            try:
                downloaded = fetcher(day)
                record = daily_counts(downloaded, day.strftime("%Y%m%d"))
                if validate_record(record) != day:
                    raise ValueError(f"Date mismatch {day}")
            except Exception as exc:
                severity = classify_source_error(exc)
                invalid |= severity == "source_invalid"
                problems.append({"day": day.isoformat(), "status": severity,
                                 "error": type(exc).__name__, "detail": str(exc)[:180]})
                continue
            _, content = source_record(record)
            status = write_immutable(bucket, day_key(prefix, day), content)
            (created if status == "created" else verified).append(day)
        evaluated_days = sorted(created)
    else:
        raise ValueError(f"Invalid mode {mode}")

    updated = existing_dates(bucket, prefix)
    reports = evaluate(bucket, prefix, updated, evaluated_days, output)
    latest = max(updated)
    first = min(updated)
    window_start = max(first, latest - dt.timedelta(days=119))
    needed = dates_between(window_start, latest)
    missing_window = [d for d in needed if d not in updated]
    recent_day = requested_through or latest
    status = ("invalid_source" if invalid else
              "partial" if problems or backlog or missing_window or
              (requested_through is not None and recent_day not in updated) else
              "complete")
    manifest = {
        "schema": "aiba.gdelt.gcs-run.v1",
        "project": PROJECT, "prefix": prefix, "mode": mode,
        "source_profile": SOURCE_PROFILE,
        "run_id": run_id,
        "first_stored_date": first.isoformat(),
        "latest_stored_date": latest.isoformat(),
        "requested_through": requested_through.isoformat() if requested_through else None,
        "created_days": [x.isoformat() for x in sorted(created)],
        "previously_verified_days": [x.isoformat() for x in sorted(verified)],
        "missing_last_120_days": [x.isoformat() for x in missing_window],
        "unattempted_backlog": [x.isoformat() for x in backlog],
        "failed_downloads": problems,
        "status": status,
        "evaluated_days": [r["day"] for r in reports],
        "eligible_shadow_comparisons": sum(r["baseline"]["eligible"] for r in reports),
        "shadow_established_leads": sum(r.get("established_lead_count", 0) for r in reports),
        "shadow_emerging_leads": sum(r.get("emerging_lead_count", 0) for r in reports),
        "source_provenance": source_info,
        "automatically_publish": False,
        "executive_alerts_approved": False,
        "note": "Four-root GDELT historical source profile only. Not the six-root operational denominator; not a prediction.",
    }
    report_bytes = canonical(manifest)
    (output/"manifest.json").write_bytes(report_bytes)
    # Immutable run-specific receipts retain source-health failures and data integrity.
    write_immutable(bucket, f"{prefix}/runs/{run_id}/manifest.json", report_bytes)
    if reports:
        comparison_bytes = (output/"shadow_comparisons.jsonl").read_bytes()
        write_immutable(bucket, f"{prefix}/runs/{run_id}/shadow_comparisons.jsonl", comparison_bytes)
    if invalid:
        raise ValueError("Invalid source archive encountered; audit manifest was preserved, no fabricated observations")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("seed","update"), required=True)
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--bucket", required=True, help="Existing versioned GCS bucket name, no gs://")
    parser.add_argument("--prefix", default=PREFIX)
    parser.add_argument("--seed-file")
    parser.add_argument("--seed-manifest")
    parser.add_argument("--through", help="Optional YYYY-MM-DD UTC last fully closed day")
    parser.add_argument("--output", default="gdelt-gcs-output")
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID","local"))
    args = parser.parse_args()
    if args.project != PROJECT:
        parser.error(f"This rollout is scoped to Google Cloud project {PROJECT}")
    from google.cloud import storage  # Only needed for authenticated runtime, not local tests.
    bucket = storage.Client(project=args.project).bucket(args.bucket)
    day = dt.date.fromisoformat(args.through) if args.through else None
    result = execute(bucket, args.mode, args.output, through=day,
                     seed_file=args.seed_file, seed_manifest=args.seed_manifest,
                     prefix=args.prefix, run_id=args.run_id)
    print(json.dumps({k:v for k,v in result.items() if k!="source_provenance"}, indent=2))
    if result["status"] == "partial":
        print("::warning::GDELT history partially available; missing dates retained as missing. See GCS run manifest.")
    print("No executive warning status or dashboard output changed.")


if __name__ == "__main__":
    main()
