"""Brazil ONS verified half-hour grid load: current/UTC, four zones, not outages."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest

from alternative_sensor_pipeline import collect,entry
from cairn_brazil_power import AREAS,BASE,urls,adapt
from ops_pipeline import load_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,20,17,0,tzinfo=UTC)
STAMP="2026-11-18T15:30:00Z"
def sample(area="SECO",stamp=STAMP,val=42653.2):
    return [{"cod_areacarga":area,"din_referenciautc":stamp,"val_cargaglobal":val,
             "val_cargaglobalcons":val-10},
            {"cod_areacarga":area,"din_referenciautc":"2026-11-18T15:00:00Z",
             "val_cargaglobal":45000.9}]

class ONSTests(unittest.TestCase):
    def test_daily_url_four_brazilian_load_areas(self):
        links=urls(NOW)
        self.assertEqual(len(links),4)
        self.assertEqual(set(AREAS),{"SECO","N","NE","S"})
        self.assertTrue(all(u.startswith(BASE) for u in links))
        self.assertTrue(all("dat_inicio=2026-11-18" in u for u in links))

    def test_source_contract_magnitude_timestamp_no_alarm(self):
        row=adapt(sample(),NOW,urls(NOW)[0],entry)[0]
        self.assertEqual(row["source_measurement"]["value"],42653.2)
        self.assertEqual(row["event_at"],STAMP)
        self.assertEqual(row["source_measurement"]["unit"],"MWmed")
        self.assertEqual(row["source_measurement"]["load_area_code"],"SECO")
        self.assertEqual(row["source_measurement"]["baseline_status"],"not_calibrated")
        self.assertTrue(row["source_measurement"]["not_outage_or_attribution"])
        self.assertIsNone(row["geography"]["latitude"])
        self.assertEqual(row["geography"]["key"],"br-ons-loadarea:SECO")
        self.assertFalse(row.get("warning_approved",False))
        self.assertIn("not_outage_or_intent",row["claim_level"])
        self.assertEqual(row["source_measurement"]["sampled_rows"],2)

    def test_official_utc_naive_clock_and_negative_values_supported(self):
        row=adapt(sample(stamp="2026-11-18T15:30:00",val=-1.4),NOW,urls(NOW)[0],entry)[0]
        self.assertEqual(row["event_at"],STAMP)
        self.assertEqual(row["source_measurement"]["value"],-1.4)

    def test_invalid_area_future_or_unparseable_data_fail(self):
        with self.assertRaisesRegex(ValueError,"mismatch"):
            adapt({"wrong":[]},NOW,urls(NOW)[0],entry)
        with self.assertRaisesRegex(ValueError,"lacks valid"):
            adapt(sample(area="NE"),NOW,urls(NOW)[0],entry)
        with self.assertRaisesRegex(ValueError,"lacks valid"):
            adapt(sample(stamp="2026-11-21T19:00:00Z"),NOW,urls(NOW)[0],entry)
        with self.assertRaisesRegex(ValueError,"lacks valid"):
            adapt(sample(val=float("nan")),NOW,urls(NOW)[0],entry)

    def test_partial_independent_zones_and_failed_health(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            def fake(url):
                if "cod_areacarga=SECO" in url:return sample()
                if "cod_areacarga=N&" in url:return sample("N")
                if "cod_areacarga=NE" in url:return sample("NE")
                if "cod_areacarga=S" in url:raise TimeoutError("Region unavailable")
                raise ValueError("unexpected")
            got=collect(base,clock=lambda:NOW,fetcher=fake,selected=("ons_br",))
            self.assertEqual(got["ons_br"]["status"],"partial")
            self.assertEqual(got["ons_br"]["source_queries_attempted"],4)
            self.assertEqual(got["ons_br"]["source_queries_ok"],3)
            self.assertEqual(got["ons_br"]["records"],3)
            snapshot=load_json(base/"latest"/"ons_br.json")
            self.assertEqual(len(snapshot["records"]),3)
            self.assertTrue(all(not r.get("warning_approved",False) for r in snapshot["records"]))
            got=collect(base,clock=lambda:NOW,fetcher=lambda _:(_ for _ in ()).throw(
                TimeoutError("All regional queries down")),selected=("ons_br",))
            self.assertEqual(got["ons_br"]["status"],"unavailable")
            self.assertIsNone(got["ons_br"]["records"])
            self.assertEqual(load_json(base/"latest"/"ons_br.json"),snapshot)

if __name__=="__main__":unittest.main()
