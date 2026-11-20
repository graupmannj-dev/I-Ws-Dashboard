"""Synthetic regression tests: source-family discovery is not corroboration."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.dynamic_bins import build, SCHEMA
from dashboard.build_atlas import generate

NOW = dt.datetime(2026, 11, 19, 20, 0, tzinfo=dt.timezone.utc)


def source(ident="beh:one", root="official:one", first="2026-11-19T19:00:00Z",
           family="airspace_restriction", case=None):
    return {
        "id": ident, "information_root": root, "first_observed_at": first,
        "source_url": "https://example.org/notice/" + ident.replace(":", "-"),
        "title": "Synthetic source-led aviation notice " + ident,
        "source_family": family, "source_kind": "test_source_notice",
        "provider": "Fixture", "case_hint": case, "event_at": None,
        "source_published_at": None, "direct_observed_behavior": False,
        "claim_level": "notice_not_verified_preparation",
        "geography": {"key": "country:FI", "kind": "country_code", "label": "FI",
                      "precision": "provider_reported_country", "latitude": None,
                      "longitude": None, "verified_iso": False},
    }


def registry(rows):
    return {"schema": "aiba.behavioral-observations.v1", "records": rows}


def analyst(rows=None):
    return {"records": rows or [], "distinct_observations": len(rows or []),
            "status": "collected"}


class DynamicBinsTests(unittest.TestCase):
    def test_unconfirmed_single_source_is_visible_immediately(self):
        result = build(registry([source()]), analyst(), now=NOW)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["emerging_count"], 1)
        self.assertEqual(result["candidate_count_total"], 1)
        candidate = result["families"][0]
        self.assertEqual(candidate["source_families"], ["airspace_restriction"])
        self.assertEqual(candidate["information_root_count"], 1)
        self.assertEqual(candidate["corroboration"]["status"], "unreviewed")
        self.assertFalse(candidate["map_eligible"])
        self.assertFalse(candidate["warning_approved"])
        self.assertEqual(candidate["anomaly_metric"]["status"], "not_calibrated")
        self.assertIsNone(candidate["anomaly_metric"]["z_score"])

    def test_different_events_same_country_do_not_collapse(self):
        a, b = source("beh:first", "root:first"), source("beh:second", "root:second")
        result = build(registry([a, b]), analyst(), now=NOW)
        self.assertEqual(result["candidate_count_total"], 2)
        self.assertEqual(len({x["id"] for x in result["families"]}), 2)

    def test_duplicate_source_root_is_one_family_not_corroborated(self):
        a = source("beh:partA", "notice:document")
        b = source("beh:partB", "notice:document")
        result = build(registry([a, b]), analyst(), now=NOW)
        self.assertEqual(result["candidate_count_total"], 1)
        self.assertEqual(result["families"][0]["source_record_count"], 2)
        self.assertEqual(result["families"][0]["information_root_count"], 1)

    def test_quiet_family_retains_id_and_reactivates_if_new_evidence(self):
        a = source("beh:one", "root:stable")
        fresh = build(registry([a]), analyst(), now=NOW)["families"][0]
        old = build(registry([a]), analyst(), now=NOW + dt.timedelta(days=25))["families"][0]
        self.assertEqual(old["state"], "quiet")
        self.assertEqual(old["id"], fresh["id"])
        updated = source("beh:new", "root:stable", "2026-12-14T18:00:00Z")
        reactivated = build(registry([a, updated]), analyst(),
                            now=NOW+dt.timedelta(days=25))["families"][0]
        self.assertEqual(reactivated["id"], fresh["id"])
        self.assertEqual(reactivated["state"], "emerging")

    def test_partial_unlocated_or_future_records_not_mapped_or_pulsed(self):
        future = source("beh:future", "root:future", "2027-01-01T00:00:00Z")
        no_url = source("beh:no-url", "root:no-url")
        no_url["source_url"] = "javascript:alert(1)"
        found = build(registry([future, no_url]), analyst(), now=NOW)
        self.assertEqual(found["candidate_count_total"], 0)

    def test_analyst_case_hints_do_not_conflate_different_events(self):
        rows = [
            {"observation_id": "analyst:a", "case_id": "iran_gulf",
             "information_root": "a", "source_url": "https://example.org/a",
             "first_collected_at": "2026-11-19T18:00:00Z",
             "title": "Synthetic port report", "publisher": "Test", "evidence_class": "media_mention"},
            {"observation_id": "analyst:b", "case_id": "iran_gulf",
             "information_root": "b", "source_url": "https://example.org/b",
             "first_collected_at": "2026-11-19T19:00:00Z",
             "title": "Synthetic unrelated road report", "publisher": "Test", "evidence_class": "media_mention"},
        ]
        found = build(registry([]), analyst(rows), now=NOW)
        self.assertEqual(found["candidate_count_total"], 2)
        self.assertTrue(all(x["map_eligible"] is False for x in found["families"]))

    def test_related_reporting_only_when_resolver_provides_explicit_link(self):
        a, b = source("beh:alpha", "root:alpha"), source("beh:beta", "root:beta")
        relation = {"candidate_groups": [{
            "id": "rel:one", "status": "possible_same_event_unreviewed",
            "match_basis": "synthetic highly similar source claims",
            "source_reports": [{"observation_id": "beh:alpha"}, {"observation_id": "beh:beta"}],
        }]}
        output = build(registry([a, b]), analyst(), relation, now=NOW)
        self.assertEqual(output["candidate_count_total"], 3)
        grouped = next(x for x in output["families"] if x["kind"] == "possible_related_reporting")
        self.assertEqual(grouped["information_root_count"], 2)
        self.assertFalse(grouped["source_independence_established"])
        self.assertFalse(grouped["map_eligible"])
        self.assertFalse(grouped["warning_approved"])

    def test_builder_accepts_missing_optional_registry_and_legacy_atlas(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"
            state = Path(d) / "ops-state"
            site.mkdir()
            (site / "index.html").write_text("<p>Legacy briefing</p>")
            (site / "hotspots.json").write_text(json.dumps({"asof": "2026-11-19"}))
            (state / "latest").mkdir(parents=True)
            (state / "latest" / "behavioral_registry.json").write_text(json.dumps(registry([
                source()
            ])))
            output = generate(site, generated="2026-11-19T20:00:00Z", state_dir=state)
            self.assertEqual(output["dynamic_bins"]["candidate_count_total"], 1)
            self.assertEqual(output["dynamic_bins"]["emerging_count"], 1)
            self.assertEqual(len(output["hotspots"]), 10)
            self.assertTrue((site / "atlas.json").exists())


if __name__ == "__main__":
    unittest.main()
