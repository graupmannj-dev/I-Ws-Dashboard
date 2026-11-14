import unittest

from scripts.aiba_action_sentence_retrieval import retrieve, build, MAX_REPORTS


def doc(rid, text, split="development", group=None):
    return {
        "id": rid,
        "source_url": "https://www.gov.uk/government/news/source-" + rid,
        "source_family": "official_media",
        "source_text": text,
        "story_lineage_id": "govuk-content:" + rid,
        "evaluation_group_id": group or "govuk-episode:" + rid,
        "split": split,
        "sampling_stratum": "incident_candidate",
        "rights_basis": "licensed_for_internal_evaluation",
        "retrieved_at": "2026-11-13T12:00:00Z",
        "title": "Government report " + rid,
    }


class ActionSentenceRetrievalTests(unittest.TestCase):
    def test_passive_claim_retains_evidence_but_does_not_infer_actor(self):
        text = "A number of buildings involved in drone operations were targeted by aircraft."
        result = retrieve(doc("a", text))
        self.assertEqual(result["candidate_count"], 1)
        c = result["candidates"][0]
        self.assertEqual(text[c["evidence_span"]["start"]:c["evidence_span"]["end"]],
                         c["evidence_span"]["text"])
        self.assertFalse(c["actor_attributed"])
        self.assertFalse(c["event_occurrence_verified"])
        self.assertFalse(c["warning_level_change"])

    def test_future_and_negated_are_caveated_not_silently_real(self):
        text = "UK forces will strike a facility tomorrow. UK forces did not attack the harbour."
        result = retrieve(doc("b", text))
        self.assertEqual(result["candidate_count"], 2)
        self.assertIn("future_conditional_or_planned_language",
                      result["candidates"][0]["modality_flags"])
        self.assertIn("negated_or_contested_language",
                      result["candidates"][1]["modality_flags"])

    def test_training_kept_separate_from_hostile_action(self):
        result = retrieve(doc("c", "RAF laser batteries shot down drones during trials."))
        self.assertEqual(result["candidate_count"], 1)
        self.assertIn("exercise_training_or_test_context",
                      result["candidates"][0]["modality_flags"])

    def test_nonincident_without_action_abstains(self):
        result = retrieve(doc("d", "The department announced a new military housing programme."))
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["candidate_count"], 0)

    def test_only_dev_by_default(self):
        reports = [
            doc("dev", "RAF Typhoons struck buildings near Sanaa."),
            doc("held", "Royal Navy intercepted a drone from the coast.", split="heldout"),
        ]
        result = build(reports)
        self.assertEqual(result["evaluation_split"], "development_only")
        self.assertEqual(result["report_count"], 1)
        self.assertEqual(len(result["reports"]), 1)
        self.assertEqual(result["candidate_sentence_count"], 1)
        self.assertFalse(result["warning_level_change"])
        explicit = build(reports, only_development=False)
        self.assertEqual(explicit["report_count"], 2)

    def test_multiple_sentences_offsets_exact(self):
        text = "Background only. Our aircraft attacked a distant battery. Some naval forces intercepted a missile."
        result = retrieve(doc("offset", text))
        self.assertEqual(result["candidate_count"], 2)
        self.assertGreater(result["candidates"][1]["evidence_span"]["start"],
                           result["candidates"][0]["evidence_span"]["start"])

    def test_source_text_missing_abstains(self):
        row = doc("e", "Some text")
        row.pop("source_text")
        result = retrieve(row)
        self.assertEqual(result["reason"], "source_body_unavailable")

    def test_bounded_source_batch(self):
        docs = [doc("r"+str(i), "RAF Typhoons struck buildings.") for i in range(MAX_REPORTS+1)]
        with self.assertRaisesRegex(ValueError, "report cap"):
            build(docs)


if __name__ == "__main__":
    unittest.main()
