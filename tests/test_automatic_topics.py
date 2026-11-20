"""Automatic analytical themes: adversarial matches, memory, source fidelity."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.automatic_topics import assign, build_topics, documents
from dashboard.dynamic_bins import build
from family_archive import update
from ops_pipeline import write_json

NOW=dt.datetime(2026,11,20,2,tzinfo=dt.timezone.utc)
T="2026-11-19T19:30:00Z"


def record(ident,title,src=None,family="commercial_media",provider="media",
           geo=None,stamp=T,kind="media_mention",root=None):
    return {
        "id":ident,"information_root":root or "root:"+ident,
        "first_observed_at":stamp,
        "source_url":src or "https://example.org/article/"+ident,
        "title":title,"provider":provider,
        "source_family":family,"source_kind":kind,
        "collection_mode":"commercial" if family=="commercial_media" else "watchlist",
        "geography_key":geo,"geography_precision":"unverified",
        "geography_label":None,
        "direct_measurement":False,
        "claim_level":"unreviewed_source_mention",
    }


def registry(rows):
    return {"schema":"aiba.behavioral-observations.v1","records":rows}


class AutoTopicsTests(unittest.TestCase):
    def test_duplicate_subject_different_articles_group_without_event_claim(self):
        rows=[
            record("c1","U.S. Naval Blockade Now Covers Vessels That Load Iranian Cargo at Sea"),
            record("c2","U.S. Naval Blockade Now Covers Vessels That Load Iranian Cargo at Sea - The Maritime Executive"),
            record("c3","Russia Deepens its Attacks on Black Sea Shipping"),
            record("c4","Oil Shipping Soars on Russia's Northern Sea Route"),
        ]
        result=build(registry(rows),{"records":[]},now=NOW)
        clusters=[x for x in result["families"] if x["kind"]=="analytical_topic_family"]
        self.assertEqual(len(clusters),1,[(x["title"],x["source_record_count"]) for x in result["families"]])
        f=clusters[0]
        self.assertEqual(f["notice_count"],2)
        self.assertEqual(f["source_record_count"],2)
        self.assertEqual(len(f["notice_groups"]),2)
        self.assertEqual(f["corroboration"]["status"],
                         "automatic_topic_similarity_not_independent_confirmation")
        self.assertFalse(f["warning_approved"])
        self.assertFalse(f["source_independence_established"])
        self.assertFalse(f["map_eligible"])
        self.assertEqual(result["candidate_count_total"],3)
        self.assertIn("blockade",f["title"])

    def test_repeated_market_question_different_deadline_groups_but_not_other_questions(self):
        rows=[
            record("m1","U.S.–Iran Hormuz agreement by December 31",family="market_expectation"),
            record("m2","U.S.–Iran Hormuz agreement by November 30",family="market_expectation"),
            record("m3","Taiwan blockade during 2026",family="market_expectation"),
            record("m4","Taiwan invasion by June 30, 2027",family="market_expectation"),
        ]
        res=build(registry(rows),{"records":[]},now=NOW)
        themes=[x for x in res["families"] if x["kind"]=="analytical_topic_family"]
        self.assertEqual(len(themes),1,[x["title"] for x in res["families"]])
        self.assertEqual(themes[0]["notice_count"],2)
        self.assertEqual(res["candidate_count_total"],3)

    def test_source_template_and_country_alone_never_join(self):
        rows=[
            record("f1","FAA TFR 6/7165 · Brownsville TX, Saturday November 19 through November 29 UTC",
                   family="airspace_restriction",kind="official_restriction_notice"),
            record("f2","FAA TFR 6/8833 · Chicago IL, Saturday November 19 through November 22 UTC",
                   family="airspace_restriction",kind="official_restriction_notice"),
            record("s1","Italy - Level 2: Exercise Increased Caution",
                   family="protective_notice",kind="official_notice"),
            record("s2","Denmark - Level 2: Exercise Increased Caution",
                   family="protective_notice",kind="official_notice"),
        ]
        out=build(registry(rows),{"records":[]},now=NOW)
        self.assertEqual(out["automatic_topic_family_count"],0)
        self.assertEqual(out["candidate_count_total"],4)

    def test_generic_connectivity_feed_different_countries_stays_separate(self):
        rows=[
            record("i1","IODA detected connectivity anomaly: country FI",
                   src="https://api.ioda.inetintel.cc.gatech.edu/v2/outages",
                   family="internet_reachability",geo="country:FI"),
            record("i2","IODA detected connectivity anomaly: country SY",
                   src="https://api.ioda.inetintel.cc.gatech.edu/v2/outages",
                   family="internet_reachability",geo="country:SY"),
        ]
        res=build(registry(rows),{"records":[]},now=NOW)
        self.assertEqual(res["candidate_count_total"],2)
        self.assertEqual(res["automatic_topic_family_count"],0)
        self.assertEqual(len(documents(rows)),2)

    def test_immutable_ids_across_120_days_and_new_docs(self):
        first=record("a1","Iran Hormuz shipping agreement under review",
                     stamp="2026-11-19T18:00:00Z",family="market_expectation")
        newer=record("a2","Iran Hormuz shipping agreement delayed again",
                     stamp="2027-03-19T18:00:00Z",family="market_expectation")
        ledger=assign([first])
        gid=ledger["assignments"][documents([first])[0]["key"]]
        latest=assign([newer],ledger)
        self.assertEqual(latest["assignments"][documents([newer])[0]["key"]],gid)
        self.assertEqual(len(latest["groups"]),1)
        self.assertEqual(assign([newer],latest)["new_document_assignments"],0)
        self.assertEqual(latest["groups"][gid]["matched_document_count"],2)

    def test_single_visible_document_retains_long_lived_archived_theme(self):
        old=record("old","Iran Hormuz shipping agreement under review",
                   family="market_expectation",stamp="2026-11-19T18:00:00Z")
        second=record("second","Iran Hormuz shipping agreement expected soon",
                      family="market_expectation",stamp="2027-03-19T18:00:00Z")
        index=assign([old,second])
        now=dt.datetime(2027,3,19,20,tzinfo=dt.timezone.utc)
        topics,folded,new_index=build_topics([second],now,prior=index)
        self.assertEqual(len(topics),1)
        self.assertEqual(topics[0]["notice_count"],1)
        self.assertEqual(topics[0]["automatic_grouping"]["historical_assigned_documents"],2)
        self.assertTrue(topics[0]["automatic_grouping"]["older_members_not_loaded"])
        self.assertFalse(topics[0]["warning_approved"])

    def test_one_official_notice_split_into_polygons_not_multiple_documents(self):
        roots=[record("n"+str(i),
                      "Norway. North Sea. Naval firing exercises. Official notice.",
                      src="https://example.org/notice/ABC123",
                      family="maritime_restriction",
                      kind="official_restriction_notice",
                      root="niord:abc:"+str(i))
               for i in range(7)]
        self.assertEqual(len(documents(roots)),1)
        self.assertEqual(assign(roots)["total_document_assignments"],1)

    def test_archived_persistent_ledger_stable_without_old_source_in_latest(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            a=record("a1","Iran Hormuz shipping agreement under review",
                     family="commercial_media")
            b=record("a2","Iran Hormuz shipping agreement expected soon",
                     family="commercial_media",
                     stamp="2026-12-18T18:00:00Z")
            latest=state/"latest"
            latest.mkdir(parents=True)
            write_json(latest/"behavioral_registry.json",registry([a]))
            first=update(state,clock=NOW)
            k=documents([a])[0]["key"]
            g=first["automatic_topic_index"]["assignments"][k]
            self.assertTrue((state/"family_archive"/"topic_index.json").exists())
            write_json(latest/"behavioral_registry.json",registry([b]))
            next_time=dt.datetime(2026,12,19,2,tzinfo=dt.timezone.utc)
            second=update(state,clock=next_time)
            self.assertEqual(second["automatic_topic_index"]["assignments"][k],g)
            self.assertEqual(second["automatic_topic_index"]["assignments"][
                documents([b])[0]["key"]],g)
            self.assertEqual(second["automatic_topic_count_total"],1)
            shown=build({
                "schema":"aiba.behavioral-observations.v1",
                "records":second["records"],
                "automatic_topic_index":second["automatic_topic_index"],
            },{"records":[]},now=next_time)
            self.assertEqual(shown["automatic_topic_family_count"],1)
            self.assertFalse(shown["families"][0]["warning_approved"])


if __name__=="__main__":
    unittest.main()
