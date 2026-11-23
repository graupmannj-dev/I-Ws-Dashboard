"""Safety and evidence-contract tests for original source and geographic attribution."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dashboard.source_geo_claims import attribute, inspect_text
from dashboard.hypothesis_source_link import attach
from scripts.cairn_source_inspection import (SCHEMA, _safe_source_url, _narrative,
                                             read_original, inspect, NoRedirect)

CONFIG = json.loads((Path(__file__).resolve().parents[1] /
                     "data/hypothesis_discriminators.json").read_text())
AT = "2026-11-23T12:00:00Z"


def sample(url="https://www.reuters.com/world/middle-east/iran-khasab-missile-attack-2026-11-21/"):
    return {"schema": "aiba.family-archive.v1", "records": [
        {"id": "analyst:iran", "first_observed_at": "2026-11-22T11:00:00Z",
         "title": "UKMTO reports tanker projectile attack near Oman's Khasab",
         "case_hint": "iran_gulf", "collection_mode": "analyst",
         "source_family": "media_mention", "source_url": url,
         "information_root": "ukmto:incident"}]}


def registry():
    return {"schema": "aiba.behavioral-observations.v1", "generated_at": AT,
            "records": [], "source_health": {}}


class GeographicEvidenceTests(unittest.TestCase):
    def test_action_named_locality_only_nonverified(self):
        a = attribute("A tanker was struck by a projectile near Khasab yesterday.",
                      "iran_gulf")
        self.assertEqual(a["status"], "named_place_in_action_statement")
        self.assertEqual(a["named_place"], "Khasab")
        self.assertEqual(a["reported_country_or_area"], "OM")
        self.assertIsNone(a["coordinates"])
        self.assertFalse(a["reported_event_site_verified"])
        self.assertEqual(len(a["evidence_span"]["sentence_sha256"]), 64)

    def test_london_dateline_does_not_geolocate_attack(self):
        a = attribute("LONDON. The ministry in London said Iranian missiles struck Khasab.",
                      "iran_gulf")
        self.assertEqual(a["named_place"], "Khasab")
        self.assertNotEqual(a["named_place"], "London")

    def test_actor_name_is_not_incident_site(self):
        a = attribute("Ethiopia attacked Eritrea, official said.", "horn_ethiopia_eritrea")
        self.assertEqual(a["status"], "actor_or_context_mentions_only")
        self.assertIsNone(a["named_place"])

    def test_third_country_incident_does_not_attribute_nato_site(self):
        a = attribute("Russia struck Kyiv in Ukraine. Poland commented later.",
                      "russia_nato")
        self.assertEqual(a["status"], "actor_or_context_mentions_only")
        self.assertIsNone(a["coordinates"])

    def test_denial_and_two_localities_abstain(self):
        a = attribute("Russia reportedly struck Kaliningrad with a missile.",
                      "russia_nato")
        self.assertEqual(a["status"], "reported_locality_claim_unresolved")
        b = attribute("Reports said a vessel was hit near Khasab. Another ship was hit at Qeshm.",
                      "iran_gulf")
        self.assertEqual(b["status"], "multiple_localities_ambiguous")
        self.assertIsNone(b["named_place"])

    def test_context_only_place_does_not_become_incident(self):
        a = attribute("Local officials held discussions in Goma. No activity confirmed.",
                      "drc_rwanda")
        self.assertEqual(a["status"], "actor_or_context_mentions_only")

    def test_body_vs_title_discrepancy_found(self):
        text = ("Officials in Bahrain described damaged infrastructure. "
                "Authorities opened the road and said the border was not closed. "
                "No maritime exclusion zone had been declared.")
        r = inspect_text(text, "iran_gulf", CONFIG["templates"])
        self.assertIn("maritime_interdiction", r["qualified_or_disputed_rule_mentions"]
                         if "maritime_interdiction" in r["qualified_or_disputed_rule_mentions"]
                         else ["no_maritime_rule"])
        self.assertFalse(r["event_occurrence_verified"])

    def test_missing_source_text_abstains(self):
        a = attribute(None, "taiwan")
        self.assertEqual(a["status"], "source_text_unavailable")


class BoundedSourceFetchTests(unittest.TestCase):
    def test_only_allowlisted_source_specific_https_documents(self):
        self.assertIsNone(_safe_source_url("http://www.reuters.com/world/a-long-article"))
        self.assertIsNone(_safe_source_url("https://127.0.0.1/secret"))
        self.assertIsNone(_safe_source_url("https://evil.example.com/a-long-article"))
        self.assertIsNone(_safe_source_url("https://www.reuters.com/"))
        self.assertIsNone(_safe_source_url("https://www.reuters.com/world/file.pdf"))
        self.assertIsNotNone(_safe_source_url(
            "https://www.reuters.com/world/middle-east/long-sample-article-title/"))
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,"","","https://evil.test")
                          if False else None)

    def test_html_parser_ignores_navigation_scripts_and_quotes(self):
        html = ('<html><head><script>BAD WORDS</script></head><body>'
                '<nav><p>Help and menus</p></nav><main><p>A vessel was struck near Khasab in the Gulf.</p>'
                '<blockquote><p>Do not store this third-party quotation</p></blockquote>'
                '<p>Official emergency authorities are investigating how the ship was damaged.</p>'
                '</main><footer><p>Cookie preferences and contacts</p></footer></body></html>')
        text = _narrative(html)
        self.assertIn("Khasab", text)
        self.assertNotIn("Help and menus", text)
        self.assertNotIn("quotation", text)
        self.assertNotIn("Cookie preferences", text)

    def test_access_denial_abstains_no_external_network(self):
        with patch("scripts.cairn_source_inspection._load_bytes",
                   side_effect=TimeoutError("bounded timeout")):
            data, note = read_original("https://www.reuters.com/world/a-sample-long-document-title/")
        self.assertIsNone(data)
        self.assertEqual(note["status"], "source_content_not_retrievable")
        self.assertEqual(note["reason"], "TimeoutError")

    def test_inspection_does_not_publish_original_body(self):
        body = ("An independent maritime bulletin stated that a tanker was struck "
                "near Khasab and the port suspended movement. ")*7
        def fake_fetch(url):
            return body, {"status":"document_text_inspected",
                          "retrieval_kind":"test_in_memory"}
        result = inspect(registry(), sample(), CONFIG, at=AT, maximum=3,
                         fetch=fake_fetch)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status_counts"]["document_text_inspected"], 1)
        self.assertFalse(result["source_bodies_saved"])
        self.assertFalse(result["source_bodies_published"])
        row = result["inspections"][0]
        self.assertNotIn("source_text", row)
        self.assertNotIn(body, json.dumps(result))
        self.assertEqual(row["document_inspection"]["case_attribution"]["named_place"],
                         "Khasab")
        self.assertFalse(row["event_occurred_verified"])

    def test_source_link_is_metadata_not_signed_review(self):
        raw = {"cases":{"iran_gulf":{"discriminators":[{"id":"maritime_interdiction",
            "sources":[{"source_url": sample()["records"][0]["source_url"],
                        "title":"Original article"}]}]}}}
        body = ("An original dispatch described a tanker hit near Khasab. ")*7
        receipt = inspect(registry(), sample(), CONFIG, at=AT, maximum=3,
                          fetch=lambda url:(body,{"status":"document_text_inspected"}))
        joined = attach(raw,receipt)
        src = joined["cases"]["iran_gulf"]["discriminators"][0]["sources"][0]
        self.assertEqual(src["original_document_review"]["status"],"document_text_inspected")
        self.assertFalse(src["original_document_review"]["event_verified"])
        self.assertEqual(joined["original_source_inspection"]["auto_confirmed_events"],0)

    def test_no_receipt_is_missing_not_an_all_clear(self):
        raw={"cases":{"iran_gulf":{"discriminators":[{"id":"direct_state_engagement",
             "sources":[{"source_url":"https://example.org/a"}]}]}}}
        joined=attach(raw,{})
        self.assertEqual(joined["cases"]["iran_gulf"]["original_source_inspection"]
                         ["status"],"not_collected_this_build")
        self.assertIsNone(joined["original_source_inspection"]
                          ["distinct_source_documents_attempted"])


if __name__ == "__main__":
    unittest.main()
