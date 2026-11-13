#!/usr/bin/env python3
"""Validate the globe front end, source chronology, and inherited classic view."""
from pathlib import Path
import json
import sys

site=Path(sys.argv[1])
atlas=json.loads((site/"atlas.json").read_text(encoding="utf-8"))
geo=json.loads((site/"dashboard"/"countries.geojson").read_text(encoding="utf-8"))
html=(site/"index.html").read_text(encoding="utf-8")
classic=(site/"classic.html").read_text(encoding="utf-8")
assert atlas["hotspots"] and atlas["reports"], "Missing source-linked data"
assert geo["type"]=="FeatureCollection" and len(geo["features"])>=150
assert "id=\"globe\"" in html and 'id="timeStart"' in html and 'id="timeEnd"' in html
assert 'id="timeSelection"' in html and 'id="discoveryDrawer"' in html
assert 'id="discoveryToggle"' in html and 'id="zoomLevel"' in html
assert 'id="layerCommands"' in html and 'id="severityControls"' in html
assert 'id="layerReports"' in html
assert 'id="frictionBriefing"' in html and 'id="frictionSummary"' in html
assert 'id="frictionExpand"' in html
assert 'id="tabBehavior"' in html and 'id="openBehavior"' in html
assert 'id="tabEvaluation"' in html and 'id="openEvaluation"' in html
assert 'id="watchDetailLink"' in html
assert "warning_evaluation" in atlas, "No embedded warning review status"
evaluation=atlas["warning_evaluation"]
assert evaluation["schema"]=="aiba.atlas-public-evaluation-readiness.v1"
assert evaluation["status"]=="prospective_skill_not_established"
assert evaluation["public_forecast_ledger"]=="not_connected"
assert evaluation["production_warning_updates"] is False
assert evaluation["publication_of_private_ledger"] is False
assert evaluation["claims_of_predictive_skill"] is False
assert all(value is None for value in evaluation["metrics"].values())
assert all(value=="not_connected" for value in evaluation["verification_gates"].values())
assert evaluation["observation"]["worldwide_source_completeness_verified"] is False
assert evaluation["observation"]["unobserved_intervals_are_negative_events"] is False
assert json.loads((site/"evaluation_summary.json").read_text(encoding="utf-8")) == evaluation
assert "behavioral_discovery" in atlas
assert atlas.get("behavior_live_url", "").startswith(
    "https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/latest/behavioral_fusion.json"
)
behavior = atlas["behavioral_discovery"]
assert behavior["schema"] == "aiba.behavioral-convergence-shadow.v1"
assert behavior["status"] in ("read_only_shadow_evidence", "unavailable")
assert behavior["approved_warning_count"] == 0
assert behavior["automated_severity_changes"] == 0
assert behavior["source_continuity_proven"] is False
assert behavior["map_coordinates_inferred"] is False
assert behavior["forecast_probability"] is None
assert len(behavior["review_groups"]) <= 25 and len(behavior["new_single_source_leads"]) <= 50
assert (site/"friction_briefs.json").exists(), "No durable friction briefing fallback"
assert "friction_briefs" in atlas and atlas["friction_briefs"].get("shadow_mode", True)
assert "friction_live_url" in atlas and atlas["friction_live_url"].startswith("https://")
assert "id=\"payload\"" in classic, "Classic watchboard unexpectedly lost"
assert (site/"dashboard"/"atlas.js").stat().st_size>10000
for h in atlas["hotspots"]:
    assert h["severity"] in ("critical","active","high","watch","low")
    assert "Approximate theater" in h["coordinate_precision"]
    assert -90 <= h["lat"] <= 90 and -180 <= h["lon"] <= 180
    if h["new_evidence"]:
        assert h["new_evidence_count"]>0 and h["brief_asof"]
    if h.get("new_analyst_lead"):
        assert h.get("new_analyst_lead_count", 0)>0 and h.get("new_analyst_lead_summary")
for r in atlas["reports"]:
    assert r["date"] and r["hotspot_id"] and "geocod" in r["location_precision"].lower() or (
        r["date"] and r["hotspot_id"] and "location" in r["location_precision"].lower()
    )
    assert not r["url"] or r["url"].startswith("https://")
    if r["id"].startswith("analyst:"):
        assert r["assessment"] == "OSINT intake; not independently reverified"
assert "not official aor boundaries" in atlas["geographic_notice"].lower()
print("Atlas validation passed:",len(atlas["hotspots"]),"theater pins,",
      len(atlas["reports"]),"dated report points,",
      len(geo["features"]),"countries.")
