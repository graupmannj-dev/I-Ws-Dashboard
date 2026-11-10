"""Regression tests: incomplete GDELT cannot create new discovery leads."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiba_v4


class PartialGdeltPublicationTests(unittest.TestCase):
    def test_partial_build_suppresses_unverified_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.object(aiba_v4, "ingest", return_value=({}, {}, {}, set(), {})), \
                 patch.object(aiba_v4, "analyze", return_value=([{"id": "false-lead", "scope": "Algorithmic lead"}], {"recent_days": 6, "baseline_days": 28})):
                result = aiba_v4.build(out=out, asof=dt.date(2026, 11, 8),
                                       suppress_incomplete_discovery=True)
            self.assertEqual(result["discovery_status"], "missing_data")
            self.assertNotIn("false-lead", [h["id"] for h in result["hotspots"]])
            self.assertEqual(json.loads((out / "hotspots.json").read_text())["discovery_status"], "missing_data")

    def test_strict_build_still_refuses_partial_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(aiba_v4, "ingest", return_value=({}, {}, {}, set(), {})), \
                 patch.object(aiba_v4, "analyze", return_value=([], {"recent_days": 6, "baseline_days": 28})):
                with self.assertRaisesRegex(ValueError, "REFUSING TO PUBLISH"):
                    aiba_v4.build(out=Path(tmp), asof=dt.date(2026, 11, 8), strict=True)


if __name__ == "__main__":
    unittest.main()
