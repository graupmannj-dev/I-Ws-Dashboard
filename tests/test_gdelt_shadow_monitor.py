"""Source-compatible GDELT shadow baseline regression tests: synthetic data."""
import datetime as dt
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.gdelt_shadow_monitor import analyze_day, run, collect_forward

BASE = dt.date(2026, 7, 1)


def daily(n, total=1000, stable=60, emergent=0):
    day = BASE + dt.timedelta(days=n)
    counts = {"BILAT:RUS:UKR": stable, "DOMESTIC:AAA": total - stable - emergent}
    if emergent:
        counts["BILAT:CHN:PHL"] = emergent
    return {"day": day.strftime("%Y%m%d"), "rows": total + 100,
            "selected": total, "counts": counts}


def dataset(size=120, anomaly=False):
    by = {}
    for n in range(size):
        item = daily(n, stable=150 if anomaly and n == size - 1 else 60,
                     emergent=15 if anomaly and n == size - 1 else 0)
        by[BASE + dt.timedelta(days=n)] = item
    return by


class ShadowBaselineTests(unittest.TestCase):
    def test_same_day_is_excluded_from_baseline(self):
        by = dataset(anomaly=True)
        day = max(by)
        result = analyze_day(by, day)
        self.assertTrue(result["baseline"]["eligible"])
        self.assertEqual(result["baseline"]["valid_days"], 90)
        established = [r for r in result["established_leads"] if r["case"] == "BILAT:RUS:UKR"]
        self.assertEqual(len(established), 1)
        self.assertEqual(established[0]["current_count"], 150)
        self.assertEqual(established[0]["baseline_event_count"], 90 * 60)
        self.assertFalse(established[0]["executive_eligible"])
        emerging = [r for r in result["emerging_leads"] if r["case"] == "BILAT:CHN:PHL"]
        self.assertEqual(len(emerging), 1)
        self.assertIsNone(emerging[0]["ratio_to_baseline"])

    def test_one_missing_recent_day_invalidates_comparison(self):
        by = dataset()
        yesterday = max(by) - dt.timedelta(days=1)
        del by[yesterday]
        result = analyze_day(by, max(by))
        self.assertFalse(result["baseline"]["eligible"])
        self.assertFalse(result["baseline"]["complete_last_28_days"])
        self.assertEqual(result["established_leads"], [])

    def test_cannot_look_ahead(self):
        by = dataset(size=50)
        target = BASE + dt.timedelta(days=38)
        r1 = analyze_day(by, target)
        by[BASE + dt.timedelta(days=49)]["counts"]["BILAT:RUS:UKR"] = 500
        r2 = analyze_day(by, target)
        self.assertEqual(r1, r2)

    def test_forward_collection_and_manifest_indicate_forward_vs_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "historical" / "daily.jsonl"
            history.parent.mkdir()
            history.write_text("".join(json.dumps(v) + "\n" for v in dataset().values()))
            report = run([str(history)], root / "out")
            self.assertEqual(report["mode"], "historical_replay_only")
            self.assertTrue(report["latest_comparison_eligible"])

    def test_missing_provider_archive_is_recorded_not_zero(self):
        by = dataset()
        start = max(by)
        class FakeUnreachable(Exception):
            pass
        def fetcher(url):
            raise ValueError("HTTP 404 unavailable")
        added, failed = collect_forward(by, start + dt.timedelta(days=1), fetcher=fetcher)
        self.assertEqual(added, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(max(by), start)

    def test_forward_bound_blocks_unlimited_downloads(self):
        by = dataset()
        with self.assertRaisesRegex(ValueError, "Forward gap"):
            collect_forward(by, max(by) + dt.timedelta(days=15), fetcher=lambda _: b"")

    def test_synthetic_download_validates_archive(self):
        by = dataset()
        day = max(by) + dt.timedelta(days=1)
        fields = [""] * 57
        fields[7], fields[17], fields[28] = "RUS", "UKR", "19"
        data = ("\t".join(fields) + "\n").encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as f:
            f.writestr(day.strftime("%Y%m%d") + ".export.CSV", data)
        added, failed = collect_forward(by, day, fetcher=lambda _: output.getvalue())
        self.assertEqual(added, [day])
        self.assertEqual(failed, [])
        self.assertEqual(by[day]["counts"]["BILAT:RUS:UKR"], 1)


if __name__ == "__main__":
    unittest.main()
