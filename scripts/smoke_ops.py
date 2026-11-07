#!/usr/bin/env python3
"""Summarize real PR smoke collection; explicitly fail if all public feeds failed."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

def check(state):
    names = ("markets", "official", "commercial")
    report = []
    ok = 0
    for name in names:
        path = Path(state) / "health" / (name + ".json")
        if not path.exists():
            report.append((name, "not_run", 0, 0, 0))
            continue
        info = json.loads(path.read_text())
        good = info.get("source_queries_ok", 0)
        tries = info.get("source_queries_attempted", 0)
        count = info.get("record_count", 0)
        if good:
            ok += 1
        report.append((name, info.get("status"), good, tries, count))
    lines = ["## AIBA public-source PR smoke test", "",
             "| Feed | Status | Successful queries | Records |",
             "|---|---|---:|---:|"]
    lines += [f"| {name} | {status} | {good}/{attempts} | {count} |"
              for name, status, good, attempts, count in report]
    lines.append("")
    lines.append("PR-only live network probes. No publication, no contract calibration, no war prediction.")
    summary = "\n".join(lines) + "\n"
    print(summary)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as file:
            file.write(summary)
    # Require at least one working external family to prevent 'all green' on all-failed calls.
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(check(sys.argv[1]))
