"""Regression tests for authenticated OSINT intake and Atlas history.

Every synthetic observation lives in a TemporaryDirectory, never production.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from dashboard.analyst_intake import load_history, store_batch, validate_batch
from dashboard.build_atlas import generate

NOW = dt.datetime(2026, 11, 8, 18, 0, tzinfo=dt.timezone.utc)


def lead(identifier="test-taiwan-001", case_id="taiwan", root="primary-source-001",
         url="https://example.org/notice"):
    return {
        "observation_id": identifier, "case_id": case_id,
        "published_at": "2026-11-08T10:15:00Z",
        "source_url": url, "publisher": "Fictional test provider",
        "title": "Taiwan source-lead example (synthetic)",
        "summary": "Synthetic fixture. Not an actual geopolitical development.",
        "evidence_class": "source_observation", "confidence": "low",
        "information_root": root, "independently_confirmed": False,
    }


def batch(rows=None, run="test-run-20261108T1200", collected="2026-11-08T12:00:00Z",
          status="completed"):
    return {"schema_version": 1, "run_id": run, "collector": "six_hour_signal",
            "status": status, "collected_at": collected,
            "observations": [lead()] if rows is None else rows}


class AnalystIntakeTests(unittest.TestCase):
    def test_immutable_roundtrip_and_no_replay_pulse(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            file = store_batch(state, batch(), clock=NOW)
            self.assertTrue(file.exists())
            first = load_history(state, clock=NOW)
            self.assertEqual(first["distinct_observations"], 1)
            self.assertEqual(first["records"][0]["published_at"], "2026-11-08")
            self.assertEqual(first["records"][0]["first_collected_at"], "2026-11-08T12:00:00+00:00")
            store_batch(state, batch([lead()], run="test-run-20261108T1300",
                                    collected="2026-11-08T13:00:00Z"), clock=NOW)
            again = load_history(state, clock=NOW)
            self.assertEqual(again["distinct_observations"], 1)
            self.assertEqual(again["records"][0]["first_collected_at"], "2026-11-08T12:00:00+00:00")
            self.assertEqual(again["run_count"], 2)

    def test_unrelated_syndicated_mirrors_share_one_root(self):
        with tempfile.TemporaryDirectory() as temp:
            a = lead()
            b = lead("test-taiwan-002", root=a["information_root"],
                     url="https://example.net/syndicated-copy")
            store_batch(temp, batch([a, b]), clock=NOW)
            self.assertEqual(load_history(temp, clock=NOW)["distinct_observations"], 1)

    def test_invalid_inputs_cannot_be_published_as_sourced_reporting(self):
        invalid = []
        no_source = batch(); no_source["observations"][0]["source_url"] = "javascript:alert(1)"
        invalid.append(no_source)
        future = batch(); future["collected_at"] = "2030-01-01T00:00:00Z"
        invalid.append(future)
        misleading = batch(); misleading["observations"][0]["independently_confirmed"] = "yes"
        invalid.append(misleading)
        without_root = batch(); without_root["observations"][0]["information_root"] = ""
        invalid.append(without_root)
        failed_with_evidence = batch(status="failed")
        invalid.append(failed_with_evidence)
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_batch(value, clock=NOW)

    def test_conflicting_observation_id_blocks_deployment(self):
        with tempfile.TemporaryDirectory() as temp:
            store_batch(temp, batch(), clock=NOW)
            other = lead()
            other["summary"] = "Different claim using the same identifier"
            store_batch(temp, batch([other], run="test-run-20261108T1300",
                                    collected="2026-11-08T13:00:00Z"), clock=NOW)
            with self.assertRaisesRegex(ValueError, "Conflicting observations"):
                load_history(temp, clock=NOW)

    def test_failed_collection_is_not_zero_risk_or_success(self):
        with tempfile.TemporaryDirectory() as temp:
            store_batch(temp, batch([], status="failed"), clock=NOW)
            current = load_history(temp, clock=NOW)
            self.assertEqual(current["status"], "partial")
            self.assertEqual(current["distinct_observations"], 0)

    def test_end_to_end_synthetic_atlas_pulse_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state, site = root / "state", root / "site"
            site.mkdir()
            (site / "index.html").write_text("<html>Classic source-linked view</html>")
            (site / "hotspots.json").write_text(json.dumps({
                "asof": "2026-11-07", "hotspots": [{
                    "id": "gdelt_BILAT_SYN_TEST", "name": "Unlocated synthetic",
                    "scope": "Algorithmic lead", "summary": "Test anomaly",
                    "asof": "2026-11-07"
                }]}))
            store_batch(state, batch([lead(), lead("test-global-002",
                                                  case_id="synthetic_unlocated",
                                                  root="independent-002",
                                                  url="https://example.org/other")]), clock=NOW)
            commercial = state / "history" / "commercial"
            commercial.mkdir(parents=True)
            snapshot = {"records": [{
                "title": "Taiwan port shipping change (synthetic source)",
                "source_url": "https://example.org/port",
                "publisher_domain": "Fictional publication",
                "published_at": "2026-11-08T09:00:00Z"
            }]}
            for name in ("20261108T1100.json", "20261108T1200.json"):
                (commercial / name).write_text(json.dumps(snapshot))
            current = generate(site, generated="2026-11-08T18:00:00+00:00",
                               state_dir=state)
            taiwan = next(x for x in current["hotspots"] if x["id"] == "taiwan")
            self.assertTrue(taiwan["new_analyst_lead"])
            self.assertFalse(taiwan["new_evidence"])
            self.assertNotEqual(taiwan["severity"], "critical")
            analyst = [r for r in current["reports"] if r["id"] == "analyst:test-taiwan-001"]
            self.assertEqual(len(analyst), 1)
            ops = [r for r in current["reports"] if r["id"].startswith("ops:")]
            self.assertEqual(len(ops), 1, "Repeated source snapshots must not create duplicate points")
            self.assertEqual(current["status"]["analyst_intake"]["distinct_observations"], 2)
            self.assertEqual(len(current["unlocated_analyst_leads"]), 1)
            self.assertEqual(current["algorithmic_unlocated_count"], 1)
            self.assertTrue((site / "atlas.json").exists())
            self.assertIn("Unreviewed analyst lead", json.dumps(current))
            late = generate(site, generated="2026-11-11T18:00:00+00:00",
                            state_dir=state)
            self.assertFalse(next(x for x in late["hotspots"] if x["id"] == "taiwan")["new_analyst_lead"])
            self.assertEqual(sum(r["id"].startswith("ops:") for r in late["reports"]), 1)


if __name__ == "__main__":
    unittest.main()
