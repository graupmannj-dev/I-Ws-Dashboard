#!/usr/bin/env python3
"""Durable, independently source-verified 90-day GDELT six-root prehistory.

GCS 17–20 v1 starts July 11, so *pre-July* parity is verified against
the already-inspected 90-day original four-root GitHub Actions artifact
(not an invented or absent GCS v1 object). Everything is append-only
in the SAME six-root v2 daily namespace, with a preserved source receipt.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.gdelt_event_profile import PREFIX, PROFILE, SCHEMA, crosscheck_v1, parse_archive
from scripts.gdelt_gcs_history import PROJECT,canonical,existing_dates,write_immutable
from scripts.gdelt_six_root_gcs import daily_key,fetch_source,stored_v2
from scripts.merge_gdelt_history import validate_record

PRE_START = dt.date(2026, 4, 12)
PRE_END = dt.date(2026, 7, 10)
EXPECTED_SHA256 = "30c9a5e8e3517acecf877c9f397236016a564e36877035c43a91f340181fef5c"
MAX_BATCHES=8
ARCHIVES_PER_BATCH=14
REF_PREFIX=f"{PREFIX}/references/verified-20260412-20260710"


def dates():
    return [PRE_START+dt.timedelta(days=n) for n in range((PRE_END-PRE_START).days+1)]


def load_reference(history, manifest, expected_sha=EXPECTED_SHA256):
    """Pin original immutable retrospective artifact and validate exact 90 days."""
    history_path, manifest_path=Path(history),Path(manifest)
    raw=history_path.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected_sha:
        raise ValueError("Verified April–July four-root reference SHA256 mismatch")
    meta=json.loads(manifest_path.read_text(encoding="utf-8"))
    expected={"start":"2026-04-12","end":"2026-07-10",
              "requested_days":90,"complete_days":90,"failed_days":0}
    if any(meta.get(k)!=v for k,v in expected.items()) or meta.get("failures"):
        raise ValueError("Incorrect or incomplete 90-day reference manifest")
    ref={}
    for n,line in enumerate(raw.splitlines(),1):
        if not line:
            raise ValueError(f"Blank reference record {n}")
        record=json.loads(line)
        day=validate_record(record)
        if day in ref:
            raise ValueError(f"Duplicate reference day {day}")
        ref[day]=record
    if list(sorted(ref))!=dates():
        raise ValueError("Reference has a missing or out-of-range UTC date")
    return ref,{"sha256":digest,"manifest":meta,"bytes":raw,"manifest_bytes":manifest_path.read_bytes()}


def migrate(bucket,output,reference,reference_metadata,max_batches=MAX_BATCHES,
            run_id="manual",fetcher=None):
    if not 1 <= max_batches <= MAX_BATCHES:
        raise ValueError("Prehistory migration limited to 1–8 batches of 14 UTC dates")
    if len(reference)!=90 or list(sorted(reference))!=dates():
        raise ValueError("Prehistory must be exactly April 12–July 10, 90 complete days")
    # Pin the reference itself to immutable, versioned GCS. Later
    # audits need not depend on an expiring Actions artifact.
    write_immutable(bucket,f"{REF_PREFIX}/daily.jsonl",reference_metadata["bytes"])
    write_immutable(bucket,f"{REF_PREFIX}/manifest.json",reference_metadata["manifest_bytes"])
    existing=existing_dates(bucket,PREFIX)
    all_dates=dates()
    # Verify previously created early records against the archived
    # source on every rerun; successful prior writes are not assumed.
    for d in all_dates:
        if d in existing:
            stored=stored_v2(bucket,existing,d)
            crosscheck_v1(stored,reference[d])
    missing=[d for d in all_dates if d not in existing]
    limit=ARCHIVES_PER_BATCH*max_batches
    selected=missing[:limit]
    downloads=fetcher or fetch_source
    results=[]
    source_failures=[]
    parity_failures=[]
    for batch_index in range(max_batches):
        segment=selected[batch_index*ARCHIVES_PER_BATCH:(batch_index+1)*ARCHIVES_PER_BATCH]
        if not segment:
            break
        successful=[]
        for d in segment:
            try:
                archive=downloads(d)
            except (OSError,TimeoutError,RuntimeError) as exc:
                source_failures.append({"date":d.isoformat(),"reason":"provider_unavailable",
                                        "error":type(exc).__name__,"message":str(exc)[:200]})
                continue
            try:
                record=parse_archive(archive,d.strftime("%Y%m%d"))
            except (ValueError,TypeError,KeyError) as exc:
                parity_failures.append({"date":d.isoformat(),"reason":"invalid_source_archive",
                                        "error":type(exc).__name__,"message":str(exc)[:200]})
                break
            try:
                crosscheck_v1(record,reference[d])
            except ValueError as exc:
                parity_failures.append({"date":d.isoformat(),"reason":"historical_source_drift",
                                        "message":str(exc)[:200]})
                break
            envelope=canonical({"schema":SCHEMA,"profile":PROFILE,"record":record})
            write_immutable(bucket,daily_key(PREFIX,d),envelope)
            successful.append(d.isoformat())
        results.append({"batch":batch_index+1,"created_days":successful,
                        "attempted_days":[d.isoformat() for d in segment]})
        if parity_failures:
            break
    updated=existing_dates(bucket,PREFIX)
    remaining=[d.isoformat() for d in all_dates if d not in updated]
    completed=[d.isoformat() for d in all_dates if d in updated]
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    receipt={
        "schema":"aiba.gdelt.sixroot-prehistory.v1",
        "project":PROJECT,"prefix":PREFIX,"status":("complete" if not remaining else "partial"),
        "verified_fourroot_reference_sha256":reference_metadata["sha256"],
        "reference_gcs_prefix":REF_PREFIX,
        "reference_artifact":"github-actions/42912512785/historical-prewindow",
        "first_utc_date":PRE_START.isoformat(),
        "last_utc_date":PRE_END.isoformat(),
        "expected_days":90,"persisted_days":len(completed),
        "remaining_dates":remaining,
        "batches":results,
        "provider_failures":source_failures,"parity_or_validation_failures":parity_failures,
        "production_warning_change":False,"executive_eligible":False,
    }
    payload=canonical(receipt)
    (out/"prehistory_manifest.json").write_bytes(payload)
    write_immutable(bucket,f"{PREFIX}/runs/{run_id}/prehistory_manifest.json",payload)
    if parity_failures:
        raise ValueError("Six-root prehistory source/17-20 projection conflict; review audited manifest before retrying")
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",default=PROJECT)
    p.add_argument("--bucket",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--reference-manifest",required=True)
    p.add_argument("--max-batches",type=int,default=MAX_BATCHES)
    p.add_argument("--output",default="gdelt-sixroot-audit")
    p.add_argument("--run-id",default=os.environ.get("GITHUB_RUN_ID","manual"))
    a=p.parse_args()
    if a.project!=PROJECT or not a.bucket or a.bucket.startswith("gs://") or any(x.isspace() for x in a.bucket):
        p.error("Unapproved GCP project or malformed bucket name")
    ref,metadata=load_reference(a.reference,a.reference_manifest)
    from google.cloud import storage
    bucket=storage.Client(project=a.project).bucket(a.bucket)
    bucket.reload()
    if not bucket.versioning_enabled:
        p.error("Bucket Object Versioning disabled; cannot persist durable prehistory")
    report=migrate(bucket,a.output,ref,metadata,max_batches=a.max_batches,
                   run_id=f"{a.run_id}-{os.getenv('GITHUB_RUN_ATTEMPT','1')}")
    print(json.dumps({k:v for k,v in report.items() if k!="batches"},indent=2))
    if report["status"]!="complete":
        print("::warning::GDELT six-root prehistory incomplete; no synthetic dates or outcomes.")


if __name__=="__main__":
    main()
