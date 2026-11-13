"""Check local custody against original frame ledger entry, no witness overclaim."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import aiba_private_pilot_capture as capture
from scripts import aiba_private_pilot_reconstruct as reconstruct
from scripts import aiba_tipper_ledger as ledger
from tests.test_aiba_prospective_shadow import NOW,registry,fusion
from tests.test_aiba_tipper_ledger import issued, ISSUE


class PrivateReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.rpath=root/"registry.json"
        self.fpath=root/"fusion.json"
        self.rpath.write_text(json.dumps(registry()))
        self.fpath.write_text(json.dumps(fusion()))
        self.private=root/"private"
        def append(path,kind,payload):
            return ledger.append(path,kind,payload,clock=lambda:"2026-11-12T22:00:30Z")
        self.result=capture.create_capture(
            self.rpath,self.fpath,now=NOW,private_root=self.private,
            freeze=True,accept_unverified_coverage=True,append_fn=append)
        self.frame=self.private/"frames"/self.result["frame_id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_historical_frame_reconstructs_after_source_archive(self):
        out=reconstruct.reconstruct(self.private,self.result["frame_id"])
        self.assertEqual(out["status"],"local_source_and_ledger_prefix_reconstructed")
        self.assertTrue(out["exact_private_source_bytes_verified"])
        self.assertEqual(out["frame_entry_hash_sha256"],self.result["ledger_head_sha256"])
        self.assertFalse(out["independent_sigstore_witness_verified"])
        self.assertFalse(out["verified_pre_news_issuance"])
        self.assertFalse(out["no_event_outcome_established"])

    def test_current_chain_may_extend_beyond_historical_frame(self):
        ledger.append(self.private/"tippers.jsonl","issued",issued(),
                      clock=lambda:"2026-11-12T23:00:00Z")
        out=reconstruct.reconstruct(self.private,self.result["frame_id"])
        self.assertEqual(out["frame_sequence"],1)
        self.assertEqual(out["ledger_entries_now"],2)
        self.assertNotEqual(out["current_local_ledger_head"],out["frame_entry_hash_sha256"])

    def test_corrupted_source_bytes_cannot_reconstruct(self):
        f=self.frame/"fusion.json"
        f.write_bytes(f.read_bytes()+b"\n")
        with self.assertRaisesRegex(reconstruct.ReconstructionError,"archived_source_hash"):
            reconstruct.reconstruct(self.private,self.result["frame_id"])

    def test_replaced_manifest_digest_cannot_reconstruct(self):
        p=self.frame/"manifest.json"
        x=json.loads(p.read_text())
        x["input_sha256"]["registry"]="0"*64
        p.write_text(json.dumps(x))
        with self.assertRaisesRegex(reconstruct.ReconstructionError,"manifest_inconsistent"):
            reconstruct.reconstruct(self.private,self.result["frame_id"])

    def test_edited_private_local_receipt_rejected(self):
        p=self.frame/"local-freeze-receipt.json"
        x=json.loads(p.read_text())
        x["ledger_head_sha256"]="f"*64
        p.write_text(json.dumps(x))
        with self.assertRaisesRegex(reconstruct.ReconstructionError,"receipt_inconsistent"):
            reconstruct.reconstruct(self.private,self.result["frame_id"])

    def test_mutated_ledger_fails_without_relying_on_receipts(self):
        p=self.private/"tippers.jsonl"
        p.write_bytes(p.read_bytes().replace(b"2026-11-12T22:00:30Z",
                                             b"2026-11-12T22:00:31Z"))
        with self.assertRaises(ledger.LedgerError):
            reconstruct.reconstruct(self.private,self.result["frame_id"])

    def test_invalid_id_cannot_traverse_private_folder(self):
        with self.assertRaises(ledger.LedgerError):
            reconstruct.reconstruct(self.private,"../../etc/passwd")

    def test_missing_orphaned_frame_no_success(self):
        (self.frame/"local-freeze-receipt.json").unlink()
        with self.assertRaises(reconstruct.ReconstructionError):
            reconstruct.reconstruct(self.private,self.result["frame_id"])

    def test_source_snapshot_is_not_a_geopolitical_forecast(self):
        out=reconstruct.reconstruct(self.private,self.result["frame_id"])
        self.assertFalse(out["actual_geopolitical_forecast_issued_by_frame"])
        self.assertFalse(out["worldwide_coverage_ascertained"])

    def test_cli_failure_returns_no_fabricated_prospective_skill(self):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            status=reconstruct.main(["--private-root",str(self.private),
                                     "--frame-id","nonexistent"])
        self.assertEqual(status,1)
        row=json.loads(buf.getvalue())
        self.assertFalse(row["verified_pre_news_issuance"])
        self.assertFalse(row["no_event_outcome_established"])

if __name__=="__main__":
    unittest.main()
