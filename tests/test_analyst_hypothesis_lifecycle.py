"""Analyst-origin hypotheses become case ACH peers after one initialization."""
import datetime as dt
import unittest
from dashboard.hypothesis_evidence import build
from scripts.approve_analyst_hypothesis import approve
from scripts.initialize_analyst_hypotheses import initialize, candidate_packet
NOW=dt.datetime(2026,11,23,15,0,tzinfo=dt.timezone.utc)
TEXT="Scheduled defensive exercises explain these movements without an impending attack."
def entry():
    return {"id":"analyst-1234567890abcdef","case_id":"taiwan","statement":TEXT,
            "origin":"analyst","active":True,
            "initial_backfill":{"status":"pending","evaluations":[],"source_references":[]}}
def archive():
    return {"schema":"aiba.family-archive.v1",
      "records":[{"id":"r-1","title":"Taiwan Strait airspace restriction for exercises",
        "source_url":"https://example.org/notice","information_root":"root-one",
        "collection_mode":"live_airspace","source_family":"aviation",
        "first_observed_at":"2026-11-21T00:00:00Z"},
       {"id":"r-1-dup","title":"Taiwan Strait airspace restriction for exercises",
        "source_url":"https://example.org/mirror","information_root":"root-one",
        "collection_mode":"live_airspace","source_family":"aviation"},
       {"id":"r-2","title":"Unrelated event","source_url":"https://example.org/distant",
        "collection_mode":"commercial","source_family":"market"}]}
def config():
    return {"schema":"cairn.hypothesis-reviews.v1","reviews":[],
            "alternative_hypotheses":{},"analyst_hypotheses":[entry()]}
def dossier():
    return {"id":"taiwan","name":"Taiwan scenario","scenario":"Military preparations could precede an attack.",
            "alternatives":"Scheduled exercises explain the activity.", "analysis":"Illustrative only",
            "evidence":[{"title":"Taiwan Strait exercise public notice","source_url":"https://example.org/notice"}]}
class AnalystLifecycleTests(unittest.TestCase):
    def test_backfill_one_time_and_deduplicated_roots(self):
        cfg=config()
        changed=initialize(cfg,archive(),clock=NOW)
        self.assertEqual(changed,1)
        result=cfg["analyst_hypotheses"][0]["initial_backfill"]
        self.assertEqual(result["status"],"interpretation_pending")
        self.assertEqual(result["source_inventory"]["matched_roots"],1)
        self.assertEqual(result["evaluated_source_ids"],["r-1"])
        self.assertTrue(result["limitations"])
        self.assertEqual(initialize(cfg,archive(),clock=NOW),0)
    def test_activation_joins_shared_ach_with_historical_record(self):
        cfg=config()
        initialize(cfg,archive(),clock=NOW)
        view=build([dossier()],{}, {},cfg)
        c=view["hypotheses"][0]
        self.assertEqual(c["alternatives"][1],TEXT)
        self.assertEqual(c["analyst_hypotheses"][0]["index"],2)
        self.assertEqual(c["analyst_hypotheses"][0]["id"],entry()["id"])
        self.assertEqual(c["balance"]["direction"],"not_assessed")
        self.assertTrue(any(f["origin"]=="analyst_initial_backfill_unreviewed"
                            for f in c["families"]))
    def test_live_model_interpretation_is_provisional(self):
        cfg=config()
        def runner(packet,key,model):
            self.assertEqual(packet["hypotheses"],[TEXT])
            return {"interpretations":[{"hypothesis_index":0,
                "meaning":"Routine exercise rather than invasion",
                "discriminator":"Compare against filed exercise ranges and schedules."}],
                "evaluations":[{"hypothesis_index":0,
                    "evidence_key":packet["evidence_families"][0]["evidence_key"],
                    "direction":"possibly_consistent","rationale":"Exercise notice may fit scheduled training",
                    "analyst_approved":False}]}
        initialize(cfg,archive(),api_key="synthetic",model="fixture",clock=NOW,runner=runner)
        state=cfg["analyst_hypotheses"][0]["initial_backfill"]
        self.assertEqual(state["status"],"initial_review_complete")
        self.assertFalse(state["evaluations"][0]["analyst_approved"])
        self.assertEqual(initialize(cfg,archive(),api_key="synthetic",model="fixture",runner=runner),0)
    def test_archive_unavailable_is_not_all_clear(self):
        cfg=config()
        initialize(cfg,{},clock=NOW)
        state=cfg["analyst_hypotheses"][0]["initial_backfill"]
        self.assertEqual(state["status"],"archive_incomplete")
        self.assertEqual(state["evaluated_source_ids"],[])
        self.assertTrue(state["limitations"])
if __name__=="__main__": unittest.main()
