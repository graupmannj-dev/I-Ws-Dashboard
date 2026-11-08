"""Offline QA of official near-live restriction snapshot publication.

No synthetic geographic warning is ever committed to a production feed.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from dashboard.live_layer_snapshots import (
    clean_row, collect, geometry_is_valid, read, stamp,
)

NOW = dt.datetime(2026, 11, 8, 19, 45, tzinfo=dt.timezone.utc)
BASE = {
    "id":"synthetic-test-001",
    "title":"SYNTHETIC FAA map geometry test (not real)",
    "source":"Fictional official provider",
    "url":"https://example.org/synthetic-notice",
    "valid_from":"2026-11-08T18:00:00Z",
    "valid_until":"2026-11-08T23:00:00Z",
    "detail":"Synthetic only; no real restriction",
}
POLYGON={"type":"Polygon","coordinates":[[[30,20],[31,20],[31,21],[30,21],[30,20]]]}
CIRCLE={"type":"Circle","center":[52,20],"radius_km":50}

def row(name="a",shape=None):
    return {**BASE,"id":f"synthetic-{name}", "geometry":shape or POLYGON}

class LiveLayerSnapshotTest(unittest.TestCase):
    def test_geometry_validation_accepts_sourced_shapes_not_inferred_positions(self):
        for geometry in (POLYGON, CIRCLE,
                         {"type":"BBox","coordinates":[[178,10],[-178,13]]},
                         {"type":"LineString","coordinates":[[45,20],[46,20]]}):
            self.assertTrue(geometry_is_valid(geometry))
            self.assertEqual(clean_row(row(shape=geometry))["geometry"],geometry)
        for geometry in (
            {"type":"Circle","center":[52,20],"radius_km":0},
            {"type":"Circle","center":[52,20],"radius_km":True},
            {"type":"Polygon","coordinates":[[[300,20]]]},
            {"type":"BBox","coordinates":[[-170,10],[170,20]]},
            {"type":"GeometryCollection","geometries":[]},
        ):
            with self.subTest(geometry=geometry):
                self.assertFalse(geometry_is_valid(geometry))
                self.assertIsNone(clean_row(row(shape=geometry)))

    def test_first_snapshot_and_deduplicated_change_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            loaders={"airspace":lambda:[row("faa")],
                     "maritime":lambda:[row("niord",CIRCLE)]}
            a=collect(state,loaders,lambda:NOW)
            self.assertEqual(a["successes"],2)
            self.assertEqual(a["snapshot"]["kind"],"aiba_restriction_snapshot")
            self.assertEqual(a["health"]["airspace"]["record_count"],1)
            self.assertEqual(len(list((state/"history"/"live_layers").glob("*.json"))),1)
            b=collect(state,loaders,lambda:NOW+dt.timedelta(minutes=15))
            self.assertEqual(b["changes"]["airspace"]["new"],[])
            self.assertEqual(b["changes"]["maritime"]["withdrawn"],[])
            self.assertEqual(len(list((state/"history"/"live_layers").glob("*.json"))),1)
            self.assertEqual(b["snapshot"]["generated_at"],"2026-11-08T20:00:00Z")
            self.assertEqual(len(b["snapshot"]["layers"]["maritime"]["records"]),1)

    def test_expiration_or_absence_is_not_confirmed_cancellation(self):
        with tempfile.TemporaryDirectory() as d:
            collect(d,{"airspace":lambda:[row("a")],
                       "maritime":lambda:[row("b",CIRCLE)]},lambda:NOW)
            b=collect(d,{"airspace":lambda:[],
                         "maritime":lambda:[row("b",CIRCLE)]},
                         lambda:NOW+dt.timedelta(minutes=15))
            self.assertEqual(b["changes"]["airspace"]["withdrawn"],["synthetic-a"])
            self.assertFalse(b["changes"]["airspace"]["withdrawal_claimed"])
            self.assertEqual(b["health"]["airspace"]["record_count"],0)

    def test_partial_results_and_failed_sources_never_imply_no_restrictions(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            a=collect(state,{"airspace":lambda:{"records":[row("ok"),row("broken",{
                "type":"Circle","center":[52,20],"radius_km":-1})],"skipped":6},
                       "maritime":lambda:[row("ship",CIRCLE)]},lambda:NOW)
            self.assertEqual(a["health"]["airspace"]["status"],"partial")
            self.assertEqual(a["health"]["airspace"]["record_count"],1)
            def fail():
                raise TimeoutError("Synthetic upstream outage")
            b=collect(state,{"airspace":fail,"maritime":lambda:[]},
                      lambda:NOW+dt.timedelta(minutes=15))
            self.assertEqual(b["health"]["airspace"]["status"],"unavailable")
            self.assertEqual(b["health"]["airspace"]["record_count"],None)
            self.assertEqual(b["health"]["airspace"]["last_success_at"],stamp(NOW))
            self.assertEqual(b["snapshot"]["layers"]["airspace"]["records"],[])
            self.assertEqual(b["changes"]["airspace"]["withdrawn"],[])
            self.assertFalse(b["changes"]["airspace"]["withdrawal_claimed"])
            self.assertEqual(b["successes"],1)
            c=collect(state,{"airspace":fail,"maritime":fail},
                      lambda:NOW+dt.timedelta(minutes=30))
            self.assertEqual(c["successes"],0)
            self.assertEqual(c["snapshot"]["layers"]["airspace"]["status"],"unavailable")
            self.assertTrue((state/"health"/"live_layers.json").is_file())

    def test_rejects_giant_arrays_bad_urls_and_unaware_times(self):
        bad={**BASE,"url":"http://example.org/unsecured"}
        self.assertIsNone(clean_row(bad))
        bad={**BASE,"valid_from":"2026-11-08T18:00:00"}
        self.assertIsNone(clean_row(bad))
        with tempfile.TemporaryDirectory() as d:
            r=collect(d,{"airspace":lambda:[row(str(i)) for i in range(1201)],
                         "maritime":lambda:[]},lambda:NOW)
            self.assertEqual(r["health"]["airspace"]["status"],"unavailable")
            self.assertIsNone(r["health"]["airspace"]["record_count"])
            self.assertEqual(r["successes"],1)


if __name__=="__main__":
    unittest.main()
