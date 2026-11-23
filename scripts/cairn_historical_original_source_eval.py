#!/usr/bin/env python3
"""Historical real-document, no-outcome-label geography diagnostic.

Uses the repo's existing reviewed GOV.UK seed manifest and Content API
rights/identity gates. Historical primary-government claims are not an
independent ground-truth record of attacks. Original narrative text is
processed in memory and never written to the public audit artifact.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aiba_govuk_corpus import api_get, canonical_path, check_manifest, to_source
from dashboard.source_geo_claims import inspect_text, CASE_GAZETTEER

SCHEMA = "cairn.historical-original-documents.v1"


def select(manifest, limit=14):
    seeds = check_manifest(manifest)
    if not 1 <= limit <= 24:
        raise ValueError("1–24 historical original sources per pilot")
    grouped = {}
    for seed in seeds:
        grouped.setdefault(seed["sampling_stratum"], []).append(seed)
    # Deliberately sample both episode-hinted and nonincident controls.
    selected = []
    indexes = {name: 0 for name in grouped}
    order = ["incident_candidate", "operational_context", "nonincident_control"]
    while len(selected) < limit:
        changed = False
        for name in order:
            group = grouped.get(name, [])
            if indexes.get(name, 0) < len(group) and len(selected) < limit:
                selected.append(group[indexes[name]])
                indexes[name] += 1
                changed = True
        if not changed:
            break
    return selected


def _type(seed):
    hint = seed["episode_hint"]
    if "yemen" in hint or "redsea" in hint:
        return "govuk_yemen_historical"
    if "ukraine" in hint:
        return "govuk_ukraine_historical"
    return None


def evaluate(manifest, *, limit=14, fetch=api_get,
             at=None):
    selected = select(manifest, limit)
    at = at or dt.datetime.now(dt.timezone.utc)
    if at.tzinfo is None:
        raise ValueError("UTC-aware inspection clock required")
    checked = []
    failures = Counter()
    success = 0
    locations = 0
    text_action_rule = 0
    for seed in selected:
        outcome = {"seed_id": seed["id"], "source_url": seed["url"],
                   "episode_hint": seed["episode_hint"],
                   "sampling_stratum": seed["sampling_stratum"],
                   "original_text_read": False, "reported_site_verified": False,
                   "source_event_verified": False, "published_before_inspection": None,
                   "geo_status": "unknown", "historical_source_date": None,
                   "original_narrative_published": False}
        try:
            obj = fetch(canonical_path(seed["url"]))
            stamp = at.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
            report, reason = to_source(seed, obj, stamp)
            if reason or not report:
                raise ValueError("source_"+str(reason))
            published = dt.datetime.fromisoformat(
                report["source_published_at"].replace("Z", "+00:00"))
            if published > at:
                raise ValueError("source_published_after_inspection")
            result = inspect_text(report["source_text"],_type(seed) or "unclassified",
                                  {})
            location = result["case_attribution"]
            outcome.update({
                "original_text_read": True,
                "published_before_inspection": True,
                "historical_source_date": report["source_published_at"],
                "source_text_sha256": result["source_text_sha256"],
                "source_text_chars_inspected": result["source_text_chars_inspected"],
                "geo_status": location["status"],
                "named_locality_from_source_text": location["named_place"],
                "location_basis": location.get("spatial_precision"),
                "reported_country_or_area": location.get("reported_country_or_area"),
                "historical_gazetteer_case": _type(seed),
                "reported_site_verified": False,
            })
            success += 1
            if location["source_text_location_asserted"]:
                locations += 1
        except Exception as exc:
            # A failed provider read or source-rights attestation is explicit.
            # Do not treat inaccessible source text as a negative report.
            reason = type(exc).__name__
            if isinstance(exc, ValueError):
                reason = "source_adapter_value_error"
            failures[reason] += 1
            outcome["error_category"] = reason
            outcome["geo_status"] = "original_source_unavailable"
        checked.append(outcome)
    return {
        "schema": SCHEMA,
        "status": "historical_source_document_diagnostic_only",
        "evaluated_at": at.astimezone(dt.timezone.utc).isoformat(),
        "historical_seed_manifest_schema": manifest["schema"],
        "source_strata_are_not_event_truth_labels": True,
        "real_original_documents_requested": len(selected),
        "real_original_documents_inspected": success,
        "source_text_retrieval_fraction": round(success/len(selected),3) if selected else None,
        "real_original_documents_with_named_action_locality": locations,
        "geo_attribution_fraction_among_fetched": round(locations/success,3) if success else None,
        "unavailable_original_document_reasons": dict(failures),
        "event_occurrence_ground_truth": None,
        "incident_geo_precision_against_verified_sites": None,
        "warning_detection_recall": None,
        "false_positive_rate": None,
        "dates_are_historical_publication_not_warning_asof": True,
        "all_original_article_bodies_ephemeral": True,
        "reports": checked,
        "limitations": [
            "Sampling strata are human-curated source kinds, NOT independent military incident labels.",
            "Sources are retrieved in this run, long after historical publication; the original historical information availability and corrections are not reconstructed.",
            "Geo labels are literal action-sentence places, not source-confirmed or independently verified incident locations.",
            "No ability to compute event-level precision, recall, negative-event false-positive rate or warning lead time without reviewed outcomes.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",type=Path,default=Path("data/govuk_source_seed_manifest.json"))
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--limit",type=int,default=14)
    a=p.parse_args()
    result=evaluate(json.loads(a.seeds.read_text(encoding="utf-8")),limit=a.limit)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("Original GOV.UK historical sources:",result["real_original_documents_inspected"],
          "of",result["real_original_documents_requested"],"retrieved; locale mentions:",
          result["real_original_documents_with_named_action_locality"])
    print("Source content access unavailable:",result["unavailable_original_document_reasons"])
    print("Independent site truth and prior warning skill: not available")


if __name__=="__main__":
    main()
