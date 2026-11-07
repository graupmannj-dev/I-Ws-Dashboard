#!/usr/bin/env python3
"""Publish a globe interface with evidence-grounded locations and timeline.

The deployment consumes the SAME daily hotspot JSON and operational decision
briefs as AIBA's analytical UI, and does not fabricate geocoded incidents or
historical severity labels. Country outlines are vendored separately.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import shutil
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "dashboard"

# Theater anchors, not actual event or source coordinates. Deliberately
# avoid spurious point precision for reports without geocoded incident data.
ANCHORS = {
    "horn_ethiopia_eritrea": (14.4, 39.3, "Northern Ethiopia / Eritrea border"),
    "horn_ethiopia_sudan": (12.8, 36.4, "Ethiopia–Sudan border"),
    "horn_ethiopia_kenya_moyale": (3.53, 39.06, "Moyale border area"),
    "afpak": (34.1, 70.7, "Afghanistan–Pakistan border sector"),
    "drc_rwanda": (-1.6, 29.0, "North Kivu / Rwanda border"),
    "thailand_cambodia": (13.6, 103.2, "Thailand–Cambodia border"),
    "russia_nato": (54.4, 23.2, "Baltic / eastern NATO theater"),
    "iran_gulf": (26.8, 55.6, "Strait of Hormuz / Persian Gulf"),
    "taiwan": (24.0, 121.0, "Taiwan Strait theater"),
    "korea": (38.3, 127.2, "Korean Peninsula theater")
}

# Severity describes EXISTING sourced state only. "Critical" is reserved for
# a specifically reviewed, separately verified critical classification.
# No existing dossier is silently promoted to Critical by UI code.
STATE_MAP = {
    "Active conflict": ("active", "Active conflict"),
    "Escalation watch": ("high", "Escalation watch"),
    "Hybrid warning": ("high", "Hybrid warning"),
    "Fragile ceasefire": ("high", "Fragile ceasefire"),
    "New tension": ("watch", "New tension"),
    "Persistent coercion": ("watch", "Persistent coercion"),
    "Activity watch": ("watch", "Activity watch"),
    "Active displacement / border watch": ("high", "Border / spillover watch")
}
MAX_POINTS = 400

def safe_date(value):
    try:
        if not value:
            return None
        value = str(value)[:10]
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None

def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def sanitize_url(value):
    return value if isinstance(value, str) and value.startswith("https://") else None

def generate(site, generated=None):
    site = Path(site)
    current = read(site / "hotspots.json", {})
    records = read(ROOT / "data/verified_hotspots.json", [])
    decision = read(site / "ops" / "decision_briefs.json", {})
    decision_by_id = {item["id"]: item for item in decision.get("cases", [])}
    collected = read(site / "collection_status.json", {})
    asof = safe_date(current.get("asof")) or (dt.datetime.now(dt.timezone.utc).date().isoformat())
    now = generated or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    # Only a case with a newly recorded case-specific change, not just a
    # successful download, qualifies for the pulse treatment.
    brief_time = None
    try:
        brief_time = dt.datetime.fromisoformat(decision.get("generated_at", "").replace("Z", "+00:00"))
        if brief_time.tzinfo is None:
            brief_time = brief_time.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        pass
    render_time = dt.datetime.fromisoformat(now.replace("Z", "+00:00"))
    fresh_brief = bool(brief_time and dt.timedelta(0) <= render_time - brief_time <= dt.timedelta(hours=36))
    hotspots, reports = [], []
    for dossier in records:
        case_id = dossier.get("id")
        if case_id not in ANCHORS:
            continue
        lat, lon, area = ANCHORS[case_id]
        severity, label = STATE_MAP.get(dossier.get("state"), ("watch", dossier.get("state") or "Watch"))
        brief = decision_by_id.get(case_id, {})
        evidence = brief.get("source_evidence", []) if fresh_brief else []
        # Need an actual observed change from the previous collection, not a
        # standing advisory, today's scrape, or a mere Wikipedia view anomaly.
        updated = bool(evidence)
        hotspots.append({
            "id": case_id, "name": dossier.get("name"), "area": area,
            "lat": lat, "lon": lon, "coordinate_precision": "Approximate theater anchor; NOT incident coordinates",
            "severity": severity, "state": label, "original_state": dossier.get("state"),
            "scope": dossier.get("scope", "Standing watch"),
            "baseline_asof": safe_date(dossier.get("asof")),
            "description": dossier.get("summary", ""),
            "scenario": dossier.get("scenario", ""),
            "analysis": dossier.get("analysis", ""),
            "next": brief.get("what_would_change_assessment") or dossier.get("next", ""),
            "so_what": brief.get("so_what") or dossier.get("analysis", ""),
            "what_changed": brief.get("what_changed") if evidence else None,
            "alternative": brief.get("alternative_explanation") or dossier.get("alternatives", ""),
            "review_status": brief.get("collection_priority", "Curated snapshot"),
            "new_evidence": updated, "new_evidence_count": len(evidence),
            "brief_asof": decision.get("generated_at") if brief else None
        })
        for ix, sig in enumerate(dossier.get("signals", [])):
            day = safe_date(sig.get("date"))
            if not day:
                continue
            reports.append({
                "id": f"{case_id}:{ix}", "hotspot_id": case_id,
                "lat": lat, "lon": lon, "date": day,
                "category": sig.get("category", "Reporting"),
                "title": sig.get("title", "Sourced observation"),
                "assessment": sig.get("assessment", "Reported"),
                "detail": sig.get("details", ""),
                "source": sig.get("source", ""),
                "url": sanitize_url(sig.get("url")),
                "location_precision": "Theater-associated report; no event-point geolocation was supplied.",
                "root": sig.get("root")
            })
        for ix, sig in enumerate(evidence):
            pub = safe_date(sig.get("published_at"))
            # An undated advisory can be new relative to another snapshot but
            # cannot honestly be positioned at a precise source event date.
            if not pub:
                continue
            reports.append({
                "id": f"{case_id}:new:{ix}", "hotspot_id": case_id,
                "lat": lat, "lon": lon, "date": pub,
                "category": sig.get("source_family", "New observed change"),
                "title": sig.get("title", "New evidence"),
                "assessment": "New since prior collection",
                "detail": sig.get("assessment_ceiling", ""),
                "source": sig.get("publisher", ""),
                "url": sanitize_url(sig.get("source_url")),
                "location_precision": "Theater-associated evidence, not a geocoded incident.",
                "root": sig.get("root")
            })
    reports = sorted(reports, key=lambda v: (v["date"],v["id"]))[-MAX_POINTS:]
    # Data source may nominate country-pair anomalies but without location
    # coordinates. They are surfaced as a count, never plotted in fake places.
    provisional = [v for v in current.get("hotspots", [])
                   if v.get("scope") == "Algorithmic lead"]
    dates = sorted({r["date"] for r in reports} | {asof})
    payload = {
        "version": 1, "generated_at": now, "asof": asof,
        "layer_feed": {"url": os.environ.get("AIBA_LAYER_FEED_URL", "layers.json")},
        "title": "AIBA Global Early Warning",
        "hotspots": hotspots, "reports": reports, "report_dates": dates,
        "algorithmic_unlocated_count": len(provisional),
        "algorithmic_caveat": "Media-coded actor-pair anomalies without incident coordinates are not plotted.",
        "collection_summary": current.get("collection_summary", "No GDELT collection status available"),
        "status": {
            "gdelt": collected.get("gdelt", {}),
            "wikipedia": (collected.get("wikipedia") or {}).get("status"),
            "decision_asof": decision.get("generated_at"),
            "decision_changed_cases": decision.get("new_change_count", 0),
            "curated_source_age": "Original dated dossiers; not reverified by this publication"
        },
        "geographic_notice": ("All colored markers are approximate theater anchors, not GPS incident locations. "
                              "Grey reporting points share those theater locations because sources provide no precise coordinates. "
                              "Combatant-command reference overlays are schematic geographic orientation, NOT official AOR boundaries."),
        "time_notice": ("Timeline filters the publication dates of available source observations. "
                        "Current hotspot severity labels are NOT reconstructed historical states."),
        "pulses_notice": ("Pulses indicate a new dated case-specific signal in the latest fusion assessment, "
                          "not proof of critical severity or fresh military escalation.")
    }
    (site / "atlas.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    asset_dir = site / "dashboard"
    asset_dir.mkdir(exist_ok=True)
    for name in ("atlas.css", "atlas.js", "layers.js", "countries.geojson"):
        shutil.copyfile(WEB / name, asset_dir / name)
    if not (site / "layers.json").exists():
        try:
            from dashboard.collect_layers import empty
        except ModuleNotFoundError:
            from collect_layers import empty
        (site / "layers.json").write_text(json.dumps(empty()), encoding="utf-8")
    # Preserve original fully featured watchboard as a linked legacy view.
    prior = site / "index.html"
    if prior.exists():
        (site / "classic.html").write_bytes(prior.read_bytes())
    shutil.copyfile(WEB / "atlas.html", prior)
    return payload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    data = generate(args.site)
    print(f"Atlas: {len(data['hotspots'])} watchspots, {len(data['reports'])} dated sourced observations; "
          f"{data['algorithmic_unlocated_count']} unplotted GDELT location-unknown leads.")

if __name__ == "__main__":
    main()
