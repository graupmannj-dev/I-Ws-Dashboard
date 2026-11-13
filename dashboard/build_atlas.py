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

try:
    from .analyst_intake import load_history as load_analyst_history
    from .feed_history import source_reports
except ImportError:  # Direct CLI invocation: python dashboard/build_atlas.py
    from analyst_intake import load_history as load_analyst_history
    from feed_history import source_reports

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

def generate(site, generated=None, state_dir=None):
    site = Path(site)
    current = read(site / "hotspots.json", {})
    records = read(ROOT / "data/verified_hotspots.json", [])
    decision = read(site / "ops" / "decision_briefs.json", {})
    decision_by_id = {item["id"]: item for item in decision.get("cases", [])}
    collected = read(site / "collection_status.json", {})
    friction = read(site / "friction_briefs.json", {})
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
    if render_time.tzinfo is None:
        render_time = render_time.replace(tzinfo=dt.timezone.utc)
    state_dir = Path(state_dir) if state_dir else None
    analyst = (load_analyst_history(state_dir, clock=render_time) if state_dir else
               {"records": [], "status": "not_connected", "run_count": 0,
                "distinct_observations": 0, "latest_collected_at": None})
    by_case = defaultdict(list)
    unlocated_analyst = []
    for item in analyst["records"]:
        if item["case_id"] in ANCHORS:
            by_case[item["case_id"]].append(item)
        else:
            unlocated_analyst.append({
                "id": item["observation_id"], "case_id": item["case_id"],
                "title": item["title"], "summary": item["summary"],
                "published_at": item["published_at"], "source_url": item["source_url"],
                "confidence": item["confidence"], "classification": "Unreviewed OSINT lead",
            })
    feed_reports, feed_stats = (source_reports(
        state_dir, read(ROOT / "data/decision_registry.json", {}), render_time)
        if state_dir else ([], {}))

    def is_recent_lead(item):
        # A reissued old story does not pulse. Source dates and first intake
        # clocks are independent, and both must be recent.
        if not item["published_at"]:
            return False
        first_seen = dt.datetime.fromisoformat(item["first_collected_at"])
        published = dt.date.fromisoformat(item["published_at"])
        return (dt.timedelta(0) <= render_time - first_seen <= dt.timedelta(hours=36)
                and dt.timedelta(0) <= render_time.date() - published <= dt.timedelta(days=7))

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
        fresh_leads = [r for r in by_case[case_id] if is_recent_lead(r)]
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
            "new_analyst_lead": bool(fresh_leads),
            "new_analyst_lead_count": len(fresh_leads),
            "new_analyst_lead_summary": fresh_leads[-1]["summary"] if fresh_leads else None,
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
    # Append source-dated history without treating ordinary polls as new
    # case-specific changes or evidence of verified commercial behavior.
    for item in feed_reports:
        if item["hotspot_id"] not in ANCHORS:
            continue
        lat, lon, _ = ANCHORS[item["hotspot_id"]]
        reports.append({**item, "lat": lat, "lon": lon})
    for item in analyst["records"]:
        if item["case_id"] not in ANCHORS or not item["published_at"]:
            continue
        lat, lon, _ = ANCHORS[item["case_id"]]
        reports.append({
            "id": "analyst:" + item["observation_id"],
            "hotspot_id": item["case_id"], "lat": lat, "lon": lon,
            "date": item["published_at"],
            "category": "Unreviewed analyst lead: " + item["evidence_class"].replace("_", " "),
            "title": item["title"], "assessment": "OSINT intake; not independently reverified",
            "detail": item["summary"], "source": item["publisher"],
            "url": item["source_url"], "root": item["information_root"],
            "location_precision": "Theater-associated source; no incident-point geolocation.",
            "confidence": item["confidence"],
            "independently_confirmed": item["independently_confirmed"],
            "collected_at": item["first_collected_at"],
        })
    # The source-separated behavioral engine already publishes a verified,
    # capped shadow-feed snapshot under /behavior/. Embed its bounded public
    # summary in the SAME Atlas without promoting any threat label.
    try:
        from dashboard.behavioral_embed import embed as embedded_behavior
    except ModuleNotFoundError:
        from behavioral_embed import embed as embedded_behavior
    behavioral = embedded_behavior(site)
    # Stable IDs keep repeat collections from multiplying a report.
    reports = sorted({r["id"]: r for r in reports}.values(),
                     key=lambda v: (v["date"], v["id"]))[-MAX_POINTS:]
    # Data source may nominate country-pair anomalies but without location
    # coordinates. They are surfaced as a count, never plotted in fake places.
    provisional = [v for v in current.get("hotspots", [])
                   if v.get("scope") == "Algorithmic lead"]
    dates = sorted({r["date"] for r in reports} | {asof})
    payload = {
        "version": 1, "generated_at": now, "asof": asof,
        "layer_feed": {"url": os.environ.get("AIBA_LAYER_FEED_URL", "layers.json"),
                       "live_url": "https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/latest/live_layers.json"},
        "title": "AIBA Global Early Warning",
        "hotspots": hotspots, "reports": reports, "report_dates": dates,
        "friction_briefs": friction,
        "behavioral_discovery": behavioral,
        "behavior_live_url": "https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/latest/behavioral_fusion.json",
        "friction_live_url": "https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/latest/friction_briefs.json",
        "algorithmic_unlocated_count": len(provisional),
        "discovery_leads": [{
            "id": x.get("id"), "title": x.get("name"),
            "summary": x.get("summary"), "date": safe_date(x.get("asof")),
            "classification": "Unverified media-coded anomaly",
        } for x in provisional[:25]],
        "unlocated_analyst_leads": unlocated_analyst[-25:],
        "algorithmic_caveat": "Media-coded actor-pair anomalies without incident coordinates are not plotted.",
        "collection_summary": current.get("collection_summary", "No GDELT collection status available"),
        "status": {
            "gdelt": collected.get("gdelt", {}),
            "wikipedia": (collected.get("wikipedia") or {}).get("status"),
            "decision_asof": decision.get("generated_at"),
            "decision_changed_cases": decision.get("new_change_count", 0),
            "operational_feeds": read(site / "ops" / "status.json", {}).get("sources", {}),
            "operational_history": feed_stats,
            "analyst_intake": {key: value for key, value in analyst.items() if key != "records"},
            "friction_generated_at": friction.get("generated_at"),
            "friction_shadow_mode": True,
            "curated_source_age": "Original dated dossiers; not reverified by this publication"
        },
        "geographic_notice": ("All colored markers are approximate theater anchors, not GPS incident locations. "
                              "Grey reporting points share those theater locations because sources provide no precise coordinates. "
                              "Combatant-command reference overlays are schematic geographic orientation, NOT official AOR boundaries."),
        "time_notice": ("Timeline filters the publication dates of available source observations. "
                        "Current hotspot severity labels are NOT reconstructed historical states."),
        "pulses_notice": ("Pulses distinguish fresh source-specific fusion evidence and recently ingested "
                          "unreviewed OSINT leads; neither automatically changes standing severity "
                          "or establishes independently verified military escalation.")
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
    parser.add_argument("--state", type=Path,
                        help="Validated durable observations (aiba-feed-data/observations)")
    args = parser.parse_args()
    data = generate(args.site, state_dir=args.state)
    print(f"Atlas: {len(data['hotspots'])} watchspots, {len(data['reports'])} dated sourced observations; "
          f"{data['algorithmic_unlocated_count']} unplotted GDELT location-unknown leads.")

if __name__ == "__main__":
    main()
