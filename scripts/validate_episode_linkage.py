#!/usr/bin/env python3
"""Fail-closed review of actor/dyad-level GDELT↔UCDP case link assertions.

This validates review *provenance and completeness*, not the factual
truth of a cited report. No auto promotion to AIBA executive alerts.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = {"episode_id","episode_date","ucdp_dyad_new_id","gdelt_case",
            "gdelt_asof_date","link_status","reviewer_1","reviewer_2",
            "primary_source_url","independent_source_url","decision","review_notes"}
DECISIONS={"accept","reject","defer"}


def host(url):
    if not url.startswith("https://"):
        return None
    value=urlparse(url)
    if value.username or value.password or value.port:
        return None
    return (value.hostname or "").lower().removeprefix("www.")


def validate(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f)
        if not REQUIRED.issubset(set(r.fieldnames or [])):
            raise ValueError("Adjudication file missing required review/provenance columns")
        completed=[];stats={"accept":0,"reject":0,"defer":0,"unreviewed":0}
        keys=set()
        for i,row in enumerate(r,2):
            marker=(row["episode_id"],row["gdelt_case"],row["gdelt_asof_date"])
            if marker in keys:
                raise ValueError(f"Duplicated episode/case/date review row on line {i}")
            keys.add(marker)
            day=dt.date.fromisoformat(row["episode_date"])
            asof=dt.date.fromisoformat(row["gdelt_asof_date"])
            if not 1 <= (day-asof).days <= 7:
                raise ValueError(f"Post-outcome or unbounded source lead in review line {i}")
            if row["link_status"] != "UNREVIEWED_NOT_EVIDENCE_OF_ACTOR_MATCH":
                raise ValueError("Source nomination status was modified; do not edit auto-generated evidence")
            decision=row["decision"].strip().lower()
            if not decision:
                if any(row[x].strip() for x in ("reviewer_1","reviewer_2","primary_source_url","independent_source_url")):
                    raise ValueError(f"Partially reviewed row requires a decision on line {i}")
                stats["unreviewed"]+=1
                continue
            if decision not in DECISIONS:
                raise ValueError(f"Invalid decision on line {i}")
            stats[decision]+=1
            if decision != "accept":
                continue
            rev1=row["reviewer_1"].strip()
            rev2=row["reviewer_2"].strip()
            if not rev1 or not rev2 or rev1.casefold()==rev2.casefold():
                raise ValueError(f"Accepted link lacks two distinct human reviewers on line {i}")
            u1=row["primary_source_url"].strip()
            u2=row["independent_source_url"].strip()
            if not host(u1) or not host(u2) or host(u1)==host(u2):
                raise ValueError(f"Accepted link lacks two independent HTTPS source domains on line {i}")
            if len(row["review_notes"].strip())<25:
                raise ValueError(f"Accepted actor-level link must explain its basis on line {i}")
            completed.append({
                "episode_id":row["episode_id"],
                "ucdp_dyad_new_id":row["ucdp_dyad_new_id"],
                "gdelt_case":row["gdelt_case"],
                "gdelt_asof_date":row["gdelt_asof_date"],
                "source_urls":[u1,u2],
                "reviewers":[rev1,rev2],
                "status":"accepted_two_human_reviews_not_prospective_forecast",
                "notes":row["review_notes"].strip(),
            })
    return completed,{"review_counts":stats,"accepted_links":len(completed),
                      "automatic_alert_promotion":False,
                      "limitations":"Review-form consistency checks do not fact-check the linked reports."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("reviewed_csv")
    p.add_argument("--out",default="episode-outcome-audit/validated-human-links.json")
    a=p.parse_args()
    links,receipt=validate(a.reviewed_csv)
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"links":links,"receipt":receipt},indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2))


if __name__=="__main__":
    main()
