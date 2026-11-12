"""Read-only collector cadence audit: no implicit missed events, no clock invention."""
import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import aiba_collection_cadence_audit as audit

NOW = dt.datetime(2026,11,12,23,30,tzinfo=dt.timezone.utc)


def z(minute):
    return (NOW+dt.timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")


def all_runs(offsets=(-200,-170,-140,-110,-80,-50,-20)):
    runs=[]
    for category in audit.GROUPS:
        for i, offset in enumerate(offsets):
            runs.append({"id":len(runs)+1,"name":category,
                         "event":"schedule","created_at":z(offset),
                         "status":"completed","conclusion":"success"})
    return {"total_count":len(runs),"workflow_runs":runs}


def snapshots():
    health={
        "ioda":{"status":"current","missingness":"provider_bounded_not_exhaustive",
                "source_scope":"country measurements"},
        "nga":{"status":"stale_or_unavailable","missingness":"not_measured_not_zero",
               "source_scope":"regional maritime reports"}
    }
    reg={"schema":"aiba.behavioral-observations.v1","generated_at":z(-5),
         "source_health":health}
    fus={"schema":"aiba.behavioral-convergence-shadow.v1",
         "generated_at":z(-5),"registry_asof":z(-5),
         "collection_coverage":copy.deepcopy(health)}
    return reg,fus


class CadenceAuditTests(unittest.TestCase):
    def test_gaps_and_trailing_are_unknown_coverage_not_zero_events(self):
        reg,fus=snapshots()
        measured=audit.evaluate(all_runs((-700,-40,-5)),reg,fus,now=NOW)
        self.assertEqual(measured["status"],"gap_or_stale_source_review_required")
        self.assertTrue(measured["collector_groups"]["friction"]["intervals_over_2x_nominal"]>=1)
        self.assertGreater(measured["collector_groups"]["restrictions"]["max_observed_start_gap_minutes"],600)
        self.assertFalse(measured["negative_events_inferred"])
        self.assertFalse(measured["source_continuity_proven"])
        self.assertEqual(measured["prospective_warnings_issued"],0)
        self.assertTrue(measured["fusion_fresh_enough_for_90_minute_shadow_preflight"])

    def test_fresh_regular_run_creation_still_not_proven_source_coverage(self):
        reg,fus=snapshots()
        data=audit.evaluate(all_runs(),reg,fus,now=NOW)
        self.assertFalse(data["source_continuity_proven"])
        self.assertFalse(data["negative_events_inferred"])
        self.assertTrue(data["fusion_fresh_enough_for_90_minute_shadow_preflight"])
        self.assertIn("nga",data["providers_degraded_or_scope_bounded"])

    def test_mixed_operational_modes_are_only_optimistic(self):
        reg,fus=snapshots()
        data=audit.evaluate(all_runs(),reg,fus,now=NOW)
        x=data["collector_groups"]["operational_mixed_modes"]
        self.assertIn("Optimistic upper bound",x["interpretation"])

    def test_late_source_rejected_even_with_all_recent_workflow_runs(self):
        reg,fus=snapshots()
        reg["generated_at"]=fus["generated_at"]=fus["registry_asof"]=z(-120)
        x=audit.evaluate(all_runs(),reg,fus,now=NOW)
        self.assertFalse(x["fusion_fresh_enough_for_90_minute_shadow_preflight"])
        self.assertEqual(x["status"],"gap_or_stale_source_review_required")

    def test_failed_and_pending_runs_are_not_false_observations(self):
        data=all_runs()
        data["workflow_runs"][0]["conclusion"]="failure"
        data["workflow_runs"][1]["conclusion"]=None
        data["workflow_runs"][1]["status"]="in_progress"
        reg,fus=snapshots()
        x=audit.evaluate(data,reg,fus,now=NOW)
        self.assertEqual(x["collector_groups"]["friction"]["failed_or_cancelled_runs_observed"],1)
        self.assertEqual(x["collector_groups"]["friction"]["pending_runs_observed"],1)
        self.assertFalse(x["source_continuity_proven"])

    def test_empty_runs_without_history_does_not_imply_quiet_period(self):
        reg,fus=snapshots()
        x=audit.evaluate({"total_count":0,"workflow_runs":[]},reg,fus,now=NOW)
        self.assertFalse(x["api_history_covers_window"])
        self.assertTrue(x["collector_groups"]["friction"]["trailing_start_gap"])
        self.assertEqual(x["collector_groups"]["friction"]["cadence_reliability_class"],"gaps_detected")

    def test_history_completeness_requires_oldest_record_before_window(self):
        reg,fus=snapshots()
        x=audit.evaluate(all_runs(),reg,fus,now=NOW)
        self.assertFalse(x["api_history_covers_window"])
        raw=all_runs()
        raw["workflow_runs"].append({"id":99999,"name":"Other pipeline", "event":"schedule",
                                      "created_at":z(-73*60), "status":"completed",
                                      "conclusion":"success"})
        raw["total_count"]=len(raw["workflow_runs"])
        x=audit.evaluate(raw,reg,fus,now=NOW)
        self.assertTrue(x["api_history_covers_window"])

    def test_run_ids_unique_and_utc_clocks_strict(self):
        reg,fus=snapshots()
        run=all_runs()
        run["workflow_runs"][1]["id"]=run["workflow_runs"][0]["id"]
        with self.assertRaisesRegex(audit.CadenceError,"duplicate_or_invalid"):
            audit.evaluate(run,reg,fus,now=NOW)
        run=all_runs()
        run["workflow_runs"][0]["created_at"]="2026-11-12T20:00:00-05:00"
        with self.assertRaisesRegex(audit.CadenceError,"invalid_utc"):
            audit.evaluate(run,reg,fus,now=NOW)
        run=all_runs()
        run["workflow_runs"][0]["created_at"]=z(10)
        with self.assertRaisesRegex(audit.CadenceError,"future_workflow_metadata"):
            audit.evaluate(run,reg,fus,now=NOW)

    def test_source_pair_must_share_provenance(self):
        reg,fus=snapshots()
        fus["registry_asof"]=z(-8)
        with self.assertRaisesRegex(audit.CadenceError,"mismatched"):
            audit.evaluate(all_runs(),reg,fus,now=NOW)
        reg,fus=snapshots()
        fus["collection_coverage"]["nga"]["status"]="current"
        with self.assertRaisesRegex(audit.CadenceError,"source_health_diverged"):
            audit.evaluate(all_runs(),reg,fus,now=NOW)

    def test_source_future_or_invalid_and_lookback_untrusted(self):
        reg,fus=snapshots()
        reg["generated_at"]=fus["generated_at"]=fus["registry_asof"]=z(9)
        with self.assertRaisesRegex(audit.CadenceError,"bad_registry_fusion_clock"):
            audit.evaluate(all_runs(),reg,fus,now=NOW)
        reg,fus=snapshots()
        for lookback in (1,0,True,169):
            with self.subTest(lookback=lookback),self.assertRaises(audit.CadenceError):
                audit.evaluate(all_runs(),reg,fus,now=NOW,lookback_hours=lookback)

    def test_duplicate_input_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"source.json"
            p.write_text('{"schema":"old","schema":"new"}')
            with self.assertRaises(audit.CadenceError):
                audit.read_json(p)

    def test_cli_missing_runs_returns_explicit_unavailable(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder)
            rp=root/"registry.json";fp=root/"fusion.json";out=root/"summary.json"
            reg,fus=snapshots()
            rp.write_text(json.dumps(reg));fp.write_text(json.dumps(fus))
            self.assertEqual(audit.main(["--runs",str(root/"does-not-exist.json"),
                                         "--registry",str(rp),"--fusion",str(fp),
                                         "--output",str(out)]),1)
            result=json.loads(out.read_text())
            self.assertEqual(result["status"],"unavailable")
            self.assertFalse(result["source_continuity_proven"])
            self.assertFalse(result["negative_events_inferred"])

    def test_cli_success_and_inputs_never_modified(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder)
            runs=root/"runs.json";rp=root/"registry.json";fp=root/"fusion.json";out=root/"summary.json"
            reg,fus=snapshots()
            runs.write_text(json.dumps(all_runs()))
            rp.write_text(json.dumps(reg));fp.write_text(json.dumps(fus))
            originals={p:p.read_bytes() for p in (runs,rp,fp)}
            with patch.object(audit,"clock_now",return_value=NOW):
                self.assertEqual(audit.main(["--runs",str(runs),"--registry",str(rp),
                                              "--fusion",str(fp),"--output",str(out)]),0)
            result=json.loads(out.read_text())
            self.assertEqual(result["schema"],audit.SCHEMA)
            self.assertFalse(result["source_continuity_proven"])
            self.assertEqual({p:p.read_bytes() for p in (runs,rp,fp)},originals)


if __name__ == "__main__":
    unittest.main()
