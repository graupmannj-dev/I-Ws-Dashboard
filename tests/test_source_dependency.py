"""USGS/BMKG same-physical-event audit without fabricated independence."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from cairn_source_dependency import SCHEMA,build,collect,utc
from ops_pipeline import write_json

NOW=dt.datetime(2026,11,20,20,0,tzinfo=dt.timezone.utc)
T="2026-11-20T19:30:00Z"

def item(mode,ident,T=T,lat=-6.0,lon=125.0,mag=5.3):
    return {"provider":mode,"id":mode+":"+ident,"event_at":T,
      "source_url":"https://example.org/"+ident,
      "geography":{"latitude":lat,"longitude":lon},
      "source_measurement":{"name":"earthquake_magnitude","value":mag}}

def input_set(usgs,bmkg):
    shots={};receipts={}
    for mode,rows in (("usgs",usgs),("bmkg_quake",bmkg)):
        shots[mode]={"schema":"cairn.alternative-sensors.v1","mode":mode,
              "observed_at":NOW.isoformat(),"records":rows}
        receipts[mode]={"mode":mode,"status":"partial","checked_at":NOW.isoformat()}
    return shots,receipts

class IdentityTests(unittest.TestCase):
    def test_one_physical_event_two_authorities_not_two_events(self):
        inputs,health=input_set([item("usgs","us1")],
                     [item("bmkg_quake","id2",lat=-6.1,lon=125.05,mag=5.4)])
        r=build(inputs,health,NOW)
        self.assertEqual(r["schema"],SCHEMA)
        self.assertTrue(r["comparison_available"])
        self.assertEqual(len(r["candidate_common_event_pairs"]),1)
        self.assertIn("unreviewed",r["candidate_common_event_pairs"][0]["status"])
        self.assertIsNone(r["independent_physical_event_count_estimated"])
        self.assertEqual(r["approved_corroborations"],0)
        self.assertFalse(r["warning_approved"])
        self.assertTrue(all(not x["independent_new_observer"] for x in r["publisher_relay_rules"]))

    def test_far_offshore_or_different_clock_mag_stays_unpaired(self):
        for different in (
            item("bmkg_quake","x",lat=1,lon=130),
            item("bmkg_quake","x",T="2026-11-20T18:20:00Z"),
            item("bmkg_quake","x",mag=7.3),
        ):
            with self.subTest(other=different):
                snapshots,health=input_set([item("usgs","y")],[different])
                r=build(snapshots,health,NOW)
                self.assertEqual(r["candidate_common_event_pairs"],[])
                self.assertIsNone(r["independent_physical_event_count_estimated"])

    def test_ambiguous_many_to_one_cannot_be_forced_as_distinct(self):
        snaps,health=input_set(
            [item("usgs","a"),item("usgs","b",lat=-6.01)],
            [item("bmkg_quake","one",lat=-6.02)])
        r=build(snaps,health,NOW)
        self.assertEqual(len(r["ambiguous_pair_candidates"]),2)
        self.assertEqual(len(r["candidate_common_event_pairs"]),0)

    def test_stale_or_unavailable_feed_has_no_negative_implication(self):
        s,h=input_set([item("usgs","a")],[item("bmkg_quake","b")])
        h["bmkg_quake"]["status"]="unavailable"
        r=build(s,h,NOW)
        self.assertFalse(r["comparison_available"])
        self.assertIsNone(r["checked_recent_event_counts"]["bmkg_quake"])
        self.assertIsNone(r["independent_physical_event_count_estimated"])
        h["bmkg_quake"]["status"]="partial"
        h["bmkg_quake"]["checked_at"]="2026-11-18T10:00:00Z"
        self.assertFalse(build(s,h,NOW)["comparison_available"])

    def test_zero_earthquakes_in_bounded_feed_not_all_clear(self):
        s,h=input_set([],[])
        r=build(s,h,NOW)
        self.assertTrue(r["comparison_available"])
        self.assertEqual(r["checked_recent_event_counts"],{"usgs":0,"bmkg_quake":0})
        self.assertIsNone(r["independent_physical_event_count_estimated"])
        self.assertEqual(r["candidate_common_event_pairs"],[])

    def test_archive_and_health_output(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            s,h=input_set([item("usgs","a")],[item("bmkg_quake","b")])
            for mode in s:
                write_json(base/"latest"/(mode+".json"),s[mode])
                write_json(base/"health"/(mode+".json"),h[mode])
            out=collect(base,clock=lambda:NOW)
            self.assertTrue(out["comparison_available"])
            self.assertTrue((base/"latest"/"source_dependency_audit.json").exists())

if __name__=="__main__":unittest.main()
