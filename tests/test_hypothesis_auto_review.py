"""Regression tests for machine screening (NOT analyst-reviewed evidence)."""
import datetime as dt
import unittest

from dashboard.hypothesis_auto_review import SCHEMA, screen

AT = "2026-11-21T15:00:00Z"
DOSSIERS = [
    {"id": "taiwan"}, {"id": "korea"}, {"id": "iran_gulf"},
    {"id": "drc_rwanda"},
]


def record(ident, title, *, first="2026-11-21T13:00:00Z",
           mode="nga", geo="Taiwan Strait", hint=None, root=None, url=None):
    return {
        "id": ident, "title": title, "first_observed_at": first,
        "collection_mode": mode, "source_url": url or f"https://example.org/{ident}",
        "source_family": "maritime_restriction", "information_root": root or ident,
        "provider": mode, "geography": geo, "case_hint": hint,
        "claim_level": "notice_not_verified_preparation",
        "registry_novelty": "newly_observed",
    }


def registry(rows, *, status="current"):
    return {"schema": "aiba.behavioral-observations.v1",
            "generated_at": "2026-11-21T14:00:00Z", "records": rows,
            "source_health": {m: {"status": status} for m in
                              {r["collection_mode"] for r in rows}}}


class AutoHypothesisReviewTests(unittest.TestCase):
    def test_explicitly_preliminary_and_no_auto_warning_or_signed_approval(self):
        row = record("a", "Taiwan maritime exclusion zone announced")
        output = screen(DOSSIERS, registry([row]), at=AT)
        self.assertEqual(output["schema"], SCHEMA)
        self.assertEqual(output["status"], "screened")
        self.assertFalse(output["analyst_direction_overridden"])
        self.assertEqual(output["operational_warnings_issued"], 0)
        c = output["cases"]["taiwan"]
        self.assertEqual(c["new_matching_records"], 1)
        self.assertEqual(c["possible_support"], 1)
        self.assertEqual(c["candidates"][0]["preliminary_direction"], "possible_support")
        self.assertEqual(c["candidates"][0]["match_basis"], "distinctive_case_cue")
        self.assertFalse(c["candidates"][0]["analyst_approved"])
        self.assertFalse(c["candidates"][0]["warning_approved"])
        self.assertEqual(output["cases"]["korea"]["new_matching_records"], 0)

    def test_counter_and_negation_never_mean_no_threat(self):
        rows = [
            record("a", "Taiwan border reopened"),
            record("b", "Taiwan no evacuation ordered"),
            record("c", "Taiwan shipping and trade continue"),
        ]
        c = screen(DOSSIERS, registry(rows), at=AT)["cases"]["taiwan"]
        self.assertEqual(c["possible_counter"], 1)
        self.assertEqual(c["requires_interpretation"], 1)
        self.assertEqual(c["context"], 1)
        self.assertNotIn("not_assessed", c)

    def test_stale_source_or_missing_source_snapshot_cannot_be_negative(self):
        r = record("x", "Taiwan mandatory evacuation")
        c = screen(DOSSIERS, registry([r], status="stale_or_unavailable"), at=AT)
        self.assertEqual(c["cases"]["taiwan"]["new_matching_records"], 0)
        self.assertEqual(c["cases"]["taiwan"]["unavailable_source_matches"], 1)
        missing = screen(DOSSIERS, {}, at=AT)
        self.assertEqual(missing["status"], "source_snapshot_unavailable")
        self.assertIsNone(missing["screened_at"])
        self.assertEqual(missing["cases"]["taiwan"]["candidates"], [])

    def test_recent_ingested_not_historical_or_future_or_initial_baseline(self):
        old = record("old", "Taiwan maritime exclusion zone", first="2026-11-18T00:00:00Z")
        future = record("future", "Taiwan maritime exclusion zone", first="2026-11-23T00:00:00Z")
        baseline = record("base", "Taiwan mandatory evacuation")
        baseline["registry_novelty"] = "initial_provider_baseline"
        c = screen(DOSSIERS, registry([old, future, baseline]), at=AT)
        self.assertEqual(c["cases"]["taiwan"]["new_matching_records"], 0)
        self.assertEqual(c["new_source_records_in_window"], 1)

    def test_explicit_case_hint_is_separate_from_geographic_inference(self):
        r = record("h", "New cross-border attack", geo="Unlocated",
                   hint="drc_rwanda")
        c = screen(DOSSIERS, registry([r]), at=AT)
        item = c["cases"]["drc_rwanda"]["candidates"][0]
        self.assertEqual(item["match_basis"], "explicit_case_hint")
        self.assertEqual(item["preliminary_direction"], "possible_support")
        self.assertEqual(c["cases"]["taiwan"]["new_matching_records"], 0)

    def test_same_source_root_deduplicated_and_not_independent_confirmation(self):
        rows = [
            record("a", "Taiwan airspace closure", root="one-root"),
            record("b", "Taiwan airspace closure repeated", root="one-root"),
        ]
        c = screen(DOSSIERS, registry(rows), at=AT)["cases"]["taiwan"]
        self.assertEqual(c["new_matching_records"], 1)
        self.assertEqual(c["possible_support"], 1)

    def test_hazards_are_context_not_suspicious_military_intent(self):
        r = record("q", "Taiwan mandatory evacuation due to earthquake",
                   mode="usgs")
        c = screen(DOSSIERS, registry([r]), at=AT)["cases"]["taiwan"]
        self.assertEqual(c["context"], 1)
        self.assertEqual(c["possible_support"], 0)

    def test_archive_used_when_valid_and_fallback_when_invalid(self):
        r = record("p", "Taiwan maritime exclusion zone")
        reg = registry([])
        reg["source_health"]["nga"] = {"status": "current"}
        good = {"schema": "aiba.family-archive.v1", "records": [r]}
        bad = {"schema": "aiba.family-archive.v0", "records": [r]}
        self.assertEqual(screen(DOSSIERS, reg, good, at=AT)
                         ["cases"]["taiwan"]["possible_support"], 1)
        self.assertTrue(screen(DOSSIERS, reg, good, at=AT)["durable_archive_used"])
        self.assertFalse(screen(DOSSIERS, reg, bad, at=AT)["durable_archive_used"])

    def test_non_https_bad_dates_and_unsupported_config_excluded(self):
        r = record("x", "Taiwan maritime exclusion zone", url="http://example.org/x")
        bad = record("y", "Taiwan mandatory evacuation", first="garbled")
        c = screen(DOSSIERS, registry([r, bad]), at=AT)
        self.assertEqual(c["cases"]["taiwan"]["new_matching_records"], 0)
        with self.assertRaises(ValueError):
            screen(DOSSIERS, registry([]), at=AT, lookback_hours=-2)

    def test_unknown_case_ids_not_inferred_from_generic_news(self):
        r = record("z", "US aircraft moved from base", geo="United States")
        o = screen([{"id":"made_up_case"}], registry([r]), at=AT)
        self.assertEqual(o["cases"]["made_up_case"]["new_matching_records"], 0)


if __name__ == "__main__":
    unittest.main()
