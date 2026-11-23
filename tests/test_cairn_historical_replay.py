"""As-of retrospective diagnostics: no future knowledge and no invented outcome accuracy."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from scripts.cairn_historical_replay import replay, snapshots, SCHEMA

CFG=json.loads((Path(__file__).resolve().parents[1] /
               "data/hypothesis_discriminators.json").read_text())


def source(t, *, title="Taiwan Strait blockade imposed", hint="taiwan",
           mode="official"):
    return {"id":"rec-"+t, "source_url":"https://example.org/"+t,
            "title":title, "first_observed_at":t,
            "collection_mode":mode,"source_family":"media_mention",
            "case_hint":hint}


def snap(t, rows):
    return {"schema":"aiba.behavioral-observations.v1","generated_at":t,
            "records":rows, "source_health":{"official":{"status":"current"},
                                             "live_maritime":{"status":"current"}}}


def at(t, rows):
    return (dt.datetime.fromisoformat(t.replace("Z","+00:00")),
            snap(t,rows),t+".json")


class HistoricalReplayTests(unittest.TestCase):
    def test_actual_snapshots_in_order_and_exclude_future_reports(self):
        first=at("2026-11-21T20:00:00Z",[])
        second=at("2026-11-22T20:00:00Z",[
            source("2026-11-22T10:00:00Z"),
            source("2026-11-23T22:00:00Z")])
        result=replay([first,second],
                      [{"id":"taiwan","signals":[{"date":"2026-11-22",
                        "assessment":"Curated source only"}]}],CFG)
        self.assertEqual(result["schema"],SCHEMA)
        self.assertTrue(result["lookahead_restricted_to_snapshot_asof"])
        self.assertEqual(result["asof_windows"][0]["cases"]["taiwan"]
                         ["linked_source_documents"],0)
        self.assertEqual(result["asof_windows"][1]["cases"]["taiwan"]
                         ["linked_source_documents"],1)
        self.assertEqual(result["reference_signals_within_available_history"],1)
        self.assertIsNone(result["real_event_precision"])
        self.assertIsNone(result["warning_lead_time_hours"])

    def test_missing_collection_days_are_not_negative_observations(self):
        first=at("2026-11-11T20:00:00Z",[])
        last=at("2026-11-15T20:00:00Z",[])
        r=replay([first,last], [{"id":"taiwan","signals":[
            {"date":"2026-11-06","assessment":"Observed"},
            {"date":"2026-11-12","assessment":"Curated"}]}],CFG)
        self.assertEqual(r["history_span_days_inclusive"],5)
        self.assertEqual(r["missing_days"],3)
        self.assertEqual(r["reference_signals_within_available_history"],1)
        self.assertEqual(r["reference_signals_preexisting_or_after_history"],1)
        self.assertIsNone(r["real_event_recall"])

    def test_training_notice_replay_not_escalation_warning(self):
        row=source("2026-11-22T10:00:00Z",title=
                   "Denmark Baltic Sea firing exercises warning",
                   hint=None,mode="live_maritime")
        state=at("2026-11-23T11:00:00Z",[row])
        r=replay([state],[],CFG)
        negative=r["controlled_source_class_audit"]
        self.assertEqual(negative["source_rows_with_literal_training_exercise_titles"],1)
        self.assertEqual(negative["escalation_title_nominations_in_this_subset"],0)

    def test_case_hint_diagnostic_is_not_called_true_event_detection(self):
        row=source("2026-11-22T10:00:00Z",title=
                   "Taiwan Strait unusual naval preparation")
        first=at("2026-11-22T20:00:00Z",[row])
        archive={"schema":"aiba.family-archive.v1","records":[row]}
        r=replay([first],[],CFG,historical_archive=archive)
        d=r["case_hint_diagnostic"]
        self.assertEqual(d["report_count"],0)  # official is not analyst-reviewed
        self.assertTrue(d["not_an_event_detection_recall_measure"])

    def test_no_history_abstains(self):
        result=replay([],[],CFG)
        self.assertEqual(result["status"],"no_historical_source_snapshots")
        self.assertIsNone(result["real_event_precision"])

    def test_snapshot_collapse_uses_latest_per_utc_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/"early.json").write_text(json.dumps(snap("2026-11-20T06:00:00Z",[])))
            (p/"later.json").write_text(json.dumps(snap("2026-11-20T22:00:00Z",[])))
            (p/"tomorrow.json").write_text(json.dumps(snap("2026-11-21T01:00:00Z",[])))
            rows,total=snapshots(p,until=dt.datetime(
                2026,11,20,23,0,tzinfo=dt.timezone.utc))
            self.assertEqual(total,2)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0][2],"later.json")


if __name__=="__main__":
    unittest.main()
