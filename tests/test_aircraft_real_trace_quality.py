"""Synthetic offline quality audit tests; no real aircraft or network access."""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import aircraft_real_trace_quality as quality


DAY = "2026-11-07"
ASSET = "v2026.11.07-planes-readsb-prod-0.tar."
ID = "abc123"


def t0():
    return int(dt.datetime(2026, 11, 7, 12, tzinfo=dt.timezone.utc).timestamp())


def row(index, *, flags=0, lat=11.0, lon=None, callsign="SAMPLE"):
    return [index * 180, lat, index * 0.1 if lon is None else lon,
            32000, 390, 85, flags, 0, {"flight": callsign}]


def envelope(identity=ID, rows=None):
    return {"icao": identity, "timestamp": t0(),
            "trace": [row(i) for i in range(11)] if rows is None else rows}


def tar(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path, data, typ in entries:
            member = tarfile.TarInfo(path)
            if typ:
                member.type = typ
                member.linkname = "ignore"
            else:
                member.size = len(data)
            archive.addfile(member, io.BytesIO(data) if not typ else None)
    return stream.getvalue()


def fixtures(*, selected=ID):
    return [
        ("./traces/ab/trace_full_" + selected + ".json",
         json.dumps(envelope(selected)).encode(), None),
        ("./traces/ff/trace_full_ffffff.json",
         json.dumps(envelope("ffffff")).encode(), None),
    ]


def files(root, body, split=None):
    if split is None:
        split = len(body)
    a = Path(root) / (ASSET + "aa")
    a.write_bytes(body[:split])
    if split < len(body):
        b = Path(root) / (ASSET + "ab")
        b.write_bytes(body[split:])
        return [a, b]
    return [a]


class RealTraceQualityTests(unittest.TestCase):
    def observed(self, entries=None, *, size=None, split=None):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            quality, "hashed_selection", side_effect=lambda icao: icao == ID
        ):
            parts = files(directory, tar(fixtures() if entries is None else entries), split=split)
            return quality.scan_day(parts, DAY, max_bytes=size or 4_000_000_000)

    def test_hash_rule_stable_independent_of_callsign_position(self):
        self.assertEqual(quality.hashed_selection(ID), quality.hashed_selection(ID))
        self.assertFalse(quality.hashed_selection("not-an-icao"))
        self.assertFalse(quality.hashed_selection("ABCDEF"))  # only canonical lowercase
        self.assertEqual(quality.HASH_MODULUS, 1024)
        self.assertFalse(quality.hashed_selection("malformed/../path"))

    def test_complete_tar_audits_only_sampled_aircraft_without_identifiers(self):
        receipt = self.observed(split=1560)
        self.assertEqual(receipt["status"], "source_sample_audited_review_required")
        self.assertTrue(receipt["source_archive_complete"])
        self.assertEqual(receipt["counts"]["source_trace_members"], 2)
        self.assertEqual(receipt["counts"]["selected_trace_members"], 1)
        self.assertEqual(receipt["counts"]["sampled_decoded_traces"], 1)
        self.assertEqual(receipt["counts"]["valid_leg_candidates"], 1)
        self.assertFalse(receipt["receiver_coverage_verified"])
        self.assertFalse(receipt["sample_is_usable_route_cohort"])
        self.assertFalse(receipt["changes_warning_status"])
        self.assertFalse(receipt["raw_geometry_saved"])
        self.assertNotIn(ID, json.dumps(receipt))
        self.assertNotIn("SAMPLE", json.dumps(receipt))
        self.assertNotIn("11.0", json.dumps(receipt))

    def test_explicit_leg_marker_splits_not_stitches(self):
        p = envelope()
        p["trace"][6][6] = 2
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertEqual(receipt["counts"]["candidate_segments"], 2)
        self.assertEqual(receipt["counts"]["valid_leg_candidates"], 1)
        self.assertEqual(receipt["leg_exclusions"]["new_source_leg"], 1)
        self.assertEqual(receipt["leg_exclusions"]["short_or_sparse"], 1)

    def test_stale_and_ground_boundaries_not_stitched(self):
        p = envelope()
        p["trace"][5][6] = 1
        p["trace"][8][3] = "ground"
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertEqual(receipt["leg_exclusions"]["stale"], 1)
        self.assertEqual(receipt["leg_exclusions"]["ground"], 1)
        self.assertEqual(receipt["counts"].get("valid_leg_candidates", 0), 0)

    def test_callsign_and_gap_boundaries_are_quality_exclusions(self):
        p = envelope()
        p["trace"][7][8]["flight"] = "DIFFERENT"
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertEqual(receipt["leg_exclusions"]["callsign_change"], 1)
        p = envelope()
        p["trace"][7][0] = p["trace"][6][0] + 601
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertGreaterEqual(receipt["leg_exclusions"]["gap_or_nonmonotonic"], 1)

    def test_malformed_rows_excluded_without_position_output(self):
        p = envelope()
        p["trace"][5][1] = 1000
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertEqual(receipt["leg_exclusions"]["invalid_or_nonfinite_row"], 1)
        self.assertNotIn("1000", json.dumps(receipt))

    def test_traces_outside_source_day_excluded(self):
        p = envelope()
        p["timestamp"] += 86400
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertGreaterEqual(receipt["leg_exclusions"]["timestamp_outside_day"], 1)
        self.assertEqual(receipt["counts"].get("valid_leg_candidates", 0), 0)

    def test_budget_exceeded_reports_incomplete_without_partial_quality(self):
        receipt = self.observed(size=1024)
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertIsNone(receipt["counts"])
        self.assertFalse(receipt["source_archive_complete"])

    def test_corrupt_tar_header_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = bytearray(tar(fixtures()))
            raw[0] ^= 1
            receipt = quality.scan_day(files(directory, bytes(raw)), DAY)
        self.assertEqual(receipt["status"], "incomplete_archive")
        self.assertEqual(receipt["reason"], "invalid_tar_header")
        self.assertIsNone(receipt["leg_exclusions"])

    def test_oversized_selected_trace_skipped_with_explicit_quality_count(self):
        p = envelope()
        p["padding"] = "x" * (quality.MAX_SAMPLE_BYTES + 1)
        receipt = self.observed([("./traces/ab/trace_full_abc123.json",
                                  json.dumps(p).encode(), None)])
        self.assertEqual(receipt["status"], "source_sample_audited_review_required")
        self.assertEqual(receipt["counts"]["sampled_oversized_members"], 1)
        self.assertEqual(receipt["counts"].get("sampled_decoded_traces", 0), 0)

    def test_malformed_selected_json_records_decode_failure(self):
        receipt = self.observed([("./traces/ab/trace_full_abc123.json", b"{broken", None)])
        self.assertEqual(receipt["counts"]["sampled_decode_failures"], 1)
        self.assertEqual(receipt["counts"].get("valid_leg_candidates", 0), 0)

    def test_selected_archive_symlink_does_not_extract(self):
        receipt = self.observed([("./traces/ab/trace_full_abc123.json", b"", tarfile.SYMTYPE)])
        self.assertEqual(receipt["status"], "unavailable")
        self.assertEqual(receipt["reason"], "sampled_trace_not_regular_file")

    def test_cli_failure_receipt_replaces_stale_success(self):
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()):
            source, output = files(root, tar(fixtures()))[0], Path(root) / "report.json"
            args = ["--date", DAY, "--part", str(source), "--output", str(output)]
            with patch.object(quality, "hashed_selection", side_effect=lambda icao: icao == ID):
                self.assertEqual(quality.main(args), 0)
                self.assertEqual(json.loads(output.read_text())["counts"]["valid_leg_candidates"], 1)
                source.write_bytes(b"bad")
                self.assertEqual(quality.main(args), 1)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["status"], "incomplete_archive")
            self.assertIsNone(receipt["counts"])

    def test_not_a_verified_cohort_even_if_eligible_segments_exist(self):
        receipt = self.observed()
        self.assertGreater(receipt["counts"]["valid_leg_candidates"], 0)
        self.assertFalse(receipt["route_classification_verified"])
        self.assertFalse(receipt["sample_is_usable_route_cohort"])


if __name__ == "__main__":
    unittest.main()
