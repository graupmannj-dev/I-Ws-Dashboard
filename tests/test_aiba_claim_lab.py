import unittest

from scripts.aiba_claim_lab import prepare


def source(id, text):
    return {
        "id": id, "source_url": f"https://source.example.net/news/{id}",
        "source_family": "commercial_media", "source_text": text,
        "rights_basis": "permission_granted",
        "rights_note": "Written permission secured for this bounded excerpt",
        "retrieved_at": "2026-11-13T12:00:00Z",
        "story_lineage_id": id, "content_type": "source_excerpt",
    }


class ClaimLabEndToEndTests(unittest.TestCase):
    def test_private_pipeline_claims_graph_two_blind_packets(self):
        rows = [source("a", "Russian missiles struck Kyiv energy station."),
                source("b", "Russian missiles struck Kyiv energy station.")]
        fixed = {"lineage_splits": {"a": "development", "b": "development"}}
        reports, manifest, claims, graph, packets, receipt = prepare(rows, fixed)
        self.assertEqual(receipt["reports"], 2)
        self.assertEqual(claims["candidate_claim_count"], 2)
        self.assertEqual(graph["candidate_count_total"], 1)
        self.assertEqual(receipt["blinded_packets_generated"], 2)
        self.assertFalse(receipt["operational_validation"])
        self.assertEqual(receipt["automatic_alerts_created"], 0)
        self.assertEqual(graph["automatic_event_merges"], 0)
        self.assertEqual(packets["A"][0]["claims"], [])
        self.assertNotIn("predicted", str(packets))
        self.assertEqual(manifest["lineage_splits"], fixed["lineage_splits"])
        self.assertEqual(len(reports[0]["source_text_sha256"]), 64)

    def test_bad_rights_fail_closed(self):
        bad = source("a", "Russian missiles struck Kyiv energy station.")
        bad["rights_basis"] = "just_found_on_web"
        with self.assertRaisesRegex(ValueError, "rights"):
            prepare([bad])

    def test_strict_batch_cap(self):
        data = [source(f"r{i}", "Russian missiles struck Kyiv energy station.")
                for i in range(251)]
        with self.assertRaisesRegex(ValueError, "one claim-lab batch"):
            prepare(data)

if __name__ == "__main__":
    unittest.main()
