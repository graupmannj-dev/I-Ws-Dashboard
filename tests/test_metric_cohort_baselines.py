"""Source-matched physical baselines: no fabricated readiness, denominator or warning."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest

from cairn_metric_baselines import (SCHEMA,measure_archive,build,full_metric_archive)
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,20,20,0,tzinfo=UTC)
GOOD={"ons_br":{"status":"current_partial"},"sg_mpa":{"status":"current_partial"}}

def ons(day, value,area="SECO"):
    stamp=day.replace(hour=23,minute=30,second=0,microsecond=0)
    return {"id":"test-ons-"+area+"-"+stamp.isoformat(),
        "collection_mode":"ons_br","event_at":stamp.isoformat(),
        "source_measurement":{"name":"verified_half_hour_global_load",
        "value":value,"historical_verified_not_live":True,
        "load_area_code":area}}

def mpa(year,value=1200,kind="Container"):
    return {"id":"test-mpa-"+str(year)+"-"+kind,
        "collection_mode":"sg_mpa",
        "source_measurement":{"name":"monthly_vessel_arrivals_over_75_gt",
        "period":f"{year}-10","vessel_type":kind,
        "not_live_tracking":True,"value":value}}

def package(rows):
    return {"schema":"aiba.family-archive.v1","records":rows,
        "public_snapshot_truncated":False}

class CohortBaselineTests(unittest.TestCase):
    def test_insufficient_histories_return_null_not_spurious_anomaly(self):
        x=measure_archive(package([ons(NOW-dt.timedelta(days=2),25000),
                                   mpa(2026,900)]),GOOD,NOW)
        self.assertEqual(x["schema"],SCHEMA)
        self.assertEqual(x["series_total"],2)
        for record in x["series"]:
            self.assertEqual(record["status"],"insufficient_or_incomplete_baseline")
            self.assertIsNone(record["historical_median"])
            self.assertIsNone(record["robust_deviation_score"])
            self.assertIsNone(record["calibrated_conflict_risk"])
            self.assertFalse(record["warning_approved"])

    def test_ons_weekday_halfhour_match_and_stale_health(self):
        latest=NOW-dt.timedelta(days=2)
        rows=[ons(latest,119)] + [ons(latest-dt.timedelta(days=7*i),100+i)
                                    for i in range(1,10)]
        # A different weekday and another area must never contaminate
        # this source-specific weekday + half-hour cohort.
        rows += [ons(latest-dt.timedelta(days=1),200000),
                 ons(latest-dt.timedelta(days=7),9,"NE")]
        record=next(x for x in measure_archive(package(rows),GOOD,NOW)["series"]
                    if x["series"]=="br-ons:SECO")
        self.assertEqual(record["status"],"descriptive_matched_cohort")
        self.assertEqual(record["independent_comparable_periods"],9)
        self.assertGreater(record["robust_deviation_score"],0)
        self.assertEqual(record["unit"],"MWmed")
        blocked=next(x for x in measure_archive(package(rows),
                    {"ons_br":{"status":"stale_or_unavailable"}},NOW)["series"]
                    if x["series"]=="br-ons:SECO")
        self.assertIsNone(blocked["robust_deviation_score"])

    def test_mpa_calendar_month_type_and_prior_distinct_years(self):
        rows=[mpa(2026,1500),mpa(2025,1000),mpa(2024,900),mpa(2023,1100),
              mpa(2025,99999,"Tanker"),
              {"collection_mode":"sg_mpa","source_measurement":{
                "name":"monthly_vessel_arrivals_over_75_gt",
                "period":"2026-09","vessel_type":"Container",
                "value":10,"not_live_tracking":True}}]
        result=measure_archive(package(rows),GOOD,NOW)
        main=next(x for x in result["series"] if x["series"]=="sg-mpa:Container")
        self.assertEqual(main["comparable_historical_points"],3)
        self.assertEqual(main["historical_median"],1000)
        self.assertEqual(main["status"],"descriptive_matched_cohort")
        self.assertIsNone(main["directional_hypothesis_evidence"])

    def test_zero_mad_is_not_division_by_zero_or_war_signal(self):
        latest=NOW-dt.timedelta(days=2)
        rows=[ons(latest,111)] + [ons(latest-dt.timedelta(days=7*i),100)
                                    for i in range(1,10)]
        x=measure_archive(package(rows),GOOD,NOW)["series"][0]
        self.assertTrue(x["zero_mad_no_division"])
        self.assertIsNone(x["robust_deviation_score"])

    def test_duplicates_and_truncation_not_hidden(self):
        latest=NOW-dt.timedelta(days=2)
        src=ons(latest,3)
        conflict={**src,"source_measurement":{**src["source_measurement"],"value":4}}
        with self.assertRaisesRegex(ValueError,"Conflicting"):
            measure_archive(package([src,conflict]),GOOD,NOW)
        x=measure_archive({"schema":"aiba.family-archive.v1",
                           "records":[src],"public_snapshot_truncated":True},GOOD,NOW)
        self.assertEqual(x["status"],"archive_public_cache_truncated_no_completeness")
        self.assertEqual(x["series"],[])

    def test_durable_shards_are_complete_even_when_public_cache_is_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            stamp=NOW-dt.timedelta(days=2)
            row=ons(stamp,120)
            shard={"schema":"aiba.family-archive.v1","roots":{
                "root_hash":{"information_root":"ons_root",
                             "members":{"stable_record":row}}}}
            write_json(state/"family_archive"/"manifest.json",
                {"schema":"aiba.family-archive.v1","bootstrapped":True})
            write_json(state/"family_archive"/"shards"/"00.json",shard)
            write_json(state/"latest"/"family_archive.json",{
                "schema":"aiba.family-archive.v1","public_snapshot_truncated":True,"records":[]})
            write_json(state/"latest"/"behavioral_registry.json",
                {"source_health":{"ons_br":{"status":"current_partial"}}})
            self.assertEqual(len(full_metric_archive(state)["records"]),1)
            result=build(state,clock=lambda:NOW)
            self.assertEqual(result["series_total"],1)
            self.assertEqual(result["eligible_anomaly_count"],0)
            self.assertTrue((state/"latest"/"metric_cohort_baselines.json").exists())

if __name__=="__main__":unittest.main()
