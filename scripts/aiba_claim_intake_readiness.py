#!/usr/bin/env python3
"""Read-only real-source intake readiness: counts, not article bodies or events."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from collections import Counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from behavioral_fusion import recently_observed
from behavioral_registry import when
from behavioral_event_resolution import is_event_reporting
from ops_pipeline import load_json

MAX_SOURCE_SCAN = 2000
ALLOWED_RIGHTS = {"public_domain", "licensed_for_internal_evaluation",
                  "permission_granted", "short_permitted_excerpt"}


def readiness(state):
    state = Path(state)
    registry = load_json(state / "latest" / "behavioral_registry.json", {}) or {}
    at = when(registry.get("generated_at"))
    if not at:
        raise ValueError("registry_asof_missing")
    recent, history = recently_observed(state, at)
    if len(recent) > MAX_SOURCE_SCAN:
        raise ValueError("source readiness scan exceeds bounded maximum")
    rows = [r for r in recent.values() if isinstance(r, dict)] if isinstance(recent, dict) else list(recent)
    reporting = [r for r in rows if is_event_reporting(r)]
    body = [r for r in reporting if isinstance(r.get("source_text"), str) and r["source_text"].strip()]
    ready = [r for r in body if (r.get("rights_basis") in ALLOWED_RIGHTS and
                                  r.get("story_lineage_id") and r.get("retrieved_at"))]
    missing_body = len(reporting) - len(body)
    by_family = Counter(str(r.get("source_family") or "unknown") for r in reporting)
    return {
        "schema": "aiba.report-intake-readiness-probe.v1",
        "status": "historical_read_only_availability_audit",
        "registry_asof": registry["generated_at"],
        "recent_unique_records": len(rows),
        "incident_report_like_records": len(reporting),
        "reporting_records_with_supplied_body": len(body),
        "reporting_records_missing_body": missing_body,
        "reporting_records_with_body_rights_lineage_and_retrieval_provenance": len(ready),
        "eligible_by_source_family": dict(sorted(by_family.items())),
        "history_files_examined": history.get("history_files_examined"),
        "claim_quality_measured": False,
        "rights_independently_verified": False,
        "licensed_text_exported": False,
        "automatic_alerts_created": 0,
        "limitations": [
            "This is only a bounded 72-hour observed-source inventory, not a worldwide event count.",
            "No full-text URL fetching or assumption of permission from public accessibility.",
            "Missing text is not evidence that no incident took place.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(readiness(args.state), indent=2))


if __name__ == "__main__":
    main()
