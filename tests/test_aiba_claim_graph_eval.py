import unittest
from scripts.aiba_claim_graph_eval import compare, wilson

def report(ident, text, split="heldout"):
    return {
        "id": ident, "source_url": f"https://news.example.org/story/{ident}",
        "source_family": "commercial_media", "source_text": text,
        "rights_basis": "permission_granted", "retrieved_at": "2026-11-13T12:00:00Z",
        "story_lineage_id": ident, "split": split, "title": text,
        "first_observed_at": "2026-11-13T12:00:00Z",
        "source_published_at": "2026-11-13T12:00:00Z",
        "information_root": "benchmark:" + ident,
    }

class ClaimGraphComparisonTests(unittest.TestCase):
    def test_pairwise_comparison_without_warning_promotion(self):
        a = report("a", "Russian missiles struck Kyiv energy substation overnight.")
        b = report("b", "Russian missiles struck Kyiv energy substation overnight.")
        c = report("c", "Russian missiles struck Kyiv energy substation overnight.")
        c["reported_event_location"] = {
            "role": "reported_event_site", "basis": "source_declared", "lat": 46.48, "lon": 30.73}
        a["reported_event_location"] = {
            "role": "reported_event_site", "basis": "source_declared", "lat": 50.45, "lon": 30.52}
        pairs = [
            {"a": "a", "b": "b", "label": "same_event", "adjudication_id": "p1"},
            {"a": "a", "b": "c", "label": "different_event", "adjudication_id": "p2"}
        ]
        result = compare([a,b,c], pairs)
        self.assertEqual(result["evaluation_split"], "heldout")
        self.assertEqual(result["scores"]["claim_graph"]["tp"], 1)
        self.assertEqual(result["scores"]["claim_graph"]["fp"], 0)
        self.assertEqual(result["scores"]["claim_graph"]["different_event_truth"],1)
        self.assertFalse(result["operational_validation"])
        self.assertFalse(result["warning_level_change"])
        self.assertEqual(result["automated_event_merges"],0)

    def test_disjoint_split_default_only_heldout(self):
        a = report("a", "Russian missiles struck Kyiv energy station.", "development")
        b = report("b", "Russian missiles struck Kyiv energy station.", "development")
        c = report("c", "Police detained suspects outside the station.", "heldout")
        pairs = [{"a":"a","b":"b","label":"same_event","adjudication_id":"p1"}]
        result = compare([a,b,c],pairs)
        self.assertEqual(result["scores"]["claim_graph"]["pairs_scored"],0)
        self.assertEqual(result["scores"]["claim_graph"]["precision"],None)

    def test_ci_never_calls_zero_observed_errors_perfect_certainty(self):
        interval = wilson(0, 10)
        self.assertEqual(interval["low"],0)
        self.assertGreater(interval["high"],0)
        self.assertIsNone(wilson(0,0))

    def test_uncertain_truth_excluded(self):
        a=report("a","Russian missiles struck Kyiv energy station.")
        b=report("b","Russian missiles struck Kyiv energy station.")
        p=[{"a":"a","b":"b","label":"uncertain","adjudication_id":"p1"}]
        result=compare([a,b],p)
        self.assertEqual(result["scores"]["claim_graph"]["pairs_scored"],0)

if __name__=="__main__":
    unittest.main()
