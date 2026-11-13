#!/usr/bin/env python3
"""Read-only actual-source report-resolution probe; historical, NOT forecast issuance.

Replays the actual source ledger at its recorded generation time so audit
results are not interpreted as "current" when Github collection is delayed.
Prints only aggregates (no report titles, source coordinates or private data).
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys

if __package__ in (None,""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from behavioral_fusion import recently_observed
from behavioral_registry import when
from behavioral_event_resolution import build
from ops_pipeline import load_json


def probe(state):
    state=Path(state)
    latest=load_json(state/"latest"/"behavioral_registry.json",{}) or {}
    at=when(latest.get("generated_at"))
    if not at:
        raise ValueError("unavailable_source_timestamp")
    recent,history=recently_observed(state,at)
    result=build(recent)
    return {
        "schema":"aiba.report-resolution-real-data-probe.v1",
        "status":"historical_public_source_audit_not_live_warning",
        "registry_asof":latest["generated_at"],
        "normalized_records_in_latest_registry":latest.get("record_count"),
        "unique_recent_source_records":history["recent_unique_records"],
        "history_files_examined":history["history_files_examined"],
        "excluded_source_observations":history["excluded_observations"],
        "exact_source_document_groups":result["same_document_group_count_total"],
        "possible_same_source_story_report_pairs":result["possible_same_source_story_count_total"],
        "possible_same_event_report_pairs":result["possible_same_event_count_total"],
        "related_but_not_same_event_report_pairs":result["related_reporting_count_total"],
        "records_examined":result["records_examined"],
        "eligible_event_reporting_records":result["eligible_event_reporting_records"],
        "routine_notice_market_or_measurement_records_excluded_from_text_event_matching":
            result["routine_notice_market_or_measurement_records_excluded_from_text_event_matching"],
        "candidate_groups_displayed":len(result["candidate_groups"]),
        "matching_input_truncated":result["input_truncated"],
        "matching_comparisons_capped":result["pairwise_comparisons_capped"],
        "all_candidates_unreviewed":True,
        "source_corroboration_verified":False,
        "geopolitical_warning_issued":False,
        "publisher_location_used_as_event_site":False,
        "forecast_accuracy_estimated":False,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state",type=Path,required=True)
    args=ap.parse_args()
    result=probe(args.state)
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
