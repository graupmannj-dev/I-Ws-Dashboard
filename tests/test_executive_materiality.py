"""Executive promotion requires substantive basis, not source novelty or corroboration."""
import datetime as dt
import unittest
from friction_synthesis import executive_materiality

AT = dt.datetime(2026, 11, 9, 22, tzinfo=dt.timezone.utc)
CASE = "Are direct interstate hostilities developing?"
EMPTY = {"internet_reachability": {"status": "insufficient_baseline", "samples": 1}}
NEW = [{"root": "ioda:x", "source_url": "https://ioda.example/test"}]

class ExecutiveMaterialityTests(unittest.TestCase):
    def check(self, new=NEW, overlap=False, anomalies=(), base=EMPTY, reviews=()):
        return executive_materiality("case", CASE, new, overlap,
                                     list(anomalies), base, list(reviews), AT)

    def test_novel_single_without_baseline_is_investigatory(self):
        got = self.check()
        self.assertFalse(got["executive_eligible"])
        self.assertIn("insufficient", got["baseline_context"])

    def test_uncorroborated_quantified_deviation_is_eligible(self):
        base = {"internet_reachability": {"status": "unusual_count", "current": 12,
                "median": 2, "samples": 16, "threshold": 7.0, "robust_z": 6.74}}
        got = self.check(anomalies=("internet_reachability",), base=base)
        self.assertTrue(got["executive_eligible"])
        self.assertIn("current 12", got["baseline_context"])
        self.assertIn(CASE, got["so_what"])

    def test_multi_family_time_overlap_not_mistaken_for_confirmation(self):
        got = self.check(overlap=True)
        self.assertTrue(got["executive_eligible"])
        self.assertIn("not proven independent", got["materiality_rationale"])

    def test_reviewed_single_event_can_be_important_without_a_second_source(self):
        record = {"case_id": "case", "root": "ioda:x",
            "source_url": "https://ioda.example/test", "status": "approved",
            "reviewed_at": "2026-11-09T21:00:00Z",
            "materiality_basis": "Documented exceptional protective action outside ordinary procedures.",
            "why_it_matters": "An exceptional disruption may obscure civilian reporting during the current watch.",
            "baseline_comparison": "Historical numeric coverage is missing, so exceptionality is qualitative.",
            "alternative_evidence": "Infrastructure failure remains an alternative and no intent is established.",
            "next_signpost": "Check next official restrictions and persistence of the observed disruption."}
        got = self.check(reviews=(record,))
        self.assertTrue(got["executive_eligible"])
        self.assertEqual(got["publication_basis"], "reviewed_single_root")

    def test_old_review_and_wrong_root_never_promote(self):
        record = {"case_id": "case", "root": "ioda:other",
            "source_url": "https://ioda.example/test", "status": "approved",
            "reviewed_at": "2026-11-01T00:00:00Z"}
        self.assertFalse(self.check(reviews=(record,))["executive_eligible"])

if __name__ == "__main__":
    unittest.main()
