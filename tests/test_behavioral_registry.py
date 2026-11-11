"""Behavioral registry source clocks, coverage, geographic uncertainty and replay."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from behavioral_registry import create, normalize, SCHEMA, iso
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,10,21,0,tzinfo=UTC)


def health(state, mode, when=NOW, status="collected"):
    p="friction_"+mode if mode in ("ioda","nga","amsa") else mode
    write_json(state/"health"/(p+".json"),{
        "checked_at":iso(when),"status":status,"truncated":False,
        "source_queries_attempted":1,"source_queries_ok":1})


def set_friction(state, rows, when=NOW, modes=("ioda",)):
    for mode in modes:
        health(state,mode,when)
    write_json(state/"latest"/"friction.json",{
        "collected_at":iso(when),"records":rows,
        "health":{m:{"status":"collected"} for m in modes}})


def set_ops(state, mode, rows, when=NOW, status="collected"):
    health(state,mode,when,status)
    write_json(state/"latest"/(mode+".json"),{
        "observed_at":iso(when),"records":rows,"status":status})


def ioda(id="ioda:x1", country="ZZ", at=NOW, published=None):
    return {"id":id,"provider":"ioda","family":"internet_reachability",
        "entity_type":"country","entity_code":country,"kind":"outage_event",
        "event_at":iso(at-dt.timedelta(minutes=10)),
        "source_published_at":published,
        "collected_at":iso(at),"first_seen_at":iso(at),
        "root":id,"title":"Connectivity change",
        "source_url":"https://ioda.inetintel.cc.gatech.edu/"}


def notice(id="advisory:x1", at=NOW):
    return {"id":id,"publisher":"Government","title":"Country ZZ travel advisory",
            "source_url":"https://gov.example/advice/zz","observed_at":iso(at),
            "published_at":iso(at-dt.timedelta(hours=1))}


class BehavioralRegistryTests(unittest.TestCase):
    def test_global_ioda_code_is_not_restricted_to_watchlist(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            set_friction(state,[ioda(country="NZ")])
            result=create(state,clock=lambda:NOW,run_id="first")
            self.assertEqual(result["record_count"],1)
            r=result["records"][0]
            self.assertEqual(r["geography"]["key"],"country:NZ")
            self.assertEqual(r["geography"]["precision"],"provider_reported_country")
            self.assertFalse(r["geography"]["verified_iso"])
            self.assertTrue(r["direct_observed_behavior"])
            self.assertFalse(r["alert_eligible"])
            self.assertTrue(result["first_registry_baseline"])
            self.assertEqual(result["new_after_baseline_count"],0)
            delta=json.loads(next((state/"history"/"behavioral_registry").glob("*.json")).read_text())
            self.assertEqual(delta["new_records"],[])

    def test_subsequent_new_records_not_realerted_on_recheck(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            set_friction(state,[ioda()])
            create(state,clock=lambda:NOW,run_id="baseline")
            future=NOW+dt.timedelta(hours=1)
            set_friction(state,[ioda(at=future),ioda(id="ioda:x2",country="MU",at=future)],future)
            second=create(state,clock=lambda:future,run_id="second")
            self.assertEqual(second["record_count"],2)
            self.assertEqual(second["new_after_baseline_count"],1)
            records={r["raw_source_id"]:r for r in second["records"]}
            self.assertEqual(records["ioda:x1"]["first_observed_at"],iso(NOW))
            self.assertEqual(records["ioda:x2"]["geography"]["key"],"country:MU")
            self.assertEqual(records["ioda:x1"]["registry_novelty"],"existing")
            again=create(state,clock=lambda:future+dt.timedelta(minutes=1),run_id="third")
            self.assertEqual(again["new_after_baseline_count"],0)
            files=list((state/"history"/"behavioral_registry").glob("*.json"))
            self.assertEqual(len(files),3)

    def test_uncoded_official_and_commercial_are_not_falsely_geolocated(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            set_ops(state,"official",[notice()])
            set_ops(state,"commercial",[{
                "id":"story:1","title":"Airlines reroute over Country ZZ",
                "source_url":"https://news.example/aviation-story",
                "observed_at":iso(NOW),"published_at":iso(NOW),
            }])
            result=create(state,clock=lambda:NOW,run_id="base")
            self.assertEqual(result["record_count"],2)
            records={r["source_family"]:r for r in result["records"]}
            self.assertIsNone(records["protective_notice"]["geography"]["key"])
            self.assertIsNone(records["commercial_media"]["geography"]["key"])
            self.assertEqual(records["commercial_media"]["claim_level"],"news_mention_not_action")
            self.assertFalse(records["commercial_media"]["direct_observed_behavior"])

    def test_health_failure_after_snapshot_is_not_presented_as_current(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            set_friction(state,[ioda()])
            write_json(state/"health"/"friction_ioda.json",{
                "checked_at":iso(NOW+dt.timedelta(minutes=5)),
                "status":"unavailable","records":None})
            result=create(state,clock=lambda:NOW+dt.timedelta(minutes=10),run_id="fail")
            self.assertEqual(result["record_count"],0)
            self.assertEqual(result["source_health"]["ioda"]["missingness"],"not_measured_not_zero")
            self.assertEqual(result["source_health"]["ioda"]["status"],"stale_or_unavailable")

    def test_partial_nonzero_feed_and_unknown_availability(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            set_ops(state,"official",[notice()],status="partial")
            result=create(state,clock=lambda:NOW,run_id="base")
            self.assertEqual(result["source_health"]["official"]["status"],"current_partial")
            self.assertTrue(result["source_health"]["official"]["truncated_or_partial"])
            self.assertEqual(result["source_health"]["amsa"]["status"],"stale_or_unavailable")
            self.assertEqual(result["source_health"]["amsa"]["missingness"],"not_measured_not_zero")

    def test_future_source_time_rejected_not_rescued_by_collection(self):
        row=ioda()
        row["event_at"]=iso(NOW+dt.timedelta(hours=1))
        item,err=normalize("ioda",row,NOW)
        self.assertIsNone(item)
        self.assertEqual(err,"source_clock_after_observation")
        row=ioda()
        row["source_url"]="http://example.org/not-https"
        item,err=normalize("ioda",row,NOW)
        self.assertIsNone(item)
        self.assertEqual(err,"missing_source_id_or_https_url")

    def test_official_maritime_region_does_not_become_point_coordinate(self):
        row={
            "id":"nga:1","provider":"nga","title":"Military hazard notice",
            "source_url":"https://msi.nga.mil/NavWarnings",
            "area":"South Atlantic","event_at":iso(NOW-dt.timedelta(hours=2)),
            "source_published_at":iso(NOW-dt.timedelta(hours=1)),
            "collected_at":iso(NOW)}
        item,err=normalize("nga",row,NOW)
        self.assertIsNone(err)
        self.assertEqual(item["geography"]["key"],"maritime-area:south atlantic")
        self.assertIsNone(item["geography"]["latitude"])
        self.assertFalse(item["direct_observed_behavior"])

    def test_source_identity_root_conflict_fails_closed(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            set_friction(state,[ioda()])
            create(state,clock=lambda:NOW,run_id="baseline")
            future=NOW+dt.timedelta(hours=1)
            changed=ioda(at=future)
            changed["root"]="ioda:different_information_root"
            set_friction(state,[changed],future)
            with self.assertRaisesRegex(ValueError,"Information root"):
                create(state,clock=lambda:future,run_id="second")

    def test_market_expectations_not_behavioral_independent_measurements(self):
        row={"id":"polymarket:123","provider":"polymarket",
             "event":"Exact contract","status":"eligible","price":0.41,
             "source_url":"https://polymarket.com/event/123",
             "observed_at":iso(NOW)}
        item,err=normalize("watchlist",row,NOW)
        self.assertIsNone(err)
        self.assertEqual(item["evidence_class"],"market_quote")
        self.assertFalse(item["direct_observed_behavior"])
        self.assertIsNone(item["geography"]["key"])


if __name__=="__main__":
    unittest.main()
