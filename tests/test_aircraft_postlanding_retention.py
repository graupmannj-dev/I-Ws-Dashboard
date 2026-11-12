"""Offline postlanding tiering: strict gates, fidelity and no raw-data mutation."""
import contextlib
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import aircraft_postlanding_retention as mod


def sample(n=1801):
    first=1794312000
    points=[{"t":first+i,"lat":38.0,"lon":-100+i*.0015,
             "altitude_ft":32000.0} for i in range(n)]
    last=points[-1]["t"]
    return {
        "schema":mod.INPUT_SCHEMA,"source":"ADSB.lol","flight_id":"synthetic-flight",
        "points":points,"gate":{
            "landed_verified":True,"leg_closed":True,"source_coverage":"complete",
            "screening_complete":True,"historical_status":"within_reference",
            "airway_status":"network_proximity_only","analyst_review":"normal_reviewed",
            "retention_approved":True,"unresolved_indicators":0,"open_tippers":0,
            "reviewer_id":"synthetic-reviewer",
            "review_note":"Tested synthetic route reviewed under normal flight evidence",
            "landing_ground_observed_at":last+20,"flight_closed_asof":last+30,
            "reviewed_asof":last+90
        }}


class PostLandingRetentionTests(unittest.TestCase):
    def test_smooth_track_reduce_without_losing_ends(self):
        src=sample()
        archive=mod.compact(src)
        self.assertEqual(archive["original_point_count"],1801)
        self.assertLess(len(archive["points"]),12)
        self.assertEqual(archive["points"][0],src["points"][0])
        self.assertEqual(archive["points"][-1],src["points"][-1])
        self.assertLessEqual(archive["fidelity"]["max_retained_gap_seconds"],600)
        self.assertLessEqual(archive["fidelity"]["max_reconstruction_km"],2.0)
        self.assertTrue(archive["original_data_preserved"])
        self.assertEqual(archive["alerts_generated"],0)

    def test_hard_turn_remains_in_compact_geometry(self):
        d=sample()
        for i,p in enumerate(d["points"]):
            if 300 <= i <= 900:
                p["lat"]=38+(i-300)*.00035
            if i>900:
                p["lat"]=38+600*.00035
        archive=mod.compact(d)
        self.assertGreater(len(archive["points"]),4)
        self.assertLessEqual(archive["fidelity"]["max_reconstruction_km"],2)
        self.assertLessEqual(archive["fidelity"]["max_retained_gap_seconds"],600)

    def test_altitude_transition_requires_additional_points(self):
        d=sample()
        for i,p in enumerate(d["points"]):
            if i>=900:
                p["altitude_ft"]=25000
        archive=mod.compact(d)
        self.assertGreater(len(archive["points"]),4)
        self.assertLessEqual(archive["fidelity"]["max_reconstruction_altitude_ft"],500)

    def test_antimeridian_interpolation(self):
        d=sample()
        for i,p in enumerate(d["points"]):
            p["lon"]=(179.0+.0015*i+180)%360-180
        a=mod.compact(d)
        self.assertLessEqual(a["fidelity"]["max_reconstruction_km"],2)

    def test_every_negative_retention_gate_fails_closed(self):
        failures=[
            ("landed_verified",False),("leg_closed",False),
            ("source_coverage","partial"),("screening_complete",False),
            ("historical_status","insufficient_history"),
            ("historical_status","deviation_candidate"),
            ("airway_status","needs_route_context_before_history"),
            ("analyst_review","unreviewed"),("retention_approved",False),
            ("unresolved_indicators",1),("open_tippers",1),
            ("unresolved_indicators",False),("open_tippers",False)]
        for name,value in failures:
            with self.subTest(name=name,value=value):
                d=sample()
                d["gate"][name]=value
                with self.assertRaisesRegex(mod.RetentionError,"retention_gate_not_met"):
                    mod.compact(d)

    def test_reviewer_and_explanation_required(self):
        for key,value in [("reviewer_id"," "),("review_note","ok")]:
            with self.subTest(key=key):
                d=sample()
                d["gate"][key]=value
                with self.assertRaises(mod.RetentionError):
                    mod.compact(d)

    def test_landing_and_review_time_order(self):
        for key,value in [
            ("landing_ground_observed_at",0),
            ("flight_closed_asof",1794311000),
            ("reviewed_asof",1794312000),
            ("landing_ground_observed_at",1794313799)]:
            with self.subTest(key=key):
                d=sample()
                d["gate"][key]=value
                with self.assertRaises(mod.RetentionError):
                    mod.compact(d)

    def test_undocumented_position_flags_never_silently_discarded(self):
        for field in ("anomaly_flag","stale","callsign","source_alert"):
            with self.subTest(field=field):
                d=sample()
                d["points"][42][field]=True
                with self.assertRaisesRegex(mod.RetentionError,"unsupported_position_fields"):
                    mod.compact(d)

    def test_gaps_reversals_and_implausible_jumps_rejected(self):
        for mutation in (
            lambda d: d["points"][900].update(t=d["points"][899]["t"]),
            lambda d: d["points"][900].update(t=d["points"][899]["t"]+601),
            lambda d: d["points"][900].update(lat=-45)):
            with self.subTest(mutation=mutation):
                d=sample()
                mutation(d)
                with self.assertRaises(mod.RetentionError):
                    mod.compact(d)

    def test_invalid_positions_and_nonfinite_metadata_fail(self):
        for field,value in (
            ("lat",math.nan),("lon",200),("altitude_ft",90000),
            ("altitude_ft",None),("t",float("inf"))):
            with self.subTest(field=field):
                d=sample()
                d["points"][100][field]=value
                with self.assertRaises(mod.RetentionError):
                    mod.compact(d)

    def test_out_of_range_interval_and_error_bounds_rejected(self):
        p=mod.validate_positions(sample())
        for interval in (0,601,True,30.0):
            with self.subTest(interval=interval),self.assertRaises(mod.RetentionError):
                mod.select_positions(p,interval_s=interval)
        for error in (-1,0,2.5,float("nan")):
            with self.subTest(error=error),self.assertRaises(mod.RetentionError):
                mod.select_positions(p,max_error_km=error)

    def test_cli_dry_run_has_only_aggregate_receipt(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp)
            inp,receipt=root/"input.json",root/"receipt.json"
            inp.write_text(json.dumps(sample()))
            original=inp.read_bytes()
            code=mod.main(["--input",str(inp),"--receipt",str(receipt)])
            self.assertEqual(code,0)
            r=json.loads(receipt.read_text())
            self.assertEqual(r["status"],"eligible_dry_run_original_preserved")
            self.assertLess(r["retained_fraction"],.05)
            self.assertFalse(r["compressed_copy_created"])
            self.assertFalse(r["original_data_deleted"])
            self.assertNotIn("synthetic-flight",json.dumps(r))
            self.assertNotIn('"lat":',json.dumps(r))
            self.assertEqual(inp.read_bytes(),original)

    def test_cli_private_gzip_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp)
            inp,receipt,out=(root/"input.json",root/"receipt.json",
                             root/"lowres.json.gz")
            inp.write_text(json.dumps(sample()))
            original=inp.read_bytes()
            cmd=["--input",str(inp),"--receipt",str(receipt),"--copy",str(out)]
            self.assertEqual(mod.main(cmd),0)
            r=json.loads(receipt.read_text())
            with gzip.open(out,"rt") as handle:
                saved=json.load(handle)
            self.assertEqual(saved["schema"],mod.ARCHIVE_SCHEMA)
            self.assertLess(len(saved["points"]),12)
            self.assertEqual(inp.read_bytes(),original)
            self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(),
                             r["compressed_copy_sha256"])
            self.assertLess(out.stat().st_size,len(original)/10)
            self.assertEqual(r["status"],"copy_created_original_preserved")
            self.assertFalse(r["published"])

    def test_ineligible_inputs_do_not_create_archive(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp)
            inp,receipt,out=root/"input.json",root/"receipt.json",root/"lowres.json.gz"
            d=sample()
            d["gate"]["open_tippers"]=1
            inp.write_text(json.dumps(d))
            cmd=["--input",str(inp),"--receipt",str(receipt),"--copy",str(out)]
            self.assertEqual(mod.main(cmd),1)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(receipt.read_text())["status"],"not_eligible")

    def test_existing_archive_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp)
            inp,receipt,out=root/"input.json",root/"receipt.json",root/"lowres.json.gz"
            inp.write_text(json.dumps(sample()))
            out.write_bytes(b"other-archive")
            cmd=["--input",str(inp),"--receipt",str(receipt),"--copy",str(out)]
            self.assertEqual(mod.main(cmd),1)
            self.assertEqual(out.read_bytes(),b"other-archive")
            self.assertEqual(json.loads(receipt.read_text())["status"],"not_eligible")

    def test_failure_receipt_replaces_success_not_source(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp)
            inp,receipt=root/"input.json",root/"receipt.json"
            inp.write_text(json.dumps(sample()))
            cmd=["--input",str(inp),"--receipt",str(receipt)]
            self.assertEqual(mod.main(cmd),0)
            inp.write_text("{invalid")
            self.assertEqual(mod.main(cmd),1)
            r=json.loads(receipt.read_text())
            self.assertEqual(r["status"],"not_eligible")
            self.assertNotIn("retained_fraction",r)

    def test_no_raw_overwrite_and_no_repo_archive(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            root=Path(tmp)
            inp,receipt=root/"in.json",root/"receipt.json"
            inp.write_text(json.dumps(sample()))
            source=inp.read_bytes()
            self.assertEqual(mod.main(["--input",str(inp),"--receipt",str(inp)]),1)
            self.assertEqual(inp.read_bytes(),source)
            out=Path(mod.__file__).resolve().parents[1]/"test-leak.json.gz"
            self.assertEqual(mod.main(["--input",str(inp),"--receipt",str(receipt),
                                       "--copy",str(out)]),1)
            self.assertFalse(out.exists())
            self.assertEqual(inp.read_bytes(),source)

    def test_documented_direct_cli_help(self):
        run=subprocess.run([sys.executable,mod.__file__,"--help"],
                           capture_output=True,text=True,timeout=10,check=False)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn("--receipt",run.stdout)


if __name__=="__main__":
    unittest.main()
