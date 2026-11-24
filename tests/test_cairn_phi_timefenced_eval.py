"""As-of historical packet integrity and no-fabricated-label regression tests."""
import datetime as dt
import unittest

from scripts.cairn_phi_timefenced_eval import (
    SCHEMA, build, check_model_outputs, GENERIC_HYPOTHESES)

UTC = dt.timezone.utc


def snap(day, rows):
    when = dt.datetime(2026, 11, day, 18, tzinfo=UTC)
    reg = {"schema":"aiba.behavioral-observations.v1",
           "generated_at":when.isoformat(),
           "records":rows}
    return (when, reg, f"snapshot-{day:02d}.json")


def rec(first, title="Taiwan Strait temporary shipping notice",
        url="https://example.org/dated-taiwan-notice", case_hint="korea",
        root="original-observer-a"):
    return {
        "id": f"record-{first}-{title[:15]}",
        "source_url": url,
        "title": title,
        "geography": {"label":"Taiwan Strait"},
        "collection_mode": "official",
        "source_family": "airspace_restriction",
        "information_root": root,
        "case_hint": case_hint,
        "first_observed_at": first,
    }


class HistoricalPacketTests(unittest.TestCase):
    def test_100_case_day_stratified_from_actual_10_snapshots(self):
        rows = [rec("2026-11-10T11:00:00Z")]
        history = [snap(d, rows) for d in range(10, 20)]
        # The actual case registry contains ten named geographic cases.
        ids = ["taiwan", "korea", "iran_gulf", "russia_nato", "afpak",
               "drc_rwanda", "horn_ethiopia_eritrea",
               "horn_ethiopia_sudan", "thailand_cambodia",
               "horn_ethiopia_kenya_moyale"]
        result = build(history, case_ids=ids)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["sampling"]["packet_count"], 100)
        self.assertEqual(result["sampling"]["actual_days"], 10)
        self.assertFalse(result["sampling"]["event_truth_labels_available"])
        self.assertFalse(result["sampling"]["independent_true_negative_events_available"])
        self.assertTrue(all(p["actual_event_outcome"] is None
                            and p["expert_evidence_direction"] is None
                            and p["hypotheses"] == list(GENERIC_HYPOTHESES)
                            for p in result["packets"]))
        self.assertEqual(len({p["packet_id"] for p in result["packets"]}), 100)
        self.assertTrue(all(p["no_collected_matches_is_not_evidence_of_no_event"]
                            for p in result["packets"]))

    def test_case_hint_masked_and_empty_does_not_mean_no_conflict(self):
        one = snap(12, [rec("2026-11-12T10:00:00Z")])
        result = build([one], case_ids=["taiwan", "korea"])
        taiwan, korea = result["packets"]
        self.assertEqual(len(taiwan["source_claims"]), 1)
        self.assertEqual(taiwan["source_claims"][0]["geography_match_basis"],
                         "distinctive_case_cue")
        self.assertEqual(len(korea["source_claims"]), 0)
        self.assertFalse(korea["negative_event_truth_established"])
        self.assertIsNone(korea["actual_event_outcome"])
        self.assertFalse(taiwan["case_label_from_future_reporting_used"])

    def test_future_dated_rows_never_enter_an_earlier_snapshot(self):
        s = snap(12, [rec("2026-11-13T18:30:00Z")])
        out = build([s], case_ids=["taiwan"])
        self.assertEqual(out["packets"][0]["source_claims"], [])
        self.assertEqual(out["summary"].get("source_rows_visible", 0), 0)

    def test_duplicate_information_roots_not_recounted_as_independent(self):
        a = rec("2026-11-12T10:00:00Z")
        b = rec("2026-11-12T11:00:00Z",
                url="https://example.net/syndicated-taiwan-notice")
        s = snap(12, [a, b])
        out = build([s], case_ids=["taiwan"])
        row = out["packets"][0]
        self.assertEqual(len(row["source_claims"]), 1)
        self.assertEqual(row["all_case_associated_roots_before_cap"], 1)
        self.assertFalse(row["source_independence_established"])

    def test_missing_snapshot_days_cannot_be_fabricated(self):
        history = [snap(10, []), snap(12, []), snap(15, [])]
        out = build(history, case_ids=["taiwan", "korea"])
        self.assertEqual(out["sampling"]["packet_count"], 6)
        self.assertEqual(out["sampling"]["actual_days"], 3)
        self.assertEqual({p["asof"][:10] for p in out["packets"]},
                         {"2026-11-10", "2026-11-12", "2026-11-15"})

    def test_model_comparison_fails_closed_and_never_invents_event_precision(self):
        data = build([snap(12, [rec("2026-11-12T10:00:00Z")])],
                     case_ids=["taiwan", "korea"])
        p = data["packets"][0]
        known = p["source_claims"][0]["evidence_key"]
        good = {"analyst_approved": False, "evaluations": [],
                "interpretations": [{"hypothesis_index":i}
                                    for i in range(len(p["hypotheses"]))],
                "evidence_notes": [{"evidence_key":known}]}
        baseline = check_model_outputs(data, {})
        self.assertEqual(baseline["attempted_packets"], 0)
        self.assertIsNone(baseline["event_precision"])
        report = check_model_outputs(data, {p["packet_id"]:good})
        self.assertEqual(report["structurally_usable"],1)
        self.assertEqual(report["not_evaluated"],1)
        self.assertIsNone(report["event_false_positive_rate"])
        mutated = {**good, "evidence_notes":[{"evidence_key":"invented"}]}
        bad = check_model_outputs(data, {p["packet_id"]:mutated})
        self.assertEqual(bad["invented_or_off_packet_reference"],1)
        unauthorized = {**good,"evaluations":[{"direction":"possibly_consistent"}]}
        flagged = check_model_outputs(data, {p["packet_id"]:unauthorized})
        self.assertEqual(flagged["unusable_or_unauthorized"],1)

    def test_invalid_request_constraints_are_rejected(self):
        with self.assertRaises(ValueError):
            build([],case_ids=[])
        with self.assertRaises(ValueError):
            build([],case_ids=["taiwan"]*2)
        with self.assertRaises(ValueError):
            build([],case_ids=["taiwan"],days=11)
        with self.assertRaises(ValueError):
            build([],case_ids=["taiwan"],source_cap=9)


if __name__=="__main__":
    unittest.main()
