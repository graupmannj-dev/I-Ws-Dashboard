"""CAIRN source geography: literal jurisdiction, not inferred full-coverage pins."""
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.source_coverage import SCHEMA, CATALOG, build
from dashboard.build_atlas import generate

def registry():
    return {"source_health":{
      "bmkg_quake":{"status":"current_partial","checked_at":"2026-11-20T18:00:00Z"},
      "sg_mpa":{"status":"current_partial","checked_at":"2026-11-20T17:00:00Z"},
      "usgs":{"status":"current","checked_at":"2026-11-20T18:00:00Z"},
      "wiki_edits":{"status":"current_partial","checked_at":"2026-11-20T18:00:00Z"},
      "imd_in":{"status":"current_partial","checked_at":"2026-11-20T18:00:00Z"},
      "saws_za":{"status":"stale_or_unavailable","checked_at":"2026-11-20T12:00:00Z"}},
      "snapshot_counts_by_mode":{"bmkg_quake":15,"sg_mpa":80,"usgs":0,
        "wiki_edits":14,"imd_in":0,"saws_za":999}}

class CoverageTests(unittest.TestCase):
    def test_jurisdictions_do_not_infer_global_country_coverage(self):
        result=build(registry(),generated_at="2026-11-20T18:10:00Z")
        self.assertEqual(result["schema"],SCHEMA)
        self.assertGreaterEqual(result["source_modes_total"],25)
        sources={r["mode"]:r for r in result["sources"]}
        self.assertEqual(sources["bmkg_quake"]["declared_country_jurisdictions"],["ID"])
        self.assertEqual(sources["sg_mpa"]["declared_country_jurisdictions"],["SG"])
        self.assertEqual(sources["inmet_br"]["declared_country_jurisdictions"],["BR"])
        self.assertEqual(sources["imd_in"]["declared_country_jurisdictions"],["IN"])
        self.assertEqual(sources["saws_za"]["declared_country_jurisdictions"],["ZA"])
        self.assertEqual(sources["wiki_edits"]["declared_country_jurisdictions"],[])
        self.assertEqual(sources["usgs"]["declared_country_jurisdictions"],[])
        self.assertEqual(sources["ripe"]["coverage_class"],"global_unlocated")
        self.assertEqual(sources["usgs"]["coverage_class"],"global_bounded")
        self.assertTrue(all(not r["country_coverage_verified"]
                            for r in result["country_jurisdictions"]))
        self.assertTrue(all(not r["supports_absence_of_threat_inference"]
                            for r in result["sources"]))

    def test_missing_data_and_bounded_zero_never_become_negative_evidence(self):
        x={r["mode"]:r for r in build(registry())["sources"]}
        self.assertEqual(x["usgs"]["recent_source_records"],0)
        self.assertEqual(x["usgs"]["visibility"],"bounded_sample_zero_not_global_all_clear")
        self.assertEqual(x["imd_in"]["visibility"],"bounded_sample_zero_not_global_all_clear")
        self.assertIsNone(x["saws_za"]["recent_source_records"])
        self.assertEqual(x["saws_za"]["visibility"],"missing_or_stale_not_measured")
        self.assertIsNone(x["nga"]["recent_source_records"])
        self.assertEqual(x["nga"]["publisher_health"],"not_measured")
        self.assertFalse(x["sg_mpa"]["has_event_site_coordinates"])

    def test_unfamiliar_source_fails_descriptive_open_not_coverage_claim(self):
        cfg={"source_health":{"new_private_feed":{"status":"current","checked_at":"2026-11-20T18:00:00Z"}},
             "snapshot_counts_by_mode":{"new_private_feed":41}}
        row=next(r for r in build(cfg)["sources"] if r["mode"]=="new_private_feed")
        self.assertEqual(row["coverage_class"],"unknown")
        self.assertIsNone(row["issuer_origin"])
        self.assertEqual(row["declared_country_jurisdictions"],[])
        self.assertTrue(row["scope_declared_not_completeness"])

    def test_build_atlas_deploys_readonly_coverage_browser_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)/"site";site.mkdir()
            (site/"hotspots.json").write_text(json.dumps({"asof":"2026-11-20"}))
            output=generate(site,generated="2026-11-20T18:00:00Z")
            self.assertEqual(output["source_coverage"]["url"],"coverage.html")
            self.assertTrue((site/"coverage.html").is_file())
            self.assertTrue((site/"dashboard"/"coverage.css").is_file())
            self.assertTrue((site/"dashboard"/"coverage.js").is_file())
            data=json.loads((site/"coverage.json").read_text())
            self.assertEqual(data["schema"],SCHEMA)
            self.assertEqual(data["currently_checked_modes"],0)
            self.assertIn("wiki_edits",data["unknown_or_unlocated_global_modes"])

if __name__=="__main__":unittest.main()
