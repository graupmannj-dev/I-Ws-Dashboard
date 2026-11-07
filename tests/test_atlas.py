"""Interface regression tests: forbid fake severity, locations and timeline dates."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from dashboard.build_atlas import generate, ANCHORS, STATE_MAP

class GlobeBuildTests(unittest.TestCase):
    def test_every_case_anchor_is_approximate_and_mapped_to_real_case(self):
        self.assertEqual(len(ANCHORS), 10)
        self.assertNotIn("Critical", STATE_MAP)
        for lat, lon, area in ANCHORS.values():
            self.assertTrue(-90 <= lat <= 90 and -180 <= lon <= 180 and area)

    def test_build_with_existing_curated_dossiers(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)
            (site/"index.html").write_text("<html>Original source-linked watchboard</html>")
            (site/"hotspots.json").write_text(json.dumps({"asof":"2026-11-06",
                "hotspots":[{"id":"gdelt_BILAT_FOO_BAR","scope":"Algorithmic lead"}],
                "collection_summary":"7/7 recent"}))
            (site/"collection_status.json").write_text('{"gdelt":{"recent_days":7,"baseline_days":28}}')
            result=generate(site,generated="2026-11-07T18:00:00+00:00")
            self.assertEqual(len(result["hotspots"]),10)
            self.assertTrue(result["reports"])
            self.assertEqual(result["algorithmic_unlocated_count"],1)
            self.assertFalse(any(h["severity"]=="critical" for h in result["hotspots"]))
            self.assertFalse(any(h["new_evidence"] for h in result["hotspots"]))
            self.assertTrue(all("Approximate theater" in h["coordinate_precision"] for h in result["hotspots"]))
            self.assertTrue(all("not" in r["location_precision"].lower() or "no" in r["location_precision"].lower() for r in result["reports"]))
            self.assertTrue((site/"classic.html").exists())
            self.assertIn("Original source-linked watchboard",(site/"classic.html").read_text())
            self.assertIn("Global Early Warning",(site/"index.html").read_text())
            self.assertTrue((site/"dashboard"/"countries.geojson").exists())
            self.assertTrue((site/"dashboard"/"atlas.js").exists())
            self.assertEqual(json.loads((site/"atlas.json").read_text())["asof"],"2026-11-06")

    def test_new_assessment_pulses_only_when_brief_is_recent_and_has_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)
            (site/"index.html").write_text("<html>old</html>")
            (site/"hotspots.json").write_text('{"asof":"2026-11-06"}')
            (site/"ops").mkdir()
            (site/"ops"/"decision_briefs.json").write_text(json.dumps({
                "generated_at":"2026-11-07T17:00:00Z",
                "cases":[{"id":"taiwan","collection_priority":"Investigate market repricing",
                          "what_changed":"A defined contract moved",
                          "source_evidence":[{"title":"Taiwan blockade", "published_at":None,
                                             "source_url":"https://example.org/case"}]}]}))
            a=generate(site,generated="2026-11-07T18:00:00+00:00")
            taiwan=next(x for x in a["hotspots"] if x["id"]=="taiwan")
            self.assertTrue(taiwan["new_evidence"])
            self.assertEqual(taiwan["new_evidence_count"],1)
            # Missing publication time cannot be given a fabricated reporting date.
            self.assertFalse(any(r["id"].startswith("taiwan:new") for r in a["reports"]))
            stale=generate(site,generated="2026-11-09T22:00:00+00:00")
            self.assertFalse(next(x for x in stale["hotspots"] if x["id"]=="taiwan")["new_evidence"])

    def test_world_geometry_has_real_country_polygons(self):
        from dashboard.build_atlas import WEB
        geo=json.loads((WEB/"countries.geojson").read_text())
        self.assertGreater(len(geo["features"]),150)
        self.assertTrue(all(f["geometry"]["type"] in ("Polygon","MultiPolygon") for f in geo["features"]))

if __name__=="__main__":
    unittest.main()
