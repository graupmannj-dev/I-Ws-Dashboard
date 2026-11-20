"""CAIRN new public sensors: source IDs, time validation, provenance & failure isolation."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest

from alternative_sensor_pipeline import (
    MODES,SCHEMA,adapt_usgs,adapt_eonet,adapt_nws,adapt_usace,adapt_coops,
    collect,urls,
)
from behavioral_registry import create,normalize,SCHEMA as REGISTRY_SCHEMA
from family_archive import update as update_family
from ops_pipeline import load_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,20,17,0,tzinfo=UTC)
STAMP="2026-11-20T16:30:00Z"


def sample(mode):
    if mode=="usgs":
        return {"type":"FeatureCollection","features":[{
            "type":"Feature","id":"us6000test",
            "properties":{"mag":5.1,"title":"M 5.1 - offshore test area",
              "time":int(NOW.timestamp()*1000)-120000,
              "updated":int(NOW.timestamp()*1000)-60000,
              "url":"https://earthquake.usgs.gov/earthquakes/eventpage/us6000test"},
            "geometry":{"type":"Point","coordinates":[140.1,24.2,10]},
        }]}
    if mode=="eonet":
        return {"events":[{
            "id":"EONET_TEST_1","title":"Cyclone in test ocean",
            "link":"https://eonet.gsfc.nasa.gov/api/v3/events/EONET_TEST_1",
            "categories":[{"title":"Severe Storms"}],
            "geometry":[{"date":STAMP,"type":"Point",
                         "geometry":{"type":"Point","coordinates":[142,22]}}],
        }]}
    if mode=="nws":
        return {"type":"FeatureCollection","features":[{
            "properties":{
                "id":"https://api.weather.gov/alerts/urn:oid:TEST",
                "event":"Gale Warning","areaDesc":"Test Marine Zone",
                "severity":"Moderate","sent":STAMP,"onset":STAMP,
            },"geometry":None,
        }]}
    if mode=="usace":
        return {"items":[{
            "controlnumber":205788,"noticeno":"205788",
            "issuedate":STAMP,"begindate":STAMP,
            "waterways":"POOL_05A_UPPER_MISSISSIPPI",
            "noticelink":"https://ndc.ops.usace.army.mil/ords/ntni/print_nav_notice?in_nav_notice_number=205788",
        }],"hasMore":False,"count":1}
    if mode=="coops":
        return {"metadata":{"id":"9414290","name":"San Francisco"},
          "data":[{"t":"2026-11-20 16:30","v":"0.82","s":"0.02",
                   "f":"0,0,0,0","q":"v"}]}


def fake(url):
    if "earthquake.usgs.gov" in url:return sample("usgs")
    if "eonet.gsfc.nasa.gov" in url:return sample("eonet")
    if "api.weather.gov" in url:return sample("nws")
    if "ndc.ops.usace.army.mil" in url:return sample("usace")
    if "api.tidesandcurrents.noaa.gov" in url:return sample("coops")
    raise ValueError("Unexpected source host")


class AlternativeSensorTests(unittest.TestCase):
    def test_all_adapters_stable_identity_and_original_source_context(self):
        for mode,adapter in (("usgs",adapt_usgs),("eonet",adapt_eonet),
                             ("nws",adapt_nws),("usace",adapt_usace),
                             ("coops",adapt_coops)):
            with self.subTest(mode=mode):
                row=adapter(sample(mode),NOW,urls(mode,NOW)[0])[0]
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertEqual(row["provider"],mode)
                self.assertFalse(row.get("warning_approved",False))
                self.assertTrue(row["id"].startswith(mode+":"))
                if mode=="usace":
                    self.assertIsNotNone(row["published_at"])
                else:
                    self.assertIsNotNone(row["event_at"])
                self.assertEqual(row["observed_at"],"2026-11-20T17:00:00Z")
                self.assertNotIn("calibrated_metric",row)
                self.assertIn("not_",row["claim_level"])

    def test_real_zero_event_is_not_error_but_wrong_schema_is(self):
        self.assertEqual(adapt_usgs({"type":"FeatureCollection","features":[]},NOW,
                         urls("usgs",NOW)[0]),[])
        with self.assertRaisesRegex(ValueError,"schema"):
            adapt_eonet({"unexpected":[]},NOW,urls("eonet",NOW)[0])
        with self.assertRaisesRegex(ValueError,"validated"):
            adapt_usace({"items":[{"id":"X"}]},NOW,urls("usace",NOW)[0])

    def test_failed_source_keeps_prior_latest_and_health_marks_missing(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            collect(state,clock=lambda:NOW,fetcher=fake,selected=("usgs","eonet"))
            previous=load_json(state/"latest"/"eonet.json")
            def outage(url):
                if "eonet" in url:raise TimeoutError("Provider timed out")
                return fake(url)
            current=collect(state,clock=lambda:NOW+dt.timedelta(hours=2),
                            fetcher=outage,selected=("usgs","eonet"))
            self.assertEqual(current["usgs"]["status"],"collected")
            self.assertEqual(current["eonet"]["status"],"unavailable")
            self.assertEqual(current["eonet"]["records"],None)
            self.assertEqual(load_json(state/"latest"/"eonet.json"),previous)
            self.assertEqual(load_json(state/"health"/"eonet.json")["missingness"],
                             "not_measured_not_zero")

    def test_all_sources_join_registry_without_automatic_warnings(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            got=collect(state,clock=lambda:NOW,fetcher=fake)
            self.assertEqual(set(got),set(MODES))
            self.assertEqual(got["coops"]["source_queries_attempted"],3)
            self.assertEqual(got["usace"]["source_queries_attempted"],3)
            self.assertEqual(got["coops"]["status"],"partial")
            reg=create(state,clock=lambda:NOW,run_id="integration",write=True)
            self.assertEqual(reg["schema"],REGISTRY_SCHEMA)
            providers={r["collection_mode"] for r in reg["records"]}
            self.assertEqual(providers,set(MODES))
            for row in reg["records"]:
                self.assertFalse(row["alert_eligible"])
                self.assertFalse(row["warning_approved"])
                self.assertIsNotNone(row["information_root"])
                self.assertTrue(row["source_url"].startswith("https://"))
            for mode in MODES:
                self.assertEqual(reg["source_health"][mode]["status"],
                    "current" if mode=="usgs" else "current_partial")
                self.assertTrue(reg["source_health"][mode]["first_provider_baseline"])
            families=update_family(state,clock=NOW,write=False)
            self.assertTrue(families["record_count_total"]>=5)
            self.assertEqual(families["alerts_promoted"],0)
            self.assertTrue(all(row.get("source_family")!="commercial_media"
                                for row in reg["records"]))

    def test_source_clock_and_unverified_geography_are_not_promoted(self):
        row=adapt_usgs(sample("usgs"),NOW,urls("usgs",NOW)[0])[0]
        item,err=normalize("usgs",row,NOW)
        self.assertIsNone(err)
        self.assertEqual(item["geography"]["precision"],"source_supplied_point_only")
        self.assertIsNone(item["geography"]["key"])
        self.assertEqual(item["source_measurement"]["baseline_status"],
                         "not_calibrated")
        row["event_at"]="2026-11-21T18:00:00Z"
        item,err=normalize("usgs",row,NOW)
        self.assertIsNone(item)
        self.assertEqual(err,"source_clock_after_observation")

    def test_station_partial_failure_is_not_a_complete_zero(self):
        def partial(url):
            if "station=8724580" in url:raise TimeoutError("No station record")
            return fake(url)
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            out=collect(state,clock=lambda:NOW,fetcher=partial,selected=("coops",))
            h=out["coops"]
            self.assertEqual(h["status"],"partial")
            self.assertEqual(h["source_queries_ok"],2)
            self.assertEqual(h["records"],2)
            self.assertEqual(len(load_json(state/"latest"/"coops.json")["records"]),2)


if __name__=="__main__":unittest.main()
