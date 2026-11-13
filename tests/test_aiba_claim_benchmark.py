import json
import unittest
from pathlib import Path
from scripts.aiba_claim_benchmark import FIXTURE, evaluate, safe_ratio

class BenchmarkIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
        cls.result = evaluate(cls.fixture)

    def test_fixture_is_explicitly_synthetic(self):
        self.assertEqual(self.result["dataset_kind"], "hand_authored_synthetic_not_real_world")
        self.assertFalse(self.result["operational_validation"])
        self.assertEqual(self.result["claim_metrics"]["examples"], 20)
        self.assertEqual(self.result["relationship_metrics"]["examples"], 8)

    def test_metric_accounting(self):
        cm = self.result["claim_metrics"]
        self.assertEqual(cm["exact_true_positives"] + cm["exact_false_negatives"],
                         sum("none" not in x for x in self.fixture["claim_cases"]))
        self.assertEqual(cm["exact_true_positives"] + cm["exact_false_positives"],
                         sum(x["predicted_claims"] for x in self.result["claim_cases"]))
        self.assertEqual(cm["negative_example_correct_abstentions"] <= cm["labeled_negative_examples"], True)

    def test_provenance_spans_are_validated_and_no_warning_promotion(self):
        self.assertEqual(self.result["claim_metrics"]["examples"], len(self.result["claim_cases"]))
        self.assertFalse(self.result["operational_validation"])

    def test_false_merge_is_reported_not_silently_hidden(self):
        rm = self.result["relationship_metrics"]
        self.assertEqual(rm["false_event_merges"],
                         sum(x["false_event_merge"] for x in self.result["relationship_cases"]))
        self.assertEqual(rm["true_same_event_nominations"],
                         sum(x["truth"] == "same_event" and x["predicted"] == "same_event"
                             for x in self.result["relationship_cases"]))

    def test_empty_denominator_is_not_zero_performance(self):
        self.assertIsNone(safe_ratio(0, 0))

    def test_duplicate_ids_fail_closed(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["claim_cases"].append(dict(fixture["claim_cases"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate benchmark case IDs"):
            evaluate(fixture)

    def test_anonymous_field_test_cannot_be_falsely_claimed(self):
        fixture = json.loads(json.dumps(self.fixture))
        fixture["dataset_kind"] = "field_validation"
        with self.assertRaisesRegex(ValueError, "provenance"):
            evaluate(fixture)

if __name__ == "__main__":
    unittest.main()
