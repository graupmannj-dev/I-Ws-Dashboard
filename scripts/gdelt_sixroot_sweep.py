#!/usr/bin/env python3
"""Bounded, resumable manual catch-up for validated GDELT six-root GCS v2.

Orchestrates *existing* immutable 14-archive chunks; never bypasses
four-root parity, source failures, provider uncertainty or GCS versioning.
No executive alerts are generated or changed.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.gdelt_gcs_history import PROJECT, dates_between, existing_dates, canonical
from scripts.gdelt_event_profile import PREFIX
from scripts.gdelt_six_root_gcs import execute, SEED_DATE, FOUR_PREFIX

MAX_BATCHES = 8
MAX_ARCHIVES_PER_BATCH = 14


def sweep(bucket, output, through, max_batches=MAX_BATCHES, run_id="local", fetcher=None):
    if not 1 <= max_batches <= MAX_BATCHES:
        raise ValueError("Sweep must use 1–8 separately audited 14-archive batches")
    if through < SEED_DATE:
        raise ValueError("Target is before six-root historical start")
    if through >= dt.datetime.now(dt.timezone.utc).date():
        raise ValueError("Target must be a completed UTC calendar day")
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    batch_reports=[]
    all_created=[]
    failures=[]
    for index in range(1,max_batches+1):
        b=execute(bucket, "update", root/f"batch-{index:02d}",
                  through=through, run_id=f"{run_id}-batch-{index:02d}",
                  batch_limit=MAX_ARCHIVES_PER_BATCH, fetcher=fetcher)
        batch_reports.append({
            "batch":index,
            "created_days":b["created_days"],
            "checked_parity":b["checked_parity"],
            "source_failures":b["source_failures"],
            "missing_v1_dependency":b["missing_v1_dependency"],
            "unattempted_backlog_count":len(b["deferred_days"]),
            "remaining_v2_calendar_days":len(b["missing_sixroot_days"]),
            "status":b["status"],
        })
        all_created.extend(b["created_days"])
        failures.extend(b["source_failures"])
        if b["status"]=="complete":
            break
        if not b["created_days"]:
            # A failed provider archive or missing v1 dependency must never
            # create a busy-loop of identical retries in the same job.
            break
    v1=existing_dates(bucket,FOUR_PREFIX)
    v2=existing_dates(bucket,PREFIX)
    wanted=dates_between(SEED_DATE,through)
    remaining=[d.isoformat() for d in wanted if d not in v2]
    missing_v1=[d.isoformat() for d in wanted if d not in v1]
    if len(set(all_created))!=len(all_created):
        raise ValueError("Repeated six-root day was created in sweep; fail closed")
    for report in batch_reports:
        if report["created_days"]!=report["checked_parity"]:
            raise ValueError("Six-root daily creation without exactly corresponding v1 parity receipt")
    status="complete" if not remaining else "partial"
    summary={
        "schema":"aiba.gdelt.sixroot-sweep.v1",
        "profile":"GDELT-v2 EventRootCode 13/16/17/18/19/20; immutable source-matched GCS",
        "mode":"bounded_sixroot_sweep",
        "project":PROJECT,
        "prefix":PREFIX,
        "through":through.isoformat(),
        "batch_limit":max_batches,
        "archives_per_batch_cap":MAX_ARCHIVES_PER_BATCH,
        "attempted_batches":len(batch_reports),
        "batch_reports":batch_reports,
        "total_new_days":len(all_created),
        "created_days":all_created,
        "remaining_sixroot_dates":remaining,
        "missing_fourroot_reference_dates":missing_v1,
        "provider_failures":failures,
        "total_required_dates":len(wanted),
        "total_existing_sixroot_in_target":len(wanted)-len(remaining),
        "status":status,
        "production_warning_integration":False,
        "approved_for_executive_alerts":False,
    }
    (root/"sweep_manifest.json").write_bytes(canonical(summary))
    # Each internal 14-day attempt is independently committed to GCS
    # by execute(). The sweep summary is a runner artifact, not a
    # competing update of any historical GCS object.
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",default=PROJECT)
    p.add_argument("--bucket",required=True)
    p.add_argument("--through",default=None,help="Last completed UTC day YYYY-MM-DD; default yesterday UTC")
    p.add_argument("--max-batches",type=int,default=MAX_BATCHES)
    p.add_argument("--run-id",default=os.environ.get("GITHUB_RUN_ID","local"))
    p.add_argument("--output",default="gdelt-sixroot-sweep-output")
    args=p.parse_args()
    if args.project!=PROJECT:
        p.error("Project mismatch; abort before GCS access")
    if not args.bucket or args.bucket.startswith("gs://") or any(x.isspace() for x in args.bucket):
        p.error("Bucket argument must be the plain private GCS bucket name")
    from google.cloud import storage
    bucket=storage.Client(project=args.project).bucket(args.bucket)
    bucket.reload()
    if not bucket.versioning_enabled:
        p.error("Bucket Object Versioning disabled; refusing to write")
    target=dt.date.fromisoformat(args.through) if args.through else (
        dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=1))
    receipt=sweep(bucket,args.output,target,max_batches=args.max_batches,
                  run_id=f"{args.run_id}-{os.getenv('GITHUB_RUN_ATTEMPT','1')}")
    print(json.dumps({
        "status":receipt["status"],"through":receipt["through"],
        "new_days":receipt["total_new_days"],
        "stored_dates":receipt["total_existing_sixroot_in_target"],
        "expected_dates":receipt["total_required_dates"],
        "missing_dates":receipt["remaining_sixroot_dates"],
        "missing_fourroot_reference_dates":receipt["missing_fourroot_reference_dates"],
        "failures":receipt["provider_failures"],
    },indent=2))
    if receipt["status"]!="complete":
        print("::warning::Six-root GCS remains incomplete; missing days preserved, no false zero filling.")


if __name__=="__main__":
    main()
