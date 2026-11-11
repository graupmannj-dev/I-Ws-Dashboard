"""Offline synthetic tests; no network requests, real tracks or scheduled jobs."""
import contextlib
import gzip
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import aircraft_archive_probe as probe


NAME = "./traces/23/trace_full_abc123.json"
DAY = "2026-11-10"


def row(lat=10, lon=20, flags=0, altitude=30000):
    return [0, lat, lon, altitude, 300, 90, flags, 0, {"flight": "TEST01 "}]


def trace(rows=None):
    return {"icao": "abc123", "timestamp": 1794268800,
            "trace": [row()] if rows is None else rows}


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:") as tar:
        for name, data in entries:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return stream.getvalue()


def encoded(value):
    return json.dumps(value).encode()


class AircraftArchiveProbeTests(unittest.TestCase):
    def test_counts_source_quality_without_outputting_positions(self):
        payload = archive([(NAME, encoded(trace([
            row(flags=3, altitude="ground"), row(), row(lat=91), row(lon=True),
        ])))])
        result = probe.summarize(payload)
        self.assertEqual(result["counts"], {
            "aircraft_files": 1, "position_rows": 4,
            "valid_position_rows": 2, "invalid_position_rows": 2,
            "source_marked_stale_rows": 1, "source_leg_start_markers": 1,
            "rows_with_callsign_metadata": 2, "rows_with_ground_altitude": 1,
        })
        self.assertNotIn("abc123", json.dumps(result))
        self.assertNotIn("TEST01", json.dumps(result))

    def test_counts_only_complete_members_in_prefix(self):
        payload = archive([(NAME, encoded(trace())),
                           ("./traces/24/trace_full_abc124.json", b"x" * 4000)])
        result = probe.summarize(payload[:1536])
        self.assertEqual(result["counts"]["aircraft_files"], 1)
        self.assertEqual(result["stop_reason"], "incomplete_member_at_prefix_boundary")

    def test_empty_or_incomplete_sample_is_not_successful_zero_day(self):
        for payload in [b"\0" * 1024, archive([("./other.json", b"{}")]),
                        archive([(NAME, b"x" * 2000)])[:1024],
                        archive([(NAME, encoded(trace([])))])]:
            with self.subTest(size=len(payload)), self.assertRaises(probe.ProbeError):
                probe.summarize(payload)

    def test_malformed_envelopes_and_json_fail_explicitly(self):
        for body in [b"not json", b"[]", encoded({"icao": "different"}),
                     encoded({**trace(), "icao": 4}),
                     encoded({**trace(), "timestamp": float("nan")}),
                     encoded({**trace(), "trace": {}})]:
            with self.subTest(body=body), self.assertRaises(probe.ProbeError):
                probe.summarize(archive([(NAME, body)]))

    def test_invalid_rows_and_nonfinite_values_are_not_usable(self):
        for bad in [row(lat=float("inf")), row(flags=True), row(flags=-1),
                    row(lat=10 ** 1000), [0, 10, 20], row(lon=-181)]:
            with self.subTest(), self.assertRaises(probe.ProbeError):
                probe.summarize(archive([(NAME, encoded(trace([bad])))]))

    def test_gzip_size_and_row_limits(self):
        payload = archive([(NAME + ".gz", gzip.compress(encoded(trace())))])
        self.assertEqual(probe.summarize(payload)["counts"]["valid_position_rows"], 1)
        bomb = gzip.compress(b"x" * (probe.MAX_JSON_BYTES + 1))
        with self.assertRaisesRegex(probe.ProbeError, "Expanded trace"):
            probe.summarize(archive([(NAME, bomb)]))
        with self.assertRaisesRegex(probe.ProbeError, "member exceeds"):
            probe.summarize(archive([(NAME, b"x" * (probe.MAX_JSON_BYTES + 1))]))
        with patch.object(probe, "MAX_ROWS", 1), self.assertRaisesRegex(probe.ProbeError, "row limit"):
            probe.summarize(archive([(NAME, encoded(trace([row(), row()])))]))

    def test_file_budget_stops_before_later_members(self):
        payload = archive([(NAME, encoded(trace())),
                           ("./traces/24/trace_full_abc124.json", b"malformed")])
        result = probe.summarize(payload, max_files=1)
        self.assertEqual(result["counts"]["aircraft_files"], 1)
        self.assertEqual(result["stop_reason"], "file_limit")

    def test_corrupt_later_header_is_not_silent_end_of_archive(self):
        payload = bytearray(archive([(NAME, encoded(trace())),
                                    ("./other", b"x")]))
        payload[1024] ^= 1
        with self.assertRaises(probe.ProbeError):
            probe.summarize(bytes(payload))

    def test_integer_conversion_errors_do_not_escape_failure_handling(self):
        body = b'{"icao":"abc123","timestamp":' + b'9' * 5000 + b',"trace":[]}'
        with self.assertRaises(probe.ProbeError):
            probe.summarize(archive([(NAME, body)]))

    def test_no_traversal_links_or_duplicate_aircraft(self):
        for payload in [archive([("../escape", b"x")]),
                        archive([(NAME, encoded(trace())), (NAME, encoded(trace()))])]:
            with self.assertRaises(probe.ProbeError):
                probe.summarize(payload)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:") as tar:
            member = tarfile.TarInfo(NAME)
            member.type = tarfile.SYMTYPE
            member.linkname = "somewhere"
            tar.addfile(member)
        with self.assertRaisesRegex(probe.ProbeError, "ordinary file"):
            probe.summarize(stream.getvalue())

    def test_source_url_has_no_arbitrary_host_or_path(self):
        url = probe.source_url(DAY)
        self.assertTrue(url.startswith("https://github.com/adsblol/globe_history_2026/"))
        self.assertTrue(url.endswith("v2026.11.10-planes-readsb-prod-0.tar.aa"))
        for value in ["2026-02-30", "2026/11/10", "2026-11-10/../../", "https://other"]:
            with self.assertRaises(probe.ProbeError):
                probe.source_url(value)

    def mock_download(self, *, status="206", content_range="bytes 0-511/10000", data=b"x" * 512, code=0):
        def run(command, **kwargs):
            Path(command[command.index("--output") + 1]).write_bytes(data)
            Path(command[command.index("--dump-header") + 1]).write_text(
                "HTTP/1.1 200 Connection established\r\n\r\n"
                "HTTP/1.1 302 Found\r\nLocation: https://example.invalid\r\n\r\n"
                f"HTTP/2 {status}\r\nContent-Range: {content_range}\r\n\r\n")
            self.assertEqual(command[command.index("--range") + 1], "0-511")
            self.assertEqual(command[command.index("--max-filesize") + 1], "512")
            self.assertEqual(command[command.index("--proto-redir") + 1], "=https")
            self.assertEqual(kwargs["timeout"], 35)
            return subprocess.CompletedProcess(command, code, stdout=status, stderr="private diagnostic")
        return run

    def test_download_requires_matching_partial_response(self):
        with patch.object(probe.subprocess, "run", self.mock_download()):
            data, receipt = probe.download_prefix(probe.source_url(DAY), 512, 30)
        self.assertEqual(len(data), 512)
        self.assertEqual(receipt["http_status"], 206)
        for changes in [{"status": "200"}, {"content_range": "bytes 1-512/10000"},
                        {"content_range": "bytes 0-511/100"}, {"data": b"short"},
                        {"code": 63}]:
            with self.subTest(changes=changes), patch.object(
                probe.subprocess, "run", self.mock_download(**changes)
            ), self.assertRaises(probe.ProbeError) as caught:
                probe.download_prefix(probe.source_url(DAY), 512, 30)
            self.assertNotIn("private diagnostic", str(caught.exception))

    def test_missing_curl_and_timeouts_fail(self):
        for error in [FileNotFoundError(), subprocess.TimeoutExpired("curl", 35)]:
            with patch.object(probe.subprocess, "run", side_effect=error), self.assertRaises(probe.ProbeError):
                probe.download_prefix(probe.source_url(DAY), 512, 30)

    def test_cli_receipt_and_failure_replaces_previous_success(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            source, output = Path(folder) / "prefix", Path(folder) / "report.json"
            source.write_bytes(archive([(NAME, encoded(trace()))]))
            args = ["--date", DAY, "--archive-prefix", str(source), "--output", str(output)]
            self.assertEqual(probe.main(args), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "input_sample_readable")
            self.assertEqual(report["transport"]["source_provenance"], "caller_supplied")
            self.assertTrue(report["sample_only"])
            self.assertEqual(report["anomaly_scoring"], "not_implemented")
            self.assertIn("python_peak_rss_kib", report["measurement"])
            source.write_bytes(b"broken")
            self.assertEqual(probe.main(args), 1)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "unavailable")
            self.assertNotIn("counts", report)

    def test_invalid_limits_fail_before_network_and_missing_input_is_reported(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            output = Path(folder) / "report.json"
            base = ["--date", DAY, "--output", str(output)]
            with patch.object(probe, "download_prefix") as download:
                for extra in [["--max-bytes", "0"], ["--max-files", "0"], ["--timeout", "121"]]:
                    self.assertEqual(probe.main(base + extra), 1)
                download.assert_not_called()
            self.assertEqual(probe.main(base + ["--archive-prefix", str(Path(folder) / "missing")]), 1)
            self.assertEqual(json.loads(output.read_text())["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
