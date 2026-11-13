import copy
import unittest

from scripts.aiba_source_text_intake import ingest
from scripts.aiba_dvids_asset_adapter import convert
from scripts.aiba_extracted_claim_graph import build, evaluate_pair
from behavioral_claim_extraction import extract_report

STAMP = "2026-11-13T12:00:00Z"


def doc(ident, body, lineage=None):
    return {
        "id": ident, "source_url": f"https://publisher.example.org/news/{ident}",
        "source_family": "commercial_media", "source_text": body,
        "retrieved_at": STAMP, "rights_basis": "permission_granted",
        "rights_note": "Publisher supplied documented authorization for evaluation",
        "content_type": "source_excerpt", "story_lineage_id": lineage or ident,
        "title": body, "source_published_at": STAMP
    }


class SourceTextAndGraphTests(unittest.TestCase):
    def test_rights_gate_and_frozen_split(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        b = doc("b", "Russian missiles struck Kyiv energy station.", lineage="a")
        rows, manifest, receipt = ingest([a, b])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["split"], rows[1]["split"])
        self.assertEqual(receipt["record_count"], 2)
        self.assertFalse(receipt["rights_verified_by_software"])
        repeat, frozen, _ = ingest([a, b], manifest)
        self.assertEqual(repeat[0]["split"], rows[0]["split"])
        self.assertEqual(manifest, frozen)

    def test_no_unattested_copyright(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        a.pop("rights_note")
        with self.assertRaisesRegex(ValueError, "rights_note"):
            ingest([a])

    def test_explicit_split_conflict_fails(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        rows, manifest, _ = ingest([a])
        a["split"] = "heldout" if rows[0]["split"] == "development" else "development"
        with self.assertRaisesRegex(ValueError, "conflicts with frozen"):
            ingest([a], manifest)

    def test_repeated_article_url_rejected(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        b = doc("b", "Russian missiles struck Kyiv energy station.")
        b["source_url"] = a["source_url"]
        with self.assertRaisesRegex(ValueError, "duplicate document"):
            ingest([a, b])

    def test_graph_nomination_and_geo_separation(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        b = doc("b", "Russian missiles struck Kyiv energy station.")
        rows, _, _ = ingest([a, b], {"lineage_splits": {"a": "development", "b": "development"}})
        graph = build(rows)
        self.assertEqual(graph["candidate_count_total"], 1)
        pair = graph["candidates"][0]
        self.assertEqual(pair["category"], "possible_same_event_claims_unreviewed")
        self.assertFalse(pair["independent_corroboration_established"])
        self.assertEqual(graph["automatic_event_merges"], 0)
        self.assertEqual(graph["automatic_alerts_created"], 0)

        a_site = {"role": "reported_event_site", "basis": "source_declared", "lat": 50.45, "lon": 30.52}
        b_site = {"role": "reported_event_site", "basis": "source_declared", "lat": 46.48, "lon": 30.73}
        a["reported_event_location"], b["reported_event_location"] = a_site, b_site
        rows, _, _ = ingest([a, b], {"lineage_splits": {"a": "development", "b": "development"}})
        self.assertEqual(build(rows)["candidates"][0]["category"],
                         "related_claims_conflicting_event_sites")

    def test_declared_time_conflict(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        b = doc("b", "Russian missiles struck Kyiv energy station.")
        a["event_at"] = "2026-11-01T12:00:00Z"
        b["event_at"] = "2026-11-12T12:00:00Z"
        rows, _, _ = ingest([a, b], {"lineage_splits": {"a": "development", "b": "development"}})
        self.assertEqual(build(rows)["candidates"][0]["category"],
                         "related_claims_conflicting_event_times")

    def test_distinct_actions_do_not_match(self):
        a = doc("a", "Russian missiles struck Kyiv energy station.")
        b = doc("b", "Russian missiles intercepted Kyiv energy station.")
        rows, _, _ = ingest([a, b], {"lineage_splits": {"a": "development", "b": "development"}})
        self.assertEqual(build(rows)["candidate_count_total"], 0)

    def test_dvids_needs_asset_specific_rights_approval(self):
        asset = {"id": "news:1234567", "type": "news",
                 "url": "https://www.dvidshub.net/news/1234567/dummy-story",
                 "title": "Military announcement",
                 "description": "Unit officials announced the deployment of military personnel overseas in response to training requirements.",
                 "date_published": STAMP, "location": {"city": "New York"}}
        rows, rejects = convert([asset], [], STAMP)
        self.assertEqual(rows, [])
        self.assertEqual(rejects["rights_not_approved"], 1)
        rows, rejects = convert([asset], ["news:1234567"], STAMP)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content_type"], "full_body")
        self.assertNotIn("reported_event_location", rows[0])
        self.assertIsNone(rows[0]["reporting_origin"])
        self.assertEqual(rows[0]["source_credit"], None)
        self.assertFalse(rejects)

    def test_dvids_wrong_url_id_rejected(self):
        asset = {"id": "news:1234567", "type": "news",
                 "url": "https://www.dvidshub.net/news/9876543/dummy-story",
                 "description": "A long enough news description for the controlled asset ingestion evaluation."}
        rows, errors = convert([asset], ["news:1234567"], STAMP)
        self.assertEqual(rows, [])
        self.assertEqual(errors["url_id_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
