"""Public Atlas projection of unreviewed report links and same-source dedup."""
import json
from pathlib import Path
import tempfile
import unittest
from behavioral_event_resolution import build
from dashboard.behavioral_embed import embed
from tests.test_behavioral_event_resolution import row,TITLE1,TITLE2


class ReportProjectionTests(unittest.TestCase):
    def source(self):
        ny=row("ny",TITLE1,provider="nydesk",reporting_origin="New York")
        ky=row("ky",TITLE2,provider="kyivdesk",reporting_origin="Kyiv")
        matching=build({"ny":ny,"ky":ky})
        return {
            "schema":"aiba.behavioral-convergence-shadow.v1",
            "generated_at":"2026-11-13T13:00:00Z",
            "review_groups":[],"review_groups_count_total":0,
            "new_single_source_leads":[],"new_single_source_count_total":0,
            "report_relationships":matching,
            "collection_coverage":{"commercial":{
                "status":"current","missingness":"provider_bounded_not_exhaustive"}},
            "approved_warning_count":0,"automated_severity_changes":0,
            "forecast_probability":None,"prediction_horizon":None,
        }
    def published(self,obj):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);(site/"behavior").mkdir()
            (site/"behavior"/"behavioral_fusion.json").write_text(json.dumps(obj))
            return embed(site)
    def test_possible_same_event_is_not_a_confirmed_case(self):
        data=self.published(self.source())
        self.assertEqual(data["status"],"read_only_shadow_evidence")
        self.assertEqual(data["report_relationships"]["possible_same_event_count_total"],1)
        g=data["report_relationships"]["candidate_groups"][0]
        self.assertEqual(g["status"],"possible_same_event_unreviewed")
        self.assertFalse(g["independent_corroboration_established"])
        self.assertFalse(g["warning_level_change"])
        self.assertFalse(data["map_coordinates_inferred"])
        origins={v["reporting_origin"] for v in g["source_reports"]}
        self.assertEqual(origins,{"New York","Kyiv"})
    def test_untrusted_report_title_safely_passes_as_text_not_html(self):
        raw=self.source()
        raw["report_relationships"]["candidate_groups"][0]["source_reports"][0]["title"]="<img onerror=alert(1)>"
        data=self.published(raw)
        self.assertEqual(data["report_relationships"]["candidate_groups"][0]["source_reports"][0]["title"],
                         "<img onerror=alert(1)>")
        self.assertFalse(data["map_coordinates_inferred"])
    def test_false_independence_or_promotion_rejected(self):
        for field,value in (("independent_corroboration_established",True),
                            ("warning_level_change",True),
                            ("reporting_origin_used_as_event_site",True)):
            with self.subTest(field=field):
                raw=self.source()
                raw["report_relationships"]["candidate_groups"][0][field]=value
                self.assertEqual(self.published(raw)["status"],"unavailable")
    def test_unsupported_report_relation_schema_rejected(self):
        raw=self.source();raw["report_relationships"]["schema"]="aiba.forecast-warning.v9"
        self.assertEqual(self.published(raw)["status"],"unavailable")
    def test_past_snapshots_without_relation_field_still_work(self):
        raw=self.source();del raw["report_relationships"]
        data=self.published(raw)
        self.assertEqual(data["status"],"read_only_shadow_evidence")
        self.assertIsNone(data["report_relationships"])

if __name__=="__main__":
    unittest.main()
