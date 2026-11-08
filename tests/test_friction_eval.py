"""Walk-forward descriptive evaluation never turns synthetic labels into production truth."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from friction_eval import evaluate, validate_labels
from friction_pipeline import write_json

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 12, 18, 0, tzinfo=UTC)


def stamp(y, m, d, h=0):
    return dt.datetime(y, m, d, h, tzinfo=UTC).isoformat()


def case_label(key, kind, start, end, event=None):
    return {"label_id": key, "case_id": "taiwan", "outcome": kind,
            "window_start": start, "window_end": end,
            "event_at": event, "finalized_at": stamp(2026, 11, 12),
            "source_url": "https://example.org/verified-outcome"}


class FrictionEvaluationTest(unittest.TestCase):
    def test_no_labeled_windows_is_not_estimable(self):
        with tempfile.TemporaryDirectory() as d:
            a = evaluate(d, {"version": 1, "horizon_hours": 72, "labels": []}, now=NOW)
            self.assertEqual(a["status"], "not_estimable")
            self.assertEqual(a["positive_windows"], 0)
            self.assertEqual(a["negative_windows"], 0)
            self.assertNotIn("precision", a)

    def test_no_post_event_hindsight_counts_as_early_warning(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            folder = state / "history" / "friction_triage"
            for h in (3, 15, 19):
                write_json(folder / f"20261108T{h:02d}0000Z.json", {
                    "asof": stamp(2026, 11, 8, h), "shadow_mode": True,
                    "triage": {"taiwan": "source_review"}
                })
            labels = {"version": 1, "horizon_hours": 72, "labels": [
                case_label("event-one", "event", stamp(2026, 11, 8),
                           stamp(2026, 11, 9), stamp(2026, 11, 8, 17)),
                case_label("negative-two", "no_event", stamp(2026, 11, 9),
                           stamp(2026, 11, 10)),
            ]}
            out = evaluate(state, labels, now=NOW, write=False)
            self.assertEqual(out["pre_event_reviewed"], 1)
            self.assertEqual(out["non_event_windows_with_review"], 0)
            self.assertGreater(out["lead_hours_in_labeled_events"][0], 0)
            self.assertIn("Descriptive", out["interpretation"])

    def test_after_event_review_alone_is_not_lead(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            write_json(state / "history" / "friction_triage" / "trace.json", {
                "asof": stamp(2026, 11, 8, 19), "shadow_mode": True,
                "triage": {"taiwan": "multi_stream_review"}
            })
            labels = {"version": 1, "horizon_hours": 72, "labels": [
                case_label("event-one", "event", stamp(2026, 11, 8),
                           stamp(2026, 11, 9), stamp(2026, 11, 8, 17)),
            ]}
            out = evaluate(state, labels, now=NOW, write=False)
            self.assertEqual(out["pre_event_reviewed"], 0)
            self.assertEqual(out["event_windows_without_prior_review"], 1)

    def test_invalid_labels_never_become_metrics(self):
        with self.assertRaises(ValueError):
            validate_labels({"version": 1, "horizon_hours": 72, "labels": [
                case_label("bad-one", "event", stamp(2026, 11, 8),
                           stamp(2026, 11, 9), stamp(2026, 11, 10)),
            ]})
        with self.assertRaises(ValueError):
            validate_labels({"version": 1, "horizon_hours": 72, "labels": [
                case_label("bad-two", "no_event", stamp(2026, 11, 8),
                           stamp(2026, 11, 9), stamp(2026, 11, 8, 18)),
            ]})


if __name__ == "__main__":
    unittest.main()
