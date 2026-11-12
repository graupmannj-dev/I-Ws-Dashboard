"""Synthetic, independent source/issuance/outcome checks for private AIBA ledger."""
import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import aiba_tipper_ledger as ledger
from scripts import aiba_tipper_score as scoring


ISSUE = "2026-11-11T12:00:00Z"
REPORT = "2026-11-12T16:00:00Z"
ADJ = "2026-11-14T01:00:00Z"
HORIZON = "2026-11-13T12:00:00Z"


def issued(tid="watch-001"):
    return {
        "tipper_id": tid, "actors": ["Example state A", "Example state B"],
        "action_key": "cross-border-military-posture-change",
        "country": "US", "location_note": "Synthetic frontier district",
        "consequence": "Synthetic impending confrontation",
        "horizon_end": HORIZON, "confidence": 0.6,
        "evidence": [
            {"family": "civil-aviation", "original_provider": "provider-A",
             "source_id": "notice-123", "observed_at": "2026-11-11T09:00:00Z",
             "available_at": "2026-11-11T10:00:00Z",
             "collected_at": "2026-11-11T11:00:00Z", "quality": "complete"},
            {"family": "internet-routing", "original_provider": "provider-B",
             "source_id": "routing-change-99", "observed_at": "2026-11-11T08:00:00Z",
             "available_at": "2026-11-11T09:00:00Z",
             "collected_at": "2026-11-11T11:30:00Z", "quality": "partial"},
        ],
        "counter_indicators": ["No confirmed independent mobilization signs"],
        "alternatives": ["Civil weather disruption"],
        "analyst_action": "Request independent follow-up on synthetic region",
        "issuer": "synthetic-analyst-1",
    }


def report(tid="watch-001", *, kind="credible_publication", timestamp="2026-11-12T04:00:00Z",
           complete=True):
    return {"tipper_id": tid, "kind": kind, "event_time": timestamp,
            "source_ref": "https://example.invalid/synthetic-report",
            "reviewer": "synthetic-reviewer",
            "publication_scope_reviewed": complete if kind == "credible_publication" else False}


def adjudication(tid="watch-001", *, outcome="matched_event",
                 event_time="2026-11-12T02:00:00Z",
                 verified_through="2026-11-13T23:00:00Z",
                 case_id="synthetic-case-42", revision_reason=None):
    return {"tipper_id": tid, "outcome": outcome, "case_id": case_id,
            "reviewer": "synthetic-reviewer",
            "source_ref": "https://example.invalid/outcome-validation",
            "adjudication_note": "Synthetic case adjudicated against actor, action, location and issued horizon.",
            "event_time": event_time if outcome == "matched_event" else None,
            "actors_match": outcome == "matched_event",
            "action_match": outcome == "matched_event",
            "geography_match": outcome == "matched_event",
            "verified_through": verified_through,
            "revision_reason": revision_reason}


class TipperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "private-ledger.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, kind, value, t):
        return ledger.append(self.path, kind, value, clock=lambda: t)

    def test_timestamped_issuance_and_hash_chained_ledger(self):
        first = self.add("issued", issued(), ISSUE)
        second = self.add("report", report(), REPORT)
        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)
        self.assertNotEqual(first["entry_hash"], second["entry_hash"])
        entries, head = ledger.read_ledger(self.path)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["recorded_at"], ISSUE)
        self.assertEqual(entries[1]["previous_hash"], first["entry_hash"])
        self.assertEqual(head, second["entry_hash"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_no_future_evidence_or_forecast_horizon_hindsight(self):
        d = issued()
        d["evidence"][0]["collected_at"] = "2026-11-11T12:00:01Z"
        with self.assertRaisesRegex(ledger.LedgerError, "evidence_not_available"):
            self.add("issued", d, ISSUE)
        d = issued()
        d["horizon_end"] = "2026-11-11T11:59:59Z"
        with self.assertRaisesRegex(ledger.LedgerError, "forecast_horizon"):
            self.add("issued", d, ISSUE)
        self.assertEqual(self.path.stat().st_size, 0)

    def test_same_underlying_source_cannot_be_counted_twice(self):
        d = issued()
        d["evidence"].append(copy.deepcopy(d["evidence"][0]))
        with self.assertRaisesRegex(ledger.LedgerError, "duplicate_underlying"):
            self.add("issued", d, ISSUE)
        d = issued()
        d["evidence"][0]["available_at"] = "2026-11-11T08:00:00Z"
        with self.assertRaisesRegex(ledger.LedgerError, "evidence_not_available"):
            self.add("issued", d, ISSUE)

    def test_duplicate_tipper_and_missing_reference_rejected(self):
        self.add("issued", issued(), ISSUE)
        with self.assertRaisesRegex(ledger.LedgerError, "already_issued"):
            self.add("issued", issued(), ISSUE)
        with self.assertRaisesRegex(ledger.LedgerError, "unknown_tipper"):
            self.add("report", report("not-issued"), REPORT)
        with self.assertRaisesRegex(ledger.LedgerError, "unknown_tipper"):
            self.add("adjudicated", adjudication("not-issued"), ADJ)

    def test_corrupted_ledger_and_truncation_fail_closed(self):
        self.add("issued", issued(), ISSUE)
        payload = self.path.read_bytes()
        self.path.write_bytes(payload.replace(b"synthetic-analyst-1", b"synthetic-analyst-2"))
        with self.assertRaisesRegex(ledger.LedgerError, "hash_chain_corrupt"):
            ledger.read_ledger(self.path)
        with self.assertRaises(ledger.LedgerError):
            self.add("issued", issued("watch-002"), REPORT)
        self.path.write_bytes(payload[:-1])
        with self.assertRaisesRegex(ledger.LedgerError, "truncated_last_entry"):
            ledger.read_ledger(self.path)

    def test_no_event_must_cover_horizon_and_bad_match_disallowed(self):
        self.add("issued", issued(), ISSUE)
        d=adjudication(outcome="no_event", verified_through="2026-11-12T23:00:00Z")
        with self.assertRaisesRegex(ledger.LedgerError,"complete_forecast_window"):
            self.add("adjudicated", d, ADJ)
        d=adjudication()
        d["geography_match"]=False
        with self.assertRaisesRegex(ledger.LedgerError,"explicit_actor_action_geography"):
            self.add("adjudicated",d,ADJ)
        self.assertEqual(len(ledger.read_ledger(self.path)[0]),1)

    def test_revisions_append_not_overwrite(self):
        self.add("issued",issued(),ISSUE)
        first=self.add("adjudicated",adjudication(outcome="censored"),ADJ)
        with self.assertRaisesRegex(ledger.LedgerError,"requires_explanation"):
            self.add("adjudicated",adjudication(),ADJ)
        revised=adjudication(revision_reason="A second independent source corrected the initial data window.")
        second=self.add("adjudicated",revised,ADJ)
        self.assertNotEqual(first["entry_hash"],second["entry_hash"])
        self.assertEqual(len(ledger.read_ledger(self.path)[0]),3)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["adjudication_revisions"],1)
        self.assertEqual(s["counts"]["resolved_matched_in_horizon"],1)

    def test_gdelt_cannot_masquerade_as_credible_first_article(self):
        self.add("issued",issued(),ISSUE)
        self.add("report",report(kind="gdelt_first_seen",
                                 timestamp="2026-11-12T06:00:00Z"),REPORT)
        self.add("adjudicated",adjudication(),ADJ)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["counts"]["matched_without_complete_publication_review"],1)
        self.assertEqual(s["pre_publication_leads_seconds"]["count"],0)
        bad=report(kind="gdelt_first_seen")
        bad["publication_scope_reviewed"]=True
        with self.assertRaisesRegex(ledger.LedgerError,"gdelt_not_credible"):
            self.add("report",bad,ADJ)

    def test_true_prepublication_lead_and_nonnews_ingestion_gap(self):
        self.add("issued",issued(),ISSUE)
        self.add("report",report(),REPORT)
        self.add("report",report(kind="gdelt_first_seen",
                                 timestamp="2026-11-12T06:00:00Z"),REPORT)
        self.add("adjudicated",adjudication(),ADJ)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["counts"]["resolved_forecasts"],1)
        self.assertEqual(s["counts"]["resolved_matched_in_horizon"],1)
        self.assertEqual(s["counts"]["matched_tipper_before_reviewed_publication"],1)
        self.assertEqual(s["pre_publication_leads_seconds"]["median"],57600)
        self.assertEqual(s["gdelt_observation_delay_seconds"]["minimum"],7200)
        self.assertIsNone(s["recall"])
        self.assertIsNone(s["false_alarms_per_analyst_day"])
        self.assertFalse(s["time_anchoring_verified"])

    def test_article_published_before_issue_means_no_early_warning(self):
        self.add("issued",issued(),ISSUE)
        self.add("report",report(timestamp="2026-11-11T09:00:00Z"),REPORT)
        self.add("adjudicated",adjudication(),ADJ)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["counts"]["matched_tipper_not_before_publication"],1)
        self.assertEqual(s["pre_publication_leads_seconds"]["count"],0)

    def test_no_event_score_requires_review_and_does_not_generate_recall(self):
        self.add("issued",issued(),ISSUE)
        self.add("adjudicated",adjudication(outcome="no_event"),ADJ)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["counts"]["resolved_forecasts"],1)
        self.assertEqual(s["resolved_forecast_false_warning_fraction"],1)
        self.assertEqual(s["mean_brier_for_resolved_tippers"],0.36)
        self.assertIsNone(s["recall"])
        self.assertFalse(s["production_warning_updates"])

    def test_unadjudicated_and_censored_not_false_alarms(self):
        self.add("issued",issued("watch-001"),ISSUE)
        self.add("issued",issued("watch-002"),ISSUE)
        self.add("adjudicated",adjudication("watch-002",outcome="censored"),ADJ)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["counts"]["unadjudicated_not_negative"],1)
        self.assertEqual(s["counts"]["unscorable_censored"],1)
        self.assertIsNone(s["resolved_forecast_hit_fraction"])
        self.assertIsNone(s["mean_brier_for_resolved_tippers"])

    def test_duplicate_case_not_independent_warning_success(self):
        for ident in ("watch-001","watch-002"):
            self.add("issued",issued(ident),ISSUE)
        for ident in ("watch-001","watch-002"):
            self.add("adjudicated",adjudication(ident),ADJ)
        s=scoring.score_ledger(self.path)
        self.assertEqual(s["counts"]["resolved_matched_in_horizon"],2)
        self.assertEqual(s["duplicate_event_cases_among_hits"],1)

    def test_local_clock_regression_blocked_and_no_hindsight_injection(self):
        self.add("issued",issued(),ISSUE)
        with self.assertRaisesRegex(ledger.LedgerError,"moved_backwards"):
            self.add("report",report(),"2026-11-11T11:59:59Z")
        with self.assertRaisesRegex(ledger.LedgerError,"timestamp_in_future"):
            self.add("report",report(timestamp="2026-11-14T00:00:00Z"),REPORT)

    def test_confidence_bool_nonfinite_and_manual_review_flags_rejected(self):
        for value in (True,float("nan"),float("inf"),0,1):
            with self.subTest(value=value):
                d=issued()
                d["confidence"]=value
                with self.assertRaises(ledger.LedgerError):
                    self.add("issued",d,ISSUE)
        self.add("issued",issued(),ISSUE)
        r=report()
        r["publication_scope_reviewed"]=1
        with self.assertRaisesRegex(ledger.LedgerError,"review_state"):
            self.add("report",r,REPORT)

    def test_cli_private_location_and_failed_score_cannot_replace_ledger(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            folder=Path(tmp)
            payload=folder/"issue.json"
            payload.write_text(json.dumps(issued()))
            # The real CLI uses current UTC and must refuse historical horizon,
            # but it must never write to Git or return the raw payload.
            ret=ledger.main(["verify","--ledger",str(root/"secret-should-not-exist.jsonl")])
            self.assertEqual(ret,1)
            self.add("issued",issued(),ISSUE)
            source=self.path.read_bytes()
            self.assertEqual(scoring.main(["--ledger",str(self.path),
                                           "--output",str(self.path)]),1)
            self.assertEqual(self.path.read_bytes(),source)

    def test_invalid_ledger_score_returns_unavailable_not_zeros(self):
        self.path.write_bytes(b"{bad\n")
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            out=Path(folder)/"score.json"
            self.assertEqual(scoring.main(["--ledger",str(self.path),
                                           "--output",str(out)]),1)
            val=json.loads(out.read_text())
            self.assertEqual(val["status"],"unavailable")
            self.assertIsNone(val["counts"])
            self.assertIsNone(val["recall"])


if __name__ == "__main__":
    unittest.main()
