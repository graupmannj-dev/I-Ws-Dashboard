"""Offline CI for Phi exact-input reuse and safe asynchronous sidecars."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.semantic_ach import digest, evidence_packet
from scripts.cairn_phi_local import MODEL
from scripts.cairn_phi_incremental import SCHEMA, assemble, prepare
from tests.test_semantic_ach import index

NOW = dt.datetime(2026, 11, 24, 15, 0, tzinfo=dt.timezone.utc)


def source():
    doc = index()
    doc["generated_at"] = "2026-11-24T14:00:00Z"
    return doc


def valid(case, when=NOW):
    packet = evidence_packet(case)
    return {"status": "provisional_complete",
            "model_family": MODEL, "analyst_approved": False,
            "interpretation_only": True, "source_truth_not_verified": True,
            "evaluations": [], "source_references": packet["evidence_families"],
            "interpretations": [{"hypothesis_index": i,
                "meaning": "This remains a provisional explanation for analysis.",
                "discriminator": "Inspect an independent dated official primary observation."}
                for i in range(len(packet["hypotheses"]))],
            "evidence_notes": [],
            "input_sha256": digest(packet),
            "model_generated_at": when.isoformat().replace("+00:00", "Z")}


def prior(doc, when=NOW):
    case = doc["hypotheses"][0]
    return {"schema": SCHEMA, "model": MODEL,
            "cases": {case["id"]: valid(case, when)}}


class IncrementalPhiTests(unittest.TestCase):
    def test_empty_cache_prepares_source_without_altering_input(self):
        with tempfile.TemporaryDirectory() as d:
            original = source()
            before = copy.deepcopy(original)
            p = prepare(original, {}, d, now=NOW)
            self.assertEqual(p["changed"], 1)
            self.assertEqual(p["reused"], 0)
            self.assertEqual(original, before)
            self.assertEqual(json.loads((Path(d)/"hypotheses.json").read_text())["schema"],
                             "cairn.hypothesis-evidence.v1")
            manifest = json.loads((Path(d)/"phi_manifest.json").read_text())
            self.assertEqual(manifest["changed"], ["taiwan"])
            self.assertEqual(manifest["input_sha256"]["taiwan"],
                             digest(evidence_packet(original["hypotheses"][0])))

    def test_exact_fresh_result_reused_without_model(self):
        with tempfile.TemporaryDirectory() as d:
            doc = source()
            old = prior(doc)
            p = prepare(doc, old, d, now=NOW)
            self.assertEqual(p["changed"], 0)
            self.assertEqual(p["reused"], 1)
            self.assertEqual(json.loads((Path(d)/"hypotheses.json").read_text())["hypotheses"], [])
            built = assemble(doc, old, d, now=NOW)
            row = built["cases"]["taiwan"]
            self.assertEqual(row["cache_status"], "reused_exact_input")
            self.assertEqual(built["summary"]["new_provisional"], 0)
            self.assertEqual(row["model_generated_at"], old["cases"]["taiwan"]["model_generated_at"])

    def test_expiry_changed_packet_and_bad_ref_force_new_model(self):
        with tempfile.TemporaryDirectory() as d:
            doc = source()
            old = prior(doc, NOW - dt.timedelta(hours=30))
            self.assertEqual(prepare(doc, old, d, now=NOW)["changed"], 1)
            old = prior(doc)
            other = copy.deepcopy(doc)
            other["hypotheses"][0]["hypothesis"] = "An independent modified claim."
            self.assertEqual(prepare(other, old, d, now=NOW)["changed"], 1)
            old = prior(doc)
            old["cases"]["taiwan"]["evidence_notes"] = [
                {"evidence_key": "fabricated", "observation": "A title makes a claim",
                 "verification_step": "Check another source"}]
            self.assertEqual(prepare(doc, old, d, now=NOW)["changed"], 1)
            old = prior(doc)
            old["cases"]["taiwan"]["evaluations"] = [{"direction":"possibly_consistent"}]
            self.assertEqual(prepare(doc, old, d, now=NOW)["changed"], 1)
            old = prior(doc)
            old["cases"]["taiwan"]["source_references"][0]["sources"][0]["url"] = "https://attacker.example/false-source"
            self.assertEqual(prepare(doc, old, d, now=NOW)["changed"], 1)

    def test_new_inference_assembled_without_signed_mutations(self):
        with tempfile.TemporaryDirectory() as d:
            doc = source()
            prepare(doc, {}, d, now=NOW)
            model_result = {"schema": "cairn.semantic-ach.v1", "model": MODEL,
                            "generated_at": NOW.isoformat().replace("+00:00", "Z"),
                            "cases": {"taiwan": valid(doc["hypotheses"][0])}}
            (Path(d)/"semantic_ach.json").write_text(json.dumps(model_result))
            output = assemble(doc, {}, d, now=NOW)
            self.assertEqual(output["summary"], {"cases":1, "reused":0,
                                                  "new_provisional":1, "failed":0})
            row = output["cases"]["taiwan"]
            self.assertEqual(row["cache_status"], "fresh_inference")
            self.assertEqual(row["evaluations"], [])
            self.assertFalse(row["analyst_approved"])
            self.assertEqual(doc["hypotheses"][0]["balance"]["direction"], "not_assessed")

    def test_missing_model_and_source_hash_race_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            doc = source()
            prepare(doc, {}, d, now=NOW)
            result = assemble(doc, {}, d, now=NOW)
            self.assertEqual(result["cases"]["taiwan"]["status"],
                             "model_or_validation_failed")
            self.assertEqual(result["cases"]["taiwan"]["evaluations"], [])
            self.assertEqual(result["cases"]["taiwan"]["error_code"],
                             "phi_runtime_unavailable")
            changed = copy.deepcopy(doc)
            changed["hypotheses"][0]["alternatives"] = ["This is now a different alternative."]
            with self.assertRaises(ValueError):
                assemble(changed, {}, d, now=NOW)

    def test_reject_duplicate_case_ids(self):
        with tempfile.TemporaryDirectory() as d:
            doc = source()
            doc["hypotheses"].append(copy.deepcopy(doc["hypotheses"][0]))
            with self.assertRaises(ValueError):
                prepare(doc, {}, d, now=NOW)

    def test_no_future_dated_or_unsigned_cache_promotion(self):
        with tempfile.TemporaryDirectory() as d:
            doc = source()
            old = prior(doc, NOW + dt.timedelta(hours=1))
            self.assertEqual(prepare(doc, old, d, now=NOW)["changed"], 1)
            old = prior(doc)
            old["cases"]["taiwan"]["analyst_approved"] = True
            self.assertEqual(prepare(doc, old, d, now=NOW)["changed"], 1)


if __name__ == "__main__":
    unittest.main()
