"""CAIRN public provider contracts: bounded samples, failure isolation, provenance."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from alternative_sensor_pipeline import (
    USGS,EONET,SWPC,NWS,USACE_ROOT,RIPE,
    MODES,collect,parse_time,usgs,eonet,swpc,nws,usace,noaa_station,ripe
)
from behavioral_registry import create
from dashboard.dynamic_bins import build as build_families

NOW=dt.datetime(2026,11,20,19,0,tzinfo=dt.timezone.utc)
Z="2026-11-20T18:30:00Z"


def fixtures():
    return {
        "usgs":{"type":"FeatureCollection","features":[{
            "id":"test-quake","type":"Feature",
            "properties":{"mag":5.2,"place":"Coastal test area",
                          "url":"https://earthquake.usgs.gov/earthquakes/eventpage/test-quake",
                          "time":int(parse_time(Z).timestamp()*1000),
                          "updated":int(parse_time(Z).timestamp()*1000)},
            "geometry":{"type":"Point","coordinates":[18,56,14]}
        }]},
        "eonet":{"events":[{
            "id":"EONET_2026_TEST","title":"Severe storm testing",
            "categories":[{"id":"severeStorms","title":"Severe Storms"}],
            "geometry":[{"date":Z,"type":"Point","coordinates":[12,54]}]
        }]},
        "swpc":[{"product_id":"K05A","issue_datetime":"2026-11-20 18:30:00.000",
                 "message":"Space Weather Message Code: ALTK05\\nSerial Number: 11\\nALERT: Geomagnetic K-index of 5"}],
        "nws":{"type":"FeatureCollection","features":[{
            "properties":{"id":"https://api.weather.gov/alerts/test-2026-11",
                          "event":"High Wind Warning","areaDesc":"Test County",
                          "sent":Z},
            "geometry":None
        }]},
        "usace":{"type":"FeatureCollection","features":[{
            "properties":{"NOTICE_ID":"2026TEST01",
                          "TITLE":"Lock closure for maintenance",
                          "WATERWAY":"Test River"},
            "geometry":{"type":"Polygon","coordinates":[]}
        }]},
        "port":{"data":[{"t":"2026-11-20 18:30","s":"5.3","g":"7.2","d":"250"}]},
        "ripe":[{"msm_id":1001,"timestamp":int(parse_time(Z).timestamp()),
                 "prb_id":i,"avg":i/10+5.0,"from":"1.1.1.1"}
                for i in range(1,36)],
    }


def fetcher(url,failed=()):
    def get(query):
        if any(f in query for f in failed):
            raise OSError("Simulated source outage")
        f=fixtures()
        if query.startswith(USGS):return f["usgs"]
        if query.startswith("https://eonet."):return f["eonet"]
        if query.startswith(SWPC):return f["swpc"]
        if query.startswith("https://api.weather."):return f["nws"]
        if query.startswith(USACE_ROOT):return f["usace"]
        if query.startswith("https://api.tidesandcurrents."):return f["port"]
        if query.startswith("https://atlas."):return f["ripe"]
        raise AssertionError("Unexpected endpoint "+query)
    return get


class AlternativeSensorPipelineTests(unittest.TestCase):
    def test_each_parser_preserves_source_identity_and_no_hostile_attribution(self):
        f=fixtures()
        parsed=[
            usgs(f["usgs"],NOW)[0],eonet(f["eonet"],NOW)[0],
            swpc(f["swpc"],NOW)[0],nws(f["nws"],NOW)[0],
            usace(f["usace"],NOW,USACE_ROOT+"/20112026")[0],
            noaa_station(f["port"],NOW,"9414290","San Francisco")[0],
            ripe(f["ripe"],NOW)[0]
        ]
        self.assertEqual(len(parsed),7)
        for rows in parsed:
            self.assertGreaterEqual(len(rows),1)
            for item in rows:
                self.assertTrue(item["source_url"].startswith("https://"))
                self.assertFalse(item["alert_eligible"])
                self.assertIsNone(item["geography"]["latitude"])
                self.assertIsNone(item["geography"]["longitude"])
                self.assertTrue(item["root"])
        wind=parsed[5][0]
        self.assertEqual(wind["observed_measurement"]["value"],5.3)
        self.assertFalse(wind["observed_measurement"]["reference_baseline_ready"])
        net=parsed[6][0]
        self.assertEqual(net["observed_measurement"]["sampled_probe_count"],35)
        self.assertFalse(any("prb_id" in json.dumps(row) or
                             "1.1.1.1" in json.dumps(row) for row in parsed[6]))
        self.assertEqual(net["geography"]["kind"],"multi_probe_measurement_cohort")

    def test_collection_fails_one_provider_without_blocking_others(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            out=collect(state,clock=lambda:NOW,fetcher=fetcher(failed=["weather.gov"]))
            self.assertEqual(out["source_health"]["nws_alerts"]["status"],"unavailable")
            self.assertEqual(out["source_health"]["usgs_quakes"]["status"],"collected")
            self.assertEqual(out["source_health"]["noaa_ports"]["status"],"collected")
            self.assertFalse((state/"latest"/"nws_alerts.json").exists())
            self.assertTrue((state/"health"/"nws_alerts.json").exists())
            self.assertTrue((state/"latest"/"ripe_atlas.json").exists())
            self.assertTrue((state/"latest"/"usace_navigation.json").exists())
            self.assertEqual(out["source_health"]["noaa_ports"]["source_queries_attempted"],4)
            self.assertEqual(out["source_health"]["noaa_ports"]["source_queries_ok"],4)

    def test_first_source_baseline_and_no_false_threat_promotion(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            collect(state,clock=lambda:NOW,fetcher=fetcher())
            result=create(state,clock=lambda:NOW,run_id="baseline")
            self.assertEqual(len(result["source_health"]),len(MODES)+8)
            self.assertEqual(result["new_after_baseline_count"],0)
            self.assertTrue(result["first_registry_baseline"])
            self.assertGreaterEqual(result["record_count"],9)
            for row in result["records"]:
                self.assertFalse(row["alert_eligible"])
                self.assertFalse(row["actor_identified"])
                if row["collection_mode"] in ("usgs_quakes","nasa_eonet","nws_alerts","noaa_swpc"):
                    self.assertEqual(row["claim_level"],
                                     "environmental_confounder_not_conflict_evidence")
                    self.assertFalse(row["direct_observed_behavior"])
                if row["collection_mode"] in ("ripe_atlas","noaa_ports"):
                    self.assertTrue(row["direct_observed_behavior"])
                    self.assertEqual(row["observed_measurement"]["reference_baseline_ready"],False)
            families=build_families(result,{"records":[]},now=NOW)
            self.assertEqual(families["registry_status"],"available")
            self.assertTrue(all(not f.get("warning_approved",False) for f in families["families"]))

    def test_partial_station_and_stale_latest_not_current(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            collect(state,clock=lambda:NOW,fetcher=fetcher(failed=["station=9447130"]))
            h=json.loads((state/"health"/"noaa_ports.json").read_text())
            self.assertEqual(h["status"],"partial")
            self.assertTrue(h["truncated"])
            self.assertEqual(h["source_queries_ok"],3)
            self.assertEqual(len(json.loads((state/"latest"/"noaa_ports.json").read_text())["records"]),3)
            create(state,clock=lambda:NOW,run_id="a")
            second=create(state,clock=lambda:NOW+dt.timedelta(hours=11),run_id="b")
            self.assertEqual(second["source_health"]["noaa_ports"]["status"],"stale_or_unavailable")
            self.assertEqual(second["source_health"]["noaa_ports"]["missingness"],"not_measured_not_zero")
            self.assertEqual(second["record_count"],0)

    def test_restricted_schemas_and_no_fake_zero_readings(self):
        with self.assertRaises(ValueError):
            usace({"foo":[]},NOW,USACE_ROOT+"/20112026")
        with self.assertRaises(ValueError):
            ripe([{"msm_id":1001,"timestamp":int(parse_time(Z).timestamp()),
                   "avg":4.2}],NOW)
        with self.assertRaises(ValueError):
            noaa_station({"data":[{"t":"2026-11-01 18:30","s":"0"}]},NOW,
                         "9414290","San Francisco")
        with self.assertRaises(ValueError):
            nws({"features":[]},NOW)
        self.assertEqual(parse_time("2026-11-20 18:30").utcoffset(),dt.timedelta(0))

    def test_notice_identity_persists_across_days(self):
        f=fixtures()["usace"]
        first=usace(f,NOW,USACE_ROOT+"/20112026")[0][0]
        second=usace(f,NOW+dt.timedelta(days=1),USACE_ROOT+"/21112026")[0][0]
        self.assertEqual(first["root"],second["root"])
        self.assertEqual(first["id"],second["id"])


if __name__=="__main__":
    unittest.main()
