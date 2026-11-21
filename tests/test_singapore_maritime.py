"""Singapore MPA measured arrivals: bounded, monthly, official and non-live."""
import datetime as dt
import unittest

from alternative_sensor_pipeline import entry
from cairn_singapore_port import RESOURCE_ID, FEED, DOC, adapt

NOW=dt.datetime(2026,11,20,17,0,tzinfo=dt.timezone.utc)
def response(month="2026-10",number="1250"):
    return {"success":True,"result":{"resource_id":RESOURCE_ID,"total":3048,
             "records":[{"month":month,"vessel_type":"Container",
                         "number_of_vessels":number,"gross_tonnage":"99999.0"},
                        {"month":month,"vessel_type":"Tanker",
                         "number_of_vessels":"850","gross_tonnage":"8000.0"}]}}


class PortStatsTests(unittest.TestCase):
    def test_correct_official_monthly_source_not_live_throughput(self):
        rows=adapt(response(),NOW,FEED,entry)
        self.assertEqual(len(rows),2)
        x=rows[0]
        self.assertEqual(x["provider"],"sg_mpa")
        self.assertEqual(x["source_url"],DOC)
        self.assertIsNone(x["event_at"])
        self.assertIsNone(x["published_at"])
        self.assertIsNone(x["first_seen_at"])
        self.assertEqual(x["source_measurement"]["period"],"2026-10")
        self.assertEqual(x["source_measurement"]["value"],1250)
        self.assertTrue(x["source_measurement"]["not_live_tracking"])
        self.assertEqual(x["source_measurement"]["period_months_lag"],1)
        self.assertEqual(x["source_measurement"]["baseline_status"],"not_calibrated")
        self.assertEqual(x["geography"]["key"],"country:SG")
        self.assertNotIn("calibrated_metric",x)
        self.assertIn("not_current_disruption",x["claim_level"])

    def test_stable_month_and_class_identity_not_poll_clock(self):
        r=adapt(response(),NOW,FEED,entry)[0]
        r2=adapt(response(),NOW+dt.timedelta(hours=1),FEED,entry)[0]
        self.assertEqual(r["id"],r2["id"])
        self.assertEqual(r["root"],r2["root"])
        self.assertNotEqual(r["observed_at"],r2["observed_at"])

    def test_wrong_dataset_duplicate_and_expired_series_fail(self):
        x=response()
        x["result"]["resource_id"]="other"
        with self.assertRaisesRegex(ValueError,"identity"):
            adapt(x,NOW,FEED,entry)
        x=response()
        x["result"]["records"].append(x["result"]["records"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            adapt(x,NOW,FEED,entry)
        x=response("2026-01")
        with self.assertRaisesRegex(ValueError,"currency"):
            adapt(x,NOW,FEED,entry)
        x=response("1995-01")
        with self.assertRaisesRegex(ValueError,"currency"):
            adapt(x,NOW,FEED,entry)

    def test_invalid_numeric_not_treated_as_zero(self):
        x=response(number="-5")
        rows=adapt(x,NOW,FEED,entry)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["source_measurement"]["vessel_type"],"Tanker")
        x=response(number="nan")
        x["result"]["records"][1]["number_of_vessels"]="unreported"
        with self.assertRaisesRegex(ValueError,"no validated"):
            adapt(x,NOW,FEED,entry)


if __name__=="__main__":
    unittest.main()
