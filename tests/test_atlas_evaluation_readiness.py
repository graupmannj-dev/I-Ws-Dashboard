"""Public Atlas scorecard: no private ledger data or fabricated accuracy."""
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.evaluation_readiness import (
    SCHEMA, FORECAST_METRICS, summary, write,
)
from dashboard.behavioral_embed import empty


def behavior(asof="2026-11-12T22:55:00Z"):
    return {
        "schema": "aiba.behavioral-convergence-shadow.v1",
        "status": "read_only_shadow_evidence",
        "source_generated_at": asof,
        "approved_warning_count": 0,
        "automated_severity_changes": 0,
        "forecast_probability": None,
        "source_continuity_proven": False,
        "map_coordinates_inferred": False,
        "collection_coverage": {
            "ioda": {"status": "current", "missingness": "provider_bounded_not_exhaustive"},
            "nga": {"status": "stale_or_unavailable", "missingness": "not_measured_not_zero"},
        },
    }


class PublicEvaluationReadinessTests(unittest.TestCase):
    def test_pre_news_stats_unknown_without_private_verified_ledger(self):
        value = summary(behavior(),generated_at="2026-11-12T23:00:00Z")
        self.assertEqual(value["schema"], SCHEMA)
        self.assertEqual(value["status"],"prospective_skill_not_established")
        self.assertEqual(value["public_forecast_ledger"],"not_connected")
        self.assertTrue(all(key in value["metrics"] for key in FORECAST_METRICS))
        self.assertTrue(all(x is None for x in value["metrics"].values()))
        self.assertTrue(all(x=="not_connected" for x in value["verification_gates"].values()))
        self.assertFalse(value["claims_of_predictive_skill"])
        self.assertFalse(value["production_warning_updates"])

    def test_current_provider_status_not_worldwide_coverage(self):
        result = summary(behavior(),generated_at="2026-11-12T23:00:00Z")
        obs = result["observation"]
        self.assertEqual(obs["source_adapters_reported"], 2)
        self.assertEqual(obs["source_adapters_bounded_or_degraded"],2)
        self.assertTrue(obs["snapshot_within_90_minutes_at_build"])
        self.assertFalse(obs["worldwide_source_completeness_verified"])
        self.assertFalse(obs["unobserved_intervals_are_negative_events"])

    def test_stale_future_or_unknown_source_fails_readiness(self):
        for time in ("2026-11-12T21:01:00Z","2026-11-12T23:01:00Z",
                     "invalid",None):
            with self.subTest(time=time):
                b = behavior(time)
                result = summary(b,generated_at="2026-11-12T23:00:00Z")
                self.assertFalse(result["observation"]["snapshot_within_90_minutes_at_build"])
                self.assertFalse(result["observation"]["worldwide_source_completeness_verified"])

    def test_invalid_source_evidence_does_not_leak_stats_or_implicitly_zero(self):
        for key,value in (
            ("approved_warning_count",1),
            ("automated_severity_changes",1),
            ("forecast_probability",0.8),
            ("source_continuity_proven",True),
            ("map_coordinates_inferred",True),
            ("schema","malicious"),
        ):
            with self.subTest(key=key):
                b=behavior()
                b[key]=value
                result=summary(b,generated_at="2026-11-12T23:00:00Z")
                self.assertIsNone(result["observation"]["source_adapters_reported"])
                self.assertTrue(all(x is None for x in result["metrics"].values()))

    def test_no_feed_is_not_zero_feeds_or_zero_warnings(self):
        val = summary(empty(),generated_at="2026-11-12T23:00:00Z")
        self.assertIsNone(val["observation"]["source_adapters_reported"])
        self.assertIsNone(val["observation"]["source_adapters_bounded_or_degraded"])
        self.assertIsNone(val["observation"]["behavioral_source_asof"])
        self.assertIsNone(val["metrics"]["issued_tippers"])

    def test_public_output_does_not_include_private_fields(self):
        b=behavior()
        b["secret_analyst"]="synthetic-secret-person"
        b["original_tipper_payload"]="synthetic-classified-evidence"
        with tempfile.TemporaryDirectory() as tmp:
            record=write(tmp,b,generated_at="2026-11-12T23:00:00Z")
            content=(Path(tmp)/"evaluation_summary.json").read_text()
            self.assertEqual(json.loads(content),record)
            self.assertNotIn("synthetic-secret-person",content)
            self.assertNotIn("synthetic-classified-evidence",content)
            self.assertNotIn("source_id",content)
            self.assertNotIn("ledger_head_sha256",content)
            self.assertFalse(record["publication_of_private_ledger"])

    def test_public_summary_is_strict_json_not_nan(self):
        b=behavior()
        b["collection_coverage"]["ioda"]["missingness"]="none"
        with tempfile.TemporaryDirectory() as tmp:
            val=write(tmp,b,generated_at="2026-11-12T23:00:00Z")
            self.assertEqual(val["observation"]["source_adapters_bounded_or_degraded"],1)
            self.assertTrue((Path(tmp)/"evaluation_summary.json").exists())
            self.assertIn('"recall_against_registered_outcomes": null',
                          (Path(tmp)/"evaluation_summary.json").read_text())

    def test_bad_clock_refused_not_backdated(self):
        with self.assertRaises(ValueError):
            summary(behavior(),generated_at="2026-11-12T19:00:00-05:00")
        with self.assertRaises(ValueError):
            summary(behavior(),generated_at="time not recorded")


if __name__ == "__main__":
    unittest.main()
