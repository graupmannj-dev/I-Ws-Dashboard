#!/usr/bin/env python3
"""Read-only AIBA collector cadence and source freshness audit.

The Actions API shows run start/creation times, NOT all scheduled slots that
were skipped or coverage achieved. Report gaps as UNVERIFIED COVERAGE, not
absence of alerts, actual source outages, or collector failure causal proof.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aiba_prospective_shadow as shadow
from scripts import aiba_tipper_ledger as ledger

SCHEMA = "aiba.collector-cadence-readiness.v1"
GROUPS = {
    "Collect AIBA structural friction (shadow mode)": ("friction", 30),
    "Collect AIBA near-current map restrictions": ("restrictions", 15),
    "Collect AIBA operational feeds": ("operational_mixed_modes", 360),
}
MAX_RUNS = 1200
LOOKBACK_HOURS = 72
MAX_FILE_BYTES = 5 * 1024 * 1024


class CadenceError(ValueError):
    pass


def clock_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def instant(raw, name):
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise CadenceError("invalid_utc_" + name)
    try:
        stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CadenceError("invalid_datetime_" + name) from exc
    if stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0):
        raise CadenceError("invalid_timezone_" + name)
    return stamp


def read_json(path):
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= MAX_FILE_BYTES:
        raise CadenceError("missing_or_oversized_audit_input")
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=ledger.object_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(CadenceError("nonfinite_json")))
    except (UnicodeError, ValueError, RecursionError, OSError) as exc:
        raise CadenceError("invalid_audit_input_json") from exc


def evaluate(runs, registry, fusion, *, now=None, lookback_hours=LOOKBACK_HOURS):
    now = now or clock_now()
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise CadenceError("utc_clock_required")
    if type(lookback_hours) is not int or not 12 <= lookback_hours <= 168:
        raise CadenceError("invalid_lookback_hours")
    beginning = now - dt.timedelta(hours=lookback_hours)
    if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
        raise CadenceError("actions_api_runs_required")
    if not isinstance(runs.get("total_count"), int) or runs["total_count"] < 0:
        raise CadenceError("actions_api_total_count_missing")
    if len(runs["workflow_runs"]) > MAX_RUNS:
        raise CadenceError("runs_beyond_bounded_limit")
    history = {}
    older = []
    seen_ids = set()
    for item in runs["workflow_runs"]:
        if not isinstance(item, dict):
            raise CadenceError("run_metadata_invalid")
        run_id = item.get("id")
        if type(run_id) is not int or run_id <= 0 or run_id in seen_ids:
            raise CadenceError("duplicate_or_invalid_actions_run")
        seen_ids.add(run_id)
        created = instant(item.get("created_at"), "workflow_created_at")
        if created > now + dt.timedelta(minutes=5):
            raise CadenceError("future_workflow_metadata")
        older.append(created)
        name = item.get("name")
        if name not in GROUPS:
            continue
        event = item.get("event")
        if event not in ("schedule", "workflow_dispatch"):
            continue
        if created < beginning:
            continue
        history.setdefault(name, []).append({
            "id": run_id, "created": created, "event": event,
            "status": item.get("status"), "conclusion": item.get("conclusion"),
        })
    history_window_sufficient = (bool(older) and min(older) <= beginning)
    results = {}
    any_gaps = False
    for name, (key, interval_minutes) in GROUPS.items():
        values = sorted(history.get(name, []), key=lambda x: x["created"])
        gaps = [(values[i]["created"]-values[i-1]["created"]).total_seconds()/60
                for i in range(1,len(values))]
        threshold = 2 * interval_minutes
        flagged = [gap for gap in gaps if gap > threshold]
        missed_excess = sum(max(0, gap - threshold) for gap in gaps)
        latest = values[-1]["created"] if values else None
        since = (now-latest).total_seconds()/60 if latest else None
        trailing = since is None or since > threshold
        any_gaps |= trailing or bool(flagged)
        results[key] = {
            "nominal_minutes": interval_minutes,
            "review_gap_threshold_minutes": threshold,
            "observed_runs": len(values),
            "scheduled_runs_observed": sum(x["event"]=="schedule" for x in values),
            "manual_runs_observed": sum(x["event"]=="workflow_dispatch" for x in values),
            "successful_runs_observed": sum(x["conclusion"]=="success" for x in values),
            "failed_or_cancelled_runs_observed": sum(x["conclusion"] in ("failure","cancelled","timed_out") for x in values),
            "pending_runs_observed": sum(x["status"]!="completed" for x in values),
            "latest_run_created_at": latest.strftime("%Y-%m-%dT%H:%M:%SZ") if latest else None,
            "minutes_since_latest_run": round(since,2) if since is not None else None,
            "max_observed_start_gap_minutes": round(max(gaps),2) if gaps else None,
            "intervals_over_2x_nominal": len(flagged),
            "observed_excess_gap_minutes": round(missed_excess,2),
            "trailing_start_gap": trailing,
            "underlying_source_continuity_verified": False,
            "cadence_reliability_class": "gaps_detected" if trailing or flagged else (
                "insufficient_run_history" if len(values)<2 else "observed_runs_within_gate"),
            "interpretation": (
                "Optimistic upper bound: operational workflow also runs commercial and audit modes; "
                "not every observed start updates six-hour core feeds"
                if key=="operational_mixed_modes" else
                "Run creation intervals do not prove source monitoring or scheduled slot delivery"),
        }
    if not isinstance(registry, dict) or not isinstance(fusion, dict) or (
            registry.get("schema") != shadow.REGISTRY_SCHEMA or
            fusion.get("schema") != shadow.FUSION_SCHEMA or
            registry.get("generated_at") != fusion.get("registry_asof")):
        raise CadenceError("current_registry_fusion_pair_missing_or_mismatched")
    a,b = instant(registry.get("generated_at"),"registry_asof"),instant(
        fusion.get("generated_at"),"fusion_asof")
    if not a <= b <= now:
        raise CadenceError("bad_registry_fusion_clock")
    if registry.get("source_health") != fusion.get("collection_coverage"):
        raise CadenceError("source_health_diverged")
    health = registry.get("source_health")
    if not isinstance(health, dict) or not health:
        raise CadenceError("source_health_unavailable")
    degraded = [name for name, item in health.items() if
                isinstance(item, dict) and (item.get("status") != "current" or item.get("missingness") != "none")]
    newest_age_min = (now-b).total_seconds()/60
    readiness = "gap_or_stale_source_review_required" if any_gaps or newest_age_min > 90 else "bounded_provisional_source_readiness"
    return {
        "schema": SCHEMA, "status": readiness,
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_hours":lookback_hours, "api_history_covers_window":history_window_sufficient,
        "api_runs_observed": len(runs["workflow_runs"]),
        "github_total_runs_reported": runs["total_count"],
        "cannot_infer_missed_scheduled_slots": True,
        "collector_groups": results,
        "source_registry_asof":a.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_fusion_asof":b.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fusion_age_minutes": round(newest_age_min,2),
        "fusion_fresh_enough_for_90_minute_shadow_preflight": 0<=newest_age_min<=90,
        "providers_observed":len(health),
        "providers_degraded_or_scope_bounded":degraded,
        "source_continuity_proven":False,
        "negative_events_inferred":False,
        "prospective_warnings_issued":0,
        "no_alert_or_publication_changes":True,
        "conclusion":"Run start gaps are a source readiness defect. No collector outcome, world calm, or event absence can be inferred.",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",required=True,type=Path)
    parser.add_argument("--registry",required=True,type=Path)
    parser.add_argument("--fusion",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    if args.output.resolve() in (args.runs.resolve(),args.registry.resolve(),args.fusion.resolve()):
        print("Refusing to overwrite input")
        return 1
    try:
        result=evaluate(read_json(args.runs),read_json(args.registry),
                        read_json(args.fusion))
        code=0
    except (CadenceError,OSError,TypeError,ValueError,OverflowError,RecursionError) as exc:
        result={"schema":SCHEMA,"status":"unavailable",
                "reason":str(exc) if isinstance(exc,CadenceError) else "input_or_clock_unavailable",
                "source_continuity_proven":False,"negative_events_inferred":False,
                "prospective_warnings_issued":0}
        code=1
    try:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    except OSError:
        return 1
    print(f"{result['status']}: {args.output}")
    return code


if __name__=="__main__":
    raise SystemExit(main())
