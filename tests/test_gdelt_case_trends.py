"""Exact-pair GDELT case profile tests: always measurable when source is complete."""
import datetime as dt
import json
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from scripts.gdelt_case_trends import build, SCHEMA
from dashboard.build_atlas import generate

DAY = dt.date(2026, 11, 22)
DATES = [DAY - dt.timedelta(days=i) for i in range(34, -1, -1)]


class GdeltCaseTrendTests(unittest.TestCase):
    def setup_data(self):
        total = {d: 100 for d in DATES}
        rows = Counter()
        taiwan = ("BILAT", ("CHN", "TWN"))
        ethiopia = ("BILAT", ("ERI", "ETH"))
        for d in DATES[:28]:
            rows[(d, taiwan)] = 4
            rows[(d, ethiopia)] = 1
        for d in DATES[28:]:
            rows[(d, taiwan)] = 12
            rows[(d, ethiopia)] = 0
        return rows, total

    def test_all_cases_measured_even_without_global_nomination(self):
        records, total = self.setup_data()
        output = build(records, total, DATES, DAY)
        self.assertEqual(output["schema"], SCHEMA)
        self.assertEqual(output["status"], "measured")
        self.assertEqual(output["measured_case_count"], 10)
        self.assertFalse(output["hypothesis_direction_estimated"])
        tw = output["cases"]["taiwan"]
        self.assertEqual(tw["baseline_coded_records"], 112)
        self.assertEqual(tw["recent_coded_records"], 84)
        self.assertEqual(tw["media_share_ratio"], 3)
        self.assertEqual(tw["trend"], "higher_coded_share")
        self.assertEqual(len(tw["daily_counts"]), 35)
        self.assertEqual(tw["direction_of_hypothesis"], "not_inferred")
        eth = output["cases"]["horn_ethiopia_eritrea"]
        self.assertEqual(eth["trend"], "lower_coded_share")
        self.assertEqual(eth["recent_coded_records"], 0)
        # A complete but unobserved matching actor pair has coded zero,
        # not proof the underlying event did not occur.
        self.assertEqual(output["cases"]["drc_rwanda"]["recent_coded_records"], 0)
        self.assertIsNone(output["cases"]["drc_rwanda"]["media_share_ratio"])
        self.assertEqual(output["cases"]["drc_rwanda"]["trend"], "equal_coded_share")

    def test_missing_day_never_imputed_as_zero_or_produces_direction(self):
        records, total = self.setup_data()
        output = build(records, total, DATES[:-1], DAY)
        self.assertEqual(output["status"], "unavailable_incomplete_coverage")
        for case in output["cases"].values():
            self.assertIsNone(case["recent_coded_records"])
            self.assertIsNone(case["baseline_share"])
            self.assertIsNone(case["daily_counts"])
            self.assertIsNone(case["media_share_ratio"])

    def test_zero_denominator_blocks_comparative_direction(self):
        records, total = self.setup_data()
        total[DATES[0]] = 0
        for d in DATES[:28]:
            total[d] = 0
        result = build(records, total, DATES, DAY)
        self.assertEqual(result["status"], "unavailable_incomplete_coverage")
        self.assertIsNone(result["cases"]["taiwan"]["recent_share"])

    def test_builder_passes_case_data_into_generated_hypothesis_index(self):
        records, total = self.setup_data()
        ctx = build(records, total, DATES, DAY)
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "hotspots.json").write_text(json.dumps({"asof": DAY.isoformat()}))
            (site / "gdelt_case_trends.json").write_text(json.dumps(ctx))
            generate(site, generated="2026-11-23T12:00:00Z")
            output=json.loads((site/"hypotheses.json").read_text())
            self.assertEqual(output["gdelt_case_status"]["measured_case_count"],10)
            cases={c["id"]:c for c in output["hypotheses"]}
            self.assertEqual(cases["taiwan"]["gdelt_media_trend"]["media_share_ratio"],3)
            self.assertIsNone(cases["taiwan"]["balance"]["signed_ordinal_balance"])
            self.assertEqual(cases["taiwan"]["balance"]["direction"],"not_assessed")


if __name__ == "__main__":
    unittest.main()
