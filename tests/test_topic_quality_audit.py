"""Topic-pair audit integrity and reproducibility; not population-validity tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.eval_family_topics import DEFAULT, load_benchmark, run, summarize


class TopicQualityAuditTests(unittest.TestCase):
    def test_dated_snapshot_has_both_distinct_labels_and_reasons(self):
        data=load_benchmark(DEFAULT)
        self.assertEqual(data["snapshot"]["observed_at"],"2026-11-20T16:28:46Z")
        self.assertGreaterEqual(len(data["documents"]),20)
        self.assertGreaterEqual(len(data["pairs"]),35)
        self.assertTrue(all(x["rationale"] for x in data["pairs"]))
        self.assertIn("not",data["limitations"].lower())

    def test_pair_metrics_add_up_and_no_incident_verification_claim(self):
        report=run(DEFAULT)
        for name in ("legacy_sparse_v1","hybrid_v2"):
            score=report[name]
            self.assertEqual(score["tp"]+score["fp"]+score["tn"]+score["fn"],
                             report["pair_count"])
            self.assertEqual(score["tp"]+score["fn"],report["positive_labels"])
            self.assertEqual(score["fp"]+score["tn"],report["negative_labels"])
            for metric in ("pair_recall","pair_precision_on_curated_sample",
                           "negative_pair_false_join_rate"):
                self.assertTrue(score[metric] is None or 0<=score[metric]<=1)
            self.assertTrue(all(x["error"] in ("FP","FN") for x in score["false_links"]))
        self.assertIn("NOT independent",report["evaluation_type"].replace("_"," ")+" NOT independent")
        self.assertIn("not",report["evaluation_caveat"].lower())
        self.assertEqual(report["hybrid_v2"]["labeled_pairs"],len(load_benchmark(DEFAULT)["pairs"]))

    def test_invalid_pair_rejected_instead_of_silently_skipped(self):
        data=load_benchmark(DEFAULT)
        data["pairs"].append(copy.deepcopy(data["pairs"][0]))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"Duplicate"):
                load_benchmark(path)

    def test_confusion_counts_flag_both_missed_and_false_link(self):
        pairs=[
            {"left":"a","right":"b","same_topic":True,"rationale":"same named document"},
            {"left":"a","right":"c","same_topic":False,"rationale":"distinct operations"},
        ]
        metric=summarize(pairs,{("a","b"):False,("a","c"):True})
        self.assertEqual(metric["fn"],1)
        self.assertEqual(metric["fp"],1)
        self.assertEqual(metric["negative_pair_false_join_rate"],1)
        self.assertEqual(metric["pair_recall"],0)


if __name__=="__main__":
    unittest.main()
