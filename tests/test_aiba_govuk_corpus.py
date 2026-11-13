import datetime as dt
import json
from pathlib import Path
import unittest

from scripts.aiba_govuk_corpus import (
    SCHEMA, canonical_path, check_manifest, to_source, collect, Paragraphs,
)
from scripts.aiba_source_text_intake import ingest
from scripts.aiba_claim_lab import prepare

SEEDS = Path(__file__).resolve().parents[1] / "data/govuk_source_seed_manifest.json"
NOW = dt.datetime(2026, 11, 13, 18, 0, tzinfo=dt.timezone.utc)
CONTENT_ID = "1ddf704c-844e-411a-90c0-03bd2d459977"


def source(seed, *, body=None, content_id=CONTENT_ID):
    html = body if body is not None else (
        "<p>Royal Air Force Typhoons struck several buildings near Sanaa.</p>"
        "<blockquote><p>This is a third-party quoted statement that must not appear in output.</p></blockquote>"
        "<p>Officials discussed the incident during a government meeting that followed the event.</p>"
        "<figure><p>Media caption from a third-party picture provider.</p></figure>"
        "<p>The RAF aircraft returned safely following the operation in Yemen.</p>"
    )
    from urllib.parse import urlsplit
    return {
        "base_path": urlsplit(seed["url"]).path,
        "content_id": content_id,
        "title": "Government statement about RAF operation",
        "document_type": "news_article",
        "first_published_at": "2025-04-30T10:00:00Z",
        "public_updated_at": "2025-05-01T10:00:00Z",
        "details": {"body": html},
    }


class GovukCorpusContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(SEEDS.read_text(encoding="utf-8"))
        cls.first = cls.manifest["seeds"][0]

    def test_historical_seed_allowlist_and_sampling_not_truth(self):
        seeds = check_manifest(self.manifest)
        self.assertGreaterEqual(len(seeds), 30)
        self.assertEqual(self.manifest["schema"], SCHEMA)
        self.assertEqual(len({x["url"] for x in seeds}), len(seeds))
        self.assertEqual(set(x["sampling_stratum"] for x in seeds), {
            "incident_candidate", "operational_context", "nonincident_control"
        })

    def test_fixed_origin_and_path(self):
        with self.assertRaisesRegex(ValueError, "canonical"):
            canonical_path("https://example.org/government/news/a-long-enough-name")
        with self.assertRaisesRegex(ValueError, "reviewed government"):
            canonical_path("https://www.gov.uk/account/details")
        with self.assertRaises(ValueError):
            canonical_path("https://www.gov.uk/government/news/a-long-enough-path?evil=1")

    def test_real_body_shape_preserves_provenance_and_excludes_quotes(self):
        item, error = to_source(self.first, source(self.first), "2026-11-13T18:00:00Z")
        self.assertIsNone(error)
        self.assertEqual(item["source_family"], "official_media")
        self.assertEqual(item["source_kind"], "government_public_statement")
        self.assertIn("Royal Air Force Typhoons struck", item["source_text"])
        self.assertNotIn("third-party quoted", item["source_text"])
        self.assertNotIn("Media caption", item["source_text"])
        self.assertEqual(item["content_type"], "source_excerpt")
        self.assertIn("Open Government Licence", item["rights_note"])
        self.assertEqual(item["sampling_stratum"], self.first["sampling_stratum"])
        self.assertTrue(item["evaluation_group_id"].startswith("govuk-episode:"))
        self.assertNotIn("reported_event_location", item)
        rows, frozen, receipt = ingest([item])
        self.assertEqual(len(rows), 1)
        self.assertIn("official_media", rows[0]["source_family"])
        self.assertTrue(rows[0]["source_text_sha256"])
        self.assertFalse(receipt["rights_verified_by_software"])

    def test_explicit_exception_rejected(self):
        bad = source(self.first, body="<p>All rights reserved. " +
                     "An extended statement about the event was published to the public.</p>")
        item, error = to_source(self.first, bad, "2026-11-13T18:00:00Z")
        self.assertEqual(error, "possible_third_party_rights")
        self.assertIsNone(item)

    def test_unavailable_full_article_rejected(self):
        bad = source(self.first, body="")
        item, error = to_source(self.first, bad, "2026-11-13T18:00:00Z")
        self.assertEqual(error, "missing_article_html")
        self.assertIsNone(item)

    def test_api_url_mismatch_rejected(self):
        bad = source(self.first)
        bad["base_path"] = "/government/news/a-different-govuk-article"
        item, reason = to_source(self.first, bad, "2026-11-13T18:00:00Z")
        self.assertEqual(reason, "api_path_mismatch")

    def test_bounded_mock_collection_and_claim_lab(self):
        seeds = self.manifest["seeds"][:2]
        manifest = {"schema": SCHEMA, "seeds": seeds}
        source_ids = [CONTENT_ID, "a1df704c-844e-411a-90c0-03bd2d459978"]
        by_path = {s["url"].replace("https://www.gov.uk", ""):
                   source(s, content_id=source_ids[i]) for i, s in enumerate(seeds)}
        rows, audit = collect(manifest, fetch=lambda path: by_path[path],
                              clock=lambda: NOW, sleep=lambda _: None, delay_seconds=0)
        self.assertEqual(audit["successful_article_text_count"], 2)
        self.assertEqual(audit["human_ground_truth_labels_created"], 0)
        self.assertTrue(audit["official_statement_not_independent_verification"])
        lab = prepare(rows, {"evaluation_group_splits": {
            "govuk-episode:" + seeds[0]["episode_hint"]: "development",
            "govuk-episode:" + seeds[1]["episode_hint"]: "development",
        }})
        self.assertEqual(lab[-1]["reports"], 2)
        self.assertGreaterEqual(lab[-1]["candidate_claims"], 1)
        self.assertEqual(lab[-1]["automatic_alerts_created"], 0)
        self.assertEqual(lab[-1]["blinded_packets_generated"], 2)

    def test_same_episode_cannot_cross_splits(self):
        a = self.first
        b = dict(self.manifest["seeds"][1])
        b["episode_hint"] = a["episode_hint"]
        item_a, _ = to_source(a, source(a), "2026-11-13T18:00:00Z")
        item_b, _ = to_source(b, source(b, content_id="a1df704c-844e-411a-90c0-03bd2d459978"),
                              "2026-11-13T18:00:00Z")
        rows, manifest, receipt = ingest([item_a, item_b])
        self.assertEqual(rows[0]["split"], rows[1]["split"])
        self.assertEqual(receipt["distinct_evaluation_groups"], 1)
        with self.assertRaisesRegex(ValueError, "frozen"):
            ingest([dict(item_a, split="heldout" if rows[0]["split"]=="development" else "development")],manifest)


if __name__ == "__main__":
    unittest.main()
