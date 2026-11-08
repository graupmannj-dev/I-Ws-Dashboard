"""Offline regression checks for the authenticated GitHub comment intake path."""
from __future__ import annotations
import datetime as dt
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from dashboard.analyst_intake import load_history
from scripts.import_analyst_report import main


def fixture():
    return {
        "schema_version": 1,
        "run_id": "synthetic-report-pilot-001",
        "collector": "six_hour_signal",
        "status": "completed",
        "collected_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "observations": [{
            "observation_id": "test-source-lead-001",
            "case_id": "taiwan",
            "published_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "title": "SYNTHETIC TEST: fictional source lead",
            "summary": "Synthetic regression-only observation, not a real geopolitical event.",
            "publisher": "Fictional source",
            "source_url": "https://example.org/synthetic-evidence",
            "information_root": "test-source-001",
            "evidence_class": "analyst_hypothesis",
            "confidence": "unknown",
            "independently_confirmed": False,
        }],
    }


def run_cli(state, content):
    with patch.dict(os.environ, {"AIBA_REPORT_JSON": content}), \
         patch("sys.argv", ["import_analyst_report.py", "--state", str(state),
                            "--from-env", "--comment-envelope"]), \
         redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return main()


class IssueHandoffTest(unittest.TestCase):
    def test_versioned_comment_envelope_validates_and_stores(self):
        with tempfile.TemporaryDirectory() as d:
            batch = fixture()
            run_cli(d, "AIBA-OSINT-V1\n" + json.dumps(batch))
            report = load_history(d)
            self.assertEqual(report["run_count"], 1)
            self.assertEqual(report["distinct_observations"], 1)
            self.assertEqual(report["records"][0]["observation_id"], "test-source-lead-001")
            # Identical repeat submission cannot produce a second report.
            run_cli(d, "AIBA-OSINT-V1\n" + json.dumps(batch))
            self.assertEqual(load_history(d)["run_count"], 1)

    def test_rejects_unprefixed_or_malformed_comments(self):
        with tempfile.TemporaryDirectory() as d:
            batch = fixture()
            for invalid in (json.dumps(batch), "AIBA-OSINT-V2\n" + json.dumps(batch),
                            "AIBA-OSINT-V1\nhello", "AIBA-OSINT-V1\n{}"):
                with self.subTest(invalid=invalid[:45]):
                    with self.assertRaises((SystemExit, ValueError, json.JSONDecodeError)):
                        run_cli(d, invalid)
            self.assertFalse((Path(d) / "analyst" / "history").exists())

    def test_failed_collection_has_no_new_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            b = fixture()
            b["status"] = "failed"
            with self.assertRaises(ValueError):
                run_cli(d, "AIBA-OSINT-V1\n" + json.dumps(b))


if __name__ == "__main__":
    unittest.main()
