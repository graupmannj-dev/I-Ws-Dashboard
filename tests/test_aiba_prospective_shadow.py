"""Offline prospective source coverage frames; no warnings or live source calls."""
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import aiba_prospective_shadow as shadow
from scripts import aiba_tipper_ledger as ledger
from scripts import aiba_tipper_score as scorer

NOW = dt.datetime(2026, 11, 12, 22, 0, tzinfo=dt.timezone.utc)
STAMP = "2026-11-12T21:55:00Z"


def registry():
    return {
        "schema": shadow.REGISTRY_SCHEMA, "generated_at": STAMP,
        "first_registry_baseline": False, "alert_eligible": False,
        "record_count": 12, "records": [],
        "source_health": {
            "ioda": {"status": "current", "missingness": "provider_bounded_not_exhaustive",
                     "source_scope": "IODA country events only"},
            "nga": {"status": "stale_or_unavailable", "missingness": "not_measured_not_zero",
                    "source_scope": "NGA unavailable regional maritime reports"},
        }
    }


def fusion():
    return {
        "schema": shadow.FUSION_SCHEMA, "generated_at": STAMP,
        "registry_asof": STAMP, "collection_coverage": registry()["source_health"],
        "new_single_source_count_total": 1,
        "new_single_source_leads": [{
            "status": "single_source_unreviewed",
            "observation_id": "beh:123", "first_observed_at": STAMP,
            "source_family": "internet_reachability",
            "requires_geolocation": True,
        }],
        "review_groups_count_total": 0, "review_groups": [],
        "approved_warning_count": 0, "automated_severity_changes": 0,
        "prediction_horizon": None, "forecast_probability": None,
    }


def group():
    return {
        "id": "behavioral:abc",
        "status": "cross_family_cooccurrence_unreviewed",
        "warning_level_change": False,
        "geography": {"key": "country:US"},
        "distinct_source_families": ["internet_reachability", "maritime_restriction"],
        "distinct_provider_count": 2, "source_root_count": 2,
        "observation_ids": ["beh:123", "beh:456"],
        "first_observed_at": STAMP, "last_observed_at": STAMP,
    }


def hashes():
    return {"registry": "a"*64, "fusion": "b"*64}


class ShadowFrameTests(unittest.TestCase):
    def test_realistic_single_source_no_crossfamily_never_issues_warning(self):
        frame, receipt = shadow.prepare(registry(), fusion(), hashes(), now=NOW)
        self.assertEqual(frame["cross_family_review_count"], 0)
        self.assertEqual(frame["single_source_review_count"], 1)
        self.assertFalse(frame["negative_outcome_inferred"])
        self.assertFalse(frame["source_completeness_verified"])
        self.assertEqual(receipt["issued_warning_count"], 0)
        self.assertEqual(receipt["providers_checked"], 2)
        self.assertIn("nga", receipt["sources_degraded"])
        self.assertFalse(receipt["approved_for_global_recall_scoring"])
        self.assertEqual(frame["window_start"], "2026-11-12T22:02:00Z")

    def test_source_data_not_complete_even_when_every_provider_current(self):
        r = registry()
        f = fusion()
        r["source_health"]["nga"]["status"] = "current"
        r["source_health"]["nga"]["missingness"] = "none"
        f["collection_coverage"] = r["source_health"]
        frame, receipt = shadow.prepare(r, f, hashes(), now=NOW)
        self.assertFalse(frame["source_completeness_verified"])
        self.assertTrue(receipt["providers_with_missingness"] >= 1)

    def test_crossfamily_unreviewed_remains_investigatory(self):
        f = fusion()
        f["review_groups_count_total"] = 1
        f["review_groups"] = [group()]
        frame, receipt = shadow.prepare(registry(), f, hashes(), now=NOW)
        self.assertEqual(frame["cross_family_review_count"], 1)
        self.assertEqual(receipt["issued_warning_count"], 0)
        self.assertFalse(receipt["frozen_issued_tipper"])

    def test_crossfamily_unlocated_or_single_family_fails(self):
        for mutation in (
            lambda g: g["geography"].update(key=None),
            lambda g: g.update(distinct_source_families=["ioda"]),
            lambda g: g.update(distinct_provider_count=1),
            lambda g: g.update(source_root_count=1),
            lambda g: g.update(warning_level_change=True),
        ):
            f = fusion()
            g = group()
            mutation(g)
            f["review_groups"], f["review_groups_count_total"] = [g], 1
            with self.subTest(g=g), self.assertRaises(shadow.ShadowError):
                shadow.prepare(registry(), f, hashes(), now=NOW)

    def test_source_future_stale_or_registry_fusion_mismatch(self):
        for modification in (
            lambda r, f: r.update(generated_at="2026-11-12T20:00:00Z"),
            lambda r, f: f.update(generated_at="2026-11-12T22:01:00Z"),
            lambda r, f: f.update(registry_asof="2026-11-12T21:00:00Z"),
            lambda r, f: r.update(first_registry_baseline=True),
            lambda r, f: f.update(approved_warning_count=1),
            lambda r, f: f.update(forecast_probability=0.5),
        ):
            r, f = registry(), fusion()
            modification(r, f)
            with self.subTest(r=r, f=f), self.assertRaises(shadow.ShadowError):
                shadow.prepare(r, f, hashes(), now=NOW)

    def test_source_health_partial_is_not_coverage_completeness(self):
        f = fusion()
        f["collection_coverage"]["nga"]["status"] = "current"
        with self.assertRaisesRegex(shadow.ShadowError, "health_mismatch"):
            shadow.prepare(registry(), f, hashes(), now=NOW)

    def test_truncated_group_list_and_future_leads_fail(self):
        f = fusion()
        f["review_groups_count_total"] = 1
        with self.assertRaisesRegex(shadow.ShadowError, "truncated"):
            shadow.prepare(registry(), f, hashes(), now=NOW)
        f = fusion()
        f["new_single_source_leads"][0]["first_observed_at"] = "2026-11-12T22:01:00Z"
        with self.assertRaisesRegex(shadow.ShadowError, "future_single_source"):
            shadow.prepare(registry(), f, hashes(), now=NOW)

    def test_hash_validation_rejects_arbitrary_values(self):
        for h in ({"registry": "x"*64, "fusion": "b"*64},
                  {"registry": "a", "fusion": "b"*64},
                  {"registry": "a"*64}):
            with self.subTest(h=h), self.assertRaises(shadow.ShadowError):
                shadow.prepare(registry(), fusion(), h, now=NOW)

    def test_frozen_monitoring_frame_excludes_tipper_denominator(self):
        frame, _ = shadow.prepare(registry(), fusion(), hashes(), now=NOW)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"shadow.jsonl"
            result = ledger.append(path, "frame", frame,
                                   clock=lambda: "2026-11-12T22:00:30Z")
            self.assertEqual(result["status"], "appended")
            entries, digest = ledger.read_ledger(path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(digest, result["entry_hash"])
            score = scorer.score_ledger(path)
        self.assertEqual(score["prospective_monitor_frames"], 1)
        self.assertEqual(score["counts"], {})
        self.assertIsNone(score["resolved_forecast_hit_fraction"])
        self.assertIsNone(score["recall"])
        self.assertIsNone(score["false_alarms_per_analyst_day"])

    def test_duplicate_frame_id_is_rejected(self):
        frame, _ = shadow.prepare(registry(), fusion(), hashes(), now=NOW)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"shadow.jsonl"
            ledger.append(path, "frame", frame,
                          clock=lambda: "2026-11-12T22:00:30Z")
            with self.assertRaisesRegex(ledger.LedgerError, "already_registered"):
                ledger.append(path, "frame", frame,
                              clock=lambda: "2026-11-12T22:00:50Z")

    def test_no_historical_or_overlong_frame_window(self):
        frame, _ = shadow.prepare(registry(), fusion(), hashes(), now=NOW)
        frame["window_start"] = "2026-11-12T21:59:59Z"
        with self.assertRaisesRegex(ledger.LedgerError, "must_be_prospective"):
            ledger.validate_monitor_frame(frame, "2026-11-12T22:00:00Z", [])
        frame["window_start"] = "2026-11-12T22:02:00Z"
        frame["window_end"] = "2026-11-14T00:00:00Z"
        with self.assertRaisesRegex(ledger.LedgerError, "duration_invalid"):
            ledger.validate_monitor_frame(frame, "2026-11-12T22:00:00Z", [])

    def test_untrusted_attempt_to_mark_no_event_fails_closed(self):
        frame, _ = shadow.prepare(registry(), fusion(), hashes(), now=NOW)
        for key, bad in (
            ("negative_outcome_inferred", True),
            ("source_completeness_verified", True),
            ("approved_tippers", 1),
            ("automated_warning_changes", 1),
        ):
            modified = copy.deepcopy(frame)
            modified[key] = bad
            with self.subTest(key=key),self.assertRaises(ledger.LedgerError):
                ledger.validate_monitor_frame(modified, "2026-11-12T22:00:00Z", [])

    def test_offline_snapshot_byte_hash_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            rp, fp=root/"r.json",root/"f.json"
            rp.write_text(json.dumps(registry()))
            fp.write_text(json.dumps(fusion()))
            with patch.object(shadow, "clock_now", return_value=NOW):
                result=shadow.run(rp,fp)
            self.assertEqual(result["status"], "eligible_for_local_shadow_frame")
            self.assertEqual(result["source_sha256"]["registry"],
                             hashlib.sha256(rp.read_bytes()).hexdigest())
            self.assertNotIn("synthetic frontier", json.dumps(result))

    def test_freeze_is_opt_in_and_persists_on_private_path_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            rp,fp=root/"r.json",root/"f.json"
            ledger_path=root/"ledger.jsonl"
            rp.write_text(json.dumps(registry()))
            fp.write_text(json.dumps(fusion()))
            with patch.object(shadow, "clock_now", return_value=NOW), patch.object(
                ledger, "utc_now", return_value="2026-11-12T22:00:30Z"
            ):
                result=shadow.run(rp,fp,mode="freeze",ledger_path=ledger_path)
            self.assertEqual(result["status"],"local_unanchored_shadow_frame_appended")
            self.assertTrue(ledger_path.exists())
            self.assertFalse(result["frozen_issued_tipper"])
            self.assertEqual(len(ledger.read_ledger(ledger_path)[0]),1)

    def test_missing_or_invalid_local_input_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"input.json"
            with self.assertRaises(shadow.ShadowError):
                shadow.read_snapshot(path)
            path.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaises(ledger.LedgerError):
                shadow.read_snapshot(path)

    def test_cli_failure_receipt_cannot_claim_success_or_overwrite_source(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder)
            rp,fp,out=root/"r.json",root/"f.json",root/"receipt.json"
            rp.write_text(json.dumps(registry()))
            fp.write_text(json.dumps(fusion()))
            initial=rp.read_bytes()
            self.assertEqual(shadow.main(["--registry",str(rp),"--fusion",str(fp),
                                          "--receipt",str(rp)]),1)
            self.assertEqual(rp.read_bytes(),initial)
            with patch.object(shadow,"clock_now",return_value=NOW):
                self.assertEqual(shadow.main(["--registry",str(rp),"--fusion",str(fp),
                                              "--receipt",str(out)]),0)
            val=json.loads(out.read_text())
            self.assertEqual(val["issued_warning_count"],0)
            self.assertFalse(val["no_event_inferred"])
            fp.write_text("{invalid")
            self.assertEqual(shadow.main(["--registry",str(rp),"--fusion",str(fp),
                                          "--receipt",str(out)]),1)
            val=json.loads(out.read_text())
            self.assertEqual(val["status"],"unavailable")
            self.assertFalse(val["frozen_issued_tipper"])


if __name__ == "__main__":
    unittest.main()
