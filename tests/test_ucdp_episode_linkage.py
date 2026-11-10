"""Dual-source review provenance and no unauthorized acceptance tests."""
import csv
import tempfile
import unittest
from pathlib import Path
from scripts.validate_episode_linkage import validate


FIELDS=["episode_id","episode_date","ucdp_dyad_new_id","gdelt_case",
        "gdelt_asof_date","link_status","reviewer_1","reviewer_2",
        "primary_source_url","independent_source_url","decision","review_notes"]


def row(**update):
    r=dict(episode_id="e1",episode_date="2026-07-12",
           ucdp_dyad_new_id="770",gdelt_case="BILAT:RUS:UKR",
           gdelt_asof_date="2026-07-11",
           link_status="UNREVIEWED_NOT_EVIDENCE_OF_ACTOR_MATCH",
           reviewer_1="",reviewer_2="",primary_source_url="",
           independent_source_url="",decision="",review_notes="")
    r.update(update)
    return r


def run(rows):
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/"candidate.csv"
        with path.open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
        return validate(path)


class LinkReviewTests(unittest.TestCase):
    def test_queue_starts_unreviewed(self):
        links,r=run([row()])
        self.assertEqual(links,[])
        self.assertEqual(r["review_counts"]["unreviewed"],1)
        self.assertFalse(r["automatic_alert_promotion"])

    def test_accept_requires_two_reviewers_and_independent_domains(self):
        good=dict(decision="accept",reviewer_1="reviewer-A",reviewer_2="reviewer-B",
                  primary_source_url="https://source-one.org/document/1",
                  independent_source_url="https://source-two.org/report/2",
                  review_notes="Actor and operational link independently substantiated by named sources.")
        links,r=run([row(**good)])
        self.assertEqual(r["accepted_links"],1)
        self.assertEqual(links[0]["status"],"accepted_two_human_reviews_not_prospective_forecast")
        with self.assertRaisesRegex(ValueError,"distinct human"):
            run([row(**{**good,"reviewer_2":"reviewer-A"})])
        with self.assertRaisesRegex(ValueError,"independent HTTPS"):
            run([row(**{**good,"independent_source_url":"https://www.source-one.org/other"})])

    def test_source_nomination_cannot_claim_verified_itself(self):
        with self.assertRaisesRegex(ValueError,"status was modified"):
            run([row(link_status="VERIFIED")])

    def test_post_event_flags_prohibited(self):
        with self.assertRaisesRegex(ValueError,"Post-outcome"):
            run([row(gdelt_asof_date="2026-07-12")])

    def test_duplicate_link_record_rejected(self):
        with self.assertRaisesRegex(ValueError,"Duplicated"):
            run([row(),row()])


if __name__=="__main__":
    unittest.main()
