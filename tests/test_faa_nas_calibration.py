"""FAA NAS numerical calibration: coverage, independence and source contract."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from faa_nas_calibration import build, DAY_SCHEMA, SCHEMA, SOURCE_URL, SOURCE_SCHEMA, HEALTH_SCHEMA
from family_archive import update
from dashboard.build_atlas import generate
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,19,20,10,tzinfo=UTC)


def populate(state, now=NOW, affected=10, status="multi_airport_ground_stops"):
    write_json(state/"latest"/"faa_nas.json",{
        "schema":SOURCE_SCHEMA,"source_url":SOURCE_URL,
        "checked_at":now.isoformat().replace("+00:00","Z"),
        "monitored_airport_count":16,"airports_with_any_nas_event":affected,
        "state_fingerprint":"synthetic-pattern",
        "monitored_airport_roster_sha256":"a"*64,
        "status":status,"source_scope":"FAA sampled airports",
    })
    write_json(state/"health"/"faa_nas.json",{
        "schema":HEALTH_SCHEMA,
        "checked_at":now.isoformat().replace("+00:00","Z"),
        "status":"collected",
    })


def dayfile(state, day, n, hour=20, minute=10):
    at=dt.datetime.combine(day,dt.time(hour,minute,tzinfo=UTC))
    write_json(state/"calibration"/"faa_nas"/(day.isoformat()+".json"),{
        "schema":DAY_SCHEMA,"day":day.isoformat(),
        "samples":[{
            "checked_at":at.isoformat(),"value":n,"source_count":16,
            "state_fingerprint":"synthetic-historic",
            "roster_sha256":"a"*64,
            "source_scope":"FAA sampled airports","status":"no_systemic_disruption_in_monitored_sample",
            "source_url":SOURCE_URL,"source_schema":SOURCE_SCHEMA,
        }],
    })


class FaaNasCalibrationTests(unittest.TestCase):
    def test_reference_uses_distinct_days_and_signed_z(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s)
            for i in range(1,15):
                dayfile(s,NOW.date()-dt.timedelta(days=i),2 if i%2 else 4)
            x=build(s,clock=NOW)
            self.assertEqual(x["status"],"calibrated")
            self.assertEqual(x["baseline_days"],14)
            self.assertGreater(x["z_score"],5)
            self.assertTrue(x["candidate_source"])
            m=x["candidate_source"]["calibrated_metric"]
            self.assertEqual(m["comparable_days"],14)
            self.assertEqual(m["metric_family"],"aviation_operations")
            self.assertEqual(m["source_id"],x["candidate_source"]["id"])
            self.assertEqual(x["automatic_warning_count"],0)
            # Same reading replay is not an extra independent observation.
            y=build(s,clock=NOW)
            self.assertEqual(y["sample_count_total_today"],1)

    def test_failure_is_missing_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s)
            h=json.loads((s/"health"/"faa_nas.json").read_text())
            h["status"]="unavailable"
            write_json(s/"health"/"faa_nas.json",h)
            with self.assertRaises(ValueError):
                build(s,clock=NOW)
            self.assertFalse((s/"calibration"/"faa_nas"/(NOW.date().isoformat()+".json")).exists())

    def test_partial_reference_and_zero_variance_no_false_sigma(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s)
            for i in range(1,9):
                dayfile(s,NOW.date()-dt.timedelta(days=i),4)
            x=build(s,clock=NOW)
            self.assertEqual(x["status"],"insufficient_or_zero_variance")
            self.assertIsNone(x["z_score"])
            for i in range(9,16):
                dayfile(s,NOW.date()-dt.timedelta(days=i),4)
            z=build(s,clock=NOW)
            self.assertIsNone(z["z_score"])
            self.assertIsNone(z["candidate_source"]["calibrated_metric"])

    def test_changed_airport_cohort_even_same_count_is_incomparable(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s)
            for i in range(1,18):
                dayfile(s,NOW.date()-dt.timedelta(days=i),3)
                path=s/"calibration"/"faa_nas"/(
                    (NOW.date()-dt.timedelta(days=i)).isoformat()+".json")
                body=json.loads(path.read_text())
                body["samples"][0]["roster_sha256"]="b"*64
                write_json(path,body)
            out=build(s,clock=NOW)
            self.assertEqual(out["baseline_days"],0)
            self.assertIsNone(out["z_score"])

    def test_successful_normal_baseline_not_a_new_family(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s,affected=3,status="no_systemic_disruption_in_monitored_sample")
            for i in range(1,16):
                dayfile(s,NOW.date()-dt.timedelta(days=i),2 if i%2 else 4)
            x=build(s,clock=NOW)
            self.assertEqual(x["status"],"calibrated")
            self.assertLess(abs(x["z_score"]),2)
            self.assertIsNone(x["candidate_source"])

    def test_no_same_clock_sample_day_is_not_imputed_as_zero(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s)
            for i in range(1,20):
                dayfile(s,NOW.date()-dt.timedelta(days=i),3, hour=6)
            x=build(s,clock=NOW)
            self.assertEqual(x["baseline_days"],0)
            self.assertIsNone(x["z_score"])
            self.assertEqual(x["missing_reference_days"],28)

    def test_calibrated_source_adds_to_persistent_family_archive(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d);populate(s)
            for i in range(1,15):
                dayfile(s,NOW.date()-dt.timedelta(days=i),2 if i%2 else 4)
            x=build(s,clock=NOW)
            # The behavioral sensor registry is a separate source, and can be
            # empty even when FAA observations are collected successfully.
            write_json(s/"latest"/"behavioral_registry.json",{
                "schema":"aiba.behavioral-observations.v1","records":[],
                "source_health":{}
            })
            result=update(s,clock=NOW)
            self.assertEqual(result["record_count_total"],1)
            record=result["records"][0]
            self.assertEqual(record["source_family"],"aviation_operations")
            self.assertEqual(record["calibrated_metric"]["source_id"],record["id"])
            self.assertFalse(record["direct_measurement"])
            self.assertEqual(result["alerts_promoted"],0)
            site=s/"site";site.mkdir()
            (site/"index.html").write_text("<p>Synthetic</p>")
            (site/"hotspots.json").write_text('{"asof":"2026-11-19"}')
            published=generate(site,generated=NOW.isoformat(),state_dir=s)
            family=next(x for x in published["dynamic_bins"]["families"]
                        if x["source_families"]==["aviation_operations"])
            self.assertGreater(family["anomaly_metric"]["z_score"],5)
            self.assertFalse(family["source_independence_established"])
            self.assertFalse(family["warning_approved"])
            self.assertEqual(family["evidence_facets"]["profile"],"aviation")


if __name__=="__main__":
    unittest.main()
