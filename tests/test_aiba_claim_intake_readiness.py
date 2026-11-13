import json
import tempfile
import unittest
from pathlib import Path

from scripts.aiba_claim_intake_readiness import readiness


class ReadinessProbeTests(unittest.TestCase):
    def test_no_event_reports_does_not_mean_no_incidents(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p/"latest").mkdir()
            (p/"history"/"behavioral_registry").mkdir(parents=True)
            (p/"latest"/"behavioral_registry.json").write_text(
                json.dumps({"generated_at": "2026-11-13T12:00:00Z"}))
            result=readiness(p)
            self.assertEqual(result["incident_report_like_records"],0)
            self.assertEqual(result["reporting_records_with_supplied_body"],0)
            self.assertFalse(result["claim_quality_measured"])
            self.assertEqual(result["automatic_alerts_created"],0)

    def test_missing_asof_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            (p/"latest").mkdir()
            (p/"latest"/"behavioral_registry.json").write_text("{}")
            with self.assertRaisesRegex(ValueError,"registry_asof_missing"):
                readiness(p)


if __name__ == "__main__":
    unittest.main()
