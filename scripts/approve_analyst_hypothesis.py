#!/usr/bin/env python3
"""Owner-approved public GitHub issue -> proposed ACH alternative."""
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
    proposal = proposal.strip()
    if not 20 <= len(proposal) <= 300 or any(ord(c)<32 and c not in "\n\t" for c in proposal):
        raise ValueError("Proposal must be 20-300 printable characters")
    if config.get("schema") != SCHEMA:
        raise ValueError("Invalid existing review schema")
    alternatives = config.setdefault("alternative_hypotheses", {})
    if not isinstance(alternatives, dict):
        raise ValueError("Invalid alternatives map")
    current = alternatives.setdefault(case_id, [])
    if not isinstance(current, list) or len(current)>3:
        raise ValueError("Invalid alternative list")
    if proposal in current:
        return False
    if len(current)>=3:
        raise ValueError("Maximum three analyst alternatives per case")
    current.append(proposal)
    return True

def main():
    event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    path=Path("data/hypothesis_reviews.json")
    config=json.loads(path.read_text())
    if approve(event,config):
        path.write_text(json.dumps(config,indent=2,ensure_ascii=False)+"\n")
        print("Approved proposal staged for PR")
    else:
        print("Duplicate proposal")
if __name__=="__main__":
    main()
