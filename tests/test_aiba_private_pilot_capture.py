"""Prospective source evidence custody, replay, privacy and witness-gate tests."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import aiba_private_pilot_capture as capture
from scripts import aiba_tipper_ledger as ledger
from tests.test_aiba_prospective_shadow import NOW, registry, fusion

STAMP = "2026-11-12T22:00:30Z"


class PrivatePilotCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source_dir=self.root/"public-feed"
        self.source_dir.mkdir()
        self.rpath=self.source_dir/"registry.json"
        self.fpath=self.source_dir/"fusion.json"
        self.rpath.write_text(json.dumps(registry()))
        self.fpath.write_text(json.dumps(fusion()))
        self.private=self.root/"private"
    def tearDown(self):
        self.tmp.cleanup()

    def check(self):
        return capture.create_capture(self.rpath,self.fpath,now=NOW)

    def freeze(self, **kwargs):
        def real_append(path,kind,payload):
            return ledger.append(path,kind,payload,clock=lambda: STAMP)
        return capture.create_capture(
            self.rpath,self.fpath,private_root=self.private,freeze=True,
            accept_unverified_coverage=True,now=NOW,
            append_fn=real_append,**kwargs)

    def test_check_only_does_not_create_private_files(self):
        x=self.check()
        self.assertEqual(x["status"],"preflight_only_not_frozen")
        self.assertFalse(self.private.exists())
        self.assertEqual(x["source_count"],2)
        self.assertEqual(x["new_single_source_leads"],1)
        self.assertEqual(x["cross_family_review_groups"],0)
        self.assertFalse(x["issued_tipper"])
        self.assertFalse(x["independent_time_witness_verified"])

    def test_freeze_saves_exact_bytes_and_verified_ledger_head(self):
        raw_r=self.rpath.read_bytes();raw_f=self.fpath.read_bytes()
        result=self.freeze()
        self.assertEqual(result["status"],"private_frame_frozen_not_independently_time_witnessed")
        self.assertFalse(result["warning_skill_estimated"])
        self.assertFalse(result["source_complete"])
        self.assertTrue(result["private_source_copies_saved"])
        self.assertFalse(result["independent_time_witness_verified"])
        self.assertEqual(result["ledger_entry_count"],1)
        entries,head=ledger.read_ledger(self.private/"tippers.jsonl")
        self.assertEqual(head,result["ledger_head_sha256"])
        self.assertEqual(entries[0]["kind"],"frame")
        self.assertEqual(entries[0]["payload"]["source_sha256"],result["source_sha256"])
        frame=self.private/"frames"/result["frame_id"]
        self.assertEqual((frame/"registry.json").read_bytes(),raw_r)
        self.assertEqual((frame/"fusion.json").read_bytes(),raw_f)
        self.assertEqual(json.loads((frame/"manifest.json").read_text())["status"],
                         "copied_not_yet_independently_witnessed")
        self.assertFalse(json.loads((frame/"local-freeze-receipt.json").read_text())["issued_tipper"])
        for path in [self.private,self.private/"frames",frame]:
            self.assertEqual(path.stat().st_mode & 0o777,0o700)
        for filename in ("registry.json","fusion.json","manifest.json","local-freeze-receipt.json"):
            self.assertEqual((frame/filename).stat().st_mode & 0o777,0o600)

    def test_public_receipt_excludes_source_body_and_actors(self):
        r=registry();r["synthetic_private_note"]="DUMMY-SENSITIVE-SOURCE-CONTENT"
        self.rpath.write_text(json.dumps(r))
        receipt=self.check()
        self.assertNotIn("DUMMY-SENSITIVE-SOURCE-CONTENT",json.dumps(receipt))
        self.assertIsNone(receipt["ledger_head_sha256"])
        self.assertFalse(receipt["negative_event_inferred"])

    def test_no_freeze_without_explicit_acceptance(self):
        with self.assertRaisesRegex(capture.CaptureError,"explicit_unverified"):
            capture.create_capture(self.rpath,self.fpath,
                private_root=self.private,freeze=True,now=NOW)
        with self.assertRaisesRegex(capture.CaptureError,"explicit_unverified"):
            capture.create_capture(self.rpath,self.fpath,
                accept_unverified_coverage=True,now=NOW)
        self.assertFalse(self.private.exists())

    def test_no_private_ledger_inside_public_repository(self):
        path=Path(capture.__file__).resolve().parents[1]/"private-forecast-dont-create"
        with self.assertRaisesRegex(capture.CaptureError,"outside_repo"):
            capture.create_capture(self.rpath,self.fpath,
                private_root=path,freeze=True,
                accept_unverified_coverage=True,now=NOW)
        self.assertFalse(path.exists())

    def test_insecure_private_directory_refused(self):
        self.private.mkdir(mode=0o755)
        os.chmod(self.private,0o755)
        with self.assertRaisesRegex(capture.CaptureError,"permissions_must_be_0700"):
            self.freeze()
        self.assertFalse((self.private/"tippers.jsonl").exists())

    def test_symlink_private_root_refused(self):
        self.private.symlink_to(self.source_dir,target_is_directory=True)
        with self.assertRaisesRegex(capture.CaptureError,"not_symlink"):
            self.freeze()
        self.assertFalse((self.source_dir/"tippers.jsonl").exists())

    def test_expired_sources_cannot_start_pilot(self):
        r=registry();f=fusion()
        r["generated_at"]="2026-11-12T19:00:00Z"
        f["generated_at"]=f["registry_asof"]="2026-11-12T19:00:00Z"
        self.rpath.write_text(json.dumps(r));self.fpath.write_text(json.dumps(f))
        with self.assertRaisesRegex(ValueError,"source_snapshot_stale_or_future"):
            self.freeze()
        self.assertFalse(self.private.exists())

    def test_source_change_between_preflight_and_copy_fails_closed(self):
        original=capture.shadow.read_snapshot
        def mutate_source(p):
            obj,digest=original(p)
            if Path(p)==self.fpath:
                with self.fpath.open("ab") as stream:
                    stream.write(b" ")
            return obj,digest
        with patch.object(capture.shadow,"read_snapshot",side_effect=mutate_source):
            with self.assertRaisesRegex(capture.CaptureError,"source_mutated"):
                self.freeze()
        self.assertFalse(self.private.exists())

    def test_duplicate_same_second_frame_fails_without_second_append(self):
        first=self.freeze()
        with self.assertRaises(FileExistsError):
            self.freeze()
        entries,_=ledger.read_ledger(self.private/"tippers.jsonl")
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["payload"]["frame_id"],first["frame_id"])

    def test_append_error_keeps_uncommitted_private_source_copies(self):
        def fail(*args,**kwargs):
            raise ledger.LedgerError("simulated_ledger_failure")
        with self.assertRaisesRegex(ledger.LedgerError,"simulated_ledger_failure"):
            capture.create_capture(self.rpath,self.fpath,private_root=self.private,
                freeze=True,accept_unverified_coverage=True,
                now=NOW,append_fn=fail)
        self.assertFalse((self.private/"tippers.jsonl").exists())
        items=list((self.private/"frames").iterdir())
        self.assertEqual(len(items),1)
        self.assertTrue((items[0]/"manifest.json").exists())
        self.assertFalse((items[0]/"local-freeze-receipt.json").exists())

    def test_cli_stale_feeds_fail_without_forecast_or_claims(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code=capture.main(["--registry",str(self.rpath),"--fusion",str(self.fpath)])
        # Current runtime is not November 12 22:00Z so fixtures must be
        # rejected as historical, not silently reissued with old clocks.
        self.assertEqual(code,1)
        result=json.loads(output.getvalue())
        self.assertEqual(result["status"],"unavailable")
        self.assertFalse(result["issued_tipper"])
        self.assertFalse(result["negative_event_inferred"])
        self.assertFalse(result["warning_skill_estimated"])

if __name__=="__main__":
    unittest.main()
