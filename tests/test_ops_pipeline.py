import datetime as dt
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from ops_pipeline import (
    as_number, collect_markets, collect_official, collect_commercial,
    ingest_mode, load_json, parse_time, update_fusion, audit, iso, UTC,
)

NOW = dt.datetime(2026, 11, 7, 18, 0, tzinfo=UTC)
CLOCK = lambda: NOW

class OperationalPipelineTests(unittest.TestCase):
    def test_time_parser_is_utc(self):
        self.assertEqual(iso(parse_time("Sat, 07 Nov 2026 15:00:00 GMT")), "2026-11-07T15:00:00Z")
        self.assertEqual(iso(parse_time("20261107150000")), "2026-11-07T15:00:00Z")
        self.assertIsNone(parse_time("not a timestamp"))

    def test_market_values_bounded(self):
        self.assertIsNone(as_number("NaN"))
        def fake(url):
            if "manifold" in url:
                return [{"id": "abc", "question": "Will Taiwan be blockaded by 2027?",
                         "outcomeType": "BINARY", "probability": 0.42,
                         "url": "https://manifold.markets/user/taiwan-blockade"},
                        {"id": "def", "question": "Bad price",
                         "outcomeType": "BINARY", "probability": 2}]
            return [{"slug": "iran-crisis",
                     "markets": [{"id": "123", "question": "Will Iran be attacked?",
                                  "outcomes": '["Yes","No"]', "outcomePrices": '["0.36","0.64"]'}]}]
        rows, errors, requests = collect_markets(fetch=fake, clock=CLOCK)
        self.assertFalse(errors)
        self.assertEqual(requests, 8)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["price"] for r in rows}, {0.42, 0.36})
        self.assertTrue(all(r["status"].startswith("candidate") for r in rows))

    def test_official_xml_dated_and_provenanced(self):
        rss = ET.fromstring("<rss><channel><item><title>Iran - Level 4</title><link>https://example.org/a</link><pubDate>Sat, 07 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>")
        atom = ET.fromstring('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Kenya</title><link href="https://example.org/b"/><updated>2026-11-07T15:00:00Z</updated></entry></feed>')
        rows, errors, total = collect_official(fetch=lambda url: rss if "state.gov" in url else atom, clock=CLOCK)
        self.assertEqual((total, len(errors), len(rows)), (2, 0, 2))
        self.assertEqual({r["publisher"] for r in rows}, {"UK FCDO", "US State Department"})
        self.assertEqual(rows[0]["published_at"], "2026-11-07T12:00:00Z")
        self.assertTrue(all(r["assessment"].endswith("military_preparation") for r in rows))

    def test_commercial_is_media_mention_not_confirmation(self):
        result = {"articles":[{"url":"https://news.example/a", "title":"Airline flights suspended near Iran", "seendate":"20261107T150000Z"},
                              {"url":"https://news.example/b", "title":"Ordinary politics"}]}
        rows, errors, attempts = collect_commercial(fetch=lambda _: result, clock=CLOCK)
        self.assertEqual(len(rows), 1)
        self.assertEqual(attempts, 3)
        self.assertEqual(rows[0]["assessment"], "media_mention_unverified_not_independent_actor_behavior")

    def test_source_failure_does_not_erase_previous_latest(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            original = {"records": [{"id": "prior"}], "observed_at": "2026-11-06T00:00:00Z"}
            (state / "latest").mkdir()
            (state / "latest" / "markets.json").write_text(json.dumps(original))
            result = ingest_mode(state, "markets", collectors={
                "markets": lambda: ([], [{"source": "a", "error": "down"}], 1)}, clock=CLOCK)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(load_json(state / "latest" / "markets.json"), original)
            self.assertEqual(load_json(state / "health" / "markets.json")["source_queries_ok"], 0)

    def test_fusion_requires_prior_18_to_36_hour_observation(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            (state / "history" / "markets").mkdir(parents=True)
            (state / "latest").mkdir()
            def market(price, at):
                return {"id": "manifold:tw", "title": "Taiwan blockade before 2027",
                        "price": price, "scenario_tags": ["Taiwan Strait"], "observed_at": at,
                        "market_url": "https://manifold.markets/user/slug"}
            before = {"observed_at": "2026-11-06T18:00:00Z", "records": [market(.20, "2026-11-06T18:00:00Z")]}
            current = {"observed_at": "2026-11-07T18:00:00Z", "records": [market(.37, "2026-11-07T18:00:00Z")]}
            (state / "history" / "markets" / "20261106T180000Z.json").write_text(json.dumps(before))
            (state / "history" / "markets" / "20261107T180000Z.json").write_text(json.dumps(current))
            (state / "latest" / "markets.json").write_text(json.dumps(current))
            result = update_fusion(state, clock=CLOCK)
            self.assertEqual(len(result["preconvergence_leads"]), 1)
            self.assertEqual(result["preconvergence_leads"][0]["kind"], "quiet_discrepancy_candidate")
            self.assertEqual(result["market_moves"][0]["change_24h_approx"], 0.17)
            self.assertIn("No validated conflict event posterior", result["warnings"])
    
    def test_audit_cannot_invent_validation_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            data = audit(root, clock=CLOCK)
            self.assertIn("NOT ESTIMABLE", data["warning_performance"])
            self.assertEqual(data["source_history_coverage"]["markets"]["snapshots"], 0)

if __name__ == "__main__":
    unittest.main()
