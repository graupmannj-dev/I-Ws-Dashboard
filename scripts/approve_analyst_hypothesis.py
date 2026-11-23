#!/usr/bin/env python3
"""Owner-approved public issue -> persistent first-class ACH hypothesis.

Approval creates a durable case-linked registry record; the one-time backfill
is a separate idempotent initialization stage before the review PR is opened.
"""
import hashlib
import json
import os
import re
from pathlib import Path
OWNER_ID = 320673296
SCHEMA = "cairn.hypothesis-reviews.v1"
BODY = re.compile(r"\ACase ID: ([a-zA-Z0-9_-]{2,100})\s+Proposed hypothesis:\s+(.+?)(?:\s+Analyst review required:.*)?\Z", re.S)

def approve(event, config):
    issue = event.get("issue") or {}
    sender = event.get("sender") or {}
    if event.get("action") != "labeled" or (event.get("label") or {}).get("name") != "cairn-hypothesis-approved":
        raise ValueError("Approval label required")
    if sender.get("id") != OWNER_ID or issue.get("user", {}).get("id") != OWNER_ID:
        raise ValueError("Owner submission and approval required")
    if issue.get("pull_request") or issue.get("state") != "open":
        raise ValueError("Requires open issue")
    match = BODY.fullmatch((issue.get("body") or "").strip())
    if not match:
        raise ValueError("Missing case ID or proposed hypothesis")
    case_id, proposal = match.groups()
    known = json.loads(Path("data/verified_hotspots.json").read_text())
    if not isinstance(known, list) or case_id not in {d.get("id") for d in known if isinstance(d, dict)}:
        raise ValueError("Unknown case ID; proposals must match a standing case")
    proposal = " ".join(proposal.strip().split())
    if not 20 <= len(proposal) <= 300 or any(ord(c)<32 for c in proposal):
        raise ValueError("Proposal must be 20-300 printable characters")
    if config.get("schema") != SCHEMA:
        raise ValueError("Invalid existing review schema")
    registered = config.setdefault("analyst_hypotheses", [])
    if not isinstance(registered, list) or len(registered)>120:
        raise ValueError("Invalid analyst registry")
    found = next((h for h in registered if h.get("case_id")==case_id and h.get("statement")==proposal), None)
    if found:
        return False
    # The current ACH presentation has three alternatives per case, including
    # the dossier alternative. Do not silently accept an invisible hypothesis.
    extras = config.get("alternative_hypotheses", {}).get(case_id, [])
    case = next(d for d in known if d.get("id")==case_id)
    base = bool(case.get("alternatives"))
    num = len({h["statement"] for h in registered if h.get("case_id")==case_id})
    if num + len(extras) + int(base) >= 3:
        raise ValueError("ACH has three alternatives; cannot silently omit another")
    ident = "analyst-" + hashlib.sha256((case_id+"\x1f"+proposal).encode("utf-8")).hexdigest()[:16]
    record = {
        "id": ident, "case_id":case_id, "statement": proposal,
        "origin":"analyst", "source_issue": issue.get("number"),
        "activated_at": issue.get("created_at") or None,
        "active": True,
        "initial_backfill": {
            "status":"pending", "evaluated_source_ids":[],
            "evaluations":[], "limitations":["Initial historical evidence review has not completed"]},
    }
    registered.append(record)
    return True

def main():
    event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    path=Path("data/hypothesis_reviews.json")
    config=json.loads(path.read_text())
    if approve(event,config):
        path.write_text(json.dumps(config,indent=2,ensure_ascii=False)+"\n")
        print("Registered first-class analyst hypothesis, awaiting one-time initialization")
    else:
        print("Duplicate proposal")

if __name__=="__main__":
    main()
