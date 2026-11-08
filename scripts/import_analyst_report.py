#!/usr/bin/env python3
"""Import an OSINT analyst report from an authenticated GitHub Actions input."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.analyst_intake import MAX_BATCH, store_batch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--input", type=Path, help="Local JSON report path")
    parser.add_argument("--from-env", action="store_true", help="Read AIBA_REPORT_JSON")
    args = parser.parse_args()
    if bool(args.input) == bool(args.from_env):
        parser.error("Specify exactly one of --input or --from-env")
    if args.from_env:
        content = os.getenv("AIBA_REPORT_JSON", "")
    else:
        if args.input.stat().st_size > MAX_BATCH:
            parser.error("Report exceeds size limit")
        content = args.input.read_text(encoding="utf-8")
    if not content or len(content.encode("utf-8")) > MAX_BATCH:
        parser.error("Report missing or exceeds size limit")
    batch = json.loads(content)
    file = store_batch(args.state, batch)
    print("Validated OSINT report saved to " + str(file))
    print("Assessment status: unreviewed; no automatic severity change")


if __name__ == "__main__":
    main()
