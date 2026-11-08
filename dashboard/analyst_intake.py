"""Validate and stage external analyst reports without promoting them to intelligence.

Only data written to the separate aiba-feed-data branch is consumed. A completed
ChatGPT automation does NOT itself write a file here: an explicit authenticated
handoff using import_analyst_report.py (or its workflow) is required.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

UTC = dt.timezone.utc
KINDS = {"six_hour_signal", "commercial_behavior", "global_discovery", "weekly_audit"}
CONFIDENCE = {"low", "moderate", "high", "unknown"}
EVIDENCE = {"source_observation", "media_mention", "analyst_hypothesis"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,119}$")
MAX_BATCH = 128_000
MAX_OBSERVATIONS = 50
MAX_HISTORY_FILES = 500


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO 8601 string")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must contain a timezone")
    return parsed.astimezone(UTC)


def string(value, name, maximum, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f"Invalid {name}")
    return value.strip()


def https_url(value):
    url = string(value, "source_url", 2048)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Every observation needs a source HTTPS URL")
    return url


def validate_batch(batch, clock=None):
    """Return canonical records; reject malformed or future-dated OSINT outright."""
    clock = clock or dt.datetime.now(UTC)
    if not isinstance(batch, dict) or batch.get("schema_version") != 1:
        raise ValueError("Expected analyst report schema version 1")
    run_id = string(batch.get("run_id"), "run_id", 120)
    if not ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be a stable machine-readable identifier")
    collector = batch.get("collector")
    if collector not in KINDS:
        raise ValueError("Unknown collector type")
    status = batch.get("status")
    if status not in {"completed", "partial", "failed"}:
        raise ValueError("Unknown collection status")
    checked = timestamp(batch.get("collected_at"))
    if checked > clock + dt.timedelta(minutes=5):
        raise ValueError("Future collection timestamp")
    rows = batch.get("observations")
    if not isinstance(rows, list) or len(rows) > MAX_OBSERVATIONS:
        raise ValueError("Invalid observation count")
    if status == "failed" and rows:
        raise ValueError("Failed collections cannot claim new evidence")
    result = []
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid observation")
        identifier = string(row.get("observation_id"), "observation_id", 120)
        if not ID_PATTERN.fullmatch(identifier) or identifier in ids:
            raise ValueError("Invalid or duplicate observation_id in batch")
        ids.add(identifier)
        case_id = row.get("case_id")
        if case_id is not None and (not isinstance(case_id, str) or not ID_PATTERN.fullmatch(case_id)):
            raise ValueError("Invalid case_id; use null for unlocated discoveries")
        day = row.get("published_at")
        if day is not None:
            event_time = timestamp(day)
            if event_time > clock + dt.timedelta(minutes=5):
                raise ValueError("Future source publication timestamp")
            day = event_time.date().isoformat()
        source = https_url(row.get("source_url"))
        kind = row.get("evidence_class")
        confidence = row.get("confidence")
        if kind not in EVIDENCE or confidence not in CONFIDENCE:
            raise ValueError("Unrecognized evidence or confidence class")
        if not isinstance(row.get("independently_confirmed"), bool):
            raise ValueError("Independent confirmation must be explicitly true or false")
        root = string(row.get("information_root"), "information_root", 200)
        result.append({
            "observation_id": identifier, "case_id": case_id,
            "published_at": day, "source_url": source,
            "title": string(row.get("title"), "title", 300),
            "summary": string(row.get("summary"), "summary", 1200),
            "publisher": string(row.get("publisher"), "publisher", 150),
            "information_root": root, "evidence_class": kind,
            "confidence": confidence,
            "independently_confirmed": row["independently_confirmed"],
            "first_collected_at": checked.isoformat(),
            "collector": collector, "run_id": run_id,
        })
    return {"run_id": run_id, "collector": collector, "status": status,
            "collected_at": checked.isoformat(), "observations": result}


def load_history(state, clock=None):
    """Bounded, immutable report history, deduplicated across recurring runs.

    The first collection time is retained, so replaying a report cannot create
    a fresh globe pulse. Invalid files block deployment rather than hide bad data.
    """
    clock = clock or dt.datetime.now(UTC)
    root = Path(state) / "analyst" / "history"
    paths = sorted(root.glob("*.json")) if root.exists() else []
    if len(paths) > MAX_HISTORY_FILES:
        raise ValueError("Analyst history exceeds the review/retention bound")
    output, runs = {}, {}
    roots = {}
    for path in paths:
        if path.stat().st_size > MAX_BATCH:
            raise ValueError(f"Oversized analyst batch: {path.name}")
        batch = validate_batch(json.loads(path.read_text(encoding="utf-8")), clock)
        prior_run = runs.get(batch["run_id"])
        if prior_run and prior_run != (batch["collector"], batch["collected_at"], batch["status"]):
            raise ValueError("Inconsistent repeated run_id")
        runs[batch["run_id"]] = (batch["collector"], batch["collected_at"], batch["status"])
        for record in batch["observations"]:
            key = record["observation_id"]
            stable = {k: v for k, v in record.items()
                      if k not in {"first_collected_at", "run_id", "collector"}}
            if key in output:
                prior = {k: v for k, v in output[key].items()
                         if k not in {"first_collected_at", "run_id", "collector"}}
                if stable != prior:
                    raise ValueError("Conflicting observations with identical ID")
                continue
            # Syndicated mirrors from the same information root are one lead,
            # not independent corroboration or multiple pulses.
            root_key = (record["case_id"], record["information_root"].lower(),
                        record["published_at"], record["evidence_class"])
            if root_key in roots:
                continue
            roots[root_key] = key
            output[key] = record
    latest = max((x[1] for x in runs.values()), default=None)
    return {"records": sorted(output.values(), key=lambda v: (v["first_collected_at"], v["observation_id"])),
            "status": "not_connected" if not runs else
                      ("partial" if any(v[2] in {"failed", "partial"} for v in runs.values()
                       if v[1] == latest) else "collected"),
            "run_count": len(runs), "latest_collected_at": latest,
            "distinct_observations": len(output)}


def report_filename(batch):
    canonical = json.dumps(batch, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    time = timestamp(batch["collected_at"]).strftime("%Y%m%dT%H%M%SZ")
    return time + "-" + digest + ".json"


def store_batch(state, batch, clock=None):
    normalized = validate_batch(batch, clock)
    # Preserve source publication timestamps rather than day-only display dates.
    # Canonical normalized records are for display; archived inputs remain replayable.
    archived = {"schema_version": 1, "run_id": normalized["run_id"],
                "collector": normalized["collector"], "status": normalized["status"],
                "collected_at": normalized["collected_at"], "observations": batch["observations"]}
    folder = Path(state) / "analyst" / "history"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / report_filename(archived)
    content = json.dumps(archived, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError("Conflicting immutable report")
    path.write_text(content, encoding="utf-8")
    return path
