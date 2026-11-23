"""Historical real-source evaluation boundaries, with mocked official Content API."""
import datetime as dt
import json
from pathlib import Path
import unittest

from scripts.cairn_historical_original_source_eval import evaluate, select

SEEDS=json.loads((Path(__file__).resolve().parents[1] /
                  "data/govuk_source_seed_manifest.json").read_text())


class HistoricalOriginalDocumentTests(unittest.TestCase):
    def test_stratified_selection_is_bounded_and_distinct(self):
        chosen=select(SEEDS,limit=12)
        self.assertEqual(len(chosen),12)
        self.assertEqual(len({s["id"] for s in chosen}),12)
        self.assertIn("incident_candidate",{s["sampling_stratum"] for s in chosen})
        self.assertIn("operational_context",{s["sampling_stratum"] for s in chosen})
        with self.assertRaises(ValueError):
            select(SEEDS,limit=70)

    def test_source_narrative_action_place_not_event_site_truth(self):
        # This mock response tests parsing/provenance only, not historical truth.
        seed=select(SEEDS,limit=1)[0]
        path=seed["url"].replace("https://www.gov.uk","")
        body="<p>" + ("Officials stated that a vessel was attacked in the Red Sea. "
                      "The authority is investigating the unconfirmed details. ")*5+"</p>"
        def fake_fetch(p):
            self.assertEqual(p,path)
            return {"base_path":path,
                    "content_id":"24a58b06-745f-416e-966c-c1befdd6484f",
                    "details":{"body":body},"title":"Official maritime statement",
                    "first_published_at":"2024-01-11T16:00:00Z"}
        r=evaluate({**SEEDS,"seeds":[seed]},limit=1,fetch=fake_fetch,
                   at=dt.datetime(2026,11,23,12,tzinfo=dt.timezone.utc))
        self.assertEqual(r["real_original_documents_requested"],1)
        self.assertEqual(r["real_original_documents_inspected"],1)
        self.assertEqual(r["real_original_documents_with_named_action_locality"],1)
        self.assertEqual(r["reports"][0]["named_locality_from_source_text"],"Red Sea")
        self.assertFalse(r["reports"][0]["reported_site_verified"])
        self.assertIsNone(r["incident_geo_precision_against_verified_sites"])
        self.assertIsNone(r["warning_detection_recall"])
        self.assertNotIn(body,json.dumps(r))

    def test_official_source_block_or_no_rights_abstains(self):
        seed=select(SEEDS,limit=1)[0]
        def blocked(p):
            raise TimeoutError("unavailable")
        r=evaluate({**SEEDS,"seeds":[seed]},limit=1,fetch=blocked)
        self.assertEqual(r["real_original_documents_inspected"],0)
        self.assertEqual(r["unavailable_original_document_reasons"]["TimeoutError"],1)
        self.assertIsNone(r["false_positive_rate"])

    def test_original_article_cannot_postdate_inspection(self):
        seed=select(SEEDS,limit=1)[0]
        path=seed["url"].replace("https://www.gov.uk","")
        body="<p>" + ("Official report confirms the naval vessel entered the Red Sea. ")*6+"</p>"
        def future(p):
            return {"base_path":path,
                    "content_id":"24a58b06-745f-416e-966c-c1befdd6484f",
                    "details":{"body":body},"title":"Future claim",
                    "first_published_at":"2027-02-10T00:00:00Z"}
        r=evaluate({**SEEDS,"seeds":[seed]},limit=1,fetch=future,
                   at=dt.datetime(2026,11,23,tzinfo=dt.timezone.utc))
        self.assertEqual(r["real_original_documents_inspected"],0)
        self.assertEqual(r["reports"][0]["geo_status"],"original_source_unavailable")


if __name__=="__main__":
    unittest.main()
