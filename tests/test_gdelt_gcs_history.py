"""Deterministic, network-free checks for GCS GDELT history reliability."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.gdelt_gcs_history import (
    EXPECTED_SEED_FIRST, EXPECTED_SEED_LAST, EXPECTED_SEED_DAYS,
    PREFIX, SOURCE_PROFILE, SCHEMA, canonical, choose_missing_dates,
    day_key, execute, parse_seed, restore_record, source_record, write_immutable,
)


class MemoryBlob:
    def __init__(self, store, name):
        self.store, self.name = store, name
    def exists(self):
        return self.name in self.store
    def download_as_bytes(self):
        return self.store[self.name]
    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        if if_generation_match != 0 or self.name in self.store:
            raise ValueError("Expected atomic create-only GCS semantics")
        self.store[self.name] = data


class MemoryBucket:
    def __init__(self):
        self.objects = {}
    def blob(self, name):
        return MemoryBlob(self.objects, name)
    def list_blobs(self, prefix=""):
        return [self.blob(key) for key in sorted(self.objects) if key.startswith(prefix)]


def make_record(day, selected=1000, stable=60):
    return {"day": day.strftime("%Y%m%d"), "rows": selected+100,
            "selected": selected, "counts": {
                "BILAT:RUS:UKR": stable,
                "DOMESTIC:AAA": selected-stable}}


def seed_files(folder):
    start = EXPECTED_SEED_FIRST
    records = [make_record(start + dt.timedelta(days=i)) for i in range(EXPECTED_SEED_DAYS)]
    seed_file = folder/"daily_aggregates.jsonl"
    seed_file.write_text("".join(json.dumps(r)+"\n" for r in records))
    manifest_file = folder/"manifest.json"
    manifest_file.write_text(json.dumps({
        "profile": SOURCE_PROFILE,
        "historical_start": str(EXPECTED_SEED_FIRST),
        "historical_end": "2026-11-07",
        "available_end": str(EXPECTED_SEED_LAST),
        "total_valid_days": EXPECTED_SEED_DAYS,
        "failed_days": []}))
    return seed_file, manifest_file


class GCSHistoryTests(unittest.TestCase):
    def test_122_day_seed_and_immutable_replay(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            seed_file, manifest_file = seed_files(folder)
            store = MemoryBucket()
            first = execute(store, "seed", folder/"seed", seed_file=str(seed_file),
                            seed_manifest=str(manifest_file), run_id="seed-1")
            self.assertEqual(first["status"], "complete")
            self.assertEqual(len(first["created_days"]), 122)
            self.assertEqual(first["latest_stored_date"], "2026-11-09")
            self.assertEqual(first["evaluated_days"], ["2026-11-09"])
            second = execute(store, "seed", folder/"seed2", seed_file=str(seed_file),
                             seed_manifest=str(manifest_file), run_id="seed-2")
            self.assertEqual(len(second["created_days"]), 0)
            self.assertEqual(len(second["previously_verified_days"]), 122)
            self.assertFalse(second["executive_alerts_approved"])

    def test_different_value_never_overwrites_existing_day(self):
        store = MemoryBucket()
        day = EXPECTED_SEED_LAST
        _, encoded = source_record(make_record(day))
        key = day_key(PREFIX, day)
        self.assertEqual(write_immutable(store, key, encoded), "created")
        self.assertEqual(write_immutable(store, key, encoded), "verified_existing")
        altered = make_record(day, stable=99)
        _, changed = source_record(altered)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            write_immutable(store, key, changed)

    def test_profile_and_object_name_are_verified(self):
        day = EXPECTED_SEED_FIRST
        _, content = source_record(make_record(day))
        self.assertEqual(restore_record(content, day)["day"], "20260711")
        incorrect = json.loads(content)
        incorrect["source_profile"] = "GDELT six-root"
        with self.assertRaisesRegex(ValueError, "profile"):
            restore_record(canonical(incorrect), day)
        with self.assertRaisesRegex(ValueError, "disagree"):
            restore_record(content, day + dt.timedelta(days=1))

    def test_missing_calendar_dates_are_prioritized_and_not_zero_filled(self):
        start = EXPECTED_SEED_FIRST
        existing = {start + dt.timedelta(days=i) for i in range(100) if i not in (71, 80)}
        target = start + dt.timedelta(days=101)
        selected, backlog = choose_missing_dates(existing, target, max_requests=2)
        self.assertEqual(selected, [target, target - dt.timedelta(days=1)])
        self.assertEqual(backlog, [start+dt.timedelta(days=80), start+dt.timedelta(days=71)])
        with self.assertRaisesRegex(ValueError, "At most 14"):
            choose_missing_dates(existing, target, max_requests=15)

    def test_seed_rejects_missing_day_or_mismatched_profile(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            file, manifest = seed_files(folder)
            lines = file.read_text().splitlines()
            file.write_text("\n".join(lines[:-1])+"\n")
            with self.assertRaisesRegex(ValueError, "Seed missing"):
                parse_seed(file, manifest)
            file.write_text("\n".join(lines)+"\n")
            obj = json.loads(manifest.read_text())
            obj["profile"] = "13/16/17/18/19/20"
            manifest.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "verified"):
                parse_seed(file, manifest)

    def test_prevent_unauthenticated_new_bucket_from_appearing_populated(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "No GCS seed"):
                execute(MemoryBucket(), "update", Path(d)/"out",
                        through=EXPECTED_SEED_LAST, run_id="update-empty")

    def test_partial_source_failure_creates_receipt_without_false_zero(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            bucket = MemoryBucket()
            seed, manifest = seed_files(folder)
            execute(bucket, "seed", folder/"seeded", seed_file=str(seed),
                    seed_manifest=str(manifest), run_id="seed-1")
            # A synthetic missing day *inside* the recent timeline is retried,
            # even when subsequent days already exist.
            missing = EXPECTED_SEED_LAST - dt.timedelta(days=2)
            del bucket.objects[day_key(PREFIX, missing)]
            def fail(day):
                raise ConnectionError("provider unavailable")
            result = execute(bucket, "update", folder/"update",
                             through=EXPECTED_SEED_LAST, fetcher=fail,
                             run_id="update-1")
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["created_days"], [])
            self.assertIn(missing.isoformat(), result["missing_last_120_days"])
            self.assertEqual(result["failed_downloads"][0]["status"], "provider_unavailable")
            self.assertTrue((folder/"update"/"manifest.json").exists())
            self.assertIn(f"{PREFIX}/runs/update-1/manifest.json", bucket.objects)


if __name__ == "__main__":
    unittest.main()
