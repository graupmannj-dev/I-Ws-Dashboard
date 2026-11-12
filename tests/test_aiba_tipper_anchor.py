"""Offline hash-only anchor tests; no attestation forged or network called."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import aiba_tipper_anchor as anchor
from scripts import aiba_tipper_ledger as ledger
from tests.test_aiba_tipper_ledger import issued, ISSUE

class PrivateLedgerAnchorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.ledger=self.folder/"private.jsonl"
    def tearDown(self):
        self.tmp.cleanup()
    def add(self):
        return ledger.append(self.ledger,"issued",issued(),clock=lambda: ISSUE)

    def test_local_head_export_contains_only_digest_and_count(self):
        original=self.add()
        v=anchor.export_head(self.ledger)
        self.assertEqual(v["ledger_head_sha256"],original["entry_hash"])
        self.assertEqual(v["ledger_entry_count"],1)
        self.assertFalse(v["external_signed_timestamp_verified"])
        self.assertFalse(v["trusted_issuance_time_proven"])
        raw=json.dumps(v)
        self.assertNotIn("Synthetic frontier",raw)
        self.assertNotIn("watch-001",raw)
        self.assertNotIn("synthetic-analyst",raw)

    def test_local_export_expected_head_rejects_changes(self):
        self.add()
        with self.assertRaisesRegex(anchor.AnchorError,"head_changed_before_anchor"):
            anchor.export_head(self.ledger,expected_hash="f"*64)
        good=ledger.read_ledger(self.ledger)[1]
        self.assertEqual(anchor.export_head(self.ledger,expected_hash=good)["ledger_head_sha256"],good)

    def test_public_anchor_only_hash_and_external_signer_upper_bound(self):
        x=anchor.create_public_anchor("a"*64,1,run_id="1234567890",source_sha="b"*40)
        self.assertEqual(x["schema"],anchor.ANCHOR_SCHEMA)
        self.assertFalse(x["verified_issuing_time_proven"])
        self.assertFalse(x["first_news_timestamp_proven"])
        self.assertFalse(x["tipper_content_uploaded"])
        self.assertNotIn("actors",json.dumps(x))
        self.assertNotIn("issuer",json.dumps(x))
        self.assertNotIn("tipper_id",json.dumps(x))

    def test_public_anchor_rejects_bogus_hash_size_and_run_identity(self):
        for head,count,run,sha in (
            ("f"*63,1,"123456","a"*40),
            ("F"*64,1,"123456","a"*40),
            ("z"*64,1,"123456","a"*40),
            ("f"*64,0,"123456","a"*40),
            ("f"*64,6001,"123456","a"*40),
            ("f"*64,True,"123456","a"*40),
            ("f"*64,1,"malicious-run","a"*40),
            ("f"*64,1,"123456","../"*14),
        ):
            with self.subTest(head=head,count=count,run=run,sha=sha),self.assertRaises(anchor.AnchorError):
                anchor.create_public_anchor(head,count,run_id=run,source_sha=sha)

    def test_corrupt_ledger_cannot_export_hash(self):
        self.add()
        original=self.ledger.read_bytes()
        self.ledger.write_bytes(original.replace(b"synthetic-analyst-1",b"synthetic-analyst-2"))
        with self.assertRaises(ledger.LedgerError):
            anchor.export_head(self.ledger)

    def test_cli_never_overwrites_ledger_or_existing_anchor(self):
        self.add()
        original=self.ledger.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(anchor.main(["export","--ledger",str(self.ledger),
                                        "--output",str(self.ledger)]),1)
        self.assertEqual(self.ledger.read_bytes(),original)
        file=self.folder/"anchor.json"
        file.write_text("existing")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(anchor.main(["export","--ledger",str(self.ledger),
                                          "--output",str(file)]),1)
        self.assertEqual(file.read_text(),"existing")

    def test_cli_export_success_file_no_source_content(self):
        self.add()
        out=self.folder/"head.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code=anchor.main(["export","--ledger",str(self.ledger),
                              "--output",str(out)])
        self.assertEqual(code,0)
        x=json.loads(out.read_text())
        self.assertEqual(x["ledger_head_sha256"],ledger.read_ledger(self.ledger)[1])
        self.assertFalse(x["external_signed_timestamp_verified"])
        self.assertFalse(x["source_evidence_included"])

    def test_cli_public_anchor_never_asserts_attestation_success(self):
        out=self.folder/"public.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code=anchor.main(["public-anchor","--head-hash","f"*64,
                              "--entry-count","2","--github-run-id","1234567890",
                              "--source-sha","e"*40,"--output",str(out)])
        self.assertEqual(code,0)
        x=json.loads(out.read_text())
        self.assertEqual(x["ledger_entry_count"],2)
        self.assertFalse(x["verified_issuing_time_proven"])
        self.assertFalse(x["tipper_content_uploaded"])

    def test_empty_or_missing_ledger_cannot_anchor(self):
        self.ledger.write_bytes(b"")
        with self.assertRaisesRegex(anchor.AnchorError,"empty_ledger"):
            anchor.export_head(self.ledger)
        self.ledger.unlink()
        with self.assertRaises(ledger.LedgerError):
            anchor.export_head(self.ledger)

    def test_main_exports_never_written_inside_public_repo(self):
        self.add()
        root=Path(anchor.__file__).resolve().parents[1]
        path=root/"would-expose-private-head.json"
        with contextlib.redirect_stdout(io.StringIO()):
            rc=anchor.main(["export","--ledger",str(self.ledger),
                            "--output",str(path)])
        self.assertEqual(rc,1)
        self.assertFalse(path.exists())

    def test_full_private_ledger_inside_public_repo_is_rejected(self):
        path=Path(anchor.__file__).resolve().parents[1]/"private-leak.jsonl"
        with self.assertRaisesRegex(anchor.AnchorError,"private_ledger_must_not_be_inside"):
            anchor.export_head(path)

if __name__=="__main__":
    unittest.main()
