"""Input validation for bounded, user-dispatched historical GDELT downloads."""
import datetime as dt
import unittest
from scripts.historical_gdelt_baseline import parse_range


class HistoricalRangeTests(unittest.TestCase):
    def test_slashes_and_hyphens_normalize_to_same_range(self):
        first, last = parse_range("2026/07/10", "2026-09-07")
        self.assertEqual(first, dt.date(2026, 7, 10))
        self.assertEqual(last, dt.date(2026, 9, 7))
        self.assertEqual((last - first).days + 1, 60)

    def test_exactly_120_days_allowed(self):
        first, last = parse_range("2026-07-10", "2026-11-06")
        self.assertEqual((last - first).days + 1, 120)

    def test_121_days_requires_balanced_chunks(self):
        with self.assertRaises(ValueError) as err:
            parse_range("2026/07/10", "2026/11/07")
        message = str(err.exception)
        self.assertIn("121 inclusive days", message)
        self.assertIn("2026-07-10 through 2026-09-08 (61 days)", message)
        self.assertIn("2026-09-09 through 2026-11-07 (60 days)", message)

    def test_bad_dates_and_reverse_date_are_rejected(self):
        for start, end in [
            ("07/10/2026", "2026-09-07"),
            ("2026/07-10", "2026-09-07"),
            ("2026-02-30", "2026-09-07"),
            ("2026-11-07", "2026-07-10"),
        ]:
            with self.subTest(start=start, end=end):
                with self.assertRaises(ValueError):
                    parse_range(start, end)


if __name__ == "__main__":
    unittest.main()
