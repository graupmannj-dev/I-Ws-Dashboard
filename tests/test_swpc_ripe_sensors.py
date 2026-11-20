"""Tests for additional SWPC and RIPE public aggregate adapters."""
import datetime as dt
from pathlib import Path
import tempfile
import json
import unittest

from alternative_sensor_pipeline import (
    adapt_swpc,adapt_ripe,collect,urls,MAX_RIPE_PROBES
)
from behavioral_registry import create

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,20,19,0,tzinfo=UTC)


def swpc_payload():
    return [{"product_id":"ALTK05","issue_datetime":"2026-11-20 18:30:00.000",
             "message":"Space Weather Message Code: ALTK05\nSerial Number: 11\nALERT: Geomagnetic K-index of 5"}]


def ripe_payload(n=32):
    timestamp=int(dt.datetime(2026,11,20,18,42,tzinfo=UTC).timestamp())
    return [{"msm_id":1001,"timestamp":timestamp,"prb_id":i,"from":f"203.0.113.{i}",
             "avg":3.5+i/10} for i in range(1,n+1)]


def fetcher(url):
    if "swpc.noaa.gov" in url:return swpc_payload()
    if "atlas.ripe.net" in url:return ripe_payload()
    raise AssertionError("Unexpected public API URL "+url)


class SwpcRipeTests(unittest.TestCase):
    def test_swpc_stable_identity_and_temporal_provenance(self):
        url=urls("swpc",NOW)[0]
        rows=adapt_swpc(swpc_payload(),NOW,url)
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertIn("ALTK05:11:20261120",row["id"])
        self.assertEqual(row["event_at"],"2026-11-20T18:30:00Z")
        self.assertEqual(row["published_at"],"2026-11-20T18:30:00Z")
        self.assertEqual(row["claim_level"],"environmental_context_not_hostile_attribution")
        self.assertEqual(rows,adapt_swpc(swpc_payload(),NOW,url))

    def test_swpc_all_old_bulletins_do_not_mean_zero_physical_activity(self):
        old=[{"product_id":"ALTK05","issue_datetime":"2026-11-01 13:30:00.000",
              "message":"Serial Number: 10\nALERT: old"}]
        self.assertEqual(adapt_swpc(old,NOW,urls("swpc",NOW)[0]),[])
        with self.assertRaisesRegex(ValueError,"list"):
            adapt_swpc({"data":old},NOW,urls("swpc",NOW)[0])

    def test_ripe_global_aggregate_with_denominator_no_probe_privacy_leaks(self):
        rows=adapt_ripe(ripe_payload(),NOW,urls("ripe",NOW)[0])
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row["source_measurement"]["sampled_probe_count"],32)
        self.assertEqual(row["source_measurement"]["valid_rtt_count"],32)
        self.assertEqual(row["source_measurement"]["baseline_status"],"not_calibrated")
        self.assertFalse(row["source_measurement"]["cohort_comparable_to_prior_snapshots"])
        self.assertEqual(row["geography"]["kind"],"global_public_probe_cohort")
        self.assertIsNone(row["geography"]["latitude"])
        self.assertNotIn("prb_id",json.dumps(row))
        self.assertNotIn("203.0.113.",json.dumps(row))

    def test_ripe_provider_sample_failure_not_empty_normal(self):
        with self.assertRaisesRegex(ValueError,"insufficient"):
            adapt_ripe(ripe_payload(3),NOW,urls("ripe",NOW)[0])
        with self.assertRaisesRegex(ValueError,"upper limit"):
            adapt_ripe([{}]*(MAX_RIPE_PROBES+1),NOW,urls("ripe",NOW)[0])

    def test_collector_registry_first_provider_baseline_and_no_warn(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            health=collect(state,clock=lambda:NOW,selected=("swpc","ripe"),fetcher=fetcher)
            self.assertEqual(health["swpc"]["status"],"collected")
            self.assertEqual(health["ripe"]["status"],"collected")
            reg=create(state,clock=lambda:NOW,run_id="swpc-ripe")
            self.assertEqual(reg["first_registry_baseline"],True)
            self.assertEqual(reg["new_after_baseline_count"],0)
            self.assertEqual(len(reg["records"]),2)
            rows={x["collection_mode"]:x for x in reg["records"]}
            self.assertEqual(rows["swpc"]["source_family"],"environmental_context")
            self.assertFalse(rows["swpc"]["direct_observed_behavior"])
            self.assertEqual(rows["ripe"]["source_family"],"internet_reachability")
            self.assertTrue(rows["ripe"]["direct_observed_behavior"])
            self.assertEqual(rows["ripe"]["source_measurement"]["sampled_probe_count"],32)
            self.assertFalse(rows["ripe"]["alert_eligible"])
            self.assertFalse(rows["swpc"]["alert_eligible"])

    def test_failure_isolation_and_old_snapshot_retention(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            collect(state,clock=lambda:NOW,selected=("swpc","ripe"),fetcher=fetcher)
            prior=json.loads((state/"latest"/"ripe.json").read_text())
            def fail_ripe(url):
                if "ripe" in url:raise OSError("upstream temporarily offline")
                return fetcher(url)
            later=NOW+dt.timedelta(hours=1)
            report=collect(state,clock=lambda:later,selected=("swpc","ripe"),fetcher=fail_ripe)
            self.assertEqual(report["ripe"]["status"],"unavailable")
            self.assertEqual(report["swpc"]["status"],"collected")
            self.assertEqual(json.loads((state/"latest"/"ripe.json").read_text()),prior)
            registry=create(state,clock=lambda:later,run_id="retry")
            self.assertEqual(registry["source_health"]["ripe"]["status"],"stale_or_unavailable")
            self.assertEqual(registry["source_health"]["ripe"]["missingness"],"not_measured_not_zero")
            self.assertTrue(all(x["collection_mode"]!="ripe" for x in registry["records"]))


if __name__=="__main__":
    unittest.main()
