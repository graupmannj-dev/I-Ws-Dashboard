"""Official Taiwan power snapshots and RIPE RIS non-Western operator ASN samples."""
import datetime as dt
import unittest
from alternative_sensor_pipeline import entry,collect,MODES
from cairn_grid_and_bgp import TAIPOWER_URL,RIPE_ASNS,urls,taiwan,ris,taiwan_release
from pathlib import Path
import tempfile
from ops_pipeline import load_json

NOW=dt.datetime(2026,11,20,17,0,tzinfo=dt.timezone.utc)
def taiwan_data(publish="115.11.21(六)00:30",load="2515.6"):
    return {"success":"true","records":[
      {"curr_load":load,"curr_util_rate":"68"},
      {"publish_time":publish,"fore_peak_dema_load":"2850.0"}]}

def ris_data(asn="AS4134",ending="2026-11-20T16:30:00Z"):
    return {"status":"ok","data":{"resource":asn,"resource_type":"asn",
      "query_endtime":ending,"updates":[
         {"starttime":"2026-11-20T16:00:00Z","announcements":7,"withdrawals":None},
         {"starttime":"2026-11-20T15:30:00Z","announcements":10,"withdrawals":None}]}}

class NewSourcesTests(unittest.TestCase):
    def test_taiwan_roc_clock_and_mw_conversion_without_event_time(self):
        rows=taiwan(taiwan_data(),NOW,TAIPOWER_URL,entry)
        self.assertEqual(len(rows),1)
        x=rows[0]
        self.assertEqual(x["published_at"],"2026-11-20T16:30:00Z")
        self.assertIsNone(x["event_at"])
        self.assertEqual(x["source_measurement"]["value"],25156.0)
        self.assertEqual(x["source_measurement"]["unit"],"MW")
        self.assertEqual(x["geography"]["key"],"country:TW")
        self.assertTrue(x["source_measurement"]["measurement_clock_distinct_from_release_not_verified"])
        self.assertIn("not_outage",x["claim_level"])
        self.assertFalse(x.get("warning_approved",False))

    def test_clock_invalid_or_stale_taiwan_never_read_as_healthy(self):
        self.assertIsNone(taiwan_release("2026-11-21 00:30"))
        with self.assertRaisesRegex(ValueError,"stale or future"):
            taiwan(taiwan_data("115.11.20(五)00:30"),NOW,TAIPOWER_URL,entry)
        with self.assertRaisesRegex(ValueError,"not numeric"):
            taiwan(taiwan_data(load="missing"),NOW,TAIPOWER_URL,entry)

    def test_ris_asn_country_hint_not_event_geography(self):
        for link in urls("ris_bgp"):
            from urllib.parse import parse_qs,urlsplit
            asn=parse_qs(urlsplit(link).query)["resource"][0]
            x=ris(ris_data(asn),NOW,link,entry)[0]
            self.assertIn(asn,RIPE_ASNS)
            self.assertEqual(x["geography"]["kind"],"network_resource_not_event_location")
            self.assertFalse(x["geography"]["verified_iso"])
            self.assertEqual(x["source_measurement"]["value"],17)
            self.assertEqual(x["source_measurement"]["returned_sampling_buckets"],2)
            self.assertTrue(x["source_measurement"]["withdrawals_unavailable_for_asn"])
            self.assertTrue(x["source_measurement"]["country_impact_not_established"])
            self.assertIsNone(x["event_at"])
            self.assertIn("not_country_outage",x["claim_level"])

    def test_no_bgp_updates_is_bounded_zero_not_global_all_clear(self):
        u=urls("ris_bgp")[0]
        x=ris({"status":"ok","data":{"resource":"AS4134","resource_type":"asn",
                 "query_endtime":"2026-11-20T16:30:00Z","updates":[]}},
              NOW,u,entry)[0]
        self.assertEqual(x["source_measurement"]["value"],0)
        self.assertFalse(x["source_measurement"]["country_impact_not_established"] is False)
        with self.assertRaisesRegex(ValueError,"wrong resource"):
            ris(ris_data("AS99999"),NOW,u,entry)

    def test_collector_fails_independent_asn_without_blocking_other_asns(self):
        with tempfile.TemporaryDirectory() as d:
            def fake(url):
                if "service.taipower" in url:return taiwan_data()
                if "AS4134" in url:raise TimeoutError("one ASN inaccessible")
                from urllib.parse import parse_qs,urlsplit
                return ris_data(parse_qs(urlsplit(url).query)["resource"][0])
            out=collect(d,clock=lambda:NOW,fetcher=fake,selected=("tw_power","ris_bgp"))
            self.assertEqual(out["tw_power"]["status"],"collected")
            self.assertEqual(out["ris_bgp"]["source_queries_attempted"],6)
            self.assertEqual(out["ris_bgp"]["source_queries_ok"],5)
            self.assertEqual(out["ris_bgp"]["status"],"partial")
            self.assertEqual(out["ris_bgp"]["records"],5)
            self.assertFalse(any(
                r.get("warning_approved") for r in load_json(Path(d)/"latest"/"ris_bgp.json")["records"]))

if __name__=="__main__":unittest.main()
