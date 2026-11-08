#!/usr/bin/env python3
"""Publish a validated snapshot of AIBA's uncalibrated friction briefing.

The browser may later refresh from the public evidence branch. This static
snapshot always exists as fallback; a missing or failed live feed is visible.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from friction_pipeline import event_time, read_json, utcnow, write_json

def publish(state, site, now=None):
    now = now or utcnow()
    site = Path(site)
    site.mkdir(parents=True, exist_ok=True)
    source = read_json(Path(state) / "latest" / "friction_briefs.json", {}) or {}
    stamp = event_time(source.get("generated_at"))
    if source.get("schema_version") == 1 and isinstance(source.get("cases"), list):
        output = dict(source)
        output["site_briefing_age_hours"] = (round((now - stamp).total_seconds() / 3600, 2)
                                             if stamp else None)
        if not stamp or not dt.timedelta(0) <= now - stamp <= dt.timedelta(hours=3):
            output["fresh_snapshot"] = False
            output["executive_summary"] = (
                "Structural-friction briefing is stale. Previous assessments are historical context, not current warning.")
    else:
        output = {
            "schema_version": 1, "generated_at": None, "fresh_snapshot": False,
            "shadow_mode": True, "cases": [], "unlocated_leads": [], "health": {},
            "coverage_gaps": ["ioda", "nga", "amsa"], "uncalibrated_review_count": 0,
            "executive_summary": "Structural-friction feeds not yet collected. No assessment is implied.",
        }
    write_json(site / "friction_briefs.json", output)
    return output

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", required=True, type=Path)
    p.add_argument("--site", required=True, type=Path)
    args = p.parse_args()
    result = publish(args.state, args.site)
    print(json.dumps({"friction_published_at": result.get("generated_at"),
                      "cases": len(result.get("cases", [])),
                      "fresh_snapshot": result["fresh_snapshot"]}))

if __name__ == "__main__":
    main()
