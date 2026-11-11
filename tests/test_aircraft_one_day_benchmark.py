"""No network, no production downloads: source pin and one-day runner tests."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest
from unittest.mock import patch

from scripts import aircraft_one_day_benchmark as bench


def pin():
    tag = "v2026.11.10-planes-readsb-prod-0"
    return {
        "schema": bench.PIN_SCHEMA, "source_repo": bench.SOURCE_REPO,
        "source_day": "2026-11-10", "release_tag": tag,
        "selection": "production_only_no_staging_or_mlat",
        "assets": [
            {"name": tag + ".tar.aa", "size_bytes": 2000000000, "sha256": "a" * 64},
            {"name": tag + ".tar.ab", "size_bytes": 1689415168, "sha256": "b" * 64},
        ],
    }


def release(p=None):
    p = p or pin()
    return {
        "tag_name": p["release_tag"], "published_at": "2026-11-11T03:27:13Z",
        "draft": False,
        "assets": [
            {"name": a["name"], "size": a["size_bytes"],
             "digest": "sha256:" + a["sha256"], "state": "uploaded"}
            for a in p["assets"]
        ],
    }


class OneDayBenchmarkTests(unittest.TestCase):
    def save_pin(self, path, value=None):
        path.write_text(json.dumps(value or pin()))

    def test_documented_direct_entrypoints_can_show_help(self):
        for script in (bench.__file__, bench.archive.__file__):
            with self.subTest(script=script):
                completed = subprocess.run(
                    [sys.executable, script, "--help"],
                    capture_output=True, text=True, timeout=10, check=False
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("--", completed.stdout)

    def test_fixed_release_pin_has_expected_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "source.json"
            self.save_pin(f)
            parsed, amount = bench.load_pin(f)
        self.assertEqual(amount, 3689415168)
        self.assertEqual(len(parsed["assets"]), 2)

    def test_rejects_wrong_source_format_or_date(self):
        for edit in (
            lambda p: p.update(source_repo="other/host"),
            lambda p: p.update(selection="staging_and_mlat"),
            lambda p: p.update(release_tag="v2026.11.11-planes-readsb-prod-0"),
            lambda p: p["assets"][0].update(size_bytes=99999999999),
            lambda p: p["assets"][0].update(sha256="bad"),
            lambda p: p["assets"][1].update(name=p["assets"][0]["name"]),
            lambda p: p.update(source_day="2026-02-30"),
            lambda p: p.update(assets=p["assets"][:1]),
            lambda p: p["assets"][0].update(size_bytes=True),
        ):
            with self.subTest(edit=edit), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "pin.json"
                value = pin()
                edit(value)
                self.save_pin(path, value)
                with self.assertRaises((bench.BenchmarkError, ValueError)):
                    bench.load_pin(path)

    def test_remote_release_must_match_pinned_asset_size_hash_and_state(self):
        self.assertEqual(bench.validate_release(pin(), release()), "2026-11-11T03:27:13Z")
        for key, value in (
            ("size", 2), ("digest", "sha256:" + "c"*64), ("state", "deleted")
        ):
            bad = release()
            bad["assets"][0][key] = value
            with self.subTest(key=key), self.assertRaises(bench.BenchmarkError):
                bench.validate_release(pin(), bad)
        bad = release()
        bad["draft"] = True
        with self.assertRaises(bench.BenchmarkError):
            bench.validate_release(pin(), bad)

    def test_network_preflight_requests_only_fixed_github_metadata(self):
        called = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read(self, size):
                return json.dumps(release()).encode()
        def opener(request, timeout):
            called.append((request.full_url, timeout))
            return Response()
        pub = bench.fetch_release(pin(), opener=opener)
        self.assertEqual(pub, "2026-11-11T03:27:13Z")
        self.assertEqual(called, [(
            "https://api.github.com/repos/adsblol/globe_history_2026/releases/tags/v2026.11.10-planes-readsb-prod-0", 20
        )])

    def test_metadata_read_over_limit_fails_closed(self):
        class TooBig:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read(self, n):
                return b"x" * n
        with self.assertRaisesRegex(bench.BenchmarkError, "too_large"):
            bench.fetch_release(pin(), opener=lambda *args, **kwargs: TooBig())

    def test_default_cli_verifies_metadata_without_downloading(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            f, output = folder / "pin.json", folder / "receipt.json"
            self.save_pin(f)
            argv = ["--pin", str(f), "--output", str(output)]
            with patch.object(bench, "fetch_release", return_value="2026-11-11T03:27:13Z"), patch.object(
                bench, "run_benchmark", side_effect=AssertionError("must not download")
            ):
                self.assertEqual(bench.main(argv), 0)
            result = json.loads(output.read_text())
            self.assertEqual(result["status"], "metadata_verified_not_downloaded")
            self.assertTrue(result["source_metadata_verified"])
            self.assertFalse(result["full_day_download_executed"])
            self.assertEqual(result["planned_bytes"], 3689415168)
            self.assertFalse(result["detector_input_ready"])

    def test_execute_requires_acknowledgement_and_explicit_inputs(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            f, output = folder / "pin.json", folder / "receipt.json"
            self.save_pin(f)
            with patch.object(bench, "fetch_release") as fetch:
                self.assertEqual(bench.main([
                    "--pin", str(f), "--output", str(output), "--execute"
                ]), 1)
                fetch.assert_not_called()
            self.assertEqual(json.loads(output.read_text())["status"], "unavailable")

    def test_mock_full_day_execute_is_explicit_only(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            f, output, cohort = folder / "pin.json", folder / "receipt.json", folder / "cohort.json"
            self.save_pin(f)
            cohort.write_text('{"schema":"synthetic"}')
            argv = ["--pin", str(f), "--output", str(output), "--execute",
                    "--acknowledge", bench.ACK, "--cohort", str(cohort),
                    "--work-dir", str(folder)]
            with patch.object(bench, "fetch_release", return_value="2026-11-11T03:27:13Z"), patch.object(
                bench, "run_benchmark", return_value={
                    "status": "archive_scanned_review_required",
                    "full_day_download_executed": True,
                    "raw_source_retained": False, "receiver_coverage_verified": False,
                    "detector_input_ready": False, "downloaded_bytes": 3689415168,
                }
            ):
                self.assertEqual(bench.main(argv), 0)
            result = json.loads(output.read_text())
            self.assertTrue(result["full_day_download_executed"])
            self.assertFalse(result["raw_source_retained"])
            self.assertEqual(result["downloaded_bytes"], 3689415168)

    def test_file_hashing_streams_without_loading_entire_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "small"
            p.write_bytes(b"tiny fixture" * 2048)
            self.assertEqual(bench.file_sha256(p), hashlib.sha256(p.read_bytes()).hexdigest())

    def test_download_rejects_failure_partial_length_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = b"fixture"
            part = {
                "name": pin()["assets"][0]["name"], "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            def runner(cmd, **kwargs):
                self.assertEqual(cmd[cmd.index("--proto-redir")+1], "=https")
                self.assertEqual(cmd[cmd.index("--max-filesize")+1], str(len(data)))
                self.assertTrue(cmd[-1].startswith("https://github.com/adsblol/"))
                Path(cmd[cmd.index("--output")+1]).write_bytes(data)
                return subprocess.CompletedProcess(cmd, 0, stdout="200", stderr="")
            path, receipt = bench.download_one(part, pin(), folder, runner=runner)
            self.assertEqual(path.read_bytes(), data)
            self.assertTrue(receipt["sha256_verified"])
            def bad_status(cmd, **kwargs):
                x = runner(cmd, **kwargs)
                x.stdout = "206"
                return x
            with self.assertRaises(bench.BenchmarkError):
                bench.download_one(part, pin(), folder, runner=bad_status)
            part["sha256"] = "c"*64
            with self.assertRaisesRegex(bench.BenchmarkError, "digest"):
                bench.download_one(part, pin(), folder, runner=runner)

    def test_full_benchmark_cleans_raw_parts_and_does_not_return_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            p = pin()
            def fake_download(asset, release_pin, scratch, **kwargs):
                path = scratch / asset["name"]
                path.write_bytes(b"synthetic bytes")
                return path, {"asset": asset["name"], "downloaded_bytes": asset["size_bytes"],
                              "sha256_verified": True, "download_seconds": 0}
            fake_scan = ({"archive_complete": True, "status": "archive_scanned_review_required",
                          "scanned_bytes": 3689415168},
                         {"aircraft_traces": [{"sensitive": "must not leak"}]})
            with patch.object(bench, "download_one", side_effect=fake_download), patch.object(
                bench.archive, "scan", return_value=fake_scan
            ):
                result = bench.run_benchmark(p, 3689415168, {"cohorts":[]}, folder)
            self.assertEqual(result["status"], "archive_scanned_review_required")
            self.assertNotIn("sensitive", json.dumps(result))
            self.assertFalse(result["raw_source_retained"])
            self.assertEqual(list(folder.iterdir()), [])

    def test_no_workdir_inside_checkout_and_insufficient_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch.object(bench.shutil, "disk_usage",
                              return_value=type("Disk", (), {"free": 123})()):
                with self.assertRaisesRegex(bench.BenchmarkError, "disk"):
                    bench.run_benchmark(pin(), 3689415168, {}, work)
        root = Path(bench.__file__).resolve().parents[1]
        with self.assertRaisesRegex(bench.BenchmarkError, "outside_checkout"):
            bench.run_benchmark(pin(), 3689415168, {}, root)

    def test_scan_rejection_cannot_be_mistaken_for_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            def fake_download(asset, release_pin, scratch, **kwargs):
                p = scratch / asset["name"]
                p.write_bytes(b"abc")
                return p, {"asset": asset["name"], "downloaded_bytes": asset["size_bytes"]}
            with patch.object(bench, "download_one", side_effect=fake_download), patch.object(
                bench.archive, "scan", return_value=(
                    {"archive_complete": False, "reason": "missing_second_tar_terminator"}, {}
                )
            ):
                with self.assertRaisesRegex(bench.BenchmarkError, "scan_failed") as caught:
                    bench.run_benchmark(pin(), 3689415168, {}, folder)
            self.assertEqual(caught.exception.partial["verified_asset_count"], 2)
            self.assertEqual(caught.exception.partial["downloaded_bytes"], 3689415168)
            self.assertEqual(caught.exception.partial["scan"]["reason"],
                             "missing_second_tar_terminator")
            self.assertEqual(list(folder.iterdir()), [])

    def test_second_asset_failure_keeps_first_asset_measurement_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            def mock_download(part, pin_data, scratch, **kwargs):
                if part["name"].endswith(".ab"):
                    raise bench.BenchmarkError("asset_download_failed_code_22")
                asset_path = scratch / part["name"]
                asset_path.write_bytes(b"bounded synthetic")
                return asset_path, {"asset": part["name"],
                                    "downloaded_bytes": part["size_bytes"]}
            with patch.object(bench, "download_one", side_effect=mock_download):
                with self.assertRaisesRegex(bench.BenchmarkError, "code_22") as caught:
                    bench.run_benchmark(pin(), 3689415168, {}, folder)
            self.assertEqual(caught.exception.partial["downloaded_bytes"], 2000000000)
            self.assertEqual(caught.exception.partial["verified_asset_count"], 1)
            self.assertTrue(caught.exception.partial["full_day_download_attempted"])
            self.assertEqual(list(folder.iterdir()), [])

    def test_failed_preflight_replaces_prior_success(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            f, out = root / "pin.json", root / "result.json"
            self.save_pin(f)
            args = ["--pin", str(f), "--output", str(out)]
            with patch.object(bench, "fetch_release", return_value="2026-11-11T03:27:13Z"):
                self.assertEqual(bench.main(args), 0)
            with patch.object(bench, "fetch_release", side_effect=bench.BenchmarkError("source_unavailable")):
                self.assertEqual(bench.main(args), 1)
            data = json.loads(out.read_text())
            self.assertEqual(data["status"], "unavailable")
            self.assertNotIn("downloaded_bytes", data)
            self.assertEqual(data["reason"], "source_unavailable")


if __name__ == "__main__":
    unittest.main()
