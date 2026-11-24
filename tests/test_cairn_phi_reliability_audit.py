"""Phi reliability across actual publication receipts, without accuracy inflation."""
import copy
import unittest
from scripts.cairn_phi_reliability_audit import MODEL, SCHEMA, summarize


def passed():
    return {"status": "provisional_complete", "analyst_approved": False,
            "interpretation_only": True, "evaluations": [],
            "source_references": [{"evidence_key": "family:one"}],
            "evidence_notes": [{"evidence_key": "family:one"}],
            "format_retry_succeeded": False}


def receipt(n, *, count=10):
    return {"schema": SCHEMA, "model": MODEL,
            "generated_at": f"2026-11-24T0{n}:00:00Z",
            "cases": {f"case-{j}": passed() for j in range(count)}}


class PhiReliabilityAuditTests(unittest.TestCase):
    def test_sufficient_real_cycle_denominator_not_one_successful_smoke(self):
        report = summarize([receipt(n) for n in range(5)])
        self.assertEqual(report["attempted_case_runs"], 50)
        self.assertEqual(report["schema_valid_case_runs"], 50)
        self.assertTrue(report["structural_validity_gate_met"])
        self.assertFalse(report["independent_real_world_event_accuracy_measured"])
        self.assertFalse(report["source_truth_independently_verified"])
        self.assertFalse(summarize([receipt(0)])["sufficient_denominator"])

    def test_duplicate_artifact_cannot_double_count_a_run(self):
        report = summarize([receipt(0), copy.deepcopy(receipt(0))])
        self.assertEqual(report["distinct_publication_runs"], 1)
        self.assertEqual(report["attempted_case_runs"], 10)

    def test_failure_codes_and_retry_recovery_counted(self):
        a = receipt(0)
        a["cases"]["case-1"] = {
            "status": "model_or_validation_failed",
            "evaluations": [], "error_code": "invalid_evidence_key"}
        a["cases"]["case-2"]["format_retry_succeeded"] = True
        report = summarize([a], minimum_cases=10, minimum_runs=1)
        self.assertEqual(report["failure_codes"], {"invalid_evidence_key": 1})
        self.assertEqual(report["format_retries_recovered"], 1)
        self.assertEqual(report["valid_fraction"], 0.9)
        self.assertFalse(report["structural_validity_gate_met"])

    def test_reject_model_direction_and_fabricated_accepted_key(self):
        a = receipt(0)
        a["cases"]["case-0"]["evaluations"] = [
            {"hypothesis_index": 0, "direction": "possibly_consistent"}]
        with self.assertRaises(ValueError):
            summarize([a])
        a = receipt(0)
        a["cases"]["case-0"]["evidence_notes"][0]["evidence_key"] = "invented"
        with self.assertRaises(ValueError):
            summarize([a])

    def test_wrong_model_and_unknown_status_fail_closed(self):
        a = receipt(0)
        a["model"] = "cloud-model"
        with self.assertRaises(ValueError):
            summarize([a])
        a = receipt(0)
        a["cases"]["case-0"]["status"] = "confirmed_warning"
        with self.assertRaises(ValueError):
            summarize([a])

    def test_inactive_cases_do_not_inflate_model_success(self):
        a = receipt(0)
        a["cases"]["case-1"] = {"status": "not_selected_in_bounded_run",
                                 "evaluations": []}
        report = summarize([a])
        self.assertEqual(report["attempted_case_runs"], 9)
        self.assertEqual(report["schema_valid_case_runs"], 9)


if __name__ == "__main__":
    unittest.main()
