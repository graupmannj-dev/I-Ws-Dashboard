"""Adversarial acceptance tests for CAIRN competing-hypothesis nominations."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from dashboard.hypothesis_discriminator_engine import SCHEMA, assess
from dashboard.build_atlas import generate

CONFIG = json.loads((Path(__file__).resolve().parents[1] /
                     "data/hypothesis_discriminators.json").read_text())
AT = "2026-11-23T12:00:00Z"
DOSSIERS = json.loads((Path(__file__).resolve().parents[1] /
                       "data/verified_hotspots.json").read_text())


def row(name, title, *, mode="official", geo="", hint=None, url=None,
        first="2026-11-22T08:00:00Z", family="official_notice", root=None):
    return {
        "id": name, "first_observed_at": first,
        "title": title, "collection_mode": mode, "source_family": family,
        "source_url": url or "https://example.org/report/" + name,
        "information_root": root or name,
        "case_hint": hint, "geography_label": geo,
        "claim_level": "official_notice_not_verified_preparation",
    }


def registry(*records, status="current"):
    modes = {r["collection_mode"] for r in records}
    return {"schema": "aiba.behavioral-observations.v1",
            "generated_at": AT, "records": list(records),
            "source_health": {mode: {"status": status,
                                     "source_scope": "Test source scope, not global"}
                              for mode in modes}}


def archive(*records):
    return {"schema": "aiba.family-archive.v1", "records": list(records)}


def run(*records, health="current", provider_baselines=None, gdelt=None):
    return assess(DOSSIERS, registry(*records, status=health),
                  archive(*records), gdelt or {},
                  provider_baselines or {}, CONFIG, at=AT)


class CompetingHypothesisTests(unittest.TestCase):
    def test_all_ten_cases_and_no_automatic_approval(self):
        cases = {r["id"] for r in DOSSIERS}
        self.assertEqual(cases, set(CONFIG["cases"]))
        self.assertEqual(len(CONFIG["templates"]), 12)
        result = run()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["hypothesis_count"], 10)
        self.assertEqual(result["automated_warnings"], 0)
        self.assertEqual(result["analyst_approved_directions"], 0)
        self.assertIsNone(result["probability_of_conflict"])
        for entry in result["cases"].values():
            self.assertEqual(entry["summary"]["competing_pattern"],
                             "no_matching_case_records_in_window")
            self.assertEqual(entry["summary"]["direction_of_armed_conflict_hypothesis"],
                             "not_estimated")

    def test_concrete_current_actor_pair_signpost_is_candidate_only(self):
        r = row("one", "Taiwan Strait blockade imposed by the navy",
                geo="Taiwan Strait")
        case = run(r)["cases"]["taiwan"]
        self.assertEqual(case["summary"]["escalation_signpost_nominations"], 1)
        self.assertEqual(case["summary"]["competing_pattern"],
                         "escalation_signposts_nominated")
        maritime = next(x for x in case["discriminators"]
                        if x["id"] == "maritime_interdiction")
        self.assertEqual(maritime["status"], "candidate_observed")
        self.assertEqual(maritime["candidate_count"], 1)
        self.assertFalse(maritime["sources"][0]["analyst_approved"])
        self.assertFalse(maritime["sources"][0]["independent_observation_confirmed"])
        self.assertEqual(case["summary"]["direction_of_armed_conflict_hypothesis"],
                         "not_estimated")

    def test_routine_exercises_nominate_alternative_not_escalation(self):
        r = row("a", "Denmark. The Baltic Sea. Firing exercises. Warning.",
                mode="live_maritime", family="maritime_restriction",
                geo="Baltic Sea")
        case = run(r)["cases"]["russia_nato"]
        self.assertEqual(case["summary"]["escalation_signpost_nominations"], 0)
        self.assertEqual(case["summary"]["alternative_signpost_nominations"], 1)
        self.assertEqual(case["summary"]["competing_pattern"],
                         "alternative_signposts_nominated")

    def test_unverified_claim_and_denial_are_ambiguous(self):
        r = row("b", "Poland reports Russian missile strike near the Baltic Sea",
                mode="analyst", family="media_mention", hint="russia_nato")
        negation = row("c", "Russian missile strike in Baltic Sea denied",
                       mode="official")
        case = run(r, negation)["cases"]["russia_nato"]
        self.assertEqual(case["summary"]["escalation_signpost_nominations"], 0)
        self.assertGreaterEqual(case["summary"]["ambiguous_signpost_nominations"], 2)
        self.assertEqual(case["summary"]["competing_pattern"],
                         "ambiguous_or_context_only")

    def test_stale_provider_does_not_contribute_signed_nomination(self):
        r = row("one", "Taiwan Strait blockade imposed by the navy")
        case = run(r, health="stale_or_unavailable")["cases"]["taiwan"]
        self.assertEqual(case["summary"]["escalation_signpost_nominations"], 0)
        self.assertGreater(case["summary"]["ambiguous_signpost_nominations"], 0)

    def test_environmental_evacuation_does_not_become_hostile_preparation(self):
        r = row("storm", "Taiwan mandatory evacuation due to typhoon",
                mode="nws", family="environmental_context")
        case = run(r)["cases"]["taiwan"]
        self.assertEqual(case["summary"]["escalation_signpost_nominations"], 0)
        self.assertGreater(case["summary"]["ambiguous_signpost_nominations"], 0)
        self.assertTrue(any(x["id"] == "natural_hazard" and x["context_count"] == 1
                            for x in case["discriminators"]))

    def test_same_notice_url_deduplicates_even_if_archive_roots_differ(self):
        url="https://niord.dma.dk/#/message/example-123"
        a = row("frag1", "Denmark. The Baltic Sea. Firing exercises. Warning.",
                mode="live_maritime",family="maritime_restriction",
                url=url,root="notices:fragment:1")
        b = row("frag2", "Denmark. The Baltic Sea. Firing exercises. Warning.",
                mode="live_maritime",family="maritime_restriction",
                url=url,root="notices:fragment:2")
        case=run(a,b)["cases"]["russia_nato"]
        rule=next(r for r in case["discriminators"] if r["id"]=="scheduled_training")
        self.assertEqual(rule["candidate_count"],1)
        self.assertEqual(case["summary"]["source_documents_case_associated"],1)

    def test_unrelated_interstate_or_third_country_does_not_map_to_case(self):
        r=row("unrelated", "Iran vessel strike off the Gulf of Mexico",
              geo="Gulf of Mexico")
        result=run(r)
        self.assertEqual(result["cases"]["iran_gulf"]["summary"]
                         ["source_documents_case_associated"],0)

    def test_provider_baselines_show_readiness_not_case_risk(self):
        r=row("x","Taiwan Strait blockade imposed",mode="official")
        baselines={"schema":"aiba.behavioral-provider-baseline.v1",
                   "minimum_comparable_days":14,"sources":{
                       "official":{"comparable_provider_snapshot_days":20,
                                   "status":"descriptive_baseline_available",
                                   "median_daily_first_seen_records":4}}}
        case=run(r,provider_baselines=baselines)["cases"]["taiwan"]
        mode=next(v for v in case["source_baseline_readiness"] if v["mode"]=="official")
        self.assertEqual(mode["status"],"provider_descriptive_baseline_available")
        self.assertFalse(mode["case_specific"])
        self.assertFalse(mode["baseline_direction_inferred"])
        self.assertEqual(case["summary"]["direction_of_armed_conflict_hypothesis"],
                         "not_estimated")

    def test_gdelt_increase_alone_does_not_favor_escalation(self):
        gdelt={"schema":"cairn.gdelt-case-trends.v1","baseline_days":28,
               "window_days":7,"cases":{"taiwan":{"status":"measured",
                    "trend":"higher_coded_share","media_share_ratio":2.4}}}
        case=run(gdelt=gdelt)["cases"]["taiwan"]
        self.assertEqual(case["gdelt_context"]["media_coded_share_trend"],
                         "higher_coded_share")
        self.assertTrue(case["gdelt_context"]["not_independent_evidence"])
        self.assertEqual(case["summary"]["escalation_signpost_nominations"],0)
        self.assertEqual(case["summary"]["alternative_signpost_nominations"],0)

    def test_missing_archive_and_provider_is_not_an_all_clear(self):
        result=assess(DOSSIERS,{}, {},{}, {},CONFIG,at=AT)
        self.assertEqual(result["status"],"source_evidence_unavailable")
        case=result["cases"]["taiwan"]
        self.assertEqual(case["status"],"source_evidence_unavailable")
        self.assertIn("no_matching",case["summary"]["competing_pattern"])
        for row_ in case["source_baseline_readiness"]:
            self.assertEqual(row_["status"],"provider_history_unavailable")

    def test_bad_config_fails_closed(self):
        with self.assertRaises(ValueError):
            assess(DOSSIERS,registry(),archive(),{},{},{"schema":"wrong"},at=AT)
        malformed=json.loads(json.dumps(CONFIG))
        malformed["cases"]["taiwan"]["escalation"]=["invalid_indicator"]
        with self.assertRaises(ValueError):
            assess(DOSSIERS,registry(),archive(),{},{},malformed,at=AT)

    def test_published_site_has_distinct_auditable_machine_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            site=Path(temp)
            (site/"hotspots.json").write_text(json.dumps({"asof":"2026-11-22"}))
            generate(site,generated=AT)
            payload=json.loads((site/"hypotheses.json").read_text())
            screen=json.loads((site/"hypothesis_discriminator_screen.json").read_text())
            self.assertEqual(screen["hypothesis_count"],10)
            self.assertEqual(payload["discriminator_screen"]["hypothesis_count"],10)
            cases={c["id"]:c for c in payload["hypotheses"]}
            self.assertIn("competing_screen",cases["taiwan"])
            self.assertEqual(cases["taiwan"]["competing_screen"]["summary"]
                             ["direction_of_armed_conflict_hypothesis"],"not_estimated")
            self.assertEqual(cases["taiwan"]["balance"]["direction"],"not_assessed")


if __name__ == "__main__":
    unittest.main()
