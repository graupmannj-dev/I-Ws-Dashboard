"""Bounded real-day pilot orchestrator; synthetic/offline tests only."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import aircraft_real_source_pilot as pilot


def pin():
    return {
        "schema": "aiba.aircraft-one-day-source-pin.v1",
        "source_repo": "adsblol/globe_history_2026",
        "source_day": pilot.DAY,
        "release_tag": "v2026.11.07-planes-readsb-prod-0",
        "selection": "production_only_no_staging_or_mlat",
        "assets": [
            {"name": "v2026.11.07-planes-readsb-prod-0.tar.aa",
             "size_bytes": 2000000000, "sha256": "a"*64},
            {"name": "v2026.11.07-planes-readsb-prod-0.tar.ab",
             "size_bytes": 1404765184, "sha256": "b"*64},
        ],
    }


class RealSourcePilotTests(unittest.TestCase):
    def test_defaults_to_source_metadata_without_downloading(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            directory = Path(folder)
            pinfile, output = directory / "pin.json", directory / "out.json"
            pinfile.write_text(json.dumps(pin()))
            with patch.object(pilot.benchmark, "fetch_release", return_value="2026-11-08T03:26:49Z"), patch.object(
                pilot, "measure", side_effect=AssertionError("must not download")
            ):
                self.assertEqual(pilot.main(["--pin", str(pinfile), "--output", str(output)]), 0)
            r = json.loads(output.read_text())
            self.assertEqual(r["status"], "metadata_verified_without_source_download")
            self.assertEqual(r["planned_source_bytes"], 3404765184)
            self.assertFalse(r["source_download_executed"])
            self.assertFalse(r["sample_is_route_cohort"])
            self.assertFalse(r["historically_prospective_warning"])

    def test_requires_explicit_full_source_opt_in_before_network(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            directory = Path(folder)
            p, result = directory/"pin.json",directory/"out.json"
            p.write_text(json.dumps(pin()))
            with patch.object(pilot.benchmark, "fetch_release") as fetch:
                self.assertEqual(pilot.main(["--pin",str(p),"--output",str(result),
                                            "--execute"]),1)
                fetch.assert_not_called()
            self.assertEqual(json.loads(result.read_text())["status"],"unavailable")

    def test_only_predeclared_training_date(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder)
            p,o=root/"pin.json",root/"out.json"
            altered=pin()
            altered["source_day"]="2026-11-08"
            altered["release_tag"]="v2026.11.08-planes-readsb-prod-0"
            for entry in altered["assets"]:
                entry["name"]=entry["name"].replace("11.07","11.08")
            p.write_text(json.dumps(altered))
            with patch.object(pilot.benchmark, "fetch_release") as fetch:
                self.assertEqual(pilot.main(["--pin",str(p),"--output",str(o)]),1)
                fetch.assert_not_called()
            self.assertEqual(json.loads(o.read_text())["reason"],"wrong_predeclared_training_day")

    def test_mock_full_source_success_retains_only_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p=pin()
            def fake_download(asset, _pin, scratch):
                path = scratch/asset["name"]
                path.write_bytes(b"synthetic")
                return path, {"asset":asset["name"],"downloaded_bytes":asset["size_bytes"],
                              "download_seconds":0.01,"sha256_verified":True}
            qa={"status":"source_sample_audited_review_required",
                "source_archive_complete":True,"counts":{"valid_leg_candidates":1},
                "receiver_coverage_verified":False,"raw_geometry_saved":False}
            with patch.object(pilot.benchmark,"download_one",side_effect=fake_download),patch.object(
                pilot.quality,"scan_day",return_value=qa
            ):
                result=pilot.measure(p,3404765184,root)
            self.assertEqual(result["status"],"quality_audit_review_required")
            self.assertEqual(result["source_download_executed"],True)
            self.assertFalse(result["source_quality"]["raw_geometry_saved"])
            self.assertEqual(result["downloaded_bytes"],3404765184)
            self.assertEqual(list(root.iterdir()),[])
            self.assertNotIn("icao",json.dumps(result).lower())

    def test_full_scan_with_no_sample_does_not_fake_success(self):
        with tempfile.TemporaryDirectory() as folder:
            def fake_download(asset,_pin,scratch):
                p=scratch/asset["name"]
                p.write_bytes(b"stub")
                return p,{"asset":asset["name"],"downloaded_bytes":asset["size_bytes"]}
            with patch.object(pilot.benchmark,"download_one",side_effect=fake_download),patch.object(
                pilot.quality,"scan_day",return_value={
                    "status":"insufficient_sample",
                    "source_archive_complete":True, "counts":{"sampled_decoded_traces":0}
                }
            ):
                result=pilot.measure(pin(),3404765184,Path(folder))
            self.assertEqual(result["status"],"insufficient_sample_or_source")
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_direct_script_help_entrypoint(self):
        p=subprocess.run([sys.executable,pilot.__file__,"--help"],
                         capture_output=True,text=True,timeout=10,check=False)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("--execute",p.stdout)


if __name__=="__main__":
    unittest.main()
