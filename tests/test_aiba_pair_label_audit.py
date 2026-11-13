import unittest
from scripts.aiba_pair_label_audit import audit

def row(coder, label):
    return {"pair_id":"pair-abcdefghijkl12345678", "annotator_id":coder,
            "a":"r1","b":"r2", "label":label,
            "reviewer_notes": "Evidence needs checking"}

class PairAuditTests(unittest.TestCase):
    def test_two_independent_human_decisions_still_require_adjudication(self):
        queue, summary = audit([row("A","same_event")], [row("B","same_event")])
        self.assertEqual(summary["pairs_double_coded"],1)
        self.assertEqual(summary["exact_agreement_rate"],1)
        self.assertIsNone(queue[0]["label"])
        self.assertIsNone(queue[0]["adjudication_id"])
        self.assertEqual(summary["human_adjudications_completed"],0)

    def test_disagreement_is_not_automatically_resolved(self):
        queue, summary = audit([row("A","same_event")], [row("B","different_event")])
        self.assertEqual(summary["disagreements"],1)
        self.assertIsNone(queue[0]["label"])
        self.assertFalse(queue[0]["reviewers_agree"])

    def test_incomplete_coding_rejected(self):
        with self.assertRaisesRegex(ValueError,"incomplete"):
            audit([row("A",None)], [row("B","same_event")])

    def test_one_reviewer_cannot_fake_two(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            audit([row("A","same_event")], [row("A","same_event")])

    def test_insufficient_truth_still_not_negative(self):
        queue, summary=audit([row("A","uncertain")], [row("B","uncertain")])
        self.assertTrue(summary["uncertain_labels_not_treated_as_negative"])
        self.assertIsNone(queue[0]["label"])

if __name__ == "__main__":
    unittest.main()
