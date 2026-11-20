"""Analytical grouping must preserve notice identity and avoid false corroboration."""
import datetime as dt
import unittest

from dashboard.dynamic_bins import build
from dashboard.topic_families import topic_key, family_id

NOW=dt.datetime(2026,11,20,2,tzinfo=dt.timezone.utc)
TITLES=[
    "Denmark. Kattegat. EK R 20 Yderby. Firing exercises. Warning.",
    "Denmark. Kattegat. EK R 45 Hevring. Firing exercises. Warning.",
    "Denmark. Kattegat. EK R 18 Jaegerspris. Firing exercises. Warning.",
    "Denmark. The North Sea. EK R 33 Vejers. Firing exercises. Warning.",
    "Denmark. Kattegat. EK R 15 Sejeroe E. Firing exercises. Warning.",
    "Denmark. The Baltic Sea. EK D 396 Hullebaek. Firing exercises. Warning.",
    "Denmark. The Baltic Sea. EK D 395 Raghammer. Firing exercises. Warning.",
    "Denmark. Kattegat. EK R 12 Gniben. Firing exercises. Warning.",
    "Denmark. The North Sea. 15 Nymindegab. Firing exercises. Warning.",
    "Denmark. Skagerrak. EK R 48 Tranum S. Firing exercises. Warning.",
    "Denmark. Kattegat. EK R 19 MULTEX. Firing exercises. Warning.",
]


def record(notice, fragment, title=None, first="2026-11-20T00:42:57Z", family="maritime_restriction"):
    return {
        "id":f"beh:{notice:02d}-{fragment:02d}",
        "information_root":f"niord:test-{notice:02d}:{fragment}:0:0",
        "first_observed_at":first,
        "source_url":f"https://niord.dma.dk/#/message/example-notice-{notice:02d}",
        "title":title or TITLES[notice % len(TITLES)],
        "provider":"niord","source_kind":"official_restriction_notice",
        "collection_mode":"live_maritime","source_family":family,
        "source_published_at":None,"source_updated_at":first,
        "scheduled_valid_from":"2026-11-22T07:00:00Z",
        "scheduled_valid_until":"2026-11-22T15:00:00Z",
        "restriction_status":"scheduled_not_yet_effective",
        "geography":{"key":None,"precision":"notice_geography_unavailable"},
        "direct_observed_behavior":False,
        "claim_level":"official_scheduled_restriction_not_military_preparation",
    }


def registry(rows):
    return {"schema":"aiba.behavioral-observations.v1","records":rows,
            "source_health":{"live_maritime":{"status":"current_partial"}}}


class AnalyticalTopicTests(unittest.TestCase):
    def test_denmark_66_fragments_collapses_to_one_topic_with_11_distinct_notices(self):
        rows=[record(i,n) for i in range(11) for n in range(6)]
        rows.append(record(20,0,"Denmark. The Liim Fiord. Bridge closed for passage in sidespans."))
        output=build(registry(rows), {"records":[]}, now=NOW)
        topics=[f for f in output["families"] if f["kind"]=="analytical_topic_family"]
        self.assertEqual(len(topics),1)
        f=topics[0]
        self.assertEqual(f["title"],"Denmark · maritime firing exercises")
        self.assertEqual(f["notice_count"],11)
        self.assertEqual(f["source_record_count"],66)
        self.assertEqual(f["information_root_count"],66)
        self.assertEqual(f["corroboration"]["issuer_count"],1)
        self.assertEqual(f["corroboration"]["status"],
                         "same_issuer_topic_not_independent_confirmation")
        self.assertFalse(f["source_independence_established"])
        self.assertFalse(f["event_occurrence_verified"])
        self.assertFalse(f["map_eligible"])
        self.assertFalse(f["warning_approved"])
        self.assertIsNone(f["anomaly_metric"]["z_score"])
        self.assertEqual(len(f["notice_groups"]),11)
        self.assertEqual(sum(x["source_record_count"] for x in f["notice_groups"]),66)
        self.assertEqual(sum(len(x["records"]) for x in f["notice_groups"]),66)
        self.assertTrue(all(x["source_record_count"]==6 for x in f["notice_groups"]))
        self.assertTrue(all(len(x["validity_windows"])==1 for x in f["notice_groups"]))
        # Only unrelated bridge closure remains in individual-source lane.
        ordinary=[x for x in output["families"] if x["kind"]=="source_root_candidate"]
        self.assertEqual(len(ordinary),1)
        self.assertIn("Bridge closed",ordinary[0]["title"])
        self.assertEqual(output["candidate_count_total"],2)
        self.assertEqual(output["source_root_candidates_folded_count"],66)

    def test_similar_activity_different_country_keeps_distinct_families(self):
        norwegian="Norway. The North Sea. Firing exercises. Warning."
        a=[record(0,i) for i in range(2)]
        b=[record(1,i,title=norwegian) for i in range(2)]
        output=build(registry(a+b), {"records":[]},now=NOW)
        titles={x["title"] for x in output["families"]}
        self.assertIn("Denmark · maritime firing exercises",titles)
        self.assertIn("Norway · maritime firing exercises",titles)
        self.assertEqual(output["analytical_topic_family_count"],2)

    def test_unknown_country_and_nonofficial_claim_not_clustered(self):
        a=record(0,0,"Kattegat. Firing exercises. Warning.")
        b=record(1,0,"Denmark. Firing exercises. News mention.",family="commercial_media")
        c=record(2,0,"Denmark. Bridge closed for transit.")
        out=build(registry([a,b,c]), {"records":[]},now=NOW)
        self.assertEqual(out["analytical_topic_family_count"],0)
        self.assertEqual(out["candidate_count_total"],3)
        self.assertIsNone(topic_key({"source_family":"maritime_restriction",
                                     "source_kind":"official_restriction_notice",
                                     "title":"Kattegat. Firing exercises. Warning."}))

    def test_group_identity_stable_across_years_and_more_notices(self):
        old=[record(i,0,first="2026-11-20T00:00:00Z") for i in range(2)]
        initial=build(registry(old),{"records":[]},now=NOW)
        fid=initial["families"][0]["id"]
        late=record(3,0,first="2027-05-20T00:30:00Z")
        updated=build(registry(old+[late]),{"records":[]},
                      now=dt.datetime(2027,5,20,2,tzinfo=dt.timezone.utc))
        self.assertEqual(updated["families"][0]["id"],fid)
        self.assertEqual(updated["families"][0]["notice_count"],3)
        self.assertEqual(updated["families"][0]["state"],"emerging")
        self.assertEqual(fid,family_id("Denmark","maritime-firing-exercises"))

    def test_one_notice_split_into_fragments_is_one_topic_not_multiple_events(self):
        rows=[record(0,i) for i in range(9)]
        res=build(registry(rows),{"records":[]},now=NOW)
        self.assertEqual(res["candidate_count_total"],1)
        f=res["families"][0]
        self.assertEqual(f["notice_count"],1)
        self.assertEqual(f["source_record_count"],9)
        self.assertEqual(f["corroboration"]["issuer_count"],1)
        self.assertFalse(f["source_independence_established"])

    def test_single_notice_fragment_remains_visible_individually(self):
        res=build(registry([record(0,0)]),{"records":[]},now=NOW)
        self.assertEqual(res["candidate_count_total"],1)
        self.assertEqual(res["families"][0]["kind"],"source_root_candidate")


if __name__=="__main__":
    unittest.main()
