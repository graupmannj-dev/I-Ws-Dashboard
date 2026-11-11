"""Source-specific descriptive baselines must not fabricate 28-day exposure."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest

from behavioral_baselines import build,SCHEMA
from behavioral_registry import iso, SCHEMA as REGISTRY_SCHEMA,MODES
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,12,2,22,0,tzinfo=UTC)


def daily(state,day,mode="live_airspace",count=10,new=0,
          health="current",first=False,run="0",time_hour=19):
    stamp=dt.datetime.combine(day,dt.time(time_hour,0),tzinfo=UTC)
    status={m:{"checked_at":None,"status":"stale_or_unavailable"} for m in MODES}
    status[mode]={"checked_at":iso(stamp),"status":health,
                  "first_provider_baseline":first}
    counts={m:None for m in MODES};counts[mode]=count
    novel={m:None for m in MODES};novel[mode]=new
    rows=[{"id":f"new-{mode}-{day}-{n}","collection_mode":mode} for n in range(new)]
    delta={
        "schema":REGISTRY_SCHEMA,"generated_at":iso(stamp),
        "source_health":status,"snapshot_counts_by_mode":counts,
        "first_seen_counts_by_mode":novel,
        "new_records":rows,
    }
    path=state/"history"/"behavioral_registry"/(
        stamp.strftime("%Y%m%dT%H%M%SZ")+f"-{run}.json")
    write_json(path,delta)


class ProviderBaselineTests(unittest.TestCase):
    def test_no_history_yields_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            x=build(s,clock=lambda:NOW,write=False)
            self.assertEqual(x["schema"],SCHEMA)
            self.assertEqual(x["history_deltas_with_per_provider_counts"],0)
            v=x["sources"]["live_airspace"]
            self.assertIsNone(v["current_provider_snapshot_count"])
            self.assertIsNone(v["median_daily_source_snapshot_records"])
            self.assertEqual(v["status"],"insufficient_comparable_source_days")
            self.assertEqual(v["source_days_unobserved_or_uncomparable"],28)
            self.assertFalse(v["warning_eligible"])

    def test_14_observed_days_allow_descriptive_not_predictive_reference(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            for i in range(14):
                day=NOW.date()-dt.timedelta(days=13-i)
                daily(s,day,count=7+i%3,new=(i%4),
                      first=i==0)
            x=build(s,clock=lambda:NOW,write=True,run_id="unit")
            row=x["sources"]["live_airspace"]
            self.assertEqual(row["status"],"descriptive_reference_only")
            self.assertEqual(row["comparable_provider_snapshot_days"],14)
            self.assertEqual(row["daily_first_seen_reviewable_days"],13)
            self.assertEqual(row["initial_baseline_days_excluded"],1)
            self.assertEqual(row["median_daily_source_snapshot_records"],8)
            self.assertIsNone(row["probability_of_conflict"])
            self.assertEqual(x["anomalies_promoted"],0)
            self.assertTrue((s/"latest"/"behavioral_baselines.json").exists())
            self.assertEqual(len(list((s/"history"/"behavioral_baselines").glob("*.json"))),1)

    def test_failed_provider_day_not_filled_as_zero_even_if_healthy_earlier(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            for i in range(14):
                day=NOW.date()-dt.timedelta(days=13-i)
                daily(s,day,count=8,first=i==0)
            bad=NOW.date()-dt.timedelta(days=2)
            daily(s,bad,count=0,new=0,health="stale_or_unavailable",
                  run="outage",time_hour=20)
            v=build(s,clock=lambda:NOW,write=False)["sources"]["live_airspace"]
            self.assertEqual(v["source_days_with_known_interruptions"],1)
            self.assertEqual(v["comparable_provider_snapshot_days"],13)
            self.assertEqual(v["status"],"insufficient_comparable_source_days")

    def test_no_repeated_same_day_source_snapshots_inflation(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            for i in range(20):
                daily(s,NOW.date(),count=12,new=0,run=str(i))
            v=build(s,clock=lambda:NOW,write=False)["sources"]["live_airspace"]
            self.assertEqual(v["source_days_with_usable_snapshots"],1)
            self.assertEqual(v["comparable_provider_snapshot_days"],1)
            self.assertIsNone(v["median_daily_source_snapshot_records"])

    def test_partial_samples_never_mix_with_complete(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            for i in range(28):
                day=NOW.date()-dt.timedelta(days=27-i)
                daily(s,day,count=50 if i%2 else 4,new=0,
                      health="current_partial" if i%2 else "current")
            v=build(s,clock=lambda:NOW,write=False)["sources"]["live_airspace"]
            self.assertEqual(v["comparable_provider_snapshot_days"],14)
            self.assertEqual(v["status"],"descriptive_reference_only")
            self.assertEqual(v["median_daily_source_snapshot_records"],50)

    def test_source_snapshot_carried_over_utc_date_is_not_new_sample(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            day=NOW.date()-dt.timedelta(days=1)
            checked=dt.datetime.combine(day,dt.time(23,50),tzinfo=UTC)
            reported=dt.datetime.combine(NOW.date(),dt.time(0,5),tzinfo=UTC)
            dct={
                "schema":REGISTRY_SCHEMA,"generated_at":iso(reported),
                "source_health":{
                    m:{"checked_at":iso(checked) if m=="live_airspace" else None,
                       "status":"current" if m=="live_airspace" else "stale_or_unavailable"}
                    for m in MODES},
                "snapshot_counts_by_mode":{
                    m:20 if m=="live_airspace" else None for m in MODES},
                "first_seen_counts_by_mode":{
                    m:0 if m=="live_airspace" else None for m in MODES},
                "new_records":[],
            }
            write_json(s/"history"/"behavioral_registry"/
                       (reported.strftime("%Y%m%dT%H%M%SZ")+".json"),dct)
            v=build(s,clock=lambda:NOW,write=False)["sources"]["live_airspace"]
            self.assertEqual(v["source_days_with_usable_snapshots"],0)

    def test_legacy_pre_counter_days_not_assumed_empty(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            stamp=NOW-dt.timedelta(days=1)
            write_json(s/"history"/"behavioral_registry"/
                       (stamp.strftime("%Y%m%dT%H%M%SZ")+".json"),{
                           "schema":REGISTRY_SCHEMA,"generated_at":iso(stamp),
                           "source_health":{},
                           "new_records":[]})
            report=build(s,clock=lambda:NOW,write=False)
            self.assertEqual(report["history_deltas_with_per_provider_counts"],0)
            self.assertEqual(report["sources"]["live_airspace"]["source_days_unobserved_or_uncomparable"],28)

    def test_future_record_and_duplicate_output_refuse_write(self):
        with tempfile.TemporaryDirectory() as d:
            s=Path(d)
            daily(s,NOW.date(),count=3)
            build(s,clock=lambda:NOW,write=True,run_id="same")
            with self.assertRaisesRegex(ValueError,"already exists"):
                build(s,clock=lambda:NOW,write=True,run_id="same")
            future=NOW+dt.timedelta(days=1)
            delta={
                "schema":REGISTRY_SCHEMA,"generated_at":iso(future),
                "source_health":{},"snapshot_counts_by_mode":{},
                "first_seen_counts_by_mode":{},"new_records":[]}
            write_json(s/"history"/"behavioral_registry"/
                       (future.strftime("%Y%m%dT%H%M%SZ")+".json"),delta)
            # Future-dated file with future day is excluded by the
            # calendar index, not silently included as a quiet day.
            report=build(s,clock=lambda:NOW,write=False)
            self.assertEqual(report["history_deltas_with_per_provider_counts"],1)


if __name__=="__main__":
    unittest.main()
