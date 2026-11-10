"""Validate independently generated historical GDELT manifests without conflating schemas.

The April--July historical builder records failed_days as an integer,
while the later shadow monitor uses a list of failed UTC day records.
Both shapes are intentional; neither is evidence of missing source data
when they represent zero failed days.
"""
from __future__ import annotations
import json
from pathlib import Path

SOURCE_PROFILE = "GDELT-v1 EventRootCode 17/18/19/20, selected-event denominator"


def validate_manifests(early, later):
    expected_early = {
        "start": "2026-04-12",
        "end": "2026-07-10",
        "requested_days": 90,
        "complete_days": 90,
        "failed_days": 0,
        "failures": [],
    }
    for key, expected in expected_early.items():
        if type(early.get(key)) is not type(expected) or early.get(key) != expected:
            raise ValueError(f"April--July historical source manifest {key!r} mismatch: expected {expected!r}")

    expected_later = {
        "historical_start": "2026-07-11",
        "available_end": "2026-11-09",
        "total_valid_days": 122,
        "failed_days": [],
        "profile": SOURCE_PROFILE,
    }
    for key, expected in expected_later.items():
        if type(later.get(key)) is not type(expected) or later.get(key) != expected:
            raise ValueError(f"July--November shadow manifest {key!r} mismatch: expected {expected!r}")
    return {"prehistory_valid_days": 90, "forward_shadow_valid_days": 122,
            "joined_valid_days": 212, "failed_days": 0}


def check_files(prehistory_manifest, forward_manifest):
    early = json.loads(Path(prehistory_manifest).read_text(encoding="utf-8"))
    later = json.loads(Path(forward_manifest).read_text(encoding="utf-8"))
    result = validate_manifests(early, later)
    print(f"Historical manifest profiles validated: {result['joined_valid_days']} "
          "consecutive days; no failed archives.")
    return result
