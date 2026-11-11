"""Guard against hindsight, incomplete source coverage and invented negatives."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from behavioral_fusion import SCHEMA as FUSION
from behavioral_validation import evaluate,validate_spec
from behavioral_registry import iso
from ops_pipeline import write_json

UTC=dt.timezone.utc
START=dt.datetime(2026,12,1,0,0,tzinfo=UTC)
END=START+dt.timedelta(hours=12)
REVIEWERS=["reviewer-alpha","reviewer-beta"]
SOURCES=["https://ucdp.uu.se/source/one","https://example.org/independent/report"]


def spec(positive=True,registered=None,scope=True):
    unit={
        "unit_id":"test-monitor-geo","geo_key":"country:ZZ",
        "registered_at":iso(registered or START-dt.timedelta(days=2)),
        "window_start":iso(START),"window_end":iso(END),
        "coverage_providers":["ioda","official"],
        "geographic_footprint_reviewed":scope,
        "coverage_reviewers":REVIEWERS,
        "coverage_evidence_urls":SOURCES,
    }
    label={
        "unit_id":"test-monitor-geo",
        "outcome":"event" if positive else "no_event",
        "event_at":iso(START+dt.timedelta(hours=10)) if positive else None,
        "finalized_at":iso(END+dt.timedelta(days=2)),
        "reviewers":REVIEWERS,
        "independent_sources":SOURCES,
    }
    return {"version":1,"horizon_hours":12,"units":[unit],"labels":[label]}


def traces(state,with_review=True,coverage="current",asof=START+dt.timedelta(hours=6)):
    d={
        "schema":FUSION,
        "generated_at":iso(asof),
        "collection_coverage":{
            "ioda":{"status":coverage},
            "official":{"status":coverage},
        },
        "review_groups":[{"id":"candidate-1","geography":{"key":"country:ZZ"},
                          "status":"cross_family_cooccurrence_unreviewed"}]
                       if with_review else []
    }
    write_json(state/"history"/"behavioral_fusion"/
               (asof.strftime("%Y%m%dT%H%M%SZ")+".json"),d)


class ValidationLedgerTests(unittest.TestCase):
    def test_empty_frame_means_no_skill_and_no_events_imputed(self):
        with tempfile.TemporaryDirectory() as p:
            r=evaluate(Path(p),{"version":1,"horizon_hours":168,
                                "units":[],"labels":[]},
                       clock=lambda:END+dt.timedelta(days=3))
            self.assertEqual(r["status"],"no_approved_labels_or_frame")
            self.assertEqual(r["eligible_event_windows"],0)
            self.assertEqual(r["eligible_non_event_windows"],0)
            self.assertIsNone(r["calibrated_precision"])
            self.assertIsNone(r["false_alarm_rate"])

    def test_independently_reviewed_positive_describes_only_pre_event_signal(self):
        with tempfile.TemporaryDirectory() as p:
            s=Path(p)
            traces(s)
            r=evaluate(s,spec(),clock=lambda:END+dt.timedelta(days=3))
            self.assertEqual(r["status"],"insufficient_balanced_outcome_sample")
            self.assertEqual(r["eligible_event_windows"],1)
            self.assertEqual(r["case_descriptions"][0]["result"],"geographic_review_preceded_event")
            self.assertEqual(r["case_descriptions"][0]["first_lead_hours"],4)
            self.assertIsNone(r["calibrated_recall"])

    def test_post_event_observation_not_backdated_as_early_warning(self):
        with tempfile.TemporaryDirectory() as p:
            s=Path(p)
            traces(s,asof=START+dt.timedelta(hours=11))
            r=evaluate(s,spec(),clock=lambda:END+dt.timedelta(days=3))
            self.assertEqual(r["case_descriptions"][0]["result"],"no_pre_event_geographic_review")

    def test_unreviewed_provider_footprint_never_creates_false_negative(self):
        with tempfile.TemporaryDirectory() as p:
            s=Path(p)
            traces(s,with_review=False)
            r=evaluate(s,spec(positive=False,scope=False),
                       clock=lambda:END+dt.timedelta(days=3))
            self.assertEqual(r["eligible_non_event_windows"],0)
            self.assertEqual(r["excluded_or_unadjudicated_windows"][0]["reason"],
                             "geographic_provider_footprint_not_verified")

    def test_provider_failure_is_not_normal_no_event(self):
        with tempfile.TemporaryDirectory() as p:
            s=Path(p)
            traces(s,with_review=False,coverage="stale_or_unavailable")
            r=evaluate(s,spec(positive=False),
                       clock=lambda:END+dt.timedelta(days=3))
            self.assertEqual(r["eligible_non_event_windows"],0)
            self.assertEqual(r["excluded_or_unadjudicated_windows"][0]["reason"],
                             "partial_or_unavailable_provider")

    def test_source_gap_is_excluded_from_negative_denominator(self):
        with tempfile.TemporaryDirectory() as p:
            s=Path(p)
            traces(s,with_review=False,asof=START+dt.timedelta(hours=0))
            # Full 12-hour window has one observation at start; gap exactly
            # 12h so eligible (but does not claim true worldwide coverage).
            r=evaluate(s,spec(positive=False),clock=lambda:END+dt.timedelta(days=3))
            self.assertEqual(r["eligible_non_event_windows"],1)
            self.assertEqual(r["case_descriptions"][0]["result"],"no_fusion_during_reviewed_non_event")

    def test_future_registration_and_single_review_refused(self):
        value=spec(registered=START)
        with self.assertRaisesRegex(ValueError,"registered before"):
            validate_spec(value)
        value=spec()
        value["labels"][0]["reviewers"]=["same","same"]
        with self.assertRaisesRegex(ValueError,"independent reviewed"):
            validate_spec(value)

    def test_undated_outcome_or_source_changes_are_rejected(self):
        value=spec()
        value["labels"][0]["finalized_at"]="2026-12-15T00:00:00"
        with self.assertRaisesRegex(ValueError,"offset-aware"):
            validate_spec(value)
        value=spec()
        value["labels"][0]["independent_sources"]=["https://same.org/1","https://www.same.org/2"]
        with self.assertRaisesRegex(ValueError,"independent reviewed"):
            validate_spec(value)

    def test_unlabeled_or_not_finalized_window_not_counted_as_no_event(self):
        with tempfile.TemporaryDirectory() as p:
            s=Path(p)
            traces(s,with_review=False)
            value=spec(positive=False)
            r=evaluate(s,value,clock=lambda:END+dt.timedelta(hours=1))
            self.assertEqual(r["eligible_non_event_windows"],0)
            self.assertEqual(r["excluded_or_unadjudicated_windows"][0]["reason"],
                             "outcome_not_adjudicated_as_of_evaluation")


if __name__=="__main__":
    unittest.main()
