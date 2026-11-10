"""Offline tests for external UCDP outcomes, censoring and lag-only comparisons."""
import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.gdelt_retrospective_eval import (
    HORIZON, OUTCOME_COVERAGE_END, confusion, country_crosswalk,
    evaluate, load_ucdp, outcome_window, seven_28_candidates,
)


FIRST = dt.date(2026, 4, 12)


def data_fixture(folder, n=170):
    out=Path(folder)
    hist=out/"daily.jsonl"
    with hist.open("w") as f:
        for i in range(n):
            d=FIRST+dt.timedelta(days=i)
            # Valid v1 denominator: sum of case counts exactly 1000.
            rec={"day":d.strftime("%Y%m%d"),"rows":1200,"selected":1000,
                 "counts":{"BILAT:RUS:UKR": 80, "DOMESTIC:UKR": 20,
                           "DOMESTIC:RUS": 10,"DOMESTIC:AFG":890}}
            if i==135:
                rec["counts"]["BILAT:RUS:UKR"]=200
                rec["counts"]["DOMESTIC:AFG"]=770
            f.write(json.dumps(rec)+"\n")
    cross=out/"crosswalk.csv"
    cross.write_text("gdelt_code,ucdp_country\nUKR,Ukraine\nRUS,Russia (Soviet Union)\n")
    ucdp=out/"ucdp.csv"
    with ucdp.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["id","country","type_of_violence","date_start","date_end",
                                      "date_prec","event_clarity","code_status","high"])
        w.writeheader()
        w.writerow(dict(id="1",country="Ukraine",type_of_violence="1",
                        date_start="2026-09-03",date_end="2026-09-03",
                        date_prec="1",event_clarity="1",code_status="Clear",high="2"))
        w.writerow(dict(id="2",country="Ukraine",type_of_violence="1",
                        date_start="2026-09-19",date_end="2026-09-22",
                        date_prec="3",event_clarity="1",code_status="Check Geography",high="1"))
    return hist,cross,ucdp


class RetrospectiveTests(unittest.TestCase):
    def test_strict_ucdp_positive_and_ambiguous_windows(self):
        with tempfile.TemporaryDirectory() as d:
            hist,cross,ucdp=data_fixture(d)
            ledger=load_ucdp(ucdp, {"Ukraine"})
            self.assertIn(dt.date(2026,9,3),ledger["exact"]["Ukraine"])
            yes,reason=outcome_window(ledger,"Ukraine",dt.date(2026,9,1))
            self.assertEqual((yes,reason),(1,None))
            uncertain,why=outcome_window(ledger,"Ukraine",dt.date(2026,9,16))
            self.assertIsNone(uncertain)
            self.assertEqual(why,"imprecise_or_uncertain_ucdp_event")
            beyond,why=outcome_window(ledger,"Ukraine",dt.date(2026,9,29))
            self.assertIsNone(beyond)
            self.assertEqual(why,"beyond_ucdp_release")

    def test_no_ucdp_coverage_after_september(self):
        with tempfile.TemporaryDirectory() as d:
            hist,cross,ucdp=data_fixture(d)
            rows,report=evaluate(hist,cross,ucdp)
            self.assertEqual(report["status"],"exploratory_proxy_only")
            self.assertEqual(report["coverage"]["end"],"2026-09-23")
            self.assertTrue(rows)
            self.assertTrue(all(r["day"]<="2026-09-23" for r in rows))
            self.assertEqual({r["gdelt_country_code"] for r in rows},{"UKR"})
            self.assertIn("RUS",report["coverage"]["unmatched_country_codes"])
            self.assertFalse(report["approved_for_alert_promotion"])
            self.assertGreater(report["metrics"]["all_country_days"]["shadow_90d"]["country_days"],0)

    def test_full_90_day_calendar_history_is_required(self):
        with tempfile.TemporaryDirectory() as d:
            hist,cross,ucdp=data_fixture(d,n=80)
            rows,report=evaluate(hist,cross,ucdp)
            self.assertFalse(rows)
            self.assertEqual(report["status"],"insufficient_labeled_coverage")
            self.assertGreater(report["coverage"]["excluded"]["missing_full_90_calendar_day_reference"],0)

    def test_no_prospective_lookahead_in_seven_28(self):
        with tempfile.TemporaryDirectory() as d:
            hist,cross,ucdp=data_fixture(d)
            data=[json.loads(l) for l in hist.read_text().splitlines()]
            by={dt.datetime.strptime(r["day"],"%Y%m%d").date():r for r in data}
            date=FIRST+dt.timedelta(days=55)
            before=seven_28_candidates(by,date)
            future=FIRST+dt.timedelta(days=69)
            by[future]["counts"]["BILAT:RUS:UKR"]=700
            by[future]["counts"]["DOMESTIC:AFG"]=270
            after=seven_28_candidates(by,date)
            self.assertEqual(before,after)

    def test_corrupt_udcp_file_cannot_create_false_negatives(self):
        with tempfile.TemporaryDirectory() as d:
            hist,cross,ucdp=data_fixture(d)
            ucdp.write_text("country,id,date_start\nUkraine,1,2026-09-01\n")
            with self.assertRaisesRegex(ValueError,"required fields"):
                evaluate(hist,cross,ucdp)

    def test_duplicate_crosswalk_does_not_silently_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"crosswalk.csv"
            f.write_text("gdelt_code,ucdp_country\nUKR,Ukraine\nUKR,Other\n")
            with self.assertRaisesRegex(ValueError,"Duplicate"):
                country_crosswalk(f)

    def test_malformed_or_contradictory_ucdp_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            hist,cross,ucdp=data_fixture(d)
            s=ucdp.read_text().splitlines()
            s.append('1,Ukraine,1,2026-09-04,2026-09-04,1,1,Clear,2')
            ucdp.write_text("\n".join(s)+"\n")
            with self.assertRaisesRegex(ValueError,"Contradictory"):
                load_ucdp(ucdp,{"Ukraine"})

    def test_metrics_have_correct_confusion_and_null_denominators(self):
        rows=[
            {"outcome":1,"shadow_90d":1,"prior_14d_quiet":1},
            {"outcome":1,"shadow_90d":0,"prior_14d_quiet":0},
            {"outcome":0,"shadow_90d":1,"prior_14d_quiet":1},
            {"outcome":0,"shadow_90d":0,"prior_14d_quiet":1},
        ]
        m=confusion(rows,"shadow_90d")
        self.assertEqual((m["tp"],m["fp"],m["fn"],m["tn"]),(1,1,1,1))
        self.assertEqual(m["precision"],0.5)
        empty=confusion([],"shadow_90d")
        self.assertIsNone(empty["precision"])
        self.assertEqual(empty["country_days"],0)


if __name__=="__main__":
    unittest.main()
