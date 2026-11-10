"""Source-reference pinning, immutable early GCS v2 and parity-failure tests."""
import copy
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.gdelt_event_profile import PREFIX
from scripts.gdelt_sixroot_prehistory import (
    PRE_START, PRE_END, dates, load_reference, migrate, REF_PREFIX
)


class Blob:
    def __init__(self, bucket, name):
        self.bucket,self.name=bucket,name
    def exists(self):
        return self.name in self.bucket.store
    def download_as_bytes(self):
        return self.bucket.store[self.name]
    def upload_from_string(self,data,content_type=None,if_generation_match=None):
        assert if_generation_match==0
        if self.exists():
            raise AssertionError("Immutable GCS object overwritten")
        self.bucket.store[self.name]=data


class Bucket:
    def __init__(self):
        self.store={}
    def blob(self,name):
        return Blob(self,name)
    def list_blobs(self,prefix=""):
        return [Blob(self,k) for k in self.store if k.startswith(prefix)]


def archive(day):
    import io,zipfile
    lines=[]
    for idx,(root,a,b) in enumerate([
        ("17","RUS","UKR"),("13","RUS","UKR"),
        ("16","RUS","RUS"),("20","RUS","RUS"),
        ("18","","UKR"),("13","RUS",""),
        ("16","USA","PHL"),("22","USA","PHL")
    ]):
        values=[""]*57
        values[0]=str(20000+idx);values[1]=day.strftime("%Y%m%d")
        values[7]=a;values[17]=b
        values[26:30]=[root,root,root,"4"]
        lines.append("\t".join(values)+"\n")
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{day:%Y%m%d}.export.CSV","".join(lines).encode("utf-8"))
    return buf.getvalue()


def reference(tmp):
    path=Path(tmp)
    history=path/"daily.jsonl"
    entries=[]
    for day in dates():
        entries.append(json.dumps({
            "day":day.strftime("%Y%m%d"),"rows":8,"selected":3,
            "counts":{"BILAT:RUS:UKR":1,"DOMESTIC:RUS":1,"DOMESTIC:UKR":1}
        },sort_keys=True))
    history.write_text("\n".join(entries)+"\n")
    manifest=path/"manifest.json"
    manifest.write_text(json.dumps({
        "start":"2026-04-12","end":"2026-07-10",
        "requested_days":90,"complete_days":90,"failed_days":0,"failures":[]
    }))
    sha=hashlib.sha256(history.read_bytes()).hexdigest()
    verified, meta=load_reference(history,manifest,expected_sha=sha)
    return verified,meta,history,manifest


class PrehistoryTests(unittest.TestCase):
    def test_reference_stitches_exact_90_day_source_without_zero_fill(self):
        with tempfile.TemporaryDirectory() as d:
            records,meta,h,m=reference(d)
            self.assertEqual(len(records),90)
            self.assertEqual(min(records),PRE_START)
            self.assertEqual(max(records),PRE_END)
            with self.assertRaisesRegex(ValueError,"SHA256"):
                load_reference(h,m,expected_sha="0"*64)
            h.write_text("\n".join(h.read_text().splitlines()[:-1])+"\n")
            with self.assertRaisesRegex(ValueError,"SHA256"):
                load_reference(h,m,expected_sha="0"*64)

    def test_bounded_migration_then_idempotent_complete_resume(self):
        with tempfile.TemporaryDirectory() as d:
            records,meta,h,m=reference(d)
            bucket=Bucket()
            a=migrate(bucket,Path(d)/"first",records,meta,max_batches=1,run_id="pre1",
                      fetcher=archive)
            self.assertEqual(a["status"],"partial")
            self.assertEqual(a["persisted_days"],14)
            self.assertEqual(len(a["remaining_dates"]),76)
            self.assertIn(f"{REF_PREFIX}/daily.jsonl",bucket.store)
            self.assertIn(f"{REF_PREFIX}/manifest.json",bucket.store)
            b=migrate(bucket,Path(d)/"second",records,meta,max_batches=8,run_id="pre2",
                      fetcher=archive)
            self.assertEqual(b["status"],"complete")
            self.assertEqual(b["persisted_days"],90)
            self.assertEqual(b["remaining_dates"],[])
            c=migrate(bucket,Path(d)/"retry",records,meta,max_batches=8,run_id="pre3",
                      fetcher=lambda day: (_ for _ in ()).throw(AssertionError("No source fetch when complete")))
            self.assertEqual(c["status"],"complete")
            self.assertEqual(c["batches"],[])
            self.assertIn(f"{PREFIX}/daily/20260412.json",bucket.store)

    def test_parity_conflict_prevents_corrupt_daily_record_and_saves_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            records,meta,h,m=reference(d)
            records=copy.deepcopy(records)
            records[PRE_START]["counts"]["BILAT:RUS:UKR"]=2
            records[PRE_START]["selected"]=4
            bucket=Bucket()
            with self.assertRaisesRegex(ValueError,"projection conflict"):
                migrate(bucket,Path(d)/"bad",records,meta,max_batches=1,
                        run_id="prebad",fetcher=archive)
            self.assertNotIn(f"{PREFIX}/daily/20260412.json",bucket.store)
            report=json.loads((Path(d)/"bad"/"prehistory_manifest.json").read_text())
            self.assertTrue(report["parity_or_validation_failures"])

    def test_cap_and_empty_prebaseline_must_fail(self):
        with tempfile.TemporaryDirectory() as d:
            records,meta,h,m=reference(d)
            with self.assertRaisesRegex(ValueError,"1–8"):
                migrate(Bucket(),Path(d),records,meta,max_batches=9)
            with self.assertRaisesRegex(ValueError,"exactly"):
                migrate(Bucket(),Path(d),{},meta,max_batches=1)


if __name__=="__main__":
    unittest.main()
