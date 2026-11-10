"""Six-root source compatibility, future-data guards and GCS migration QA."""
import datetime as dt
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.gdelt_event_profile import (
    SCHEMA, PROFILE, PREFIX, classify_actors, crosscheck_v1,
    four_root_projection, parse_archive, validate
)
from scripts.gdelt_gcs_history import (
    PREFIX as FOUR_PREFIX, canonical, day_key, source_record
)
from scripts.gdelt_six_root_gcs import eligible_dates, execute


DAY = dt.date(2026, 7, 11)


def archive(day=DAY):
    rows = []
    for code, a, b in [
        ("17", "RUS", "UKR"), ("13", "RUS", "UKR"),
        ("16", "RUS", "RUS"), ("20", "RUS", "RUS"),
        ("18", "", "UKR"), ("13", "RUS", ""),
        ("16", "USA", "PHL"), ("22", "USA", "PHL"),
    ]:
        fields = [""] * 57
        fields[0] = str(10000+len(rows))
        fields[1] = day.strftime("%Y%m%d")
        fields[7], fields[17] = a, b
        fields[26], fields[27], fields[28], fields[29] = code, code, code, "4"
        rows.append("\t".join(fields)+"\n")
    binary=io.BytesIO()
    with zipfile.ZipFile(binary, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(day.strftime("%Y%m%d")+".export.CSV", "".join(rows).encode("utf-8"))
    return binary.getvalue()


class Blob:
    def __init__(self, store, name):
        self.store, self.name = store, name
    def exists(self):
        return self.name in self.store
    def download_as_bytes(self):
        return self.store[self.name]
    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        assert if_generation_match == 0
        if self.exists():
            raise AssertionError("Unconditional overwrite attempted")
        self.store[self.name] = data


class Bucket:
    def __init__(self):
        self.store = {}
    def blob(self, name):
        return Blob(self.store, name)
    def list_blobs(self, prefix=""):
        return [Blob(self.store, key) for key in self.store if key.startswith(prefix)]


def baseline_record(day=DAY):
    return {"day": day.strftime("%Y%m%d"), "rows": 8, "selected": 3,
            "counts": {"BILAT:RUS:UKR": 1, "DOMESTIC:RUS": 1, "DOMESTIC:UKR": 1}}


def add_v1(store, day=DAY):
    _, payload=source_record(baseline_record(day))
    store.store[day_key(FOUR_PREFIX, day)] = payload


class ProfileParityTests(unittest.TestCase):
    def test_all_root_denominator_and_four_root_projection(self):
        payload=archive()
        rec=parse_archive(payload, "20260711")
        self.assertEqual(rec["rows"], 8)
        self.assertEqual(rec["selected"], 7)  # counts unmappable six-root observations
        self.assertEqual(rec["mapped"], 5)
        self.assertEqual(rec["unmapped"], 2)
        self.assertEqual(rec["counts"]["BILAT:RUS:UKR"], 2)
        self.assertTrue(crosscheck_v1(rec, baseline_record()))
        self.assertEqual(four_root_projection(rec), baseline_record())
        self.assertEqual(validate(rec, DAY), DAY)

    def test_malformed_archive_must_fail_even_if_other_rows_valid(self):
        p=archive()
        with self.assertRaisesRegex(ValueError, "member"):
            parse_archive(p, "20260712")
        with self.assertRaises(ValueError):
            parse_archive(b"bad ZIP", "20260711")

    def test_parity_drift_fails_closed(self):
        r=parse_archive(archive(), "20260711")
        v1=baseline_record()
        v1["selected"]=4
        with self.assertRaisesRegex(ValueError, "parity"):
            crosscheck_v1(r, v1)

    def test_production_ingestion_matches_sixroot_aggregate(self):
        from aiba_v4 import ingest
        day=DAY
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/(day.strftime("%Y%m%d")+".export.CSV.zip")
            p.write_bytes(archive(day))
            cases,totals,roots,available,samples=ingest(Path(d))
            rec=parse_archive(p.read_bytes(), day.strftime("%Y%m%d"))
            self.assertEqual(totals[day], rec["selected"])
            for case, amount in rec["counts"].items():
                kind, *parts=case.split(":")
                key=(kind,tuple(parts))
                self.assertEqual(cases[(day,key)], amount)

    def test_historical_migration_and_repeat_are_safe(self):
        bucket=Bucket()
        add_v1(bucket)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            first=execute(bucket,"backfill",root/"one",start=DAY,end=DAY,
                          run_id="mig1",fetcher=lambda d: archive(d))
            self.assertEqual(first["created_days"],[DAY.isoformat()])
            self.assertEqual(first["checked_parity"],[DAY.isoformat()])
            self.assertEqual(first["eligible_evaluations"],[])
            self.assertFalse(first["executive_eligible"])
            second=execute(bucket,"backfill",root/"two",start=DAY,end=DAY,
                           run_id="mig2",fetcher=lambda d: (_ for _ in ()).throw(AssertionError("no re-fetch")))
            self.assertEqual(second["created_days"],[])
            self.assertIn(f"{PREFIX}/daily/20260711.json", bucket.store)

    def test_backfill_blocks_unverified_four_root_dependencies(self):
        bucket=Bucket()
        add_v1(bucket, DAY+dt.timedelta(days=1))
        with tempfile.TemporaryDirectory() as d:
            m=execute(bucket,"backfill",Path(d),start=DAY,end=DAY+dt.timedelta(days=1),
                      run_id="mig3",fetcher=lambda day: archive(day))
            self.assertEqual(m["missing_v1_dependency"],[DAY.isoformat()])
            self.assertEqual(m["status"], "partial")

    def test_batch_bounds_and_update_priority(self):
        existing={DAY}
        four=set(DAY+dt.timedelta(days=i) for i in range(23))
        selected,blocked,deferred,target=eligible_dates(
            None, "update",None,DAY+dt.timedelta(days=22),existing,four,max_batch=3)
        self.assertEqual(selected[0], DAY+dt.timedelta(days=22))
        self.assertEqual(selected[1:], [DAY+dt.timedelta(days=1),DAY+dt.timedelta(days=2)])
        self.assertTrue(deferred)
        with self.assertRaisesRegex(ValueError,"1–14"):
            eligible_dates(None,"backfill",DAY,DAY+dt.timedelta(days=14),set(),four)

    def test_profile_classification_same_actor_domestic_only_for_17_through_20(self):
        self.assertIsNone(classify_actors("13","RUS","RUS"))
        self.assertEqual(classify_actors("18","RUS","RUS"),("DOMESTIC",("RUS",)))
        self.assertEqual(classify_actors("13","RUS","UKR"),("BILAT",("RUS","UKR")))


if __name__=="__main__":
    unittest.main()
