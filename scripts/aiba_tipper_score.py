#!/usr/bin/env python3
"""Offline AIBA issued-tipper scoring; ledger is read-only, labels conservative.

No GDELT or UCDP API calls. Sources are separately reviewed append-only facts.
No recall without monitored negative risk sets / independently discovered events.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import aiba_tipper_ledger as ledger
from scripts import aircraft_route_history as routes

SCHEMA = "aiba.tipper-scoring-summary.v1"


def score_entries(entries):
    # Chain already verified by ledger.validate_log/read_ledger.
    issued = {}
    reports = {}
    outcomes = {}
    revisions = Counter()
    frames = []
    for event in entries:
        if event["kind"] == "frame":
            frames.append(event)
            continue
        p = event["payload"]
        key = p["tipper_id"]
        if event["kind"] == "issued":
            issued[key] = event
        elif event["kind"] == "report":
            reports.setdefault(key, []).append(p)
        elif event["kind"] == "adjudicated":
            revisions[key] += int(key in outcomes)
            outcomes[key] = p
    counts = Counter()
    leads, gdelt_lags, brier_terms = [], [], []
    matched_case_ids = set()
    repeated_case_ids = set()
    for tipper_id, issuance in issued.items():
        counts["issued_tippers"] += 1
        p = issuance["payload"]
        issued_at = ledger.iso_time(issuance["recorded_at"])
        end = ledger.iso_time(p["horizon_end"])
        review = outcomes.get(tipper_id)
        if review is None:
            counts["unadjudicated_not_negative"] += 1
            continue
        status = review["outcome"]
        if status in ("censored", "inconclusive", "not_applicable"):
            counts["unscorable_" + status] += 1
            continue
        matched = status == "matched_event"
        if matched:
            occurred = ledger.iso_time(review["event_time"])
            # Only a genuinely future event in the issued forecast horizon
            # may count as success; hindsight and late events do not.
            within_window = issued_at < occurred <= end
            if not within_window:
                counts["occurred_outside_forecast_window_not_hit"] += 1
        else:
            within_window = False
        if not matched or not within_window:
            # 'no_event' requires horizon-wide verification, enforced
            # on append and replay; outside-window labels need coverage.
            if matched and ledger.iso_time(review["verified_through"]) < end:
                counts["event_outside_window_but_window_not_verified"] += 1
                continue
            counts["resolved_no_in_horizon_event"] += 1
        else:
            counts["resolved_matched_in_horizon"] += 1
            if review["case_id"] in matched_case_ids:
                repeated_case_ids.add(review["case_id"])
            matched_case_ids.add(review["case_id"])
        counts["resolved_forecasts"] += 1
        outcome = int(within_window)
        brier_terms.append((p["confidence"] - outcome) ** 2)
        if not within_window:
            continue
        news = reports.get(tipper_id, [])
        # A GDELT observation is NOT first publication. Require separately
        # reviewed credible source; take earliest credible candidate.
        credible = [r for r in news if r["kind"] == "credible_publication"]
        gdelt = [r for r in news if r["kind"] == "gdelt_first_seen"]
        if credible and any(r["publication_scope_reviewed"] for r in credible):
            earliest = min(ledger.iso_time(r["event_time"]) for r in credible)
            counts["matched_with_reviewed_publication_timeline"] += 1
            if earliest > issued_at:
                counts["matched_tipper_before_reviewed_publication"] += 1
                leads.append(round((earliest - issued_at).total_seconds()))
            else:
                counts["matched_tipper_not_before_publication"] += 1
            if gdelt:
                first_gdelt = min(ledger.iso_time(r["event_time"]) for r in gdelt)
                if first_gdelt >= earliest:
                    gdelt_lags.append(round((first_gdelt - earliest).total_seconds()))
                else:
                    counts["gdelt_record_before_reviewed_earliest_article_check_timeline"] += 1
        else:
            counts["matched_without_complete_publication_review"] += 1
    # These are per issued tipper, not event recall; multiple warnings
    # about one actual event are explicitly flagged and not independent hits.
    return {
        "schema": SCHEMA, "status": "offline_ledger_score_review_required",
        "scored_unit": "issued_tipper_not_unique_geopolitical_event",
        "source_entries": len(entries),
        "prospective_monitor_frames": len(frames),
        "monitor_frames_are_not_verified_negative_outcomes": True,
        "counts": dict(counts),
        "duplicate_event_cases_among_hits": len(repeated_case_ids),
        "adjudication_revisions": sum(revisions.values()),
        "resolved_forecast_hit_fraction": (
            round(counts["resolved_matched_in_horizon"] / counts["resolved_forecasts"], 6)
            if counts["resolved_forecasts"] else None),
        "resolved_forecast_false_warning_fraction": (
            round(counts["resolved_no_in_horizon_event"] / counts["resolved_forecasts"], 6)
            if counts["resolved_forecasts"] else None),
        "mean_brier_for_resolved_tippers": (
            round(sum(brier_terms) / len(brier_terms), 6) if brier_terms else None),
        "pre_publication_leads_seconds": {
            "count": len(leads), "median": (
                sorted(leads)[len(leads)//2] if len(leads)%2 else
                (sorted(leads)[len(leads)//2-1]+sorted(leads)[len(leads)//2])/2
            ) if leads else None, "maximum": max(leads) if leads else None,
        },
        "gdelt_observation_delay_seconds": {
            "count": len(gdelt_lags),
            "minimum": min(gdelt_lags) if gdelt_lags else None
        },
        "recall": None, "precision_over_all_world_events": None,
        "false_alarms_per_analyst_day": None,
        "risk_set_and_source_coverage_validated": False,
        "first_media_report_independently_proven": False,
        "time_anchoring_verified": False,
        "production_warning_updates": False,
        "limitations": [
            "Local hash chain cannot prove authentic issuance time or prevent privileged rewrite",
            "Lead time refers to manually reviewed first credible publication candidates; completeness is not independently established",
            "GDELT first seen is news ingestion, not event or first article time",
            "No-event labels require a reviewed complete forecast horizon; censored/unadjudicated never count as negatives",
            "No recall, global false-alarm rate or analyst-day burden without frozen risk sets and observation denominators",
            "Confidence and outcome labels lack prospective calibration and independent adjudication here",
        ],
    }


def score_ledger(path):
    entries, head = ledger.read_ledger(path)
    output = score_entries(entries)
    output["ledger_head_hash"] = head
    output["ledger_chain_verified"] = True
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.ledger.resolve() == args.output.resolve():
        print('{"status":"unavailable","reason":"output_cannot_overwrite_ledger"}')
        return 1
    try:
        output = score_ledger(args.ledger)
        code = 0
    except (ledger.LedgerError, OSError, TypeError, OverflowError, ValueError) as exc:
        output = {"schema": SCHEMA, "status": "unavailable",
                  "reason": str(exc) if isinstance(exc, ledger.LedgerError)
                  else "ledger_unavailable_or_invalid",
                  "counts": None, "production_warning_updates": False,
                  "recall": None}
        code = 1
    try:
        routes.write_atomic(args.output, output)
    except OSError:
        return 1
    print(f"{output['status']}: {args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
