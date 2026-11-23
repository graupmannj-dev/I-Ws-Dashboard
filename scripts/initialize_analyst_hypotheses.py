"""One-time analyst hypothesis initialization from CAIRN's retained public archive.

Run only in the owner-approved hypothesis intake PR workflow. A completed
backfill is immutable across normal CAIRN collection/publishing cycles.
Semantic candidate scores are not independent corroboration or signed evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dashboard.semantic_ach import ask_model, retrieve, compact

SCHEMA = "cairn.hypothesis-reviews.v1"
MAX_CANDIDATES = 24
MAX_SCAN = 24000

def valid_url(url):
    if not isinstance(url,str) or len(url)>1800:
        return False
    try:
        p=urlsplit(url)
        return p.scheme=="https" and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False

def source_id(record):
    return compact(record.get("id"),110) or hashlib.sha256(record["source_url"].encode()).hexdigest()[:20]

def candidate_packet(statement, case_id, archive):
    """Collect distinct case-linked information roots; never infer direction."""
    if archive.get("schema")!="aiba.family-archive.v1" or not isinstance(archive.get("records"),list):
        return [],{"status":"archive_unavailable","scanned":0,"matched_roots":0,"partial":True}
    try:
        from dashboard.hypothesis_auto_review import _match_case
    except ModuleNotFoundError:
        from hypothesis_auto_review import _match_case
    original=archive["records"]
    seen=set()
    matched=[]
    for row in original[:MAX_SCAN]:
        if not isinstance(row,dict) or not valid_url(row.get("source_url")):
            continue
        if not _match_case(case_id,row):
            continue
        root=compact(row.get("information_root"),200) or row["source_url"]
        identity=(compact(row.get("collection_mode"),70),root)
        if identity in seen:
            continue
        seen.add(identity)
        url=row["source_url"]
        sid=source_id(row)
        matched.append({"evidence_key":"archive:"+hashlib.sha256(
            (str(case_id)+"\x1f"+str(identity)).encode()).hexdigest()[:24],
            "family_title":compact(row.get("title"),240),
            "family_mechanism":compact(row.get("source_family") or row.get("collection_mode"),100),
            "source_health":"historical_source_current_health_not_established",
            "sources":[{"url":url,"title":compact(row.get("title"),240),
                "provider":compact(row.get("provider"),80),
                "first_observed_at":compact(row.get("first_observed_at"),45),
                "record_id":sid}],"reviewed_direction":"not_assessed"})
    packet={"hypotheses":[statement],"evidence_families":matched}
    shortlist=retrieve(packet,limit=MAX_CANDIDATES)
    # Archive can be truncated by its own retention rules; no full-world
    # observation guarantee even if the scan completed.
    partial=(len(original)>MAX_SCAN or len(matched)>len(shortlist) or
             bool(archive.get("public_snapshot_truncated")) or
             bool(archive.get("records_truncated")))
    info={"status":"candidate_shortlist","scanned":min(len(original),MAX_SCAN),
          "matched_roots":len(matched),"selected_roots":len(shortlist),
          "partial":partial,"archive_snapshot_truncated":bool(
              archive.get("public_snapshot_truncated"))}
    return shortlist,info

def initialize(config,archive,*,api_key=None,model=None,clock=None,runner=ask_model):
    if config.get("schema")!=SCHEMA:
        raise ValueError("Unsupported configuration")
    changed=0
    stamp=(clock or dt.datetime.now(dt.timezone.utc)).isoformat().replace("+00:00","Z")
    for hypothesis in config.get("analyst_hypotheses",[]):
        state=hypothesis.get("initial_backfill",{})
        if state.get("status")!="pending":
            continue
        statement=hypothesis["statement"]
        refs,inventory=candidate_packet(statement,hypothesis["case_id"],archive)
        limitation=[]
        if inventory["status"]=="archive_unavailable":
            limitation.append("Retained source archive unavailable for initial backfill")
        if inventory["partial"]:
            limitation.append("Initial review covers only a bounded retained public-source sample")
        if inventory["status"]!="archive_unavailable":
            limitation.append("Sensor coverage for the hypothesis geography and timeframe is not verified")
        if not refs:
            limitation.append("No source-linked case evidence was retrieved; absence is not contradictory evidence")
        if not api_key or not model:
            limitation.append("Natural-language interpretation is not configured; initial directional evaluation is pending")
        # Missing model is explicit, never a fabricated signed ACH review.
        state.update({"status":"initial_review_complete" if api_key and model and refs else
                        "interpretation_pending" if refs else "archive_incomplete",
                      "initialized_at":stamp,"source_inventory":inventory,
                      "evaluated_source_ids":[source.get("record_id") for f in refs
                          for source in f["sources"] if source.get("record_id")],
                      "source_references":refs,"evaluations":[],
                      "interpretation":None,"limitations":limitation})
        if api_key and model and refs:
            try:
                response=runner({"case_id":hypothesis["case_id"],
                   "hypotheses":[statement],"evidence_families":refs},api_key,model)
                state["evaluations"]=response["evaluations"]
                state["interpretation"]=response["interpretations"][0]
            except (ValueError,KeyError,IndexError,TypeError,TimeoutError,OSError) as exc:
                state["status"]="interpretation_failed"
                state["limitations"].append("AI interpretation failed validation: "+type(exc).__name__)
        changed+=1
    return changed

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="data/hypothesis_reviews.json")
    p.add_argument("--archive",default="ops-state/observations/latest/family_archive.json")
    args=p.parse_args()
    path=Path(args.config)
    config=json.loads(path.read_text())
    archive=json.loads(Path(args.archive).read_text()) if Path(args.archive).exists() else {}
    changed=initialize(config,archive,api_key=os.getenv("OPENAI_API_KEY"),
                      model=os.getenv("CAIRN_SEMANTIC_MODEL"))
    if changed: path.write_text(json.dumps(config,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"initial_backfills":changed,
                      "reviewed_directions_created":0}))

if __name__=="__main__":
    main()
