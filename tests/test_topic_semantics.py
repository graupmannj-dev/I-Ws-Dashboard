"""Issue #75: local embedding determinism, automatic themes, hard negatives."""
import datetime as dt
import time
import unittest

from dashboard.topic_semantics import LocalTopicEmbeddings, SCHEMA
from dashboard.automatic_topics import assign, documents, _subject_geo, _roles, _domain

T0="2026-11-20T12:00:00Z"


def row(ident,title,family="commercial_media",location=None,source=None):
    return {
        "id":ident,"information_root":"r:"+ident,
        "first_observed_at":T0,
        "source_url":source or "https://example.org/"+ident,
        "title":title,"provider":family,
        "source_family":family,
        "source_kind":"trade_press_commercial_behavior_lead",
        "collection_mode":"commercial",
        "geography_key":location,
    }


def together(a,b):
    result=assign([a,b])
    docs=documents([a,b])
    if len(docs)!=2:
        raise AssertionError("Pair fixture must contain distinct documents")
    x,y=(result["assignments"].get(d["key"]) for d in docs)
    return x is not None and x==y,result


class HybridSemanticsTests(unittest.TestCase):
    def test_local_model_is_deterministic_and_no_download(self):
        titles=[
            "Iranian freighters face naval blockade at sea",
            "Maritime interdiction blocks cargo ships from Iran",
            "Internet outage in Finland",
            "China launches satellite",
            "Denmark live-fire exercises in waters",
            "FAA airport traffic restrictions in Chicago",
            "Russia strike on Kerch bridge",
            "Ships divert across Black Sea",
            "Hormuz shipping insurance premium changes",
            "Taiwan military exercise drills",
        ]
        a=LocalTopicEmbeddings(titles)
        b=LocalTopicEmbeddings(titles)
        self.assertEqual(a.count,10)
        self.assertIsNotNone(a.latent)
        self.assertEqual(a.pair(0,1),b.pair(0,1))
        self.assertGreater(a.pair(0,1)["score"],a.pair(0,3)["score"])
        self.assertEqual(a.pair(0,1)["embedding_method"],SCHEMA)

    def test_paraphrased_subject_not_exact_words_can_group(self):
        x=row("p1","Iranian freighters face naval blockade at sea")
        y=row("p2","Maritime interdiction of cargo ships from Iran")
        joined,data=together(x,y)
        self.assertTrue(joined, data.get("assignment_explanations"))
        doc=documents([x,y])[-1]
        e=data["assignment_explanations"][doc["key"]]
        self.assertIn(e["method"],(SCHEMA,"legacy_sparse_v1"))
        self.assertFalse(e["same_incident_proven"])
        self.assertFalse(e["independent_corroboration_proven"])
        self.assertIsInstance(e["shared_subject_terms"],list)

    def test_cross_source_related_subject_can_group_without_corroboration(self):
        x=row("c1","Shipping ships halted by Hormuz maritime blockade","commercial_media")
        y=row("m1","Will Hormuz shipping blockade halt cargo ships this year?","market_expectation")
        joined,data=together(x,y)
        self.assertTrue(joined,data.get("assignment_explanations"))

    def test_false_joins_rejected_on_country_domain_and_distinct_roles(self):
        neg=[
            (row("a","Internet outage Syria country SY",location="country:SY",family="internet_reachability"),
             row("b","Internet outage Finland country FI",location="country:FI",family="internet_reachability")),
            (row("c","Iran Hormuz shipping blockade announced"),
             row("d","Iran Hormuz shipping agreement signed")),
            (row("e","Denmark naval firing exercise in Kattegat",family="maritime_restriction"),
             row("f","Denmark railway bridge repair in Copenhagen")),
            (row("g","FAA TFR restrictions Chicago Illinois",family="airspace_restriction"),
             row("h","FAA TFR restrictions Orlando Florida",family="airspace_restriction")),
            (row("i","Taiwan island blockade naval ships"),
             row("j","Taiwan internet traffic outage affected networks")),
        ]
        for a,b in neg:
            with self.subTest(a=a["title"],b=b["title"]):
                merged,_=together(a,b)
                self.assertFalse(merged)

    def test_immutable_previous_ledger_and_timestamp(self):
        a=row("old","Iranian cargo ships under naval blockade")
        b=row("new","Maritime blockade blocks Iranian freighters")
        historical=assign([a])
        gid=historical["assignments"][documents([a])[0]["key"]]
        second=assign([b],historical)
        self.assertEqual(second["assignments"][documents([a])[0]["key"]],gid)
        self.assertEqual(second["assignments"][documents([b])[0]["key"]],gid)
        self.assertEqual(second["groups"][gid]["first_document_at"],T0)
        self.assertEqual(assign([b],second)["new_document_assignments"],0)

    def test_blockade_and_freighter_phrasings_share_domain(self):
        a=row("domain-a","Iranian cargo ships under naval blockade")
        b=row("domain-b","Maritime blockade blocks Iranian freighters")
        docs=documents([a,b])
        self.assertEqual(docs[0]["domain"],"maritime")
        self.assertEqual(docs[1]["domain"],"maritime")
        joined,_=together(a,b)
        self.assertTrue(joined)

    def test_repeated_official_source_fragments_one_document(self):
        a=row("frag1","Denmark firing exercise Kattegat",family="maritime_restriction",
              source="https://example.org/notice/123")
        b=row("frag2","Denmark firing exercise Kattegat",family="maritime_restriction",
              source="https://example.org/notice/123")
        out=assign([a,b])
        self.assertEqual(len(documents([a,b])),1)
        self.assertEqual(out["total_document_assignments"],1)

    def test_lsa_bounded_realistic_300_titles(self):
        titles=[f"Shipping disruption and maritime news bulletin region {i}"+
                (" navy blockade" if i%5==0 else " commercial freight")
                for i in range(300)]
        start=time.perf_counter()
        m=LocalTopicEmbeddings(titles)
        self.assertEqual(m.count,300)
        self.assertTrue(0<=m.pair(0,20)["score"]<=1)
        self.assertLess(time.perf_counter()-start,18,
                        "Semantic embedding should fit existing GitHub CI budget")


if __name__=="__main__":
    unittest.main()
