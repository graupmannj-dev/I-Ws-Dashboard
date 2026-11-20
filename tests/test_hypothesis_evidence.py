"""CAIRN hypothesis evidence: synthetic review direction, links and missingness."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.hypothesis_evidence import (
    SCHEMA, REVIEW_SCHEMA, build, signal_key,
)
from dashboard.build_atlas import generate

STAMP="2026-11-20T16:00:00Z"


def dossier(ident,root="original-document"):
    return {
        "id":ident,"name":"Synthetic "+ident,"scenario":"Investigate an unusual disruption",
        "asof":"2026-11-20","state":"Watch","analysis":"Competing explanations remain.",
        "next":"Verify source independent follow-up",
        "alternatives":"Routine maintenance rather than a security contingency.",
        "signals":[
            {"date":"2026-11-19","title":"A source report","assessment":"Confirmed observation only",
             "source":"Agency","category":"Official","root":root,
             "url":"https://example.org/first"},
            {"date":"2026-11-19","title":"Same source further detail","assessment":"Disputed interpretation",
             "source":"Agency","category":"Official","root":root,
             "url":"https://example.org/second"},
        ],
    }


def dynamic():
    return {"families":[{"id":"family:shared","case_hints":["case-a","case-b"],
        "title":"Independent public observation","kind":"source_root_candidate",
        "source_families":["internet_reachability"],"information_root_count":1,
        "source_independence_established":False,
        "sources":[{"source_url":"https://example.org/aggregate","title":"Network measurement",
                    "provider":"Public probe","collection_mode":"ripe",
                    "first_observed_at":STAMP,"source_family":"internet_reachability"}]}]}


def reviews(rows):
    return {"schema":REVIEW_SCHEMA,"reviews":rows,"alternative_hypotheses":{}}


def review(hid,key,direction,strength=1,dependency=None):
    return {"hypothesis_id":hid,"evidence_key":key,"direction":direction,
        "strength":strength,"rationale":"Synthetic reviewer rationale",
        "reviewed_at":STAMP,"dependency_group":dependency or key}


class HypothesisEvidenceTests(unittest.TestCase):
    def test_case_hints_are_many_to_many_not_inferred_corroboration(self):
        c=build([dossier("case-a"),dossier("case-b")],dynamic(),
                {"ripe":{"status":"current","checked_at":STAMP}},reviews([]),STAMP)
        self.assertEqual(c["schema"],SCHEMA)
        self.assertEqual(c["hypothesis_count"],2)
        for h in c["hypotheses"]:
            self.assertEqual(h["family_count"],2)
            self.assertEqual(h["balance"]["direction"],"not_assessed")
            self.assertIsNone(h["balance"]["signed_ordinal_balance"])
            family=next(f for f in h["families"] if f["evidence_key"]=="family:shared")
            self.assertEqual(family["linked_hypotheses"],["case-a","case-b"])
            self.assertFalse(family["source_independence_established"])
            self.assertEqual(family["health"]["status"],"current")
            dossier_family=next(f for f in h["families"] if f["origin"]=="curated_dossier")
            self.assertEqual(dossier_family["source_count"],2)
            self.assertEqual(dossier_family["health"]["status"],"historical_reference_not_live")

    def test_signed_review_only_ordinal_and_explicit(self):
        d=dossier("case-a")
        key=signal_key("case-a","original-document")
        annotated=reviews([
            review("case-a",key,"supports",3),
            review("case-a","family:shared","contradicts",1),
        ])
        c=build([d],dynamic(),{"ripe":{"status":"current","checked_at":STAMP}},annotated,STAMP)
        b=c["hypotheses"][0]["balance"]
        self.assertEqual(b["direction"],"leans_support")
        self.assertEqual(b["signed_ordinal_balance"],0.5)
        self.assertEqual(b["support_strength"],3)
        self.assertEqual(b["contradict_strength"],1)
        self.assertIsNone(b["calibrated_probability"])

    def test_shared_dependency_caps_weight_and_conflicts_are_excluded(self):
        from dashboard.hypothesis_evidence import _balance
        rows=[
            {"review":{"direction":"supports","strength":3,"dependency_group":"same"}},
            {"review":{"direction":"supports","strength":1,"dependency_group":"same"}},
            {"review":{"direction":"contradicts","strength":1,"dependency_group":"other"}},
        ]
        self.assertEqual(_balance(rows)["support_strength"],3)
        rows[2]["review"]["dependency_group"]="same"
        self.assertEqual(_balance(rows)["conflicting_dependency_groups_excluded"],1)
        self.assertIsNone(_balance(rows)["signed_ordinal_balance"])

    def test_invalid_reviews_and_unsupported_evidence_rejected(self):
        key=signal_key("case-a","original-document")
        with self.assertRaisesRegex(ValueError,"Missing or duplicate"):
            build([dossier("case-a"),dossier("case-a")])
        with self.assertRaisesRegex(ValueError,"strength"):
            build([dossier("case-a")],reviews=reviews([
                review("case-a",key,"supports",True)]))
        with self.assertRaisesRegex(ValueError,"missing hypothesis"):
            build([dossier("case-a")],reviews=reviews([
                review("case-a","not-an-existing-source","supports")]))
        with self.assertRaisesRegex(ValueError,"Maximum three"):
            build([dossier("case-a")],reviews={"schema":REVIEW_SCHEMA,"reviews":[],
                "alternative_hypotheses":{"case-a":["a","b","c","d"]}})

    def test_stale_source_never_appears_current_or_zero(self):
        c=build([dossier("case-a")],dynamic(),
                {"ripe":{"status":"stale_or_unavailable","checked_at":STAMP}},
                reviews([]),STAMP)
        f=next(x for x in c["hypotheses"][0]["families"]
               if x["evidence_key"]=="family:shared")
        self.assertEqual(f["health"]["status"],"stale_or_unavailable")
        self.assertEqual(f["direction"],"not_assessed")

    def test_builder_publishes_hypothesis_page_and_json(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)/"site";site.mkdir()
            (site/"hotspots.json").write_text(json.dumps({"asof":"2026-11-20"}))
            output=generate(site,generated=STAMP)
            assert output["hypothesis_views"]["hypothesis_count"]>=1
            result=json.loads((site/"hypotheses.json").read_text())
            self.assertEqual(result["schema"],SCHEMA)
            self.assertEqual(result["reviewed_hypotheses"],0)
            self.assertTrue((site/"hypotheses.html").exists())
            self.assertTrue((site/"dashboard"/"hypotheses.js").exists())
            self.assertTrue((site/"dashboard"/"hypotheses.css").exists())


if __name__=="__main__":
    unittest.main()
