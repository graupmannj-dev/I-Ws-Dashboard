"""Synthetic offline retention loss audits; zero network or actual aircraft geometry."""
import contextlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import aircraft_retention_shadow_audit as audit

DAY = "2026-11-10"
PART_NAME = "v2026.11.10-planes-readsb-prod-0.tar."
SELECTED = "abc123"


def synthetic_points(n=31, spike_km=0):
    start = 1794312000
    return [(start + i*30, 35 + (0.0135 if i == 5 else 0)*spike_km,
             -90 + i*.01, 32000) for i in range(n)]


def envelope(n=31):
    return {"icao": SELECTED, "timestamp": 1794312000,
            "trace": [[i*30, 35, -90 + i*.01, 32000, 400, 90, 0, 0,
                       {"flight":"TEST"}] for i in range(n)]}


def tar(source):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode="w",format=tarfile.USTAR_FORMAT) as stream:
        for name,data in source:
            member=tarfile.TarInfo(name)
            member.size=len(data)
            stream.addfile(member,io.BytesIO(data))
    return output.getvalue()


class ShadowAuditTests(unittest.TestCase):
    def test_straight_leg_can_be_stored_with_fewer_points(self):
        measurement=audit.compare_leg(synthetic_points())
        self.assertLess(measurement["retained_points"],measurement["original_points"])
        self.assertLess(measurement["retained_gzip_bytes"],measurement["original_gzip_bytes"])
        self.assertFalse(measurement["full_bend_probe"])
        self.assertFalse(measurement["reduced_bend_probe"])

    def test_short_lateral_excursion_can_be_lost_below_error_budget(self):
        """2 km tolerance may erase a 1.5 km short maneuver signature."""
        points=synthetic_points(spike_km=1)
        original=audit.segment_event_flags(points)
        measurement=audit.compare_leg(points)
        self.assertTrue(original[0])
        self.assertFalse(measurement["reduced_bend_probe"])
        self.assertLessEqual(measurement["max_reconstruction_km"],2)
        counts={}
        from collections import Counter
        counter=Counter()
        audit.summarize(measurement,counter)
        self.assertEqual(counter["lost_bend_probe"],1)
        self.assertEqual(counter["eligible_shadow_legs"],1)

    def test_altitude_spike_preserved_in_geometry_even_if_event_window_changes(self):
        points=synthetic_points()
        modified=[(*p[:3],(33500 if i==5 else p[3])) for i,p in enumerate(points)]
        m=audit.compare_leg(modified)
        self.assertTrue(m["full_alt_probe"])
        self.assertLessEqual(m["max_reconstruction_altitude_ft"],500)

    def test_invalid_source_day_never_claims_complete(self):
        with self.assertRaisesRegex(audit.ShadowError,"only_frozen"):
            audit.scan_day([],day="2026-11-07")

    def test_fragment_stops_at_ground_stale_and_gap(self):
        sample=envelope(n=65)
        sample["trace"][31][3]="ground"
        sample["trace"][40][6]=1
        from collections import Counter
        cnt=Counter()
        segments=list(audit.extract_segments(sample,DAY,cnt))
        self.assertGreater(cnt["candidate_segments"],1)
        self.assertGreater(cnt["invalid_or_ground_rows"],0)
        self.assertGreater(cnt["source_boundary_rows"],0)
        for seg in segments:
            self.assertTrue(all(seg[i][0] < seg[i+1][0] for i in range(len(seg)-1)))

    def test_sample_tar_and_privacy_safe_aggregate(self):
        body=tar([("./traces/ab/trace_full_abc123.json",
                   json.dumps(envelope()).encode()),
                  ("./traces/ff/trace_full_ffffff.json",
                   json.dumps(envelope()).encode())])
        with tempfile.TemporaryDirectory() as folder,patch.object(
            audit.qa,"hashed_selection",side_effect=lambda name:name==SELECTED
        ):
            root=Path(folder)
            a=root/(PART_NAME+"aa")
            b=root/(PART_NAME+"ab")
            a.write_bytes(body[:2000])
            b.write_bytes(body[2000:])
            result=audit.scan_day([a,b],DAY)
        self.assertEqual(result["status"],"shadow_audit_review_required")
        self.assertTrue(result["source_archive_complete"])
        self.assertEqual(result["counts"]["selected_trace_members"],1)
        self.assertEqual(result["counts"]["eligible_shadow_legs"],1)
        self.assertFalse(result["approved_for_raw_deletion"])
        self.assertFalse(result["actual_alert_detector_comparison"])
        self.assertNotIn("abc123",json.dumps(result))
        self.assertNotIn("TEST",json.dumps(result))
        self.assertNotIn('"lat"',json.dumps(result))

    def test_incomplete_tar_never_releases_partial_counts(self):
        body=tar([("./traces/ab/trace_full_abc123.json",json.dumps(envelope()).encode())])
        with tempfile.TemporaryDirectory() as folder,patch.object(
            audit.qa,"hashed_selection",return_value=True
        ):
            path=Path(folder)/(PART_NAME+"aa")
            path.write_bytes(body[:2400])
            result=audit.scan_day([path],DAY)
        self.assertEqual(result["status"],"incomplete_archive")
        self.assertIsNone(result["counts"])
        self.assertFalse(result["source_archive_complete"])

    def test_excessive_byte_budget_fails_closed(self):
        body=tar([("./traces/ab/trace_full_abc123.json",json.dumps(envelope()).encode())])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/(PART_NAME+"aa")
            path.write_bytes(body)
            result=audit.scan_day([path],DAY,max_bytes=1024)
        self.assertEqual(result["status"],"incomplete_archive")
        self.assertIsNone(result["counts"])

    def test_no_trace_sample_is_not_clean_zero_event(self):
        body=tar([("./traces/ab/trace_full_abc123.json",json.dumps(envelope()).encode())])
        with tempfile.TemporaryDirectory() as folder,patch.object(
            audit.qa,"hashed_selection",return_value=False
        ):
            path=Path(folder)/(PART_NAME+"aa")
            path.write_bytes(body)
            result=audit.scan_day([path],DAY)
        self.assertEqual(result["status"],"insufficient_sample")
        self.assertTrue(result["source_archive_complete"])
        self.assertFalse(result["approved_for_raw_deletion"])

    def test_main_writes_no_data_when_source_missing(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder)
            fake=root/(PART_NAME+"aa")
            out=root/"receipt.json"
            ret=audit.main(["--date",DAY,"--part",str(fake),"--output",str(out)])
            self.assertEqual(ret,1)
            result=json.loads(out.read_text())
        self.assertEqual(result["status"],"unavailable")
        self.assertFalse(result["approved_for_raw_deletion"])


if __name__ == "__main__":
    unittest.main()
