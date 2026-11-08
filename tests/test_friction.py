"""Offline regressions for public-source friction capture and conservative synthesis."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from friction_pipeline import (
    amsa_records, collect, event_time, ioda_records, nga_records, read_json, write_json,
)
from friction_synthesis import build, robust_change, unique_recent, baseline
from friction_render import publish

UTC = dt.timezone.utc
AT = dt.datetime(2026, 11, 8, 18, 30, tzinfo=UTC)


def ioda_fixture(t=AT, ident="test-event-one"):
    # Mirrors the live IODA v2 outages.events envelope observed in PR CI.
    return {"type": "outages.events", "error": None, "data": [{
        "location": "country/IR",
        "location_name": "Iran",
        "datasource": "bgp",
        "method": "data-driven",
        "start": int((t - dt.timedelta(minutes=45)).timestamp()),
        "status": 0, "duration": 1800, "uncertainty": None,
        "overlaps_window": False, "score": 2000.0,
    }], "metadata": {"pagination": {}}}


def nga_fixture(t=AT, number="17"):
    return {"warnings": [{
        "msgNumber": number, "msgYear": 2026, "navArea": "XII",
        "title": "Live-fire exercise near Strait of Hormuz",
        "warningText": "Navigation safety warning. Military exercise in the Strait of Hormuz.",
        "issueDate": (t - dt.timedelta(minutes=25)).isoformat(),
    }]}


def amsa_fixture():
    return """<html><body><pre>SECURITE
FM JRCC AUSTRALIA 080330Z NOV 26
NAVAREA X 121/26
SPACE DEBRIS DANGER AREA SOUTH INDIAN OCEAN.
NNNN</pre></body></html>"""


class FrictionCollectorTests(unittest.TestCase):
    def test_ioda_is_country_context_not_attribution(self):
        data, more = ioda_records(ioda_fixture(), AT)
        self.assertFalse(more)
        self.assertEqual(data[0]["case_id"], "iran_gulf")
        self.assertEqual(data[0]["family"], "internet_reachability")
        self.assertEqual(data[0]["entity_type"], "country")
        self.assertEqual(data[0]["entity_code"], "IR")
        self.assertEqual(data[0]["signal_types"], ["bgp"])
        self.assertEqual(data[0]["detection_method"], "data-driven")
        self.assertEqual(data[0]["source_score"], 2000.0)
        self.assertIsNone(data[0]["source_published_at"])
        self.assertTrue(data[0]["event_at"].endswith("Z"))
        self.assertIn("not", data[0]["summary"].lower())

    def test_ioda_live_envelope_can_return_genuine_zero_events(self):
        rows, more = ioda_records({"type": "outages.events", "error": None,
                                   "data": [], "metadata": {}}, AT)
        self.assertEqual(rows, [])
        self.assertFalse(more)
        with self.assertRaises(ValueError):
            ioda_records({"type": "outages.events", "error": "Upstream failed",
                          "data": []}, AT)

    def test_ioda_distinguishes_measurements_but_not_as_separate_source_families(self):
        example = ioda_fixture()
        first = dict(example["data"][0])
        second = {**first, "datasource": "ping-slash24"}
        rows, _ = ioda_records({**example, "data": [first, second]}, AT)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        self.assertEqual({r["family"] for r in rows}, {"internet_reachability"})

    def test_nga_detects_navigation_warning_without_invented_polygon(self):
        records, more = nga_records(nga_fixture(), AT)
        self.assertFalse(more)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["kind"], "military_hazard_mention")
        self.assertEqual(records[0]["case_id"], "iran_gulf")
        self.assertNotIn("lat", records[0])
        self.assertNotIn("lon", records[0])

    def test_amsa_official_warning_retains_source_issued_time(self):
        rows, more = amsa_records(amsa_fixture(), AT)
        self.assertFalse(more)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "amsa")
        self.assertEqual(rows[0]["event_at"], "2026-11-08T03:30:00Z")
        self.assertIsNone(rows[0]["case_id"])
        self.assertNotIn("lat", rows[0])

    def test_unknown_response_is_not_an_empty_success(self):
        for parse in (ioda_records, nga_records):
            with self.assertRaises(ValueError):
                parse({"error": "blocked"}, AT)

    def test_repeated_events_are_deduplicated_across_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def f(url):
                return ioda_fixture() if "ioda" in url else nga_fixture()
            first = collect(root, lambda: AT, f, text_fetcher=lambda url: amsa_fixture())
            self.assertEqual(first["coverage"], "collected")
            self.assertEqual(len(first["records"]), 3)
            second = collect(root, lambda: AT + dt.timedelta(minutes=30), f,
                             text_fetcher=lambda url: amsa_fixture())
            self.assertEqual(second["records"][0]["first_seen_at"], first["records"][0]["first_seen_at"])
            files = sorted((root / "history" / "friction").glob("*.json"))
            self.assertEqual(len(files), 2)
            self.assertEqual(len(read_json(files[0])["new_records"]), 3)
            self.assertEqual(len(read_json(files[1])["new_records"]), 0)
            self.assertNotIn("records", read_json(files[1]), "Historical archives store deltas, not full dumps.")
            self.assertEqual(len(read_json(root / "index" / "friction_seen.json")), 3)

    def test_partial_feed_failure_is_visible_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            def fetch(url):
                if "ioda" in url:
                    return ioda_fixture()
                raise TimeoutError("NGA did not respond")
            a = collect(d, lambda: AT, fetch,
                        text_fetcher=lambda url: (_ for _ in ()).throw(TimeoutError()))
            self.assertEqual(a["coverage"], "partial")
            self.assertEqual(a["health"]["nga"]["status"], "unavailable")
            self.assertIsNone(a["health"]["nga"]["records"])
            b = collect(d, lambda: AT + dt.timedelta(minutes=10),
                        lambda url: (_ for _ in ()).throw(TimeoutError()),
                        text_fetcher=lambda url: (_ for _ in ()).throw(TimeoutError()))
            self.assertEqual(b["coverage"], "unavailable")
            self.assertIsNone(b["health"]["ioda"]["records"])
            self.assertEqual(read_json(Path(d) / "latest" / "friction.json")["collected_at"],
                             a["collected_at"], "Last successful observation must not be replaced.")

    def test_naive_source_time_is_unknown(self):
        self.assertIsNone(event_time("2026-11-08T11:00:00"))
        self.assertIsNone(event_time(None))
        self.assertIsNone(event_time(True))


class FrictionSynthesisTests(unittest.TestCase):
    def test_conservative_baseline_and_flat_series(self):
        self.assertEqual(robust_change(50, [])["status"], "insufficient_baseline")
        self.assertEqual(robust_change(1, [0] * 14)["status"], "within_observed_range")
        self.assertEqual(robust_change(8, [0] * 14)["status"], "unusual_count")

    def test_first_collection_is_baseline_not_an_alert(self):
        with tempfile.TemporaryDirectory() as d:
            collect(d, lambda: AT, lambda url: ioda_fixture() if "ioda" in url else nga_fixture(),
                    text_fetcher=lambda url: amsa_fixture())
            r = build(d, clock=lambda: AT)
            self.assertEqual(r["alert_count"], 0)
            self.assertEqual(r["uncalibrated_review_count"], 0)
            self.assertEqual(r["shadow_mode"], True)
            self.assertEqual(len(r["cases"]), 10)

    def test_two_independent_family_observations_are_review_not_severity(self):
        with tempfile.TemporaryDirectory() as d:
            def first(url):
                # Valid, genuine source response with zero observations.
                return {"data": {"events": []}} if "ioda" in url else {"warnings": []}
            collect(d, lambda: AT - dt.timedelta(hours=2), first,
                    text_fetcher=lambda url: amsa_fixture())
            def second(url):
                return ioda_fixture(AT) if "ioda" in url else nga_fixture(AT)
            collect(d, lambda: AT, second,
                    text_fetcher=lambda url: amsa_fixture())
            briefing = build(d, clock=lambda: AT)
            iran = next(c for c in briefing["cases"] if c["id"] == "iran_gulf")
            self.assertEqual(iran["triage"], "multi_stream_review")
            self.assertEqual(set(iran["new_families"]),
                             {"internet_reachability", "maritime_restriction"})
            self.assertEqual(briefing["alert_count"], 0)
            self.assertEqual(iran["standing_state"], next(x for x in read_json(
                Path(__file__).resolve().parent.parent / "data" / "verified_hotspots.json")
                if x["id"] == "iran_gulf")["state"])
            self.assertTrue(briefing["shadow_mode"])
            self.assertTrue((Path(d) / "history" / "friction_triage").exists())

    def test_count_baseline_requires_matched_hours_and_span(self):
        with tempfile.TemporaryDirectory() as d:
            history = []
            for i in range(1, 12):
                when = AT - dt.timedelta(days=i)
                history.append({
                    "collected_at": when.isoformat(), "health": {
                        "ioda": {"status": "collected", "truncated": False}},
                    "case_counts": {"iran_gulf": {"internet_reachability": 1}},
                })
            history.reverse()
            history.append({"collected_at": AT.isoformat(),
                            "health": {"ioda": {"status": "collected"}},
                            "case_counts": {"iran_gulf": {"internet_reachability": 8}}})
            report = baseline(d, history, "iran_gulf", "internet_reachability", AT)
            self.assertEqual(report["status"], "unusual_count")
            self.assertGreaterEqual(report["samples"], 8)

    def test_static_render_reports_missing_and_stale(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            output = publish(root / "missing", root / "site", now=AT)
            self.assertFalse(output["fresh_snapshot"])
            self.assertEqual(output["cases"], [])
            self.assertTrue((root / "site" / "friction_briefs.json").exists())
            write_json(root / "history" / "latest" / "friction_briefs.json",
                       {"schema_version": 1, "shadow_mode": True,
                        "generated_at": (AT - dt.timedelta(days=2)).isoformat(), "cases": []})
            output = publish(root / "history", root / "site", now=AT)
            self.assertFalse(output["fresh_snapshot"])
            self.assertIn("stale", output["executive_summary"].lower())


if __name__ == "__main__":
    unittest.main()
