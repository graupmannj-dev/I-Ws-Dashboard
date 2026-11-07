import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops_pipeline import UTC, iso, write_json
from watchlist_collector import collect_watchlist, parse_contract
from fusion_briefs import (
    change_in_notices, recent_snapshot, market_changes,
    build, matches_case
)

NOW = dt.datetime(2026, 11, 7, 21, 0, tzinfo=UTC)
CLOCK = lambda: NOW

def market(id="manifold:abc", price=.20, time="2026-11-07T15:00:00Z",
           eligible=True, case_id="taiwan"):
    return {"id": id, "price": price, "observed_at": time,
            "market_question": "Will China blockade Taiwan in 2026?",
            "case_id": case_id, "event": "Taiwan blockade 2026", "effect": "escalation",
            "status": "eligible" if eligible else "thin_market",
            "source_url": "https://example.org/market", "caveat": "Blockade not invasion",
            "end_at": "2027-01-01T05:00:00Z"}

class FusionBriefTests(unittest.TestCase):
    def test_registry_id_and_question_required(self):
        entry = {"id": "manifold:abc", "case_id": "taiwan", "event": "blockade", "effect": "escalation",
                 "expected": "will china blockade taiwan", "min_liquidity": 50,
                 "horizon": "2026-12-31", "caveat": "not invasion"}
        payload = {"id": "abc", "outcomeType": "BINARY", "question": "Will China blockade Taiwan?",
                   "probability": 0.4, "totalLiquidity": 1000, "closeTime": 1798761600000}
        x = parse_contract(entry, payload, NOW)
        self.assertEqual(x["status"], "eligible")
        self.assertEqual(x["case_id"], "taiwan")
        with self.assertRaisesRegex(ValueError, "Question changed"):
            parse_contract(entry, dict(payload, question="Will China invade Canada?"), NOW)
        with self.assertRaisesRegex(ValueError, "Market ID"):
            parse_contract(entry, dict(payload, id="bad"), NOW)

    def test_thin_and_expired_markets_ineligible(self):
        c = {"id": "manifold:abc", "case_id": "taiwan", "event": "test", "effect": "escalation",
             "expected": "will china blockade taiwan", "min_liquidity": 900,
             "horizon": "2026-12-31", "caveat": ""}
        p = {"id": "abc", "outcomeType": "BINARY", "question": "Will China blockade Taiwan?",
             "probability": .82, "totalLiquidity": 100, "closeTime": 1798761600000}
        self.assertEqual(parse_contract(c, p, NOW)["status"], "thin_market")
        self.assertEqual(parse_contract(c, dict(p, isResolved=True), NOW)["status"], "expired_or_closed")

    def test_first_collection_is_not_a_new_notice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_json(root/"latest"/"official.json", {
                "observed_at": iso(NOW), "records": [{
                    "source_url": "https://state.gov/advisory", "title": "Iran Do Not Travel",
                    "published_at": "2026-11-07T19:00:00Z"}]})
            cfg = {"patterns": ["\\biran\\b"]}
            changes, state = change_in_notices(root, "official", NOW, cfg, recent_snapshot(root, "official", NOW))
            self.assertFalse(changes)
            self.assertFalse(state["baseline"])

    def test_undated_standing_advisory_not_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prior = {"observed_at": "2026-11-07T15:00:00Z",
                     "records": [{"source_url": "https://state.gov/advisory",
                                  "title": "Iran Do Not Travel", "published_at": None}]}
            current = {"observed_at": iso(NOW), "records": prior["records"]}
            write_json(root/"history"/"official"/"20261107T150000Z.json", prior)
            write_json(root/"latest"/"official.json", current)
            changes, info = change_in_notices(root,"official",NOW, {"patterns":["\\biran\\b"]},recent_snapshot(root, "official", NOW))
            self.assertFalse(changes)
            self.assertTrue(info["baseline"])
            current["records"] = [dict(prior["records"][0], title="Iran Level 3: Reconsider Travel")]
            write_json(root/"latest"/"official.json", current)
            changes,_=change_in_notices(root,"official",NOW,{"patterns":["\\biran\\b"]},recent_snapshot(root,"official",NOW))
            self.assertEqual(changes[0]["kind"],"revision_observed_between_checks")
            self.assertIsNone(changes[0]["published_at"])

    def test_no_cross_case_conflation(self):
        self.assertFalse(matches_case({"patterns":["\\bethiopia\\b.{0,80}\\bsudan\\b","\\bsudan\\b.{0,80}\\bethiopia\\b"]},
                                     {"title":"Sudan under travel advisory"}))
        self.assertTrue(matches_case({"patterns":["\\bethiopia\\b.{0,80}\\bsudan\\b"]},
                                    {"title":"Ethiopia and Sudan exchange protests"}))

    def test_market_requires_same_question_and_price_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            old = {"observed_at":"2026-11-07T15:00:00Z",
                   "records":[market(price=.20,time="2026-11-07T15:00:00Z")]}
            current = {"observed_at":iso(NOW),
                       "records":[market(price=.33,time=iso(NOW))]}
            write_json(root/"history"/"watchlist"/"20261107T150000Z.json", old)
            write_json(root/"history"/"watchlist"/"20261107T210000Z.json", current)
            write_json(root/"latest"/"watchlist.json", current)
            moves, diag = market_changes(root,recent_snapshot(root,"watchlist",NOW),NOW)
            self.assertEqual(len(moves),1)
            self.assertEqual(moves[0]["change_pp"],13)
            self.assertEqual(moves[0]["window"],"6h")
            # Market question changed: old record no longer provides a valid comparator.
            old["records"][0]["market_question"]="Will Taiwan become independent?"
            write_json(root/"history"/"watchlist"/"20261107T150000Z.json", old)
            self.assertFalse(market_changes(root,recent_snapshot(root,"watchlist",NOW),NOW)[0])

    def test_stale_snapshots_cannot_generate_move(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            current = {"observed_at":"2026-11-06T10:00:00Z",
                       "records":[market(price=.9,time="2026-11-06T10:00:00Z")]}
            write_json(root/"latest"/"watchlist.json", current)
            self.assertFalse(market_changes(root,recent_snapshot(root,"watchlist",NOW),NOW)[0])

    def test_thin_market_cannot_trigger(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            past={"observed_at":"2026-11-07T15:00:00Z","records":[market(price=.1,time="2026-11-07T15:00:00Z")]}
            latest={"observed_at":iso(NOW),"records":[market(price=.95,time=iso(NOW),eligible=False)]}
            write_json(root/"history"/"watchlist"/"20261107T150000Z.json",past)
            write_json(root/"latest"/"watchlist.json",latest)
            self.assertFalse(market_changes(root,recent_snapshot(root,"watchlist",NOW),NOW)[0])

    def test_fusion_outputs_next_indicator_not_automatic_escalation(self):
        with tempfile.TemporaryDirectory() as d:
            output=build(d, clock=CLOCK)
            self.assertEqual(len(output["cases"]),10)
            self.assertEqual(output["new_change_count"],0)
            self.assertIn("not a no-risk",output["executive_summary"])
            self.assertEqual(output["cases"][0]["collection_priority"],"Collection gap")
            self.assertTrue(all(x["what_would_change_assessment"] for x in output["cases"]))
            self.assertTrue(all("No automated classification" in x["verification"] for x in output["cases"]))

    def test_source_failures_never_turn_into_fresh_updates(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            write_json(root/"latest"/"official.json",
                       {"observed_at":"2026-11-01T00:00:00Z","records":[
                        {"title":"Iran military action", "source_url":"https://example.org/a",
                         "published_at":"2026-11-01T00:00:00Z"}]})
            result=build(root,clock=CLOCK)
            iran=next(x for x in result["cases"] if x["id"]=="iran_gulf")
            self.assertEqual(iran["official_change_count"],0)
            self.assertEqual(result["source_health"]["official"]["status"],"stale_or_missing")

    def test_watchlist_fails_closed_on_wrong_id_and_preserves_prior(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            cfg={"version":1,"markets":[{
                "id":"manifold:abc","expected":"will china blockade taiwan","case_id":"taiwan",
                "event":"Taiwan blockade", "effect":"escalation","horizon":"2026-12-31",
                "min_liquidity":100,"caveat":""}]}
            f=root/"registry.json";f.write_text(json.dumps(cfg))
            existing={"observed_at":"2026-11-06T00:00:00Z","records":[{"id":"old"}]}
            write_json(root/"latest"/"watchlist.json",existing)
            health=collect_watchlist(root,registry=f,fetch=lambda _:{"id":"bad","question":"x"},clock=CLOCK)
            self.assertEqual(health["status"],"unavailable")
            self.assertEqual(json.loads((root/"latest"/"watchlist.json").read_text()),existing)

if __name__=="__main__":
    unittest.main()
