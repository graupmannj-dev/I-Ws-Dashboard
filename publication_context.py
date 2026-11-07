#!/usr/bin/env python3
"""Add GDELT/Wikimedia daily *context* to AIBA's six-hour decision briefs.

These media/event-coded and public-interest signals are not independent
confirmation, and do NOT raise threat classifications or the change counter.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
from ops_pipeline import load_json
from fusion_briefs import matches_case, REGISTRY

PAGES = {
    "iran_gulf": {"Iran"},
    "taiwan": {"Taiwan"},
    "russia_nato": set(),  # Wikipedia collector lacks a NATO-attack matched article.
    "korea": {"North Korea", "South Korea"},
    "horn_ethiopia_eritrea": {"Eritrea", "Ethiopia"},
    "horn_ethiopia_sudan": {"Sudan", "Ethiopia"},
    "horn_ethiopia_kenya_moyale": {"Kenya", "Ethiopia"},
    "afpak": {"Afghanistan", "Pakistan"},
    "drc_rwanda": {"Democratic Republic of the Congo", "Rwanda"},
    "thailand_cambodia": {"Thailand", "Cambodia"},
}

def decorate(base, site, registry=REGISTRY):
    cfg = json.loads(Path(registry).read_text(encoding="utf-8"))
    lookup = {case["id"]: case for case in cfg["cases"]}
    all_gdelt = load_json(Path(site) / "hotspots.json", {})
    status = load_json(Path(site) / "collection_status.json", {})
    leads = [x for x in all_gdelt.get("hotspots", [])
             if x.get("scope") == "Algorithmic lead" and str(x.get("id", "")).startswith("gdelt_BILAT_")]
    wiki = status.get("wikipedia") or {}
    attention = wiki.get("results", {}).get("recent_flags", [])
    result = deepcopy(base)
    for brief in result.get("cases", []):
        case_id = brief["id"]
        config = lookup.get(case_id)
        matches = [x for x in leads if config and matches_case(config, {"title": x.get("name", "")})]
        flags = [x for x in attention if x.get("name") in PAGES.get(case_id, set())]
        note = ("No case-matched daily GDELT nomination or public-attention flag. "
                "This is NOT evidence of normal military conditions.")
        if matches and flags:
            note = ("Media-coded conflict coverage and English-language public attention both show anomalies. "
                    "Both may be reactions to the SAME publicly reported event, not independent leading warnings.")
        elif matches:
            note = ("A GDELT-coded bilateral media anomaly was nominated. Verify unique events, country coding "
                    "and original primary sources before drawing an escalation inference.")
        elif flags:
            note = ("Public interest changed without a matching GDELT bilateral nomination under these thresholds. "
                    "Check whether this reflects news exposure or a distinct event; it is not a warning by itself.")
        brief["daily_context"] = {
            "gdelt_dataset_asof": all_gdelt.get("asof"),
            "gdelt_coverage": all_gdelt.get("data_completeness", {}),
            "gdelt_anomalies": [
                {"name": x.get("name"), "scope": x.get("scope"), "dataset_asof": x.get("asof"),
                 "event_share_ratio": x.get("metrics", {}).get("ratio"),
                 "sample_n_recent": x.get("metrics", {}).get("recent"),
                 "source_url": "https://data.gdeltproject.org/events/",
                 "status": "GDELT media-coded nomination only"}
                for x in matches[:5]
            ],
            "wikipedia_flags": [
                {"page": x.get("name"), "date": x.get("date"), "robust_z": x.get("robust_z"),
                 "source_url": x.get("source"), "status": "Public attention, not local action"}
                for x in flags[:5]
            ],
            "wikipedia_source_coverage": wiki.get("completeness", {}),
            "interpretation": note,
            "caveat": "Daily signals have different clocks than six-hour operational feeds; no causal ordering is inferred."
        }
    result["daily_context_status"] = {
        "gdelt_dataset_asof": all_gdelt.get("asof"),
        "gdelt_candidates_total": len(leads),
        "wikipedia_source_asof": wiki.get("requested_through"),
        "wikipedia_recent_flags_total": len(attention),
        "caveat": "Context alone cannot promote an escalation warning."
    }
    return result
