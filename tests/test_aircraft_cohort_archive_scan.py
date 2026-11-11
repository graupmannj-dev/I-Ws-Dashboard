"""Offline split-TAR scanner tests; all tracks and archives are synthetic."""
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from scripts import aircraft_cohort_archive_scan as scan


DAY = "2026-11-10"
PREFIX = "v2026.11.10-planes-readsb-prod-0.tar."


def cohort():
    return {"schema": "aiba.aircraft-route-cohort.v1",
            "frozen_before": "2026-11-09",
            "cohorts": [{
                "id": "test-route", "label": "Only a synthetic selection",
                "direction": "east",
                "aircraft_ids": ["abc123", "abc124"],
            }]}


def trace(identity):
    return {"icao": identity, "timestamp": 1794268800,
            "trace": [[i * 180, 0, i * .20, 30000, 340, 90, 0, 0,
                       {"flight": "SYNTHETIC"}] for i in range(11)]}


def entries(*, zipped=False):
    return [
        ("./traces/ff/trace_full_ffffff.json", json.dumps(trace("ffffff")).encode(), None),
        ("./traces/ab/trace_full_abc123.json" + (".gz" if zipped else ""),
         gzip.compress(json.dumps(trace("abc123")).encode()) if zipped
         else json.dumps(trace("abc123")).encode(), None),
        ("./traces/ab/trace_full_abc124.json",
         json.dumps(trace("abc124")).encode(), None),
    ]


def archive(items):
    binary = io.BytesIO()
    with tarfile.open(fileobj=binary, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, body, kind in items:
            entry = tarfile.TarInfo(name)
            if kind is not None:
                entry.type = kind
                entry.linkname = "../bad"
            else:
                entry.size = len(body)
            tar.addfile(entry, io.BytesIO(body) if kind is None else None)
    return binary.getvalue()


def parts(folder, payload, cut=None):
    if cut is None:
        cut = len(payload)
    paths = [Path(folder) / (PREFIX + ".aa")]
    paths[0].write_bytes(payload[:cut])
    if cut < len(payload):
        paths.append(Path(folder) / (PREFIX + ".ab"))
        paths[1].write_bytes(payload[cut:])
    return paths


class BoundedOfflineArchiveScanTests(unittest.TestCase):
    def run_scan(self, paths, limit=None, manifest=None):
        return scan.scan(paths, manifest or cohort(), DAY,
                         max_bytes=limit if limit is not None else 64 * 1024 * 1024)

    def test_complete_split_archive_selects_only_predeclared_icao(self):
        payload = archive(entries())
        with tempfile.TemporaryDirectory() as folder:
            filenames = parts(folder, payload, cut=1907)  # split inside member payload
            receipt, candidate = self.run_scan(filenames)
        self.assertEqual(receipt["status"], "archive_scanned_review_required")
        self.assertTrue(receipt["archive_complete"])
        self.assertFalse(receipt["receiver_coverage_verified"])
        self.assertEqual(receipt["scanned_bytes"], len(payload))
        self.assertEqual(receipt["scanned_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(receipt["input_file_bytes"], len(payload))
        self.assertEqual(receipt["selected_trace_members"], 2)
        self.assertEqual(receipt["scanned_trace_members"], 3)
        self.assertEqual(receipt["parts_supplied"], 2)
        self.assertNotIn("abc123", json.dumps(receipt))
        self.assertNotIn("SYNTHETIC", json.dumps(receipt))
        self.assertEqual(candidate["status"], "review_required")
        self.assertFalse(candidate["detector_input_ready"])
        self.assertEqual(candidate["coverage"], "unverified")
        self.assertEqual({e["aircraft_id"] for e in candidate["aircraft_traces"]},
                         {"abc123", "abc124"})
        self.assertTrue(all(e["flight_leg_review"] == "required"
                            for e in candidate["aircraft_traces"]))

    def test_boundary_within_header_and_compressed_member(self):
        payload = archive(entries(zipped=True))
        with tempfile.TemporaryDirectory() as folder:
            receipt, candidate = self.run_scan(parts(folder, payload, cut=733))
        self.assertEqual(receipt["status"], "archive_scanned_review_required")
        self.assertEqual(candidate["aircraft_traces"][0]["readsb"]["icao"], "abc123")
        self.assertAlmostEqual(candidate["aircraft_traces"][0]["readsb"]["trace"][3][2], .6)

    def test_small_budget_explicitly_incomplete_even_after_a_selected_trace(self):
        payload = archive(entries())
        with tempfile.TemporaryDirectory() as folder:
            receipt, candidate = self.run_scan(parts(folder, payload), limit=4096)
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertEqual(receipt["reason"], "scan_byte_budget_exhausted")
        self.assertFalse(receipt["archive_complete"])
        self.assertEqual(candidate["aircraft_traces"], [])
        self.assertLessEqual(receipt["scanned_bytes"], 4096)

    def test_missing_terminal_part_is_not_complete(self):
        payload = archive(entries())
        with tempfile.TemporaryDirectory() as folder:
            filename = parts(folder, payload, cut=3000)[0]
            receipt, candidate = self.run_scan([filename])
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertFalse(receipt["archive_complete"])
        self.assertEqual(candidate["aircraft_traces"], [])
        self.assertIn("truncated", receipt["reason"])

    def test_missing_tar_terminator_is_not_successful_completion(self):
        payload = archive(entries())
        # complete members but no two-block terminator
        # Stop immediately after the final member's padded data, before EOF blocks.
        member_end = sum(512 + ((len(body) + 511) // 512) * 512
                         for _, body, _ in entries())
        payload = payload[:member_end]
        with tempfile.TemporaryDirectory() as folder:
            receipt, candidate = self.run_scan(parts(folder, payload))
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertEqual(receipt["reason"], "missing_two_block_tar_terminator")
        self.assertFalse(candidate["detector_input_ready"])

    def test_trailing_nonzero_after_terminator_is_rejected(self):
        payload = archive(entries()) + b"x" * 512
        with tempfile.TemporaryDirectory() as folder:
            receipt, _ = self.run_scan(parts(folder, payload))
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertEqual(receipt["reason"], "nonzero_bytes_after_tar_terminator")

    def test_bad_header_checksum_cannot_silently_pass(self):
        payload = bytearray(archive(entries()))
        payload[0] ^= 1
        with tempfile.TemporaryDirectory() as folder:
            receipt, candidate = self.run_scan(parts(folder, bytes(payload)))
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertEqual(receipt["reason"], "invalid_tar_header_or_checksum")
        self.assertEqual(candidate["aircraft_traces"], [])

    def test_reject_missing_or_reordered_split_parts(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = parts(folder, archive(entries()), cut=1024)
            with self.assertRaisesRegex(scan.ScanError, "contiguous"):
                self.run_scan([paths[1]])
            with self.assertRaisesRegex(scan.ScanError, "contiguous"):
                self.run_scan([paths[1], paths[0]])
            with self.assertRaisesRegex(scan.ScanError, "duplicated"):
                self.run_scan([paths[0], paths[0]])
            other = Path(folder) / "v2026.11.09-planes-readsb-prod-0.tar.ac"
            other.write_bytes(b"x")
            with self.assertRaisesRegex(scan.ScanError, "source date"):
                self.run_scan([paths[0], other])

    def test_mixed_source_variants_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = parts(folder, archive(entries()), cut=1024)
            other = Path(folder) / "v2026.11.10-planes-readsb-staging-0.tar.ab"
            other.write_bytes(b"x")
            with self.assertRaisesRegex(scan.ScanError, "Mixed"):
                self.run_scan([paths[0], other])

    def test_duplicate_selected_member_is_unavailable(self):
        items = entries()
        items.append(items[1])
        payload = archive(items)
        with tempfile.TemporaryDirectory() as folder:
            receipt, candidate = self.run_scan(parts(folder, payload))
        self.assertEqual(receipt["status"], "unavailable")
        self.assertEqual(receipt["reason"], "Duplicate selected aircraft trace")
        self.assertEqual(candidate["aircraft_traces"], [])

    def test_invalid_selected_envelope_is_unavailable(self):
        cases = [b"x", json.dumps({"icao": "000000", "timestamp": 1234, "trace": []}).encode(),
                 b'{"icao":"abc123","timestamp":NaN,"trace":[]}', b'[]']
        for body in cases:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as folder:
                payload = archive([("./traces/ab/trace_full_abc123.json", body, None)])
                receipt, candidate = self.run_scan(parts(folder, payload))
                self.assertEqual(receipt["status"], "unavailable")
                self.assertEqual(candidate["aircraft_traces"], [])

    def test_regular_files_only_no_symlink_extraction(self):
        payload = archive([("./traces/ab/trace_full_abc123.json", b"", tarfile.SYMTYPE)])
        with tempfile.TemporaryDirectory() as folder:
            receipt, _ = self.run_scan(parts(folder, payload))
        self.assertEqual(receipt["status"], "unavailable")
        self.assertEqual(receipt["reason"], "Selected TAR member is not a regular file")

    def test_selected_members_and_expanded_output_are_limited(self):
        bomb = gzip.compress(b"x" * (scan.MAX_SELECTED_JSON + 1))
        payload = archive([("./traces/ab/trace_full_abc123.json.gz", bomb, None)])
        with tempfile.TemporaryDirectory() as folder:
            receipt, _ = self.run_scan(parts(folder, payload))
        self.assertEqual(receipt["status"], "unavailable")
        self.assertIn("Expanded selected trace", receipt["reason"])

    def test_invalid_cohort_and_bad_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = parts(folder, archive(entries()))
            bad = cohort()
            bad["frozen_before"] = DAY
            with self.assertRaisesRegex(Exception, "frozen"):
                self.run_scan(paths, manifest=bad)
            for value in (0, scan.HARD_SCAN_BYTES + 1):
                with self.assertRaisesRegex(scan.ScanError, "limits"):
                    self.run_scan(paths, limit=value)
            with self.assertRaisesRegex(scan.ScanError, "limits"):
                scan.scan(paths, cohort(), DAY, max_seconds=0)

    def test_cli_writes_local_receipts_and_clears_stale_candidate_success(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            paths = parts(folder, archive(entries()))
            manifest = root / "cohort.json"
            report, candidates = root / "receipt.json", root / "selection.json"
            manifest.write_text(json.dumps(cohort()))
            args = ["--cohort", str(manifest), "--date", DAY, "--part", str(paths[0]),
                    "--report", str(report), "--candidates-output", str(candidates)]
            self.assertEqual(scan.main(args), 0)
            saved = json.loads(candidates.read_text())
            self.assertEqual(saved["status"], "review_required")
            self.assertEqual(len(saved["aircraft_traces"]), 2)
            self.assertEqual(scan.main(args + ["--max-bytes", "4096"]), 1)
            saved = json.loads(candidates.read_text())
            self.assertEqual(saved["status"], "incomplete_archive")
            self.assertEqual(saved["aircraft_traces"], [])
            self.assertEqual(json.loads(report.read_text())["status"], "incomplete_archive")

    def test_cannot_accidentally_write_real_tracks_into_checkout(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            filename = parts(folder, archive(entries()))[0]
            manifest = root / "cohort.json"
            report = root / "receipt.json"
            manifest.write_text(json.dumps(cohort()))
            forbidden = Path(scan.__file__).resolve().parents[1] / "selected-test-output.json"
            args = ["--cohort", str(manifest), "--date", DAY, "--part", str(filename),
                    "--report", str(report), "--candidates-output", str(forbidden)]
            self.assertEqual(scan.main(args), 1)
            self.assertEqual(json.loads(report.read_text())["status"], "unavailable")
            self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
