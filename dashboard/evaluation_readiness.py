"""Public-only AIBA evaluation readiness summary for the ONE Atlas.

Deliberately NOT a private ledger reader or predictive-skill evaluator.
No private issuance data, case IDs, actor hypotheses, analyst identities,
raw aircraft observations or unsigned claims of verified false alarms.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

SCHEMA = "aiba.atlas-public-evaluation-readiness.v1"
BEHAVIOR_SCHEMA = "aiba.behavioral-convergence-shadow.v1"
MAX_SOURCE_ADAPTERS = 30
FRESHNESS_MINUTES = 90
FORECAST_METRICS = (
    "issued_tippers",
    "adjudicated_tippers",
    "independently_verified_before_publication",
    "verified_false_warnings",
    "median_verified_prepublication_lead_seconds",
    "false_alarms_per_analyst_day",
    "recall_against_registered_outcomes",
    "precision_across_monitored_risk_set",
    "brier_calibration_score",
)


def utc_time(value):
    if not isinstance(value, str) or len(value) > 38:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return None
    return parsed.astimezone(dt.timezone.utc)


def summary(behavior, *, generated_at=None):
    """Return bounded public readiness only. Never infer no-event labels."""
    now = utc_time(generated_at) if generated_at is not None else dt.datetime.now(dt.timezone.utc)
    if now is None:
        raise ValueError("invalid_public_summary_clock")
    evidence_ok = (
        isinstance(behavior, dict)
        and behavior.get("schema") == BEHAVIOR_SCHEMA
        and behavior.get("status") == "read_only_shadow_evidence"
        and behavior.get("approved_warning_count") == 0
        and behavior.get("automated_severity_changes") == 0
        and behavior.get("forecast_probability") is None
        and behavior.get("source_continuity_proven") is False
        and behavior.get("map_coordinates_inferred") is False
        and isinstance(behavior.get("collection_coverage"), dict)
        and len(behavior["collection_coverage"]) <= MAX_SOURCE_ADAPTERS
    )
    source = utc_time(behavior.get("source_generated_at")) if evidence_ok else None
    age = (now - source).total_seconds() / 60 if source else None
    source_recent = bool(age is not None and 0 <= age <= FRESHNESS_MINUTES)
    coverage = behavior["collection_coverage"] if evidence_ok else {}
    missing = sum(
        1 for entry in coverage.values()
        if not isinstance(entry, dict)
        or entry.get("status") != "current"
        or entry.get("missingness") != "none"
    )
    # Count only data adapters that self-report; never total possible world
    # sensors, registered risk sets, or reviewed quiet intervals.
    provider_count = len(coverage)
    return {
        "schema": SCHEMA,
        "status": "prospective_skill_not_established",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "public_forecast_ledger": "not_connected",
        "observation": {
            "behavioral_source_asof": source.strftime("%Y-%m-%dT%H:%M:%SZ") if source else None,
            "source_age_minutes_at_build": round(age, 2) if age is not None and age >= 0 else None,
            "snapshot_within_90_minutes_at_build": source_recent,
            "source_adapters_reported": provider_count if evidence_ok else None,
            "source_adapters_bounded_or_degraded": missing if evidence_ok else None,
            "worldwide_source_completeness_verified": False,
            "unobserved_intervals_are_negative_events": False,
        },
        "verification_gates": {
            # "unknown" means there may be private work but the public
            # evaluation has no verified evidence of it.
            "prospective_monitoring_frames_witnessed": "not_connected",
            "actual_forecasts_with_independent_signed_timestamps": "not_connected",
            "independent_first_publication_review": "not_connected",
            "actor_action_geography_outcomes_adjudicated": "not_connected",
            "complete_risk_set_and_negative_case_ascertainment": "not_connected",
            "false_alarm_and_missed_event_denominators": "not_connected",
        },
        "metrics": {key: None for key in FORECAST_METRICS},
        "publication_of_private_ledger": False,
        "forecast_probability": None,
        "production_warning_updates": False,
        "claims_of_predicitive_skill": False,
        "interpretation": (
            "The Atlas displays source monitoring context, not validated early-warning performance. "
            "The private ledger and any real signed timestamps are not connected to this public site. "
            "No forecast counts, hits, false alarms, skill estimates, or calm periods can be inferred."
        ),
    }


def write(site, behavior, *, generated_at=None):
    """Produce a public safe machine-readable file for the Atlas only."""
    result = summary(behavior, generated_at=generated_at)
    output = Path(site) / "evaluation_summary.json"
    # No reading from an external private ledger or import of arbitrary
    # third-party metric values; all metric keys are deliberately null.
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    return result
