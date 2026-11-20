"""Synthetic, adversarial tests for separate anomaly and corroboration dimensions."""
import datetime as dt
import unittest

from dashboard.evidence_facets import facets, qualified_metric
from dashboard.dynamic_bins import build

NOW = dt.datetime(2026, 11, 19, 20, tzinfo=dt.timezone.utc)


def source(ident="obs:one", root="root:one", family="airspace_restriction"):
    return {
        "id": ident, "information_root": root,
        "first_observed_at": "2026-11-19T19:00:00Z",
        "source_url": "https://example.org/"+ident.replace(":","-"),
        "title": "Synthetic aircraft notice", "provider": "Test",
        "source_family":family,"source_kind":"notice",
        "collection_mode":"live_airspace",
        "direct_observed_behavior":False,
        "geography":{"key":None,"precision":"source_geography_missing"},
    }


def metric(family="airspace_restriction", observed=19.0, sd=2.0, days=28):
    return {
        "metric":"daily source-defined test measurement","metric_family":family,
        "source_id":"obs:one","unit":"events",
        "observed_window":"2026-11-19","reference_window":"2026-10-15/2026-11-18",
        "observed":observed,"mean":11.0,"sd":sd,
        "comparable_days":days,"reference_sample_count":days,
        "baseline_ready":True,"coverage_current":True,
    }


class FacetAndMagnitudeTests(unittest.TestCase):
    def test_single_official_notice_is_supported_facet_not_confirmed_event(self):
        f=facets([source()])
        self.assertEqual(f["profile"],"aviation")
        by={x["key"]:x for x in f["values"]}
        self.assertEqual(by["source_notice"]["status"],"supported")
        self.assertEqual(by["telemetry"]["status"],"not_measured")
        self.assertEqual(by["contradiction"]["status"],"not_measured")
        self.assertEqual(by["corroboration"]["status"],"not_measured")
        self.assertFalse(f["independent_event_corroboration_established"])

    def test_partially_sampled_source_is_partial_not_proof_of_no_event(self):
        f=facets([source()],{"live_airspace":{"status":"current_partial"}})
        self.assertEqual(f["values"][0]["status"],"partial")
        self.assertEqual(f["values"][1]["coverage_note"],"unmeasured_not_zero")

    def test_media_claim_is_partial_even_when_source_is_current(self):
        x=source(family="commercial_media")
        f=facets([x],{"live_airspace":{"status":"current"}})
        self.assertEqual(f["profile"],"general")
        self.assertEqual(next(z for z in f["values"] if z["key"]=="commercial")["status"],"partial")

    def test_metric_calibration_missing_mismatched_or_zero_variance(self):
        x=source()
        self.assertIsNone(qualified_metric([x])["z_score"])
        cases=[dict(metric(),sd=0),dict(metric(),comparable_days=5),
               dict(metric(),metric_family="maritime_restriction"),
               dict(metric(),baseline_ready=False),dict(metric(),coverage_current=False),
               dict(metric(),mean=float("nan"))]
        for m in cases:
            with self.subTest(metric=m):
                row={**x,"calibrated_metric":m}
                self.assertEqual(qualified_metric([row])["status"],"not_calibrated")

    def test_qualified_z_score_is_signed_and_clipped_only_visually(self):
        x=source();x["calibrated_metric"]=metric()
        result=qualified_metric([x])
        self.assertEqual(result["status"],"calibrated_metric")
        self.assertEqual(result["z_score"],4)
        self.assertFalse(result["clipped_on_axis"])
        x["calibrated_metric"]=metric(observed=-1)
        result=qualified_metric([x])
        self.assertEqual(result["z_score"],-6)
        self.assertTrue(result["clipped_on_axis"])

    def test_extreme_uncorroborated_measurement_outranks_new_uncalibrated_source(self):
        a=source("obs:one","root:old")
        a["first_observed_at"]="2026-11-18T14:00:00Z"
        a["calibrated_metric"]=metric()
        b=source("obs:new","root:new")
        r=build({"schema":"aiba.behavioral-observations.v1",
                 "records":[a,b]}, {"records":[]}, now=NOW)
        self.assertEqual(r["candidate_count_total"],2)
        self.assertIn("root:old",r["families"][0]["sources"][0]["information_root"])
        self.assertFalse(r["families"][0]["source_independence_established"])
        self.assertEqual(r["families"][0]["anomaly_metric"]["z_score"],4)


if __name__=="__main__":
    unittest.main()
