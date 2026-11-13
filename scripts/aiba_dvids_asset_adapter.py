#!/usr/bin/env python3
"""DVIDS source-asset API export -> locally permission-attested article input.

Uses DVIDS documented /asset results, not generic HTML scraping. A news
description is an original publisher text *candidate*, not an independently
verified incident. No network is accessed in this parser; API access requires
a separately registered DVIDS key and explicit fetch invocation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from scripts.aiba_source_text_intake import ingest

MAX_ASSETS = 250


def utc(value):
    if not isinstance(value, str):
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z") if d.tzinfo else None


def asset_to_input(obj, approved, retrieved_at):
    """Requires explicit asset-specific confirmation by an operator."""
    if not isinstance(obj, dict):
        return None, "invalid_asset"
    if obj.get("type") != "news":
        return None, "not_news"
    ident = obj.get("id")
    if not isinstance(ident, str) or not re.fullmatch(r"news:\d+", ident):
        return None, "invalid_asset_id"
    if ident not in approved:
        return None, "rights_not_approved"
    description = obj.get("description")
    if not isinstance(description, str) or len(description.strip()) < 40:
        return None, "full_description_missing"
    if len(description) > 12000:
        return None, "description_exceeds_bound"
    url = obj.get("url")
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        return None, "invalid_source_url"
    if parsed.scheme != "https" or parsed.hostname not in ("www.dvidshub.net", "dvidshub.net"):
        return None, "invalid_source_url"
    if f"/news/{ident.split(':')[1]}/" not in parsed.path:
        return None, "url_id_mismatch"
    # DVIDS location describes asset production/capture, not necessarily
    # site of a claimed armed incident. Never copy it to event location.
    return {
        "id": "dvids-" + ident.replace(":", "-"),
        "source_url": url,
        "source_family": "commercial_media",  # eligible text-report lane, NOT commercial assertion
        "source_kind": "source_event_report",
        "provider": "dvids",
        "source_text": description,
        "rights_basis": "public_domain",
        "rights_note": "Operator confirmed this individual DVIDS news asset is US federal work with no exception.",
        "retrieved_at": retrieved_at,
        "story_lineage_id": "dvids:" + ident,
        "title": obj.get("title", ""),
        "source_published_at": utc(obj.get("date_published")),
        "reporting_origin": None,
        "content_type": "full_body",
        "source_credit": obj.get("credit"),
    }, None


def convert(assets, approved_ids, retrieved_at):
    if not isinstance(assets, list) or len(assets) > MAX_ASSETS:
        raise ValueError("invalid or oversized asset batch")
    approved = set(approved_ids)
    if not all(isinstance(i, str) and re.fullmatch(r"news:\d+", i) for i in approved):
        raise ValueError("invalid approval list")
    rows, rejected = [], {}
    for obj in assets:
        row, reason = asset_to_input(obj, approved, retrieved_at)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
        else:
            rows.append(row)
    # No implicit blanket rights approval; caller must list actual asset IDs.
    return rows, rejected


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset-export", type=Path, required=True)
    p.add_argument("--approved-ids", type=Path, required=True)
    p.add_argument("--retrieved-at", required=True)
    p.add_argument("--private-output", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    payload = json.loads(a.asset_export.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("results"), dict):
        assets = [payload["results"]]
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        assets = payload["results"]
    else:
        raise ValueError("expected DVIDS /asset response object or list of full assets")
    approved = json.loads(a.approved_ids.read_text(encoding="utf-8"))
    if not isinstance(approved, list):
        raise ValueError("approved asset ids must be JSON list")
    source_rows, rejected = convert(assets, approved, a.retrieved_at)
    existing = json.loads(a.manifest.read_text()) if a.manifest.exists() else {}
    reports, manifest, receipt = ingest(source_rows, existing)
    for path in (a.private_output, a.manifest, a.receipt):
        path.parent.mkdir(parents=True, exist_ok=True)
    with a.private_output.open("w", encoding="utf-8") as f:
        for row in reports:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    a.private_output.chmod(0o600)
    a.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    receipt["provider"] = "dvids_offline_asset_export"
    receipt["rejected"] = dict(sorted(rejected.items()))
    a.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
