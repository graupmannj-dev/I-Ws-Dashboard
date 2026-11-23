"""Owner-approved proposals never create directional reviews."""
import unittest
from scripts.approve_analyst_hypothesis import approve
def event(body,owner=320673296):
    return {"action":"labeled","label":{"name":"cairn-hypothesis-approved"},
            "sender":{"id":owner},"issue":{"user":{"id":320673296},"state":"open","body":body}}
class AnalystProposalTests(unittest.TestCase):
    def test_success_and_duplicate(self):
        e=event("Case ID: taiwan\n\nProposed hypothesis:\nRoutine exercises explain the unusual airspace activity.")
        cfg={"schema":"cairn.hypothesis-reviews.v1","reviews":[],"alternative_hypotheses":{}}
        self.assertTrue(approve(e,cfg))
        self.assertFalse(approve(e,cfg))
        self.assertEqual(cfg["reviews"],[])
    def test_reject_nonowner(self):
        with self.assertRaises(ValueError):
            approve(event("Case ID: taiwan\n\nProposed hypothesis:\nRoutine exercises explain the unusual activity.",42),{"schema":"cairn.hypothesis-reviews.v1"})
if __name__=="__main__":
    unittest.main()
