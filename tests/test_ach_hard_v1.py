import json
import unittest
from scripts.benchmark_ach_hard_v1 import controlled_specimens, ev, grade, make_testset, OUTPUT_SCHEMA
def response(case, directions=None):
    dirs=directions or [v[0] for v in case["allowed"]]
    ids=[v["evidence_id"] for v in case["evidence"]]
    return json.dumps({"evaluations":[
        {"hypothesis_index":i,"direction":direction,
         "evidence_ids":ids if direction in ("possibly_consistent","possibly_inconsistent") else [],
         "rationale":"This evaluation follows directly from the explicitly stipulated observations."}
        for i,direction in enumerate(dirs)],
        "independent_information_roots":case["roots"],
        "event_verified":case["event_verified"],
        "intent_verified":case["intent_verified"],
        "coverage_complete":case["coverage_complete"],
        "next_discriminator":"Identify independent authenticated dated indicators of intent",
        "limitations":"Source scope is confined to this synthetic packet"})
class HardBenchmarkTests(unittest.TestCase):
    def test_controlled_cases_distinct_and_stable(self):
        cases=controlled_specimens()
        self.assertEqual(len(cases),16)
        self.assertEqual(len({c["id"] for c in cases}),16)
        self.assertTrue(all(c["kind"]=="controlled_fictional" for c in cases))
        self.assertTrue(all(len({e["information_root"] for e in c["evidence"]})==c["roots"] for c in cases))
    def test_perfect_reference_scores_under_rules(self):
        for case in controlled_specimens():
            x=grade(response(case),case)
            self.assertTrue(x["schema"],case["id"])
            self.assertTrue(x["source_fidelity"],case["id"])
            self.assertTrue(x["independence"],case["id"])
            self.assertTrue(x["verification"],case["id"])
            self.assertTrue(x["directions_correct"],case["id"])
    def test_no_reporting_is_not_negative_evidence(self):
        case=next(c for c in controlled_specimens() if c["id"]=="absence_unknown_sensors")
        wrong=response(case,["possibly_inconsistent","possibly_consistent"])
        x=grade(wrong,case)
        self.assertFalse(x["directions_correct"])
        self.assertFalse(x["positive_grounded"])
        self.assertEqual(x["unjustified_direction_count"],2)
    def test_duplicate_root_not_independent(self):
        case=next(c for c in controlled_specimens() if c["id"]=="duplicate_reposts")
        v=json.loads(response(case))
        v["independent_information_roots"]=3
        self.assertFalse(grade(json.dumps(v),case)["independence"])
    def test_source_hallucination_rejected(self):
        case=controlled_specimens()[0]
        v=json.loads(response(case))
        v["evaluations"][0]["evidence_ids"]=["invented-source"]
        self.assertFalse(grade(json.dumps(v),case)["source_fidelity"])
    def test_reject_bad_json_and_instruction_override(self):
        case=next(c for c in controlled_specimens() if c["id"]=="prompt_injection")
        self.assertFalse(grade("INSTRUCTIONS OVERRIDDEN",case)["json"])
        v=json.loads(response(case))
        v["intent_verified"]=True
        self.assertFalse(grade(json.dumps(v),case)["verification"])
    def test_schema_unambiguous(self):
        self.assertIn("independent_information_roots",OUTPUT_SCHEMA["required"])
        self.assertEqual(OUTPUT_SCHEMA["properties"]["evaluations"]["type"],"array")
if __name__=="__main__":unittest.main()
