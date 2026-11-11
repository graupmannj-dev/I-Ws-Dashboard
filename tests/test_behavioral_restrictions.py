"""Integration of real existing official restrictions into AIBA behavioral ledger."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from behavioral_restrictions import adapt, geographic_scope, adapt_layer
from behavioral_registry import create, mode_status, iso
from behavioral_fusion import candidate_observation, converge, build
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,11,3,0,tzinfo=UTC)
AREA={"type":"Polygon",
      "coordinates":[[[-70.0,41.0],[-69.8,41.0],[-69.8,41.2],[-70.0,41.0]]]}
OTHER={"type":"Polygon",
       "coordinates":[[[12,54],[13,54],[13,55],[12,54]]]}
URL1="https://tfr.faa.gov/6_7082.html"
URL2="https://niord.dma.dk/#/message/abcdef"


def row(provider="airspace",now=NOW,polygon=AREA,notice_id=None,change_title=False):
    x={
        "id":notice_id or ("6/7082:0:0" if provider=="airspace" else "abcdef:0:0:0"),
        "title":("Revised official restriction" if change_title else "Scheduled official restriction"),
        "source":"Federal Aviation Administration" if provider=="airspace" else
                 "Danish Maritime Authority",
        "url":URL1 if provider=="airspace" else URL2,
        "geometry":polygon,
        "valid_from":iso(now+dt.timedelta(days=1)),
        "valid_until":iso(now+dt.timedelta(days=2)),
        "date":iso(now-dt.timedelta(hours=1)),
        "in_force":True,
    }
    return x


def put_layers(state,now=NOW,air=None,sea=None,
               air_status="snapshot",sea_status="snapshot"):
    if air is None:air=[]
    if sea is None:sea=[]
    layers={}
    health={}
    for kind,records,status in (("airspace",air,air_status),("maritime",sea,sea_status)):
        layers[kind]={"status":status,"checked_at":iso(now),
                      "records":records if status!="unavailable" else []}
        health[kind]={"status":status,"checked_at":iso(now),
                      "record_count":len(records) if status!="unavailable" else None,
                      "skipped":1 if status=="partial" else 0}
    write_json(state/"latest"/"live_layers.json",{
        "kind":"aiba_restriction_snapshot","version":1,
        "generated_at":iso(now),"layers":layers})
    write_json(state/"health"/"live_layers.json",health)


class RestrictionBehaviorTests(unittest.TestCase):
    def test_scheduled_time_is_not_claimed_event_or_published_time(self):
        rec,err=adapt("live_airspace",row(),NOW)
        self.assertIsNone(err)
        self.assertEqual(rec["restriction_time_state"],"scheduled_not_yet_effective")
        self.assertIsNone(rec["event_at"])
        self.assertIsNone(rec["source_published_at"])
        self.assertEqual(rec["scheduled_valid_from"],iso(NOW+dt.timedelta(days=1)))
        self.assertEqual(rec["geography"]["kind"],"source_notice_footprint")
        self.assertIsNone(rec["geography"]["latitude"])
        self.assertEqual(rec["geography"]["precision"],
                         "provider_defined_notice_boundary_not_event_point")

    def test_notice_versions_share_one_underlying_information_root(self):
        first,_=adapt("live_airspace",row(),NOW)
        revised,_=adapt("live_airspace",row(change_title=True),NOW)
        self.assertNotEqual(first["id"],revised["id"])
        self.assertEqual(first["root"],revised["root"])
        self.assertEqual(first["geography"]["key"],revised["geography"]["key"])

    def test_invalid_geometry_rejected_not_downgraded_to_unlocated(self):
        bad=row(polygon={"type":"Circle","center":[400,90],"radius_km":23})
        adapted,reason=adapt("live_airspace",bad,NOW)
        self.assertIsNone(adapted)
        self.assertEqual(reason,"invalid_notice_geometry")

    def test_naive_updated_at_is_not_invented_utc_publication(self):
        r=row()
        r["date"]="2026-11-10T22:15:00"
        item,err=adapt("live_airspace",r,NOW)
        self.assertIsNone(err)
        self.assertIsNone(item["source_updated_at"])
        self.assertIsNone(item["source_published_at"])

    def test_missing_geometry_remains_unlocated(self):
        r=row()
        del r["geometry"]
        item,err=adapt("live_airspace",r,NOW)
        self.assertIsNone(err)
        self.assertIsNone(item["geography"]["key"])

    def test_ledger_per_provider_first_baseline_then_only_revisions(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            put_layers(state,air=[row()],sea=[row("maritime",polygon=OTHER)])
            first=create(state,clock=lambda:NOW,run_id="base")
            self.assertEqual(first["record_count"],2)
            self.assertEqual(first["new_after_baseline_count"],0)
            self.assertTrue(first["first_registry_baseline"])
            self.assertTrue(first["source_health"]["live_airspace"]["first_provider_baseline"])
            later=NOW+dt.timedelta(minutes=15)
            put_layers(state,later,air=[row(now=NOW)],
                       sea=[row("maritime",now=NOW,polygon=OTHER)])
            second=create(state,clock=lambda:later,run_id="again")
            self.assertEqual(second["new_after_baseline_count"],0)
            self.assertTrue(all(r["registry_novelty"]=="existing" for r in second["records"]))
            revised=row(now=NOW,change_title=True)
            revised["date"]=iso(later-dt.timedelta(minutes=1))
            third_at=later+dt.timedelta(minutes=15)
            put_layers(state,third_at,air=[revised],
                       sea=[row("maritime",now=NOW,polygon=OTHER)])
            third=create(state,clock=lambda:third_at,run_id="revision")
            self.assertEqual(third["new_after_baseline_count"],1)
            item=next(r for r in third["records"] if r["collection_mode"]=="live_airspace")
            self.assertEqual(item["registry_novelty"],"newly_observed")
            self.assertEqual(item["claim_level"],"official_scheduled_restriction_not_military_preparation")
            self.assertEqual(item["source_family"],"airspace_restriction")
            self.assertEqual(item["source_updated_at"],iso(later-dt.timedelta(minutes=1)))
            fusion=build(state,clock=lambda:third_at,run_id="fused")
            self.assertEqual(fusion["new_single_source_count_total"],1)
            self.assertEqual(fusion["review_groups_count_total"],0)
            self.assertEqual(fusion["automated_severity_changes"],0)

    def test_two_authority_sources_same_maritime_family_not_two_confirmations(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            put_layers(state,air=[row()],sea=[row("maritime",polygon=AREA)])
            baseline=create(state,clock=lambda:NOW,run_id="base")
            r=baseline["records"]
            # FAA airspace and Niord maritime can share notice footprints
            # but this is only an investigatory geographic co-occurrence.
            self.assertEqual(r[0]["geography"]["key"],r[1]["geography"]["key"])
            groups,total=converge({a["id"]:a for a in r},
                                  {a["id"] for a in r},NOW)
            self.assertEqual(total,1)
            self.assertFalse(groups[0]["warning_level_change"])
            self.assertEqual(groups[0]["status"],"cross_family_cooccurrence_unreviewed")

    def test_partial_and_failed_official_sources_are_missing_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            put_layers(state,air=[row()],sea=[],air_status="partial",sea_status="unavailable")
            v=create(state,clock=lambda:NOW,run_id="partial")
            self.assertEqual(v["record_count"],1)
            self.assertEqual(v["source_health"]["live_airspace"]["status"],"current_partial")
            self.assertEqual(v["source_health"]["live_maritime"]["status"],"stale_or_unavailable")
            self.assertEqual(v["source_health"]["live_maritime"]["missingness"],"not_measured_not_zero")
            self.assertFalse(v["source_health"]["live_maritime"].get("first_provider_baseline",False))

    def test_known_old_source_revision_does_not_claim_new_preparations(self):
        old=NOW-dt.timedelta(days=9)
        r=row("maritime",polygon=OTHER)
        r["date"]=iso(old)
        v,err=adapt("live_maritime",r,NOW)
        self.assertIsNone(err)
        v["alert_eligible"]=False
        v["first_observed_at"]=iso(NOW)
        v["source_family"]="maritime_restriction"
        v["information_root"]=v["root"]
        allowed,reason=candidate_observation(v,NOW)
        self.assertFalse(allowed)
        self.assertEqual(reason,"old_or_future_source_revision")

    def test_first_live_provider_success_after_initial_failed_check_is_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            put_layers(state,air=[],sea=[],air_status="unavailable",sea_status="unavailable")
            create(state,clock=lambda:NOW,run_id="first")
            then=NOW+dt.timedelta(minutes=15)
            put_layers(state,then,air=[row(now=then)],sea=[],sea_status="unavailable")
            result=create(state,clock=lambda:then,run_id="newprov")
            self.assertEqual(result["record_count"],1)
            self.assertEqual(result["new_after_baseline_count"],0)
            self.assertEqual(result["records"][0]["registry_novelty"],"initial_baseline")


if __name__=="__main__":
    unittest.main()
