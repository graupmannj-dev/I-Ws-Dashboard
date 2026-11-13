import unittest
from behavioral_claim_extraction import build, extract_report

def report(text=None, **extra):
    row = {
        "id": "r1", "source_url": "https://example.org/articles/r1",
        "source_family": "commercial_media",
        "reporting_origin": "New York",
        "title": "Kyiv energy story",
    }
    if text is not None:
        row["source_text"] = text
    row.update(extra)
    return row

class ClaimExtractionTests(unittest.TestCase):
    def test_literal_clause_evidence_offsets(self):
        body = "Background. Russian missiles struck Kyiv energy substation overnight."
        result = extract_report(report(body))
        self.assertEqual(result["status"], "candidate_claims_unreviewed")
        claim = result["claims"][0]
        self.assertEqual(claim["actor_text"], "Russian missiles")
        self.assertEqual(claim["action"], "strike")
        self.assertEqual(claim["object_text"], "Kyiv energy substation overnight")
        s = claim["evidence_span"]
        self.assertEqual(body[s["start"]:s["end"]], s["text"])
        self.assertIsNone(claim["event_site"])
        self.assertIsNone(claim["event_time"])

    def test_deny_and_unconfirmed(self):
        self.assertEqual(extract_report(report("Russian missiles did not strike Kyiv energy station."))["claims"], [])
        result = extract_report(report("Russian missiles reportedly struck Kyiv energy station."))
        self.assertEqual(result["claims"][0]["assertion_status"], "attributed_or_uncertain")

    def test_no_body_is_abstention(self):
        result = extract_report(report())
        self.assertEqual(result["reason"], "source_body_unavailable")
        self.assertEqual(result["claims"], [])

    def test_publisher_does_not_create_event_site(self):
        r = extract_report(report("Russian missiles struck Kyiv energy substation.",
                                  reporting_origin="New York lat 40.7 lon -74"))
        self.assertIsNone(r["claims"][0]["event_site"])

    def test_only_source_site_and_time(self):
        r = extract_report(report(
            "Russian missiles struck Kyiv energy station.",
            event_at="2026-11-13T03:00:00Z",
            reported_event_location={"role": "reported_event_site", "basis": "source_declared",
                                     "lat": 50.45, "lon": 30.52}))
        c = r["claims"][0]
        self.assertEqual(c["event_time_basis"], "source_supplied_event_at_unreviewed")
        self.assertEqual(c["event_site"]["lat"], 50.45)

    def test_publisher_or_coarse_location_not_event_site(self):
        for site in [{"role": "publisher_office", "basis": "source_declared", "lat": 40.7,"lon":-74},
                     {"role": "reported_event_site", "basis": "inferred", "lat": 50.45,"lon":30.52}]:
            c=extract_report(report("Russian missiles struck Kyiv energy station.",
                                    reported_event_location=site))["claims"][0]
            self.assertIsNone(c["event_site"])

    def test_quoted_or_pronoun_claims_abstain(self):
        self.assertEqual(extract_report(report('The article said "Russian missiles struck Kyiv station."'))["claims"], [])
        self.assertEqual(extract_report(report("They attacked the station."))["claims"], [])

    def test_contextual_notice_excluded(self):
        r=extract_report(report("Russia attacked a facility.",source_family="protective_notice"))
        self.assertEqual(r["reason"], "not_event_reporting")

    def test_overlong_and_incomplete_rejected(self):
        self.assertEqual(extract_report(report("A" * 12001))["reason"], "source_body_over_limit")
        self.assertEqual(extract_report(report("Ukraine military security conflict."))["claims"], [])

    def test_no_warning_or_corroboration(self):
        out=build([report("Russian missiles struck Kyiv energy station."),report()])
        self.assertEqual(out["candidate_claim_count"],1)
        self.assertEqual(out["abstention_count"],1)
        self.assertEqual(out["automatic_alerts_created"],0)
        self.assertFalse(out["warning_level_change"])
        self.assertFalse(out["reports"][0]["independent_corroboration_established"])

    def test_hard_cap(self):
        with self.assertRaises(ValueError):
            build([report()] * 251)

if __name__ == "__main__":
    unittest.main()
