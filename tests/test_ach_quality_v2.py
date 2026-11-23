import unittest
from scripts.benchmark_ach_quality_v2 import dataset, grade, SCHEMA
def sources():
    return [{"id":f"r{i}","title":f"Actual source title sample {i}",
       "url":f"https://example.org/{i}","root_hash":f"hash{i}"} for i in range(8)]
def valid_result(item,directions=None):
    directions=directions or [x[0] for x in item["allowed"]]
    return {"evaluations":[{"hypothesis_index":i,"evidence_key":item["evidence_key"],
        "direction":direction,"rationale":"Only supplied evidence is available for interpretation"}
        for i,direction in enumerate(directions)],
      "discriminator":"Seek independent primary-source facts that distinguish the hypotheses",
      "coverage_limitations":"Only supplied record titles, not complete coverage",
      "source_independence_established":item["independent_corroboration"],
      "event_verified":item["verified_event"]}
import json
class QualityV2Tests(unittest.TestCase):
    def test_dataset_has_distinct_real_and_controlled_gold(self):
        rows=dataset(sources())
        self.assertEqual(len(rows),14)
        self.assertEqual(len([r for r in rows if r["kind"]=="real"]),6)
        self.assertEqual(len([r for r in rows if r["kind"]=="controlled"]),8)
        self.assertTrue(all(r["source_url"].startswith("https://") for r in rows))
    def test_gold_accepts_cautious_valid_reference(self):
        for item in dataset(sources()):
            result=grade(json.dumps(valid_result(item)),item)
            self.assertTrue(result["schema_valid"],item["id"])
            self.assertTrue(result["gold_correct"],item["id"])
            self.assertTrue(result["source_fidelity"],item["id"])
    def test_incorrect_direction_is_not_mistaken_for_good_reasoning(self):
        item=dataset(sources())[6]
        wrong=valid_result(item,["possibly_consistent","possibly_inconsistent"])
        self.assertFalse(grade(json.dumps(wrong),item)["gold_correct"])
    def test_schema_and_evidence_validation(self):
        item=dataset(sources())[0]
        wrong=valid_result(item)
        wrong["evaluations"][0]["evidence_key"]="invented"
        result=grade(json.dumps(wrong),item)
        self.assertTrue(result["schema_valid"])
        self.assertFalse(result["source_fidelity"])
        self.assertFalse(grade("not a json object",item)["json_valid"])
    def test_absence_does_not_create_contradiction(self):
        item=next(x for x in dataset(sources()) if x["case_label"]=="no_reports")
        wrong=valid_result(item,["possibly_inconsistent","possibly_consistent"])
        self.assertFalse(grade(json.dumps(wrong),item)["gold_correct"])
    def test_forced_schema_has_required_fields(self):
        self.assertIn("event_verified",SCHEMA["required"])
        self.assertEqual(SCHEMA["properties"]["evaluations"]["minItems"],2)
if __name__=="__main__":unittest.main()
