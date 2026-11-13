import copy
import unittest

from scripts.aiba_real_report_eval import (
    assignment, score, validate_reports, validate_labels, validate_pairs, review_audit
)

STAMP = "2026-11-13T15:00:00Z"
TEXT1 = "Russian missiles struck Kyiv energy substation overnight."
TEXT2 = "Kyiv energy substation struck overnight by Russian missiles."
TEXT3 = "Insurance markets reviewed quarterly shipping exposures."


def report(rid, text, lineage, split, title=None):
    return {
        "id": rid, "source_url": f"https://publisher.example.net/news/{rid}",
        "source_family": "commercial_media",
        "source_text": text, "story_lineage_id": lineage, "split": split,
        "rights_basis": "permission_granted", "retrieved_at": STAMP,
        "first_observed_at": STAMP, "source_published_at": STAMP,
        "information_root": f"publisher:{rid}", "title": title or text.strip(".")
    }


def gold_claim(text, actor, action, obj):
    return {"actor_text": actor, "action": action, "object_text": obj,
            "assertion_status": "source_asserted_unverified",
            "evidence_span": {"start": 0, "end": len(text), "text": text}}


def fixture():
    reports = [
        report("r1", TEXT1, "story-kyiv-a", "development"),
        report("r2", TEXT2, "story-kyiv-b", "development"),
        report("r3", TEXT3, "story-markets", "heldout"),
    ]
    labels = [
        {"report_id": "r1", "annotator_id": "ADJUDICATED", "adjudication_id": "a1",
         "claims": [gold_claim(TEXT1, "Russian missiles", "strike", "Kyiv energy substation overnight")]},
        {"report_id": "r2", "annotator_id": "ADJUDICATED", "adjudication_id": "a2",
         "claims": []}, # passive/inverted headline-style clause deliberately abstained
        {"report_id": "r3", "annotator_id": "ADJUDICATED", "adjudication_id": "a3", "claims": []},
    ]
    pairs = [{"a": "r1", "b": "r2", "label": "same_event", "adjudication_id": "p1"}]
    return reports, labels, pairs


class RealReportEvaluationTests(unittest.TestCase):
    def test_prepare_blinds_extractor_results(self):
        reports, _, _ = fixture()
        packets = assignment(reports)
        self.assertEqual(len(packets["A"]), 3)
        self.assertEqual(packets["A"][0]["source_text"], TEXT1)
        self.assertNotIn("predicted", str(packets))
        self.assertNotIn("claim_id", str(packets))
        self.assertEqual(packets["B"][0]["annotator_id"], "B")

    def test_scoring_is_auditable_and_split_separated(self):
        reports, gold, pairs = fixture()
        a = [{**copy.deepcopy(x), "annotator_id": "A"} for x in gold]
        b = [{**copy.deepcopy(x), "annotator_id": "B"} for x in gold]
        out = score(reports, gold, pairs, a, b)
        self.assertFalse(out["operational_validation"])
        self.assertEqual(out["report_count"], 3)
        self.assertEqual(out["by_split"]["development"]["report_count"], 2)
        self.assertEqual(out["by_split"]["heldout"]["report_count"], 1)
        self.assertEqual(out["claim_metrics"]["tp"], 1)
        self.assertEqual(out["claim_metrics"]["fp"], 1)  # exposes unsafe active-voice reading of telegraphic passive
        self.assertEqual(out["claim_metrics"]["fn"], 0)
        self.assertEqual(out["review_audit"]["disagreement_count"], 0)

    def test_missing_second_reviewer_rejected(self):
        reports, gold, pairs = fixture()
        with self.assertRaisesRegex(ValueError, "two completed independent"):
            score(reports, gold, pairs)

    def test_disagreements_recorded_before_adjudication(self):
        reports, gold, _ = fixture()
        a = [{**copy.deepcopy(x), "annotator_id": "A"} for x in gold]
        b = [{**copy.deepcopy(x), "annotator_id": "B"} for x in gold]
        b[0]["claims"] = []
        out = review_audit(reports, a, b)
        self.assertEqual(out["disagreement_report_ids"], ["r1"])

    def test_lineage_leak_rejected(self):
        reports, _, _ = fixture()
        reports[2]["story_lineage_id"] = reports[0]["story_lineage_id"]
        with self.assertRaisesRegex(ValueError, "lineage leak"):
            validate_reports(reports)

    def test_missing_source_rights_rejected(self):
        reports, _, _ = fixture()
        reports[0].pop("rights_basis")
        with self.assertRaisesRegex(ValueError, "rights basis"):
            validate_reports(reports)

    def test_invalid_evidence_offsets_rejected(self):
        reports, gold, _ = fixture()
        gold[0]["claims"][0]["evidence_span"]["start"] = 2
        with self.assertRaisesRegex(ValueError, "span mismatch"):
            validate_labels(reports, gold)

    def test_cross_split_pair_rejected(self):
        reports, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "cross-split"):
            validate_pairs(reports, [{"a": "r1", "b": "r3",
                                       "label": "different_event", "adjudication_id": "p2"}])

    def test_uncertain_pair_not_scored_as_negative(self):
        reports, gold, _ = fixture()
        pair = [{"a": "r1", "b": "r2", "label": "uncertain", "adjudication_id": "p3"}]
        a = [{**copy.deepcopy(x), "annotator_id": "A"} for x in gold]
        b = [{**copy.deepcopy(x), "annotator_id": "B"} for x in gold]
        result = score(reports, gold, pair, a, b)
        self.assertEqual(result["pair_metrics"]["scored_pairs"], 0)
        self.assertEqual(result["pair_metrics"]["uncertain_truth_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
