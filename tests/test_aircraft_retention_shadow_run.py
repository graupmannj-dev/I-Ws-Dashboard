"""No-network tests for explicit held-out source benchmark opt-in."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import aircraft_retention_shadow_run as run

def pin():
    tag="v2026.11.10-planes-readsb-prod-0"
    return {"schema":"aiba.aircraft-one-day-source-pin.v1",
            "source_repo":"adsblol/globe_history_2026",
            "source_day":"2026-11-10","release_tag":tag,
            "selection":"production_only_no_staging_or_mlat",
            "assets":[{"name":tag+".tar.aa","size_bytes":2000000000,
                       "sha256":"a"*64},
                      {"name":tag+".tar.ab","size_bytes":1689415168,
                       "sha256":"b"*64}]}


class ShadowRunTests(unittest.TestCase):
    def test_metadata_only_default_never_downloads(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder); f=root/"pin.json";out=root/"r.json"
            f.write_text(json.dumps(pin()))
            with patch.object(run.bench,"fetch_release",return_value="2026-11-11T03:27:13Z"),patch.object(
                run,"measure",side_effect=AssertionError("must not download")
            ):
                self.assertEqual(run.main(["--pin",str(f),"--output",str(out)]),0)
            receipt=json.loads(out.read_text())
            self.assertEqual(receipt["status"],"metadata_verified_not_downloaded")
            self.assertFalse(receipt["source_download_executed"])
            self.assertFalse(receipt["deletion_authorized"])

    def test_full_mode_requires_literal_explicit_ack_before_network(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder);f=root/"pin.json";out=root/"r.json"
            f.write_text(json.dumps(pin()))
            with patch.object(run.bench,"fetch_release") as network:
                self.assertEqual(run.main(["--pin",str(f),"--output",str(out),
                                           "--execute","--work-dir",str(root)]),1)
                network.assert_not_called()
            self.assertEqual(json.loads(out.read_text())["status"],"unavailable")

    def test_end_to_end_fake_download_and_empty_source_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def mock_download(asset,pin_value,temp):
                f=temp/asset["name"];f.write_bytes(b"temporary")
                return f,{"asset":asset["name"],"downloaded_bytes":asset["size_bytes"],
                          "sha256_verified":True}
            with patch.object(run.bench,"download_one",side_effect=mock_download),patch.object(
                run.audit,"scan_day",return_value={"status":"shadow_audit_review_required"}
            ):
                report=run.measure(pin(),3689415168,root)
            self.assertEqual(report["downloaded_bytes"],3689415168)
            self.assertEqual(report["assets_sha256_verified"],2)
            self.assertEqual(report["status"],"shadow_audit_review_required")
            self.assertEqual(list(root.iterdir()),[])

    def test_incomplete_archive_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            def mock_download(asset,pin_value,temp):
                f=temp/asset["name"];f.write_bytes(b"x")
                return f,{"asset":asset["name"],"downloaded_bytes":asset["size_bytes"]}
            with patch.object(run.bench,"download_one",side_effect=mock_download),patch.object(
                run.audit,"scan_day",return_value={"status":"incomplete_archive"}
            ):
                report=run.measure(pin(),3689415168,Path(folder))
            self.assertEqual(report["status"],"insufficient_data_or_incomplete_source")

    def test_wrong_source_day_preflight_blocks_network(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
            root=Path(folder); f=root/"pin.json";out=root/"r.json"
            p=pin();p["source_day"]="2026-11-09";p["release_tag"]=p["release_tag"].replace("11.10","11.09")
            for a in p["assets"]:
                a["name"]=a["name"].replace("11.10","11.09")
            f.write_text(json.dumps(p))
            with patch.object(run.bench,"fetch_release") as network:
                self.assertEqual(run.main(["--pin",str(f),"--output",str(out)]),1)
                network.assert_not_called()
            self.assertEqual(json.loads(out.read_text())["status"],"unavailable")

if __name__=="__main__":
    unittest.main()
