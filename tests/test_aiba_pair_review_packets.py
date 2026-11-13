import unittest

from scripts.aiba_pair_review_packets import generate


def report(rid, text, split="heldout", stratum="incident_candidate", episode=None):
    return {
        "id": rid, "source_url": f"https://www.gov.uk/government/news/sample-{rid}",
        "source_family": "official_media",
        "story_lineage_id": "govuk-content:" + rid,
        "evaluation_group_id": episode or "govuk-episode:" + rid,
        "split": split, "sampling_stratum": stratum,
        "source_text": text, "title": text,
        "rights_basis": "licensed_for_internal_evaluation",
        "rights_note": "GOV.UK government text under Open Government Licence v3",
        "retrieved_at": "2026-11-13T12:00:00Z",
        "source_published_at": "2025-04-30T12:00:00Z",
    }


class PairPacketTests(unittest.TestCase):
    def test_same_incident_pair_is_nominated_but_not_human_labeled(self):
        rows = [
            report("a", "Royal Air Force Typhoons struck two buildings near Sanaa."),
            report("b", "Royal Air Force Typhoons struck two buildings near Sanaa."),
            report("c", "Ministry announced defence housing improvements.",
                   stratum="nonincident_control"),
        ]
        packets, audit = generate(rows, 5)
        self.assertEqual(packets["A"][0]["annotator_id"], "A")
        self.assertTrue(packets["B"])
        self.assertGreaterEqual(audit["selected_pair_count"], 2)
        self.assertEqual(audit["human_ground_truth_completed"], 0)
        self.assertEqual(audit["automatic_event_merges"], 0)
        for p in packets["A"]:
            self.assertIsNone(p["label"])
            self.assertNotIn("prediction", str(p))
            self.assertNotIn("episode_hint", str(p))
            self.assertEqual(p["a"]["source_url"].split("/")[2], "www.gov.uk")

    def test_cross_split_pair_never_generated(self):
        rows = [
            report("a", "RAF Typhoons struck two buildings near Sanaa.", "development"),
            report("b", "Royal Navy units deployed to the Red Sea.", "heldout"),
        ]
        packets, audit = generate(rows, 5)
        self.assertEqual(audit["selected_pair_count"], 0)
        self.assertEqual(packets["A"], [])

    def test_output_is_deterministic(self):
        rows = [
            report("a", "Royal Air Force Typhoons struck two buildings near Sanaa."),
            report("b", "Royal Air Force Typhoons struck two buildings near Sanaa."),
            report("c", "A government review announced new conditions for the armed forces."),
        ]
        self.assertEqual(generate(rows, 3), generate(rows, 3))

    def test_batch_limit_no_silent_truncation(self):
        rows = [report(f"r{i}", f"Nonincident government statement number {i} for public evaluation.")
                for i in range(251)]
        with self.assertRaisesRegex(ValueError, "source cap"):
            generate(rows, 10)

    def test_invalid_pair_limit(self):
        with self.assertRaisesRegex(ValueError, "pair cap"):
            generate([report("a", "A government official issued a statement about the policy.")], 121)


if __name__ == "__main__":
    unittest.main()
