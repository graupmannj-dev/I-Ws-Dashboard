#!/usr/bin/env python3
"""Forward-time shadow-mode warning audit against independently defined outcomes.

AIBA's unreviewed change queue is *not* a calibrated forecasting model.
Counts are descriptive for labeled windows and cannot estimate performance
for unknown, selected-on-the-dependent-variable coverage.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

from friction_pipeline import event_time, iso, read_json, utcnow, write_json

ALERT_TRIAGE = {"multi_stream_review", "baseline_review", "source_review"}
VALID_OUTCOMES = {"event", "no_event"}
MAX_LABELS = 1000
MAX_TRACES = 20_000


def strict_time(value):
    stamp = event_time(value)
    if stamp is None:
        raise ValueError("Event evaluation labels need explicit UTC or offset-aware timestamps")
    return stamp


def validate_labels(spec):
    if not isinstance(spec, dict) or spec.get("version") != 1:
        raise ValueError("Expected outcome label schema version 1")
    hours = spec.get("horizon_hours")
    if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 168:
        raise ValueError("Outcome horizon must be an integer from 1 to 168 hours")
    rows = spec.get("labels")
    if not isinstance(rows, list) or len(rows) > MAX_LABELS:
        raise ValueError("Invalid number of outcome labels")
    unique, output = set(), []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Outcome label must be an object")
        key = row.get("label_id")
        case = row.get("case_id")
        outcome = row.get("outcome")
        if (not isinstance(key, str) or not key or len(key) > 120
            or key in unique or not isinstance(case, str) or not case
            or len(case) > 120 or outcome not in VALID_OUTCOMES):
            raise ValueError("Invalid or duplicate labeled outcome")
        unique.add(key)
        start, end = strict_time(row.get("window_start")), strict_time(row.get("window_end"))
        if end <= start or end - start > dt.timedelta(days=90):
            raise ValueError("Invalid event/non-event observation window")
        truth = strict_time(row["event_at"]) if outcome == "event" else None
        if truth and not start <= truth < end:
            raise ValueError("Positive event must be inside its audited outcome window")
        if outcome == "no_event" and row.get("event_at") is not None:
            raise ValueError("Non-event windows cannot contain an event timestamp")
        finalized = strict_time(row.get("finalized_at"))
        if finalized < end:
            raise ValueError("Label must be finalized after its observation window")
        url = row.get("source_url")
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 2048:
            raise ValueError("A label needs a reviewable HTTPS outcome source")
        output.append({"label_id": key, "case_id": case, "outcome": outcome,
                       "start": start, "end": end, "event": truth,
                       "finalized_at": finalized, "source_url": url})
    return hours, output


def load_traces(state):
    folder = Path(state) / "history" / "friction_triage"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if len(files) > MAX_TRACES:
        raise ValueError("Excessive triage history; archive before audit")
    snapshots = []
    seen = set()
    for file in files:
        if file.stat().st_size > 25_000:
            raise ValueError("Triage trace is too large")
        x = json.loads(file.read_text(encoding="utf-8"))
        when = strict_time(x.get("asof"))
        if x.get("shadow_mode") is not True or not isinstance(x.get("triage"), dict):
            raise ValueError("Invalid shadow-mode trace")
        if when in seen:
            continue
        seen.add(when)
        snapshots.append((when, x["triage"]))
    return sorted(snapshots)


def evaluate(state, specification, now=None, write=True):
    now = now or utcnow()
    horizon, labels = validate_labels(specification)
    traces = load_traces(state)
    results = []
    positives, negatives = 0, 0
    detected, missed, non_event_reviewed, non_event_unreviewed = 0, 0, 0, 0
    for label in labels:
        if label["finalized_at"] > now:
            # Never leak future-reviewed outcomes into earlier evaluation.
            continue
        cid = label["case_id"]
        if label["outcome"] == "event":
            positives += 1
            event = label["event"]
            # Predictions MUST PRECEDE the independently labeled event.
            eligible = [(t, value) for t, state in traces
                        if event - dt.timedelta(hours=horizon) <= t < event
                        for case_id, value in state.items() if case_id == cid
                        and value in ALERT_TRIAGE]
            if eligible:
                detected += 1
                earliest = min(t for t, _ in eligible)
                lead_hours = round((event - earliest).total_seconds() / 3600, 2)
                outcome = "preceded_event"
            else:
                missed += 1
                lead_hours = None
                outcome = "no_pre_event_review"
        else:
            negatives += 1
            alert = any(start <= t < label["end"] and state.get(cid) in ALERT_TRIAGE
                        for t, state in traces
                        for start in [label["start"]])
            if alert:
                non_event_reviewed += 1
                outcome = "review_in_non_event_window"
            else:
                non_event_unreviewed += 1
                outcome = "no_review_in_non_event_window"
            lead_hours = None
        results.append({
            "label_id": label["label_id"], "case_id": cid, "outcome": label["outcome"],
            "result": outcome, "lead_hours": lead_hours, "source_url": label["source_url"]})
    status = "not_estimable" if not labels or not traces else (
        "partial_labeled_sample" if not positives or not negatives else "descriptive_sample_only")
    out = {
        "version": 1, "generated_at": iso(now), "status": status,
        "horizon_hours": horizon,
        "traces_available": len(traces), "labels_finalized": len(results),
        "positive_windows": positives, "negative_windows": negatives,
        "pre_event_reviewed": detected, "event_windows_without_prior_review": missed,
        "non_event_windows_with_review": non_event_reviewed,
        "non_event_windows_without_review": non_event_unreviewed,
        "lead_hours_in_labeled_events": [r["lead_hours"] for r in results if r["lead_hours"] is not None],
        "cases": results,
        "interpretation": ("Descriptive comparisons of source-reviewed outcomes and earlier shadow-mode "
                           "triage traces. Selection, incomplete non-event windows, overlapping episodes, "
                           "source gaps, and unobserved events prohibit a calibrated precision, "
                           "sensitivity, or false-positive rate. No prior warning is inferred "
                           "from a post-event review."),
    }
    if write:
        write_json(Path(state) / "latest" / "friction_validation.json", out)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    args = p.parse_args()
    spec = json.loads(args.labels.read_text(encoding="utf-8"))
    result = evaluate(args.state, spec)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
