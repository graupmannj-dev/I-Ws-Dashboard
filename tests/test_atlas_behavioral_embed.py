"""Unified Atlas behavioral discovery: bounded source provenance, no false threat pins."""
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.behavioral_embed import embed, empty, SCHEMA
from dashboard.build_atlas import generate

STAMP="2026-11-12T19:56:26Z"


def source(group=True, lead=True):
    groups=[{
        "id":"behavioral:source-check-1",
        "status":"cross_family_cooccurrence_unreviewed",
        "warning_level_change":False,
        "geography":{"label":"Synthetic source-declared maritime area",
                     "key":"maritime-area:synthetic", "precision":"source_geography_only",
                     "latitude":18,"longitude":118,"verified_iso":False},
        "first_observed_at":STAMP,"last_observed_at":STAMP,
        "source_family_count":2,
        "distinct_source_families":["internet_reachability","maritime_restriction"],
        "distinct_provider_count":2,"source_root_count":2,
        "assessment":"Unreviewed coincidence, not verified military intent.",
        "source_links":[{
            "url":"https://example.org/notam","provider":"Synthetic restriction",
            "family":"maritime_restriction",
            "first_observed_at":STAMP,"published_at":STAMP
        },{
            "url":"javascript:alert(1)","provider":"Bad link",
            "family":"internet_reachability",
            "first_observed_at":STAMP,"published_at":None
        }]
    }] if group else []
    singles=[{
        "observation_id":"beh:synthetic-1","title":"Synthetic source notification",
        "source_family":"protective_notice","source_url":"https://example.org/info",
        "first_observed_at":STAMP,"source_published_at":STAMP,
        "geography":{"label":"Location unverified","key":None,"precision":"unknown"},
        "requires_geolocation":True,"status":"single_source_unreviewed"
    }] if lead else []
    return {
        "schema":SCHEMA,"generated_at":STAMP,
        "site_snapshot_fresh":False,"site_source_age_hours":3.25,
        "review_groups":groups,"review_groups_count_total":len(groups),
        "new_single_source_leads":singles,"new_single_source_count_total":len(singles),
        "collection_coverage":{
            "ioda":{"status":"current","missingness":"provider_bounded_not_exhaustive",
                    "source_scope":"IODA selected countries","snapshot_at":STAMP},
            "nga":{"status":"stale_or_unavailable","missingness":"not_measured_not_zero",
                    "source_scope":"Unavailable maritime feed","snapshot_at":STAMP},
        },
        "prediction_horizon":None,"forecast_probability":None,
        "approved_warning_count":0,"automated_severity_changes":0,
    }


def setup(site,raw=None):
    (site/"behavior").mkdir(parents=True,exist_ok=True)
    if raw is not None:
        (site/"behavior"/"behavioral_fusion.json").write_text(json.dumps(raw),encoding="utf-8")
    (site/"behavior"/"behavioral_baselines.json").write_text(json.dumps({
        "schema":"aiba.behavioral-provider-baseline.v1","generated_at":STAMP,
        "sources":{"ioda":{"status":"insufficient_history",
                           "comparable_provider_snapshot_days":4,
                           "median_daily_source_snapshot_records":None}}
    }),encoding="utf-8")


class BehavioralEmbedTests(unittest.TestCase):
    def test_unreviewed_groups_and_leads_embedded_without_unverified_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site,source())
            value=embed(site)
        self.assertEqual(value["status"],"read_only_shadow_evidence")
        self.assertEqual(value["cross_family_count_total"],1)
        self.assertEqual(value["single_source_count_total"],1)
        self.assertEqual(value["review_groups"][0]["source_root_count"],2)
        self.assertEqual(value["review_groups"][0]["source_links"][1]["url"],None)
        self.assertNotIn("latitude",json.dumps(value))
        self.assertNotIn("longitude",json.dumps(value))
        self.assertFalse(value["map_coordinates_inferred"])
        self.assertIsNone(value["forecast_probability"])

    def test_source_missing_is_not_calm(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site)
            result=embed(site)
        self.assertEqual(result["status"],"unavailable")
        self.assertFalse(result["source_continuity_proven"])
        self.assertEqual(result["review_groups"],[])
        self.assertEqual(result["reason"],"missing_or_invalid_behavioral_fusion")

    def test_unavailable_providers_are_explicitly_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site,source())
            health=embed(site)["collection_coverage"]
        self.assertEqual(health["nga"]["status"],"stale_or_unavailable")
        self.assertEqual(health["nga"]["missingness"],"not_measured_not_zero")
        self.assertEqual(health["ioda"]["missingness"],"provider_bounded_not_exhaustive")

    def test_baseline_history_is_not_calibration_or_forecast(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site,source())
            val=embed(site)
        self.assertEqual(val["provider_baselines"]["ioda"]["comparable_days"],4)
        self.assertIsNone(val["provider_baselines"]["ioda"]["median_records"])
        self.assertEqual(val["approved_warning_count"],0)

    def test_promotion_and_prospective_probabilities_are_fail_closed(self):
        for key,value in (
            ("approved_warning_count",1),
            ("automated_severity_changes",1),
            ("forecast_probability",0.9),
            ("prediction_horizon","2026-11-15T00:00:00Z"),
        ):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                site=Path(tmp);raw=source();raw[key]=value;setup(site,raw)
                self.assertEqual(embed(site)["status"],"unavailable")

    def test_unexpected_approved_group_rejected(self):
        for key,value in (("status","approved_warning"),
                          ("warning_level_change",True)):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                site=Path(tmp);raw=source();raw["review_groups"][0][key]=value;setup(site,raw)
                self.assertEqual(embed(site)["status"],"unavailable")

    def test_unexpected_single_source_promotion_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);raw=source();raw["new_single_source_leads"][0]["status"]="warning"
            setup(site,raw)
            self.assertEqual(embed(site)["status"],"unavailable")

    def test_invalid_group_and_lead_total_counts_rejected(self):
        for key,value in (("review_groups_count_total",0),("new_single_source_count_total",-1)):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                site=Path(tmp);raw=source();raw[key]=value;setup(site,raw)
                self.assertEqual(embed(site)["status"],"unavailable")

    def test_empty_healthy_collection_does_not_equal_no_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site,source(group=False,lead=False))
            value=embed(site)
        self.assertEqual(value["status"],"read_only_shadow_evidence")
        self.assertFalse(value["source_continuity_proven"])
        self.assertEqual(value["review_groups"],[])
        self.assertEqual(value["new_single_source_leads"],[])

    def test_timestamps_need_explicit_utc_offset(self):
        for raw_stamp in ("2026-11-12T22:00:00","invalid","2026-11-12T18:00:00-05:00"):
            with self.subTest(stamp=raw_stamp),tempfile.TemporaryDirectory() as tmp:
                site=Path(tmp);raw=source();raw["generated_at"]=raw_stamp;setup(site,raw)
                self.assertEqual(embed(site)["status"],"unavailable")

    def test_oversized_file_does_not_get_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site)
            (site/"behavior"/"behavioral_fusion.json").write_text("x"*2_000_001)
            val=embed(site)
        self.assertEqual(val["status"],"unavailable")

    def test_build_one_atlas_embeds_existing_site_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);setup(site,source())
            (site/"index.html").write_text("<html>Existing watchboard</html>")
            (site/"hotspots.json").write_text(json.dumps({
                "asof":"2026-11-06", "hotspots":[],
                "collection_summary":"missing historical data"
            }))
            (site/"collection_status.json").write_text(json.dumps({
                "gdelt":{"recent_days":0,"baseline_days":0}
            }))
            result=generate(site,generated="2026-11-12T23:55:00+00:00")
            out=json.loads((site/"atlas.json").read_text())
            html=(site/"index.html").read_text()
        self.assertEqual(result["behavioral_discovery"]["status"],"read_only_shadow_evidence")
        self.assertEqual(out["behavioral_discovery"]["single_source_count_total"],1)
        self.assertIn('id="tabBehavior"',html)
        self.assertIn('id="openBehavior"',html)
        self.assertIn("Behavioral signals",html)
        self.assertTrue(out["behavioral_discovery"]["map_coordinates_inferred"] is False)


if __name__=="__main__":
    unittest.main()
