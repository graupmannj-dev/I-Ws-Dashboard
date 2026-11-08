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
assert "id=\"globe\"" in html and 'id="timeCursor"' in html
assert 'id="layerCommands"' in html and 'id="severityControls"' in html
assert 'id="layerReports"' in html
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
