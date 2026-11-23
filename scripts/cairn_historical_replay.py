#!/usr/bin/env python3
"""Read-only historical-as-of CAIRN source-discrimination diagnostic.

Replay actual archived behavioral-registry snapshots, NEVER a pooled newest
registry disguised as what the engine knew on day t. No future source versions,
as-of confirmation after the fact, or inferred attack events. The reference
dossier dates are *curated observations*, not outcome labels. A source title
match cannot be scored as an independently verified warning.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path

import sys
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard.hypothesis_discriminator_engine import assess
from dashboard.hypothesis_auto_review import _match_case, _parse_time

SCHEMA = "cairn.historical-source-attribution-audit.v1"


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _stamp(row):
    return _parse_time(row.get("generated_at")) if isinstance(row, dict) else None


def snapshots(directory, *, until=None):
    """Reconstruct as-of snapshots from actual timestamped *incremental* files.

    The durable history stores new_records (not complete records). This replay
    rolls them forward in original capture order, omits initial baseline
    records when not individually represented and never inserts modern archive
    contents retroactively. Health is from each real source receipt.
    """
    original = []
    for path in sorted(Path(directory).glob("*.json")):
        obj = _read(path)
        when = _stamp(obj)
        if (not when or obj.get("schema") != "aiba.behavioral-observations.v1"
                or (until and when > until)):
            continue
        entries = obj.get("new_records")
        if not isinstance(entries, list) and not isinstance(obj.get("records"), list):
            continue
        original.append((when, obj, path.name))
    original.sort(key=lambda item: (item[0], item[2]))
    known = {}
    byday = {}
    for when, obj, name in original:
        # Support direct full snapshots for local test fixtures only; actual
        # production historical receipts have the new_records array.
        if isinstance(obj.get("new_records"), list):
            for row in obj["new_records"]:
                if not isinstance(row, dict):
                    continue
                first = _parse_time(row.get("first_observed_at"))
                ident = row.get("id")
                if not ident or not first or first > when:
                    continue
                if row.get("registry_novelty") == "initial_provider_baseline":
                    continue
                known.setdefault(ident, row)
        elif isinstance(obj.get("records"), list):
            known = {row["id"]: row for row in obj["records"]
                     if isinstance(row, dict) and row.get("id") and
                     (first := _parse_time(row.get("first_observed_at"))) and
                     first <= when}
        day = when.date().isoformat()
        output = {**obj, "records": list(known.values()),
                  "asof_reconstructed_from_new_records": True,
                  "initial_registry_baseline_not_reconstructed": True}
        byday[day] = (when, output, name)
    return [byday[day] for day in sorted(byday)], len(original)


def _case_records_at(snapshot, case_id):
    rows = []
    for r in snapshot.get("records", []):
        if not isinstance(r, dict):
            continue
        basis = _match_case(case_id, {"title": r.get("title"),
                                     "geography": r.get("geography"),
                                     "case_hint": r.get("case_hint")})
        if basis:
            rows.append((r, basis))
    return rows


def replay(source_snapshots, dossier, config, *, historical_archive=None,
           source_inspection=None):
    if not source_snapshots:
        return {"schema": SCHEMA, "status": "no_historical_source_snapshots",
                "real_event_precision": None, "real_event_recall": None,
                "warning_lead_time_hours": None, "source_snapshots_used": 0}
    windows = []
    first = source_snapshots[0][0].date()
    last = source_snapshots[-1][0].date()
    bycase = {cid: [] for cid in config["cases"]}
    total_screens = Counter()
    source_freshness = Counter()
    for when, registry, filename in source_snapshots:
        if registry.get("schema") != "aiba.behavioral-observations.v1":
            continue
        # As-of snapshot is the actual recorded registry at that time,
        # not today's archive: avoids ex-post additions and future sources.
        asof_rows = [row for row in registry.get("records", [])
                     if (isinstance(row, dict) and
                         (stamp := _parse_time(row.get("first_observed_at")))
                         and stamp <= when)]
        asof_reg = {**registry, "records": asof_rows}
        result = assess(dossier, asof_reg, {}, {}, {}, config, at=when)
        day = when.date().isoformat()
        daily = {"asof": when.isoformat().replace("+00:00", "Z"),
                 "source_snapshot_filename": filename,
                 "visible_source_rows": len(asof_rows),
                 "cases": {}}
        for cid, value in result["cases"].items():
            s = value["summary"]
            daily["cases"][cid] = {
                "linked_source_documents": s["source_documents_case_associated"],
                "escalation_signposts": s["escalation_signpost_nominations"],
                "alternative_signposts": s["alternative_signpost_nominations"],
                "ambiguous_signposts": s["ambiguous_signpost_nominations"],
                "status": s["competing_pattern"],
            }
            bycase[cid].append((when, daily["cases"][cid]))
            total_screens["escalation_signposts"] += s["escalation_signpost_nominations"]
            total_screens["alternative_signposts"] += s["alternative_signpost_nominations"]
            total_screens["ambiguous_signposts"] += s["ambiguous_signpost_nominations"]
            if s["source_documents_case_associated"]:
                total_screens["case_with_visible_observations"] += 1
        windows.append(daily)
    latest = source_snapshots[-1][1]
    hints = []
    analyst_rows = (historical_archive or {}).get("records", []) if isinstance(historical_archive, dict) else []
    for rec in analyst_rows:
        if not isinstance(rec, dict) or rec.get("collection_mode") != "analyst":
            continue
        cid = rec.get("case_hint")
        if cid not in config["cases"]:
            continue
        first_observed = _parse_time(rec.get("first_observed_at"))
        if not first_observed or not first <= first_observed.date() <= last:
            continue
        masked = _match_case(cid, {"title": rec.get("title"),
                                  "geography": rec.get("geography_label"),
                                  "case_hint": None})
        hints.append({"record_id": rec.get("id"), "case_id": cid,
                      "first_ingested": rec.get("first_observed_at"),
                      "case_link_without_explicit_hint": masked is not None,
                      "case_association_basis_without_hint": masked,
                      "claim_is_not_outcome_ground_truth": True})
    # Reference material identifies dated, sourced observations, not
    # adjudicated escalation outcomes. They may predate data collection.
    reference = []
    for case in dossier:
        for ev in case.get("signals", []):
            date = ev.get("date")
            if not isinstance(date, str):
                continue
            try:
                day = dt.date.fromisoformat(date[:10])
            except ValueError:
                continue
            reference.append({"case_id": case.get("id"), "date": day.isoformat(),
                              "within_available_collection_history": first <= day <= last,
                              "assessment": str(ev.get("assessment", ""))[:90]})
    covered_ref = [r for r in reference if r["within_available_collection_history"]]
    # Negative-control test checks only the source-family intent. A title
    # describing a scheduled military exercise is not independently verified
    # as an absence of hostile preparation.
    controls = []
    for r in latest.get("records", []):
        title = str(r.get("title") or "").lower()
        if ("firing exercise" in title or "training exercise" in title or
                "routine drill" in title):
            controls.append(r)
    negative = assess(dossier,
                      {**latest, "records": controls},
                      {}, {}, {}, config, at=source_snapshots[-1][0])
    neg_total = sum(x["summary"]["escalation_signpost_nominations"]
                    for x in negative["cases"].values())
    neg_ambig = sum(x["summary"]["ambiguous_signpost_nominations"]
                    for x in negative["cases"].values())
    percase = {}
    for cid, series in bycase.items():
        seen = [(clock, row) for clock, row in series if row["linked_source_documents"]]
        signposts = [(clock, row) for clock, row in series if
                     row["escalation_signposts"] or row["alternative_signposts"]]
        percase[cid] = {
            "daily_snapshots_evaluated": len(series),
            "days_with_any_case_linked_source": len(seen),
            "first_case_source_visible": (seen[0][0].isoformat() if seen else None),
            "first_nomination_visible": (signposts[0][0].isoformat() if signposts else None),
            "last_asof": series[-1][0].isoformat(),
            "last": series[-1][1],
        }
    receipts = source_inspection if isinstance(source_inspection, dict) else {}
    source_status = ({"attempted": receipts.get("unique_source_documents_attempted"),
                      "inspected": receipts.get("status_counts", {}).get("document_text_inspected"),
                      "contains_no_retrospective_body_versions": True}
                     if receipts.get("schema") == "cairn.source-inspection.v1" else
                     {"status": "not_available_for_historical_replay"})
    return {
        "schema": SCHEMA, "status": "historical_source_visibility_diagnostic_only",
        "first_source_snapshot_day": first.isoformat(),
        "last_source_snapshot_day": last.isoformat(),
        "source_snapshots_used": len(windows),
        "history_span_days_inclusive": (last - first).days + 1,
        "missing_days": (last - first).days + 1 - len(windows),
        "real_outcome_gold_standard": False,
        "retrospective_reconstruction": True,
        "reconstructed_from_incremental_first_seen_records": True,
        "initial_registry_baseline_coverage": "not_reconstructed",
        "lookahead_restricted_to_snapshot_asof": True,
        "real_event_precision": None, "real_event_recall": None,
        "false_positive_rate_on_true_non_events": None,
        "warning_lead_time_hours": None,
        "reference_curated_dated_signals": len(reference),
        "reference_signals_within_available_history": len(covered_ref),
        "reference_signals_preexisting_or_after_history": len(reference)-len(covered_ref),
        "reference_source_is_not_an_independent_outcome": True,
        "case_hint_diagnostic": {
            "report_count": len(hints),
            "title_and_geography_matched_without_prior_hint":
                sum(x["case_link_without_explicit_hint"] for x in hints),
            "title_and_geography_missed_without_prior_hint":
                sum(not x["case_link_without_explicit_hint"] for x in hints),
            "not_an_event_detection_recall_measure": True,
            "source_reports": hints[:70],
        },
        "controlled_source_class_audit": {
            "source_rows_with_literal_training_exercise_titles": len(controls),
            "escalation_title_nominations_in_this_subset": neg_total,
            "ambiguous_nominations_in_this_subset": neg_ambig,
            "not_true_negative_event_labels": True,
        },
        "aggregate_case_day_screen_counts": dict(total_screens),
        "cases": percase,
        "asof_windows": windows,
        "deployed_source_inspection_diagnostic": source_status,
        "limits": [
            "Records are source-collection snapshots, not independently verified military outcomes.",
            "Present archive records are excluded from historical scoring; earlier as-of snapshot contents are used.",
            "If historical source body snapshots are unavailable, today's source retrieval cannot be backdated.",
            "Dossier timestamps are source-reported observations, not truth labels or episode onsets.",
            "No false-positive rate, sensitivity, lead time or probabilistic skill can be estimated without labeled events/non-events.",
            "This diagnostic evaluates source visibility, rule nomination and geographic/source claim processing only.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--cases", type=Path, default=Path("data/verified_hotspots.json"))
    p.add_argument("--config", type=Path, default=Path("data/hypothesis_discriminators.json"))
    p.add_argument("--inspection", type=Path, default=None)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--end", default=None, help="optional UTC cutoff, never permits future observation")
    a = p.parse_args()
    end = _parse_time(a.end) if a.end else None
    snapshots_by_day, full_count = snapshots(a.history, until=end)
    result = replay(snapshots_by_day, _read(a.cases) or [],
                    _read(a.config) or {},
                    historical_archive=_read(a.archive) or {},
                    source_inspection=_read(a.inspection) if a.inspection else None)
    result["historical_snapshot_files_valid"] = full_count
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("CAIRN historical replay:",result["status"])
    print("UTC source days:",result.get("source_snapshots_used",0),
          "of",result.get("history_span_days_inclusive",0))
    print("Dated dossier reference observations covered:",
          result.get("reference_signals_within_available_history",0),
          "of",result.get("reference_curated_dated_signals",0))
    print("Case-hinted real source reports:",result.get("case_hint_diagnostic",{}).get("report_count",0),
          "title/geography match without hints:",
          result.get("case_hint_diagnostic",{}).get("title_and_geography_matched_without_prior_hint",0))
    print("Scheduled exercise source controls:",
          result.get("controlled_source_class_audit",{}))
    print("Warning precision, recall, lead-time: NOT ESTIMABLE without independent outcome annotations")


if __name__ == "__main__":
    main()
