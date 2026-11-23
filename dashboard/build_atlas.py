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
    # A separate source-review queue makes accepted evidence discoverable
    # regardless of whether its case is one of the standing map anchors.
    # This is neither a verified event list nor an executive-warning feed.
    queue = []
    for row in analyst["records"]:
        first = dt.datetime.fromisoformat(row["first_collected_at"].replace("Z", "+00:00"))
        pub = safe_date(row.get("published_at"))
        recent = (dt.timedelta(0) <= render_time - first <= dt.timedelta(hours=36)
                  and pub is not None
                  and dt.timedelta(0) <= render_time.date() - dt.date.fromisoformat(pub) <= dt.timedelta(days=7))
        queue.append({
            "id": "analyst:" + row["observation_id"], "title": row["title"],
            "summary": row["summary"], "source_url": sanitize_url(row["source_url"]),
            "publisher": row["publisher"], "source_family": row["evidence_class"],
            "case_id": row["case_id"] if row["case_id"] in ANCHORS else None,
            "case_association": "standing_case" if row["case_id"] in ANCHORS else "unassigned",
            "original_case_hint": row["case_id"],
            "published_at": pub, "first_observed_at": row["first_collected_at"],
            "information_root": row["information_root"], "recent_new": recent,
            "classification": "unreviewed_source_report", "reviewed_warning": False,
        })
    # The operational source chronology is included for search/review, but
    # repeated snapshots are not counted as fresh claims.
    for row in feed_reports:
        queue.append({
            "id": row["id"], "title": row["title"], "summary": row["detail"],
            "source_url": sanitize_url(row["url"]), "publisher": row["source"],
            "source_family": row["category"], "case_id": row["hotspot_id"],
            "case_association": "standing_case", "original_case_hint": row["hotspot_id"],
            "published_at": row["date"], "first_observed_at": None,
            "information_root": row["root"], "recent_new": False,
            "classification": "unreviewed_source_report", "reviewed_warning": False,
        })
    queue.sort(key=lambda x: (x["first_observed_at"] or x["published_at"] or "", x["id"]), reverse=True)
    queue_total = len(queue)
    queue = queue[:200]
    new_queue_count = sum(x["recent_new"] for x in queue)
    for item in queue:
        reasons = ["not_an_analyst_reviewed_warning"]
        if item["case_association"] != "standing_case":
            reasons.append("no_source_verified_map_association")
        if not item["published_at"]:
            reasons.append("missing_source_publication_date")
        if not item["first_observed_at"]:
            reasons.append("first_collection_time_not_in_chronology")
        if not item["recent_new"]:
            reasons.append("not_recent_new_report")
        item["display_targets"] = ["source_queue"]
        if item["case_association"] == "standing_case" and item["published_at"]:
            item["display_targets"].append("dated_map_context")
        item["visibility_reasons"] = reasons

    # The source-separated behavioral engine already publishes a verified,
    # capped shadow-feed snapshot under /behavior/. Embed its bounded public
    # summary in the SAME Atlas without promoting any threat label.
    try:
        from dashboard.behavioral_embed import embed as embedded_behavior
    except ModuleNotFoundError:
        from behavioral_embed import embed as embedded_behavior
    behavioral = embedded_behavior(site)
    # Make the complete publication funnel auditable without treating accepted
    # source mentions, map points, or source counts as confirmed events.
    visibility = behavioral.get("discovery_visibility") or {}
    providers = behavioral.get("collection_coverage") or {}
    visibility_funnel = {
        "schema": "aiba.atlas-visibility-funnel.v1",
        "generated_at": now,
        "source_queue_total_before_cap": queue_total,
        "source_queue_displayed": len(queue),
        "source_queue_truncated": queue_total > len(queue),
        "analyst_intake_accepted": analyst["distinct_observations"],
        "analyst_intake_health": analyst["status"],
        "new_source_reports_for_review": new_queue_count,
        "source_queue_unassigned": sum(x["case_association"] != "standing_case" for x in queue),
        "source_queue_undated": sum(not x["published_at"] for x in queue),
        "source_queue_map_context": sum("dated_map_context" in x["display_targets"] for x in queue),
        "dated_map_reports_total": len(reports),
        "curated_standing_cases": len(hotspots),
        "reviewed_case_changes": sum(bool(x["new_evidence"]) for x in hotspots),
        "behavioral_recent_72h": visibility.get("recent_unique_record_count_72h"),
        "behavioral_missing_geo_72h": visibility.get("recent_unlocated_count_72h"),
        "behavioral_exact_geo_overlaps": visibility.get("shared_exact_geography_keys_across_behavior_families"),
        "behavioral_new_leads": behavioral.get("single_source_count_total"),
        "behavioral_cross_family_leads": behavioral.get("cross_family_count_total"),
        "provider_health": [
            {"name": name, "status": record.get("status", "unknown"),
             "scope": record.get("source_scope", "coverage not established"),
             "asof": record.get("snapshot_at")}
            for name, record in sorted(providers.items()) if isinstance(record, dict)
        ],
        "explanation": "Each counter represents a different processing population. The map is a subset of source-linked geographic context, not all accepted OSINT and not an event truth set.",
        "reviewed_warning_from_source_queue": False,
    }

    # Dynamic candidate families are investigative source records. Unlike
    # the ten legacy curated theaters, they include worldwide and unlocated
    # sources from the source-separated behavioral registry.
    try:
        from dashboard.dynamic_bins import build as build_dynamic_bins
    except ModuleNotFoundError:
        from dynamic_bins import build as build_dynamic_bins
    registry = read(state_dir / "latest" / "behavioral_registry.json", {}) if state_dir else {}
    archive = read(state_dir / "latest" / "family_archive.json", {}) if state_dir else {}
    archive_available = (archive.get("schema") == "aiba.family-archive.v1"
                         and isinstance(archive.get("records"), list))
    # Archive records are persistent across source outages / 45-day index
    # expiry; source health still comes from the current registry snapshot.
    if archive_available:
        durable_registry = {
            "schema": "aiba.behavioral-observations.v1",
            "records": archive["records"],
            "source_health": registry.get("source_health", {}),
            "automatic_topic_index": archive.get("automatic_topic_index"),
        }
        families_links = archive.get("report_relationships")
    else:
        durable_registry = registry
        families_links = behavioral.get("report_relationships")
    dynamic_families = build_dynamic_bins(
        durable_registry, analyst, families_links, now=render_time)
    dynamic_families["archive_status"] = ("durable_bounded_public_index"
        if archive_available else "not_yet_collected")
    dynamic_families["archive_root_count_total"] = (
        archive.get("root_count_total") if archive_available else None)
    dynamic_families["archive_public_truncated"] = (
        archive.get("public_snapshot_truncated") if archive_available else None)
    # Public source geography / missingness ledger. Jurisdictions are NOT
    # assumed geographic coverage; missing source never implies all-clear.
    try:
        from dashboard.source_coverage import build as build_source_coverage
    except ModuleNotFoundError:
        from source_coverage import build as build_source_coverage
    source_coverage = build_source_coverage(registry, generated_at=now)
    (site / "coverage.json").write_text(
        json.dumps(source_coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    # Matched physical history diagnostics; not calibrated conflict forecasts.
    metric_path = state_dir / "latest" / "metric_cohort_baselines.json" if state_dir else None
    metrics = read(metric_path, {}) if metric_path else {}
    if not isinstance(metrics, dict) or metrics.get("schema") != "cairn.metric-cohort-baselines.v1":
        metrics = {"schema": "cairn.metric-cohort-baselines.v1",
                   "status": "metric_history_not_yet_collected",
                   "series": [], "series_total": 0,
                   "series_ready_for_descriptive_deviation": 0,
                   "warnings_approved": 0}
    (site / "metric_baselines.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    # Cross-publisher common event candidates are NOT independent incidents.
    dependency_path = state_dir / "latest" / "source_dependency_audit.json" if state_dir else None
    dependency = read(dependency_path, {}) if dependency_path else {}
    if not isinstance(dependency, dict) or dependency.get("schema") != "cairn.source-dependency-audit.v1":
        dependency = {"schema": "cairn.source-dependency-audit.v1",
                      "comparison_available": False,
                      "candidate_common_event_pairs": [], "ambiguous_pair_candidates": [],
                      "independent_physical_event_count_estimated": None,
                      "approved_corroborations": 0}
    (site / "source_dependency_audit.json").write_text(
        json.dumps(dependency, ensure_ascii=False, indent=2), encoding="utf-8")
    # Hypothesis center: explicit case IDs and reviewer-tagged evidence only.
    # Historical dossier source items are visible, not reverified as live data.
    try:
        from dashboard.hypothesis_evidence import build as build_hypothesis_views
    except ModuleNotFoundError:
        from hypothesis_evidence import build as build_hypothesis_views
    hypothesis_views = build_hypothesis_views(
        records, dynamic_families, registry.get("source_health", {}),
        read(ROOT / "data" / "hypothesis_reviews.json", {}),
        generated_at=now)
    # Post-collection preliminary screening, rerun on each approved Pages
    # publication (including collection-completion workflow_run events).
    # No lexical candidate can alter signed analyst reviews or issue warnings.
    try:
        from dashboard.hypothesis_auto_review import screen as auto_screen
    except ModuleNotFoundError:
        from hypothesis_auto_review import screen as auto_screen
    machine_screen = auto_screen(records, registry, archive, at=render_time)
    hypothesis_views["automated_screen"] = {
        key: value for key, value in machine_screen.items() if key != "cases"}
    gdelt_trends = read(site / "gdelt_case_trends.json", {})
    valid_trends = (gdelt_trends.get("schema") == "cairn.gdelt-case-trends.v1"
                    and isinstance(gdelt_trends.get("cases"), dict))
    hypothesis_views["gdelt_case_status"] = (
        {k: gdelt_trends.get(k) for k in
         ("schema", "status", "asof", "coverage", "window_days", "baseline_days",
          "measured_case_count", "hypothesis_direction_estimated")}
        if valid_trends else {"status": "unavailable_missing_trend_file",
                             "asof": None, "hypothesis_direction_estimated": False})
    for case in hypothesis_views["hypotheses"]:
        case["automated_screen"] = machine_screen["cases"].get(case["id"], {})
        case["gdelt_media_trend"] = (
            gdelt_trends["cases"].get(case["id"]) if valid_trends else None)
    (site / "hypotheses.json").write_text(
        json.dumps(hypothesis_views, ensure_ascii=False, indent=2), encoding="utf-8")
    # Only safe source monitoring context is included publicly. The private
    # forecast ledger, Sigstore subject records and outcome labels stay off
    # GitHub Pages until a separately approved audited aggregate pipeline.
    try:
        from dashboard.evaluation_readiness import write as write_evaluation
    except ModuleNotFoundError:
        from evaluation_readiness import write as write_evaluation
    evaluation = write_evaluation(site, behavioral, generated_at=now)
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
        "title": "CAIRN — Alternative Indicator Early Warning",
        "hotspots": hotspots, "reports": reports, "report_dates": dates,
        "friction_briefs": friction,
        "behavioral_discovery": behavioral,
        "intake_queue": queue,
        "intake_queue_new_count": new_queue_count,
        "visibility_funnel": visibility_funnel,
        "dynamic_bins": dynamic_families,
        "metric_baselines": {"url": "metric_baselines.json",
                             "status": metrics.get("status"),
                             "series_total": len(metrics.get("series", [])),
                             "readiness_count": metrics.get("series_ready_for_descriptive_deviation", 0),
                             "automatic_security_warnings": 0},
        "source_coverage": {"url": "coverage.html",
                           "source_modes_total": source_coverage["source_modes_total"],
                           "recently_checked_modes": source_coverage["currently_checked_modes"]},
        "source_dependency_audit": {"url": "source_dependency_audit.json",
                                    "comparison_available": dependency["comparison_available"],
                                    "potential_common_physical_events": len(dependency["candidate_common_event_pairs"]),
                                    "reviewed_independent_confirmations": 0},
        "hypothesis_views": {"url": "hypotheses.html",
                             "hypothesis_count": hypothesis_views["hypothesis_count"],
                             "reviewed_hypotheses": hypothesis_views["reviewed_hypotheses"]},
        "warning_evaluation": evaluation,
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
    for name in ("atlas.css", "cairn-nav.css", "atlas.js", "layers.js", "countries.geojson",
                 "hypotheses.css", "hypotheses.js",
                 "coverage.css", "coverage.js"):
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
    shutil.copyfile(WEB / "sources.html", site / "sources.html")
    shutil.copyfile(WEB / "hypotheses.html", site / "hypotheses.html")
    shutil.copyfile(WEB / "coverage.html", site / "coverage.html")
    shutil.copyfile(WEB / "source_status.js", asset_dir / "source_status.js")
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
