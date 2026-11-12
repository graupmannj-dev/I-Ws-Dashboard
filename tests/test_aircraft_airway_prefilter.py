"""Synthetic official-schema FAA airway proximity screening tests; no network."""
import contextlib
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import aircraft_airway_prefilter as app


DAY = "2026-11-10"


def epoch(day=DAY):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def network(features=None, start="2026-10-29", end="2026-11-26"):
    if features is None:
        features = [{"route_id": "Q102", "geometry_lonlat": [[-90.0, 35.0], [-85.0, 35.0]]}]
    return {"schema": app.NETWORK_SCHEMA, "source": "FAA NASR",
            "scope": "CONUS_J_Q_published_only",
            "source_page": app.FAA_NASR_URL, "effective_from": start,
            "effective_until_exclusive": end, "scope_bbox": app.CONUS.copy(),
            "source_dataset_completeness_verified": False,
            "flight_plan_assignment_known": False, "features": features}


def leg(shift=0, day=DAY, alt=32000, count=11):
    start = epoch(day) + 12 * 3600
    return {"flight_id": "sample", "coverage": "complete",
            "points": [{"t": start+i*180, "lat": 35+shift,
                        "lon": -89.5+i*.3, "altitude_ft": alt}
                       for i in range(count)]}


def screen(legs=None, routes=None, width=25):
    return app.screen(routes or network(), {"schema": app.INPUT_SCHEMA, "day": DAY,
                                              "legs": legs or [leg()]}, width=width)


def csvfile(folder, filename, fields, rows):
    path = Path(folder)/filename
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def nasr_fixture(folder):
    ffields = ["EFF_DATE", "FIX_ID", "LAT_DECIMAL", "LONG_DECIMAL"]
    nfields = ["EFF_DATE", "NAV_ID", "LAT_DECIMAL", "LONG_DECIMAL"]
    afields = ["EFF_DATE", "AWY_ID", "POINT_SEQ", "FROM_POINT", "TO_POINT",
               "AWY_SEG_GAP_FLAG", "SIGNAL_GAP_FLAG", "MEA_GAP"]
    fixed = "2026/10/29"
    fdata = [{"EFF_DATE": fixed, "FIX_ID": name, "LAT_DECIMAL": lat, "LONG_DECIMAL": lon}
             for name, lat, lon in [("A", 35, -90), ("B", 35, -87), ("C", 35, -85)]]
    ndata = [{"EFF_DATE": fixed, "NAV_ID": "Z", "LAT_DECIMAL": 35, "LONG_DECIMAL": -84}]
    adata = [
        {"EFF_DATE": fixed, "AWY_ID": "Q102", "POINT_SEQ": "10", "FROM_POINT": "A",
         "TO_POINT": "B", "AWY_SEG_GAP_FLAG": "N", "SIGNAL_GAP_FLAG": "N", "MEA_GAP": "N"},
        {"EFF_DATE": fixed, "AWY_ID": "Q102", "POINT_SEQ": "20", "FROM_POINT": "B",
         "TO_POINT": "C", "AWY_SEG_GAP_FLAG": "N", "SIGNAL_GAP_FLAG": "N", "MEA_GAP": "N"},
        {"EFF_DATE": fixed, "AWY_ID": "J80", "POINT_SEQ": "10", "FROM_POINT": "C",
         "TO_POINT": "Z", "AWY_SEG_GAP_FLAG": "N", "SIGNAL_GAP_FLAG": "N", "MEA_GAP": "N"},
        {"EFF_DATE": fixed, "AWY_ID": "V14", "POINT_SEQ": "10", "FROM_POINT": "C",
         "TO_POINT": "Z", "AWY_SEG_GAP_FLAG": "N", "SIGNAL_GAP_FLAG": "N", "MEA_GAP": "N"},
    ]
    return (csvfile(folder, "AWY_SEG_ALT.csv", afields, adata),
            csvfile(folder, "FIX_BASE.csv", ffields, fdata),
            csvfile(folder, "NAV_BASE.csv", nfields, ndata))


class FaaNasrAirwayPrefilterTests(unittest.TestCase):
    def test_nasr_translation_resolves_only_j_and_q(self):
        with tempfile.TemporaryDirectory() as d:
            awy, fix, nav = nasr_fixture(d)
            result = app.nasr_network(awy, fix, nav, "2026-10-29", "2026-11-26")
        self.assertEqual(result["counts"]["mapped_segments"], 3)
        self.assertEqual(result["counts"]["j_q_rows"], 3)
        self.assertEqual(result["scope"], "CONUS_J_Q_published_only")
        self.assertEqual(set(f["route_class"] for f in result["features"]), {"J", "Q"})
        self.assertFalse(result["source_dataset_completeness_verified"])
        self.assertEqual(len(result["input_sha256"]), 3)
        self.assertEqual(app.screen(result, {"schema": app.INPUT_SCHEMA, "day": DAY,
                                             "legs": [leg()]})["results"][0]["status"],
                         "network_proximity_only")

    def test_missing_and_ambiguous_fixes_never_fabricated_as_segments(self):
        with tempfile.TemporaryDirectory() as d:
            awy, fix, nav = nasr_fixture(d)
            with fix.open("a") as stream:
                stream.write("2026/10/29,A,44,-75\n")
            with nav.open("a") as stream:
                stream.write("2026/10/29,B,44,-74\n")
            result = app.nasr_network(awy, fix, nav, "2026-10-29", "2026-11-26")
        self.assertEqual(result["counts"]["mapped_segments"], 1)
        self.assertEqual(result["counts"]["missing_or_ambiguous_fix"], 2)

    def test_gapped_or_unusable_ats_segments_are_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            awy, fix, nav = nasr_fixture(d)
            content=awy.read_text()
            content=content.replace("Q102,10,A,B,N,N,N", "Q102,10,A,B,Y,N,N")
            content=content.replace("Q102,20,B,C,N,N,N", "Q102,20,B,C,N,Y,N")
            awy.write_text(content)
            result=app.nasr_network(awy, fix, nav, "2026-10-29", "2026-11-26")
        self.assertEqual(result["counts"]["mapped_segments"], 1)
        self.assertEqual(result["counts"]["flagged_route_or_signal_gap"], 2)
        self.assertEqual(result["features"][0]["route_id"],"J80")

    def test_mixed_nasr_cycle_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            awy,fix,nav=nasr_fixture(d)
            with fix.open("a") as stream:
                stream.write("2026/10/01,FAR,30,-80\n")
            with self.assertRaisesRegex(app.AirwayError, "mixed_nasr"):
                app.nasr_network(awy,fix,nav,"2026-10-29","2026-11-26")

    def test_wrong_csv_columns_and_no_resolved_route_fails(self):
        with tempfile.TemporaryDirectory() as d:
            awy,fix,nav=nasr_fixture(d)
            nav.write_text("wrong,column\nA,B\n")
            with self.assertRaisesRegex(app.AirwayError,"unsupported_nasr"):
                app.nasr_network(awy,fix,nav,"2026-10-29","2026-11-26")
            nasr_fixture(d)
            awy.write_text(awy.read_text().replace("Q102","V10").replace("J80","V80"))
            with self.assertRaisesRegex(app.AirwayError,"no_resolved"):
                app.nasr_network(awy,fix,nav,"2026-10-29","2026-11-26")

    def test_matched_points_are_network_proximity_only_not_normal_or_alert(self):
        report = screen()
        result = report["results"][0]
        self.assertEqual(result["status"], "network_proximity_only")
        self.assertEqual(result["route_assignment_known"], False)
        self.assertFalse(result["changes_warning_status"])
        self.assertEqual(report["alerts_emitted"], 0)
        self.assertEqual(report["review_candidate_count"], 0)
        self.assertEqual(result["points_near_any_published_airway"], 11)

    def test_distant_path_needs_route_context_not_anomaly(self):
        result = screen(legs=[leg(shift=2.0)])["results"][0]
        self.assertEqual(result["status"], "uncovered_by_local_reference_index")
        self.assertFalse(result["requires_historical_validation"])
        # Some point locations share a route's coarse geographic cells,
        # but remain far from the actual route line.
        result = screen(legs=[leg(shift=0.8)])["results"][0]
        self.assertEqual(result["status"], "needs_route_context_before_history")
        self.assertTrue(result["requires_historical_validation"])
        self.assertNotIn("anomaly", result["status"])

    def test_no_relevant_network_is_uncovered_not_flight_normality(self):
        report=screen(routes=network([
            {"route_id":"Q20","geometry_lonlat":[[-120,40],[-119,40]]}]))
        self.assertEqual(report["results"][0]["status"],"uncovered_by_local_reference_index")
        self.assertEqual(report["review_candidate_count"],0)

    def test_stale_future_and_wrong_source_refused(self):
        for item in (
            network(start="2026-11-26",end="2026-12-24"),
            network(start="2026-10-01",end="2026-10-29"),
            {**network(),"source":"third-party"},
            {**network(),"source_dataset_completeness_verified":True},
        ):
            with self.subTest(meta=item),self.assertRaises(app.AirwayError):
                screen(routes=item)

    def test_date_leakage_and_missing_altitude_are_insufficient_not_off_network(self):
        track=leg()
        track["points"][0]["t"]-=86400
        result=screen(legs=[track])["results"][0]
        self.assertEqual(result["status"],"insufficient_observations")
        self.assertEqual(result["reason"],"observation_outside_reference_day")
        track=leg()
        del track["points"][0]["altitude_ft"]
        result=screen(legs=[track])["results"][0]
        self.assertEqual(result["reason"],"invalid_or_missing_position_altitude")

    def test_lower_altitude_and_partial_coverage_not_misclassified(self):
        lower=leg(alt=12000)
        result=screen(legs=[lower])["results"][0]
        self.assertEqual(result["status"],"insufficient_observations")
        self.assertEqual(result["excluded_other_altitudes"],11)
        partial=leg()
        partial["coverage"]="partial"
        result=screen(legs=[partial])["results"][0]
        self.assertEqual(result["reason"],"leg_coverage_unverified")

    def test_transponder_dropouts_or_leg_splicing_fail_coverage(self):
        for mutation in (
            lambda track: track["points"][6].update(t=track["points"][5]["t"]+1200),
            lambda track: track["points"][6].update(t=track["points"][5]["t"]),
            lambda track: track["points"][6].update(lat=45),
        ):
            with self.subTest(mutation=mutation):
                track=leg()
                mutation(track)
                result=screen(legs=[track])["results"][0]
                self.assertEqual(result["status"],"insufficient_observations")
                self.assertEqual(result["reason"],"gap_or_invalid_track_continuity")

    def test_conus_geography_guard_and_no_global_coverage_claim(self):
        outside=leg(shift=18.0)
        result=screen(legs=[outside])["results"][0]
        self.assertEqual(result["status"],"insufficient_observations")
        self.assertEqual(result["excluded_outside_CONUS"],11)
        self.assertFalse(screen()["reference_dataset_completeness_verified"])

    def test_spatial_index_reduces_candidate_geometry_comparisons(self):
        far_routes=[{"route_id":"Q1","geometry_lonlat":[[-120+i*0.2,40],[-119.95+i*0.2,40]]}
                    for i in range(100)]
        far_routes.append({"route_id":"J22","geometry_lonlat":[[-90,35],[-85,35]]})
        result=screen(routes=network(far_routes))
        self.assertLess(result["total_actual_comparisons"],result["full_scan_upper_bound"]/10)
        self.assertEqual(result["results"][0]["status"],"network_proximity_only")

    def test_dateline_and_unsupported_geometries_fail_closed(self):
        bad=network([{"route_id":"Q1","geometry_lonlat":[[179.9,45],[-179.9,45]]}])
        with self.assertRaises(app.AirwayError):
            screen(routes=bad)
        other=network([{"route_id":"Q1","geometry_lonlat":[[-90,"nan"],[-85,35]]}])
        with self.assertRaises(app.AirwayError):
            screen(routes=other)

    def test_reject_duplicate_leg_and_outsize_input(self):
        a=leg()
        with self.assertRaisesRegex(app.AirwayError,"duplicate"):
            screen(legs=[a,a])
        a=leg(count=2001)
        with self.assertRaisesRegex(app.AirwayError,"bounded_point"):
            screen(legs=[a])

    def test_geo_screen_never_implies_causal_iw_claim(self):
        d=screen()
        self.assertFalse(d["changes_aiba_warning_status"])
        self.assertFalse(d["publication_enabled"])
        self.assertFalse(d["individual_clearance_known"])
        self.assertEqual(d["interpretation"].startswith("Proximity to SOME"),True)

    def test_cli_reports_failed_run_without_stale_success(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder)
            n=root/"network.json"
            inp=root/"input.json"
            out=root/"report.json"
            n.write_text(json.dumps(network()))
            inp.write_text(json.dumps({"schema":app.INPUT_SCHEMA,"day":DAY,"legs":[leg()]}))
            argv=["screen","--network",str(n),"--input",str(inp),"--output",str(out)]
            self.assertEqual(app.main(argv),0)
            self.assertEqual(json.loads(out.read_text())["results"][0]["status"],"network_proximity_only")
            inp.write_text("{invalid")
            self.assertEqual(app.main(argv),1)
            self.assertEqual(json.loads(out.read_text())["status"],"unavailable")
            self.assertEqual(json.loads(out.read_text())["results"],[])

    def test_direct_cli_help(self):
        r=subprocess.run([sys.executable,app.__file__,"--help"],
                         capture_output=True,text=True,timeout=10,check=False)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("build",r.stdout)


if __name__=="__main__":
    unittest.main()
