#!/usr/bin/env python3
"""Opt-in, capped DVIDS API asset retrieval (never runs in normal CI).

Uses developer-supplied DVIDS_API_KEY, explicit reviewed news:IDs only, and
a fixed HTTPS API host. Stores PRIVATE raw JSON, not repository artifacts.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_ASSETS = 25
MAX_RESPONSE_BYTES = 100000
API_HOST = "api.dvidshub.net"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("DVIDS API redirect refused")


def fetch_assets(asset_ids, api_key):
    if not isinstance(api_key, str) or not re.fullmatch(r"key-[A-Za-z0-9_-]{8,120}", api_key):
        raise ValueError("DVIDS_API_KEY invalid or absent")
    if not isinstance(asset_ids, list) or not 1 <= len(asset_ids) <= MAX_ASSETS:
        raise ValueError("asset ID list must contain 1-25 reviewed items")
    if len(set(asset_ids)) != len(asset_ids) or any(
        not isinstance(v, str) or not re.fullmatch(r"news:\d+", v) for v in asset_ids
    ):
        raise ValueError("duplicate or invalid asset ID")
    opener = urllib.request.build_opener(NoRedirect)
    results = []
    for ident in asset_ids:
        query = urllib.parse.urlencode({"id": ident, "api_key": api_key})
        target = "https://" + API_HOST + "/asset?" + query
        request = urllib.request.Request(target, headers={
            "Accept": "application/json",
            "User-Agent": "AIBA-Research-Evaluation/1.0 (rights-reviewed read-only source study)",
        })
        try:
            with opener.open(request, timeout=15) as resp:
                if resp.status != 200:
                    raise ValueError("provider returned non-200")
                if resp.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise ValueError("provider did not return JSON")
                body = resp.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ValueError("provider response over cap")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            # Never stringify errors containing secret-bearing request URLs.
            raise RuntimeError(f"provider fetch failed for {ident}; HTTP/network error (secret suppressed)") from None
        data = json.loads(body)
        if not isinstance(data, dict) or not isinstance(data.get("results"), dict):
            raise ValueError("unexpected provider response shape")
        row = data["results"]
        if row.get("id") != ident or row.get("type") != "news":
            raise ValueError("provider identity or content type mismatch")
        results.append(row)
    return {"results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved-ids", type=Path, required=True)
    ap.add_argument("--private-export", type=Path, required=True)
    args = ap.parse_args()
    ids = json.loads(args.approved_ids.read_text(encoding="utf-8"))
    export = fetch_assets(ids, os.environ.get("DVIDS_API_KEY", ""))
    args.private_export.parent.mkdir(parents=True, exist_ok=True)
    with args.private_export.open("w", encoding="utf-8") as f:
        json.dump(export, f)
    args.private_export.chmod(0o600)
    # Print counts only: not secret, source prose or article URLs.
    print(json.dumps({"asset_count": len(export["results"]),
                      "status": "private_source_export_only",
                      "automatic_alerts_created": 0}))


if __name__ == "__main__":
    main()
