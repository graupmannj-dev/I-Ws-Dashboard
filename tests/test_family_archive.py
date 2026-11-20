"""Durable family archive: synthetic replay, expiry, reactivation, and audit."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from family_archive import SCHEMA, update, root_id
from dashboard.build_atlas import generate

NOW = dt.datetime(2026, 11, 19, 22, tzinfo=dt.timezone.utc)


def item(ident="beh:test-one", root="root:one", observed="2026-11-19T20:00:00Z"):
    return {
        "id": ident, "information_root": root,
        "first_observed_at": observed,
        "source_url": "https://example.org/source/" + ident.replace(":", "-"),
        "title": "Synthetic test outage " + ident,
        "source_family": "internet_reachability",
        "source_kind": "outage_event",
        "provider": "synthetic",
        "collection_mode": "ioda",
        "source_published_at": None,
        "geography": {"key": "country:FI", "label": "FI",
                      "precision": "provider_reported_country", "latitude": None,
                      "longitude": None},
    }


def registry(state, rows):
    path = state / "latest" / "behavioral_registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "aiba.behavioral-observations.v1",
                                "generated_at": NOW.isoformat(), "records": rows,
                                "source_health": {"ioda": {"status": "current"}}}))


class FamilyArchiveTests(unittest.TestCase):
    def test_repeated_polls_do_not_create_novelty(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d); registry(state, [item()])
            first = update(state, clock=NOW)
            self.assertEqual(first["root_count_total"], 1)
            self.assertEqual(first["new_records_added"], 1)
            second = update(state, clock=NOW+dt.timedelta(hours=2))
            self.assertEqual(second["new_records_added"], 0)
            self.assertEqual(second["records"][0]["first_observed_at"],
                             first["records"][0]["first_observed_at"])
            self.assertTrue((state/"family_archive"/"shards"/
                             (root_id("root:one")[:2]+".json")).exists())

    def test_absent_from_provider_does_not_delete_or_mean_zero(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);registry(state,[item()])
            update(state, clock=NOW)
            registry(state,[])
            later=update(state,clock=NOW+dt.timedelta(days=90))
            self.assertEqual(later["record_count_total"],1)
            self.assertEqual(later["root_count_total"],1)
            self.assertEqual(later["new_records_added"],0)
            self.assertTrue(later["missing_data_is_not_zero"])

    def test_long_running_root_gains_new_item_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);registry(state,[item()])
            first=update(state,clock=NOW)
            new=item("beh:second","root:one","2027-01-19T20:00:00Z")
            registry(state,[new])
            later=update(state,clock=NOW+dt.timedelta(days=61))
            self.assertEqual(later["root_count_total"],1)
            self.assertEqual(later["record_count_total"],2)
            self.assertEqual(later["new_records_added"],1)
            self.assertEqual(first["records"][0]["information_root"],
                             later["records"][0]["information_root"])
            self.assertTrue(any(x["id"]=="beh:test-one" for x in later["records"]))

    def test_bootstrap_backfills_historical_first_seen_without_false_date(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);registry(state,[])
            path=state/"history"/"behavioral_registry"
            path.mkdir(parents=True)
            (path/"20261110T120000Z-test.json").write_text(json.dumps({
                "schema":"aiba.behavioral-observations.v1",
                "generated_at":"2026-11-10T12:00:00Z",
                "new_records":[item("beh:older","root:older","2026-11-10T12:00:00Z")]
            }))
            result=update(state,clock=NOW)
            self.assertEqual(result["record_count_total"],1)
            self.assertEqual(result["records"][0]["first_observed_at"],
                             "2026-11-10T12:00:00+00:00")

    def test_invalid_schema_fails_without_erasing_existing_archive(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);registry(state,[item()])
            first=update(state,clock=NOW)
            shard=state/"family_archive"/"shards"/(root_id("root:one")[:2]+".json")
            prior=shard.read_text()
            registry(state,[])
            (state/"latest"/"behavioral_registry.json").write_text(
                '{"schema":"untrusted-source","records":[]}')
            with self.assertRaises(ValueError):
                update(state,clock=NOW+dt.timedelta(days=1))
            self.assertEqual(prior,shard.read_text())
            self.assertEqual(first["root_count_total"],1)

    def test_archive_supplies_quiet_candidates_to_atlas_without_live_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/"state";site=root/"site"
            site.mkdir()
            (site/"index.html").write_text("<p>Source grounded view</p>")
            (site/"hotspots.json").write_text(json.dumps({"asof":"2026-11-19"}))
            registry(state,[item()])
            update(state,clock=NOW)
            registry(state,[])
            result=generate(site,generated=(NOW+dt.timedelta(days=60)).isoformat(),
                            state_dir=state)
            self.assertEqual(result["dynamic_bins"]["archive_status"],
                             "durable_bounded_public_index")
            self.assertEqual(result["dynamic_bins"]["candidate_count_total"],1)
            self.assertEqual(result["dynamic_bins"]["quiet_count"],1)
            self.assertTrue(result["dynamic_bins"]["families"][0]["sources"][0]["source_url"].startswith("https://"))


    def test_related_source_links_persist_after_latest_resolver_disappears(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            a=item("beh:a","independent:source-a")
            b=item("beh:b","independent:source-b")
            registry(state,[a,b])
            from ops_pipeline import write_json
            write_json(state/"latest"/"behavioral_fusion.json",{
                "report_relationships":{"candidate_groups":[{
                    "id":"related:synthetic","status":"possible_same_event_unreviewed",
                    "match_basis":"synthetic explicit possible match",
                    "source_reports":[{"observation_id":"beh:a"},{"observation_id":"beh:b"}],
                }]}
            })
            initial=update(state,clock=NOW)
            self.assertEqual(initial["historical_relationship_count"],1)
            registry(state,[])
            write_json(state/"latest"/"behavioral_fusion.json",{})
            later=update(state,clock=NOW+dt.timedelta(days=35))
            self.assertEqual(later["historical_relationship_count"],1)
            link=later["report_relationships"]["candidate_groups"][0]
            self.assertEqual({x["observation_id"] for x in link["source_reports"]},
                             {"beh:a","beh:b"})
            self.assertFalse(link["independent_corroboration_established"])
            site=state/"site";site.mkdir()
            (site/"index.html").write_text("<p>Test</p>")
            (site/"hotspots.json").write_text('{"asof":"2026-11-19"}')
            rendered=generate(site,generated=(NOW+dt.timedelta(days=35)).isoformat(),
                              state_dir=state)
            grouped=[x for x in rendered["dynamic_bins"]["families"]
                     if x["kind"]=="possible_related_reporting"]
            self.assertEqual(len(grouped),1)
            self.assertFalse(grouped[0]["source_independence_established"])
            self.assertFalse(grouped[0]["warning_approved"])

    def test_source_id_cannot_move_between_persistent_root_families(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            registry(state,[item("beh:collision","root:a")])
            update(state,clock=NOW)
            registry(state,[item("beh:collision","root:b")])
            with self.assertRaisesRegex(ValueError,"Cross-archive observation identity/root conflict"):
                update(state,clock=NOW+dt.timedelta(days=61))


if __name__=="__main__":
    unittest.main()
