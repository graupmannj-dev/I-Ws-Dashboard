#!/usr/bin/env python3
"""Prospective AIBA shadow monitoring frame from current source-ledger snapshots.

Read-only against production snapshots; offline by default. A frame records
covered and *uncovered* sources and investigation leads before a future window.
It is NOT a forecast, no-event label, review signoff, or severity update.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aiba_tipper_ledger as ledger

SCHEMA = "aiba.prospective-shadow-monitor-preflight.v1"
REGISTRY_SCHEMA = "aiba.behavioral-source-registry.v1"
FUSION_SCHEMA = "aiba.behavioral-convergence-shadow.v1"
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_SOURCES = 30
MAX_LEADS = 100
MAX_GROUPS = 25
MAX_SOURCE_AGE_MINUTES = 90


class ShadowError(ValueError):
    pass


def read_snapshot(path):
    if not isinstance(path, Path):
        path = Path(path)
    if (not path.is_file() or path.is_symlink()
            or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES):
        raise ShadowError("missing_or_untrusted_snapshot")
    raw = path.read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=ledger.object_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ShadowError("nonfinite_source")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ShadowError("invalid_snapshot_json") from exc
    if not isinstance(value, dict):
        raise ShadowError("snapshot_not_object")
    return value, hashlib.sha256(raw).hexdigest()


def count(value, name, maximum=100000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ShadowError("invalid_" + name)
    return value


def clock_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def prepare(registry, fusion, source_hashes, *, now=None):
    now = now or clock_now()
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise ShadowError("UTC_aware_clock_required")
    now = now.replace(microsecond=0)
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise ShadowError("behavioral_registry_schema_mismatch")
    if fusion.get("schema") != FUSION_SCHEMA:
        raise ShadowError("behavioral_fusion_schema_mismatch")
    reg_time = ledger.iso_time(registry.get("generated_at"))
    fusion_time = ledger.iso_time(fusion.get("generated_at"))
    if fusion.get("registry_asof") != registry.get("generated_at"):
        raise ShadowError("fusion_does_not_correspond_to_registry_snapshot")
    if not (now - dt.timedelta(minutes=MAX_SOURCE_AGE_MINUTES)
            <= reg_time <= fusion_time <= now):
        raise ShadowError("source_snapshot_stale_or_future")
    if fusion_time - reg_time > dt.timedelta(minutes=15):
        raise ShadowError("fusion_registry_lag_unacceptable")
    if registry.get("first_registry_baseline") is True:
        raise ShadowError("initial_source_baseline_not_prospective_novelty")
    if registry.get("alert_eligible") is not False:
        raise ShadowError("unexpected_warning_promotion_in_registry")
    if (fusion.get("forecast_probability") is not None or
            fusion.get("prediction_horizon") is not None or
            fusion.get("approved_warning_count") != 0 or
            fusion.get("automated_severity_changes") != 0):
        raise ShadowError("fusion_not_shielded_from_warning_promotion")
    health = registry.get("source_health")
    coverage = fusion.get("collection_coverage")
    if (not isinstance(health, dict) or not isinstance(coverage, dict)
            or not health or len(coverage) > MAX_SOURCES or health != coverage):
        raise ShadowError("source_coverage_health_mismatch")
    providers = []
    degraded = []
    for provider, fields in sorted(coverage.items()):
        if not isinstance(fields, dict) or not isinstance(provider, str):
            raise ShadowError("invalid_provider_health_object")
        status = fields.get("status")
        missing = fields.get("missingness")
        scope = fields.get("source_scope")
        for value in (provider, status, missing, scope):
            if not isinstance(value, str) or not 3 <= len(value) <= 350:
                raise ShadowError("invalid_source_coverage_metadata")
        providers.append({"provider": provider, "status": status,
                          "missingness": missing, "source_scope": scope})
        if status != "current" or missing != "none":
            degraded.append(provider)
    groups = fusion.get("review_groups")
    leads = fusion.get("new_single_source_leads")
    if (not isinstance(groups, list) or len(groups) > MAX_GROUPS
            or not isinstance(leads, list) or len(leads) > MAX_LEADS):
        raise ShadowError("candidate_lists_not_bounded")
    total_groups = count(fusion.get("review_groups_count_total"), "cross_family_count")
    total_leads = count(fusion.get("new_single_source_count_total"), "single_source_count")
    if total_groups != len(groups) or total_leads < len(leads):
        # If the cross-family list was truncated we cannot verify all
        # source roots; a valid frame must not silently claim coverage.
        raise ShadowError("candidate_count_inconsistent_or_truncated")
    ids = set()
    for item in groups:
        if not isinstance(item, dict) or item.get("status") != "cross_family_cooccurrence_unreviewed":
            raise ShadowError("unverified_or_promoted_fusion_candidate")
        if item.get("warning_level_change") is not False:
            raise ShadowError("fusion_candidate_has_warning_change")
        key = item.get("id")
        if not isinstance(key, str) or not key or key in ids:
            raise ShadowError("duplicate_or_missing_group_id")
        ids.add(key)
        if item.get("geography", {}).get("key") is None:
            raise ShadowError("crossfamily_geography_unverified")
        families = item.get("distinct_source_families")
        if (not isinstance(families, list) or len(set(families)) < 2
                or len(families) < 2 or not all(isinstance(x, str) for x in families)
                or count(item.get("distinct_provider_count"), "group_providers") < 2
                or count(item.get("source_root_count"), "group_source_roots") < 2):
            raise ShadowError("crossfamily_independence_unverified")
        obs = item.get("observation_ids")
        if not isinstance(obs, list) or len(obs) < 2 or len(set(obs)) != len(obs):
            raise ShadowError("crossfamily_source_ids_unverified")
        if ledger.iso_time(item.get("first_observed_at")) > fusion_time or ledger.iso_time(
                item.get("last_observed_at")) > fusion_time:
            raise ShadowError("future_crossfamily_observation")
    seen_leads = set()
    for item in leads:
        if not isinstance(item, dict) or item.get("status") != "single_source_unreviewed":
            raise ShadowError("unreviewed_lead_expected")
        key = item.get("observation_id")
        if not isinstance(key, str) or not key or key in seen_leads:
            raise ShadowError("duplicate_or_missing_lead_id")
        seen_leads.add(key)
        if ledger.iso_time(item.get("first_observed_at")) > fusion_time:
            raise ShadowError("future_single_source_observation")
    for field in ("registry", "fusion"):
        digest = source_hashes.get(field)
        if not isinstance(digest, str) or len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest):
            raise ShadowError("unverified_source_sha256")
    start = now + dt.timedelta(minutes=2)
    end = start + dt.timedelta(hours=24)
    frame = {
        "frame_id": "shadow-" + now.strftime("%Y%m%dT%H%M%S") + "-" + source_hashes["fusion"][:12],
        "window_start": iso(start), "window_end": iso(end),
        "registry_asof": iso(reg_time), "fusion_asof": iso(fusion_time),
        "source_sha256": source_hashes,
        "sensor_coverage": providers,
        "single_source_review_count": total_leads,
        "cross_family_review_count": total_groups,
        "collection_scope": "source_observed_nonexhaustive",
        "approved_tippers": 0,
        "source_completeness_verified": False,
        "negative_outcome_inferred": False,
        "automated_warning_changes": 0,
    }
    ledger.validate_monitor_frame(frame, iso(now), [])
    # Unlike a source frame, no latent event hypothesis or aircraft track
    # is included. Forecasts require separately reviewed tipper issuance.
    return frame, {
        "schema": SCHEMA, "status": "eligible_for_local_shadow_frame",
        "input_checked_at": iso(now),
        "registry_asof": frame["registry_asof"],
        "fusion_asof": frame["fusion_asof"],
        "frame_id": frame["frame_id"], "window_start": frame["window_start"],
        "window_end": frame["window_end"],
        "single_source_review_count": total_leads,
        "cross_family_review_count": total_groups,
        "providers_checked": len(providers), "providers_with_missingness": len(degraded),
        "sources_degraded": degraded, "reviewed_falsifiable_tippers": 0,
        "issued_warning_count": 0, "automatic_promotion": False,
        "no_event_inferred": False, "source_completeness_verified": False,
        "approved_for_global_recall_scoring": False,
        "frozen_issued_tipper": False, "time_anchor_trusted": False,
        "source_sha256": source_hashes,
        "interpretation": "Evidence coverage frame only; no verified prospective forecast, absence of event or global risk denominator",
    }


def run(registry_path, fusion_path, *, mode="check", ledger_path=None, now=None):
    if mode not in ("check", "freeze"):
        raise ShadowError("unsupported_shadow_mode")
    if mode == "freeze" and ledger_path is None:
        raise ShadowError("ledger_required_for_freeze")
    registry, rhash = read_snapshot(registry_path)
    fusion, fhash = read_snapshot(fusion_path)
    frame, receipt = prepare(registry, fusion, {"registry": rhash, "fusion": fhash},
                             now=now)
    if mode == "freeze":
        repo = Path(__file__).resolve().parents[1]
        ledger_path = Path(ledger_path)
        if ledger_path.resolve().is_relative_to(repo):
            raise ShadowError("private_frame_ledger_must_be_outside_checkout")
        if ledger_path.resolve() in (Path(registry_path).resolve(), Path(fusion_path).resolve()):
            raise ShadowError("cannot_overwrite_source_snapshots")
        appended = ledger.append(ledger_path, "frame", frame)
        receipt["status"] = "local_unanchored_shadow_frame_appended"
        receipt["frame_entry_hash"] = appended["entry_hash"]
        receipt["local_recorded_at"] = appended["recorded_at"]
        receipt["frozen_issued_tipper"] = False
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--fusion", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--mode", choices=("check", "freeze"), default="check")
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args(argv)
    if args.receipt.resolve() in (args.registry.resolve(), args.fusion.resolve()) or (
            args.ledger is not None and args.receipt.resolve() == args.ledger.resolve()):
        print('{"status":"unavailable","reason":"receipt_cannot_overwrite_inputs_or_ledger"}')
        return 1
    try:
        report = run(args.registry, args.fusion, mode=args.mode, ledger_path=args.ledger)
        code = 0
    except (ShadowError, ledger.LedgerError, OSError, TypeError,
            ValueError, OverflowError, RecursionError) as exc:
        report = {"schema": SCHEMA, "status": "unavailable",
                  "reason": str(exc) if isinstance(exc, (ShadowError, ledger.LedgerError))
                  else "source_or_clock_unavailable",
                  "issued_warning_count": 0,
                  "automatic_promotion": False,
                  "no_event_inferred": False,
                  "frozen_issued_tipper": False,
                  "source_completeness_verified": False,
                  "approved_for_global_recall_scoring": False}
        code = 1
    # Aggregate output only, not original per-sensor observation geometry.
    try:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("w", encoding="utf-8") as out:
            json.dump(report, out, indent=2, allow_nan=False)
            out.write("\n")
    except OSError:
        return 1
    print(f"{report['status']}: {args.receipt}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
