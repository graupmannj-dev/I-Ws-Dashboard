import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from ops_pipeline import UTC
from publication_context import decorate, matching_bilateral_id
from decision_render import attach
from ops_pipeline import write_json

class PublicationContextTests(unittest.TestCase):
    def test_exact_actor_pair_not_one_shared_country(self):
        self.assertTrue(matching_bilateral_id("horn_ethiopia_eritrea", "gdelt_BILAT_ERI_ETH"))
        self.assertFalse(matching_bilateral_id("horn_ethiopia_eritrea", "gdelt_BILAT_ETH_SUD"))
        self.assertFalse(matching_bilateral_id("iran_gulf", "gdelt_BILAT_IRN_PAK"))
        self.assertTrue(matching_bilateral_id("iran_gulf", "gdelt_BILAT_IRN_USA"))
        self.assertFalse(matching_bilateral_id("russia_nato", "gdelt_BILAT_RUS_UKR"))

    def test_daily_signals_are_context_not_verified_warning(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            write_json(root/"hotspots.json",{"asof":"2026-11-06",
                "data_completeness":{"recent_days":7,"baseline_days":28},
                "hotspots":[{"id":"gdelt_BILAT_ERI_ETH","scope":"Algorithmic lead",
                             "name":"Eritrea–Ethiopia","asof":"2026-11-06",
                             "metrics":{"ratio":3.5,"recent":48}},
                            {"id":"gdelt_BILAT_ETH_SUD","scope":"Algorithmic lead",
                             "name":"Ethiopia–Sudan","asof":"2026-11-06",
                             "metrics":{"ratio":2.1,"recent":22}}]})
            write_json(root/"collection_status.json",{"wikipedia":{
                "requested_through":"2026-11-06",
                "results":{"recent_flags":[{"name":"Eritrea","date":"2026-11-06",
                                            "robust_z":4,"source":"https://en.wikipedia.org/wiki/Eritrea"}]},
                "completeness":{"success":15,"attempted":15}}})
            base={"new_change_count":0,"cases":[
                {"id":"horn_ethiopia_eritrea","title":"Ethiopia Eritrea","source_evidence":[]},
                {"id":"horn_ethiopia_sudan","title":"Ethiopia Sudan","source_evidence":[]}]}
            out=decorate(base,root)
            er=next(x for x in out["cases"] if x["id"]=="horn_ethiopia_eritrea")
            su=next(x for x in out["cases"] if x["id"]=="horn_ethiopia_sudan")
            self.assertEqual(len(er["daily_context"]["gdelt_anomalies"]),1)
            self.assertEqual(len(er["daily_context"]["wikipedia_flags"]),1)
            self.assertEqual(len(su["daily_context"]["gdelt_anomalies"]),1)
            self.assertEqual(len(su["daily_context"]["wikipedia_flags"]),0)
            self.assertEqual(out["new_change_count"],0)
            self.assertIn("SAME", er["daily_context"]["interpretation"])

    def test_render_works_with_missing_decision_briefs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"ops").mkdir()
            (root/"ops"/"index.html").write_text(
                '<html><head><style></style></head><body><div class="cards"></div></body></html>')
            result=attach(root/"data", root, clock=lambda:dt.datetime(2026,11,7,21,0,tzinfo=UTC))
            output=(root/"ops"/"index.html").read_text()
            self.assertIn("Scenario synthesis is unavailable",output)
            self.assertEqual(result["case_count"],0)
            self.assertIn('id="aiba-decision"',output)

if __name__=="__main__": unittest.main()
