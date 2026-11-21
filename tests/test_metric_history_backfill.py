"""Official historical ONS and MPA backfill: bounded, source clocks and readiness."""
import datetime as dt
from pathlib import Path
import tempfile
from urllib.parse import parse_qs,urlsplit
import unittest

from cairn_metric_history_backfill import (
    SCHEMA,ONS_WEEKS,SG_URL,adapt_ons_day,adapt_sg,collect,ons_urls
)
from cairn_metric_baselines import build,full_metric_archive
from ops_pipeline import load_json,write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,20,17,0,tzinfo=UTC)
AREAS=("SECO","N","NE","S")

def ons_day(area,day,missing=0):
    begin=dt.datetime.combine(day,dt.time(0,0),tzinfo=UTC)
    return [{"cod_areacarga":area,
             "din_referenciautc":(begin+dt.timedelta(minutes=30*i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "val_cargaglobal":float({"SECO":30000,"N":5000,"NE":6500,"S":7000}[area]+i)}
            for i in range(48-missing)]

def sg_history():
    values=[]
    for year in range(2023,2027):
        for typ in ("Container","Tanker","Freighter","Bulk Carrier",
                    "Passenger","Barges","Tug","Miscellaneous"):
            values.append({"month":f"{year}-10","vessel_type":typ,
                           "number_of_vessels":str(1200+year-2023)})
    return {"success":True,"result":{"resource_id":
            "d_8f264219109e61fffa87ac64dd5a9a65","records":values}}

def fake(url):
    if "apicarga.ons.org.br" in url:
        query=parse_qs(urlsplit(url).query)
        area=query["cod_areacarga"][0]
        day=dt.date.fromisoformat(query["dat_inicio"][0])
        return ons_day(area,day)
    if "data.gov.sg" in url:return sg_history()
    raise ValueError("Unapproved historical source")

class HistoryBackfillTests(unittest.TestCase):
    def test_publisher_specific_one_day_windows_and_monthly_identity(self):
        urls=list(ons_urls(NOW))
        self.assertEqual(len(urls),4*ONS_WEEKS)
        self.assertEqual(len({(area,day) for area,day,_ in urls}),4*ONS_WEEKS)
        self.assertEqual(urls[0][1],NOW.date()-dt.timedelta(days=2+7))
        area,day,url=urls[0]
        out=adapt_ons_day(fake(url),area,day,url,NOW)
        self.assertEqual(len(out),48)
        self.assertEqual(len({x["event_at"] for x in out}),48)
        self.assertTrue(all(x["historical_backfill"] for x in out))
        self.assertIsNotNone(out[0]["event_at"])
        self.assertEqual(out[0]["source_measurement"]["unit"],"MWmed")
        sg=adapt_sg(sg_history(),SG_URL,NOW)
        self.assertEqual(len(sg),32)
        self.assertEqual(len({(x["source_measurement"]["period"],
                               x["source_measurement"]["vessel_type"]) for x in sg}),32)
        self.assertTrue(all(x["source_measurement"]["not_live_tracking"] for x in sg))

    def test_missing_ons_halfhours_are_not_imputed_as_zero(self):
        area,day,url=list(ons_urls(NOW))[0]
        with self.assertRaisesRegex(ValueError,"coverage"):
            adapt_ons_day(ons_day(area,day,missing=10),area,day,url,NOW)
        out=ons_day(area,day)
        out[0]["val_cargaglobal"]="not-measured"
        with self.assertRaisesRegex(ValueError,"invalid"):
            adapt_ons_day(out,area,day,url,NOW)
        out=ons_day(area,day)
        out[1]["cod_areacarga"]="wrong"
        with self.assertRaisesRegex(ValueError,"unexpected"):
            adapt_ons_day(out,area,day,url,NOW)

    def test_ons_source_date_may_end_in_next_utc_day(self):
        area,day,url=list(ons_urls(NOW))[0]
        rows=ons_day(area,day)
        # A domestic calendar day may have an interval endpoint after
        # midnight UTC; this is not a fabricated second source day.
        rows[0]["din_referenciautc"]=(dt.datetime.combine(
            day+dt.timedelta(days=1),dt.time(0,0),tzinfo=UTC).isoformat())
        result=adapt_ons_day(rows,area,day,url,NOW)
        self.assertEqual(len(result),48)
        rows[0]["din_referenciautc"]=(dt.datetime.combine(
            day+dt.timedelta(days=2),dt.time(0,0),tzinfo=UTC).isoformat())
        with self.assertRaisesRegex(ValueError,"misaligned"):
            adapt_ons_day(rows,area,day,url,NOW)

    def test_singapore_years_and_duplicates_are_required(self):
        with self.assertRaisesRegex(ValueError,"multiple years"):
            adapt_sg({"success":True,"result":{"resource_id":
                 "d_8f264219109e61fffa87ac64dd5a9a65",
                 "records":[{"month":"2026-10","vessel_type":"Container",
                             "number_of_vessels":"23"}]}},SG_URL,NOW)
        broken=sg_history()
        broken["result"]["records"][0]["number_of_vessels"]="-1"
        with self.assertRaisesRegex(ValueError,"outside bounds"):
            adapt_sg(broken,SG_URL,NOW)

    def test_bounded_full_backfill_refresh_and_partial_failure_history_retention(self):
        with tempfile.TemporaryDirectory() as d:
            first=collect(d,clock=lambda:NOW,fetcher=fake)
            self.assertEqual(first["status"],"all_sources_completed")
            self.assertEqual(first["successful_source_windows"],37)
            self.assertEqual(first["records_total"],4*ONS_WEEKS*48+32)
            self.assertFalse(first["baseline_calibrated_as_warning"])
            second=collect(d,clock=lambda:NOW+dt.timedelta(hours=4),fetcher=lambda _:(
                _ for _ in ()).throw(TimeoutError("Should skip"))
            )
            self.assertTrue(second["collection_skipped_due_to_refresh_window"])
            self.assertEqual(second["records_total"],first["records_total"])
            def fail_one(url):
                if "cod_areacarga=SECO" in url:return fake(url)
                if url.endswith("cod_areacarga=N"):raise TimeoutError("temporary area outage")
                return fake(url)
            partial=collect(d,clock=lambda:NOW+dt.timedelta(days=22),fetcher=fail_one)
            self.assertEqual(partial["status"],"partial_failed_source_windows")
            self.assertGreaterEqual(partial["records_total"],first["records_total"])
            self.assertGreater(partial["failed_source_windows"],0)
            self.assertEqual(partial["baseline_calibrated_as_warning"],False)

    def test_backfill_warmstarts_real_comparable_cohort_from_live_archive(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            collect(state,clock=lambda:NOW,fetcher=fake)
            latest_day=(NOW-dt.timedelta(days=2)).date()
            stamp=dt.datetime.combine(latest_day,dt.time(23,30),tzinfo=UTC)
            live={
              "id":"beh:official_live_ons",
              "collection_mode":"ons_br",
              "event_at":stamp.isoformat(),
              "information_root":"ons_br:SECO",
              "source_measurement":{
                 "name":"verified_half_hour_global_load",
                 "value":30047.0,"historical_verified_not_live":True,
                 "load_area_code":"SECO"},
            }
            write_json(state/"family_archive"/"manifest.json",
                {"schema":"aiba.family-archive.v1","bootstrapped":True})
            write_json(state/"family_archive"/"shards"/"01.json",
                {"schema":"aiba.family-archive.v1","roots":{
                  "hash":{"information_root":"ons_br:SECO",
                          "members":{live["id"]:live}}}})
            write_json(state/"latest"/"behavioral_registry.json",
                {"source_health":{"ons_br":{"status":"current_partial"},
                                  "sg_mpa":{"status":"current_partial"}}})
            all_raw=full_metric_archive(state)["records"]
            self.assertEqual(len(all_raw),4*ONS_WEEKS*48+32+1)
            out=build(state,clock=lambda:NOW,write=False)
            region=next(x for x in out["series"] if x["series"]=="br-ons:SECO")
            self.assertEqual(region["status"],"descriptive_matched_cohort")
            self.assertGreaterEqual(region["independent_comparable_periods"],8)
            self.assertIsNone(region["calibrated_conflict_risk"])
            self.assertFalse(region["warning_approved"])
            self.assertEqual(out["warnings_approved"],0)

if __name__=="__main__":unittest.main()
