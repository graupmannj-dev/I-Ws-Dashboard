#!/usr/bin/env python3
"""Bounded official GOV.UK Content API ingestion for AIBA evaluation.

GOV.UK documents the public Content API and OGL v3.0 default, subject to
exceptions. This pilot uses *only* a curated allowlist of www.gov.uk pages,
excludes HTML quotations/media and retains source-specific attribution.
It does not verify real-world events, access private providers, or alert.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from scripts.aiba_source_text_intake import ingest

SCHEMA = "aiba.govuk-curated-seeds.v1"
BASE = "https://www.gov.uk"
API = BASE + "/api/content"
ALLOWED_STRATA = {"incident_candidate", "operational_context", "nonincident_control"}
MAX_SEEDS = 60
MAX_RESPONSE_BYTES = 550_000
MAX_PARAGRAPH_CHARS = 3500
MAX_TEXT = 10000
MIN_TEXT = 180
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
EXCLUDED_LICENSE_MARKERS = (
    "all rights reserved", "used with permission", "third-party copyright",
    "third party copyright", "reproduced with permission",
)
RETRIEVAL_USER_AGENT = "AIBA-offline-research/1.0 (GOV.UK licensed content evaluation; no production alerts)"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect refused for fixed-domain source corpus")


class Paragraphs(HTMLParser):
    """Keep literal paragraph text, excluding figures, media and blockquotes."""

    EXCLUDED = {"blockquote", "figure", "figcaption", "script", "style",
                "table", "svg", "iframe", "aside", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.excluded = []
        self.depth = 0
        self.fragments = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag in self.EXCLUDED:
            self.excluded.append(tag)
        if tag == "p":
            self.depth += 1
            if self.depth == 1:
                self.fragments = []

    def handle_endtag(self, tag):
        if tag == "p" and self.depth:
            if self.depth == 1 and not self.excluded:
                text = re.sub(r"\s+", " ", "".join(self.fragments)).strip()
                if 20 <= len(text) <= MAX_PARAGRAPH_CHARS:
                    self.paragraphs.append(text)
            self.depth -= 1
            self.fragments = []
        if tag in self.EXCLUDED:
            if self.excluded and self.excluded[-1] == tag:
                self.excluded.pop()

    def handle_data(self, data):
        if self.depth and not self.excluded:
            self.fragments.append(data)


def canonical_path(raw):
    if not isinstance(raw, str) or len(raw) > 500:
        raise ValueError("invalid source URL")
    p = urllib.parse.urlsplit(raw)
    if p.scheme != "https" or p.hostname != "www.gov.uk" or p.query or p.fragment:
        raise ValueError("only canonical www.gov.uk HTTPS content URLs allowed")
    path = p.path
    if not (path.startswith("/government/news/") or
            path.startswith("/government/speeches/") or
            path.startswith("/government/case-studies/")):
        raise ValueError("source outside reviewed government content types")
    if not re.fullmatch(r"/[A-Za-z0-9/._-]{20,450}", path):
        raise ValueError("invalid government content path")
    return path


def check_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("unknown curated seed manifest")
    seeds = manifest.get("seeds")
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= MAX_SEEDS:
        raise ValueError("source manifest seed count invalid")
    seen = set()
    for seed in seeds:
        if not isinstance(seed, dict):
            raise ValueError("invalid seed")
        path = canonical_path(seed.get("url"))
        if path in seen:
            raise ValueError("duplicate government source URL")
        seen.add(path)
        if seed.get("sampling_stratum") not in ALLOWED_STRATA:
            raise ValueError("missing sampling stratum")
        if not isinstance(seed.get("episode_hint"), str) or not re.fullmatch(
                r"[a-z0-9._-]{5,100}", seed["episode_hint"]):
            raise ValueError("missing reviewed episode hint")
    return seeds


def api_get(path, *, opener=None):
    """Single fixed-origin request. No arbitrary URL, redirect, link crawl."""
    url = API + canonical_path(BASE + path)
    opener = opener or urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": RETRIEVAL_USER_AGENT})
    with opener.open(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError("content API returned non-200")
        typ = response.headers.get("Content-Type", "").lower()
        if "application/json" not in typ:
            raise ValueError("content API returned non-JSON")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("content API response over byte limit")
    return json.loads(raw)


def utc(value):
    if not isinstance(value, str):
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d.astimezone(dt.timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z")) if d.tzinfo else None


def to_source(seed, item, retrieved_at):
    if not isinstance(item, dict):
        return None, "invalid_api_object"
    path = canonical_path(seed["url"])
    if item.get("base_path") != path:
        return None, "api_path_mismatch"
    content_id = item.get("content_id")
    if not isinstance(content_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{20,50}", content_id):
        return None, "missing_content_id"
    details = item.get("details")
    html_body = details.get("body") if isinstance(details, dict) else None
    if not isinstance(html_body, str) or not html_body.strip():
        return None, "missing_article_html"
    # Text-only extracted government narrative. Page-level copyright exceptions
    # cannot be certified automatically. Avoid embedded third-party material.
    if any(flag in html_body.lower() for flag in EXCLUDED_LICENSE_MARKERS):
        return None, "possible_third_party_rights"
    parser = Paragraphs()
    parser.feed(html_body)
    paragraphs = []
    chars = 0
    for p in parser.paragraphs:
        if chars + len(p) + 2 > MAX_TEXT:
            break
        paragraphs.append(p)
        chars += len(p) + 2
    body = "\n".join(paragraphs)
    if len(body) < MIN_TEXT:
        return None, "insufficient_government_narrative"
    pub = utc(item.get("first_published_at") or item.get("public_updated_at"))
    if not pub:
        return None, "missing_published_at"
    source_url = BASE + path
    title = str(item.get("title") or "")[:240]
    row = {
        "id": "govuk-" + content_id,
        "source_url": source_url, "provider": "govuk_content_api",
        "source_family": "official_media",
        "source_kind": "government_public_statement",
        "source_text": body, "title": title,
        "source_published_at": pub,
        "retrieved_at": retrieved_at,
        "rights_basis": "licensed_for_internal_evaluation",
        "rights_note": ("GOV.UK text-only original public-sector content; Open Government Licence v3.0 "
                        + OGL_URL + "; subject to exclusions; no embedded figures, tables or blockquotes."),
        "content_type": "source_excerpt",  # filtered body is never a complete original
        "story_lineage_id": "govuk-content:" + content_id,
        "evaluation_group_id": "govuk-episode:" + seed["episode_hint"],
        "sampling_stratum": seed["sampling_stratum"],
        "source_credit": "UK Government / GOV.UK; Open Government Licence v3.0",
        "source_document_type": str(item.get("document_type") or "")[:90],
        "content_api_updated_at": utc(item.get("public_updated_at")),
    }
    return row, None


def collect(manifest, *, fetch=api_get, clock=None, sleep=time.sleep, delay_seconds=0.35):
    seeds = check_manifest(manifest)
    retrieved_at = (clock or (lambda: dt.datetime.now(dt.timezone.utc)))().astimezone(
        dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    reports = []
    status = Counter()
    details = []
    for i, seed in enumerate(seeds):
        if i and delay_seconds:
            sleep(delay_seconds)
        try:
            path = canonical_path(seed["url"])
            item = fetch(path)
            source, reason = to_source(seed, item, retrieved_at)
            if reason:
                status[reason] += 1
            else:
                reports.append(source)
                status["accepted_source_text"] += 1
            details.append({"id": seed["id"], "source_url": seed["url"],
                            "sampling_stratum": seed["sampling_stratum"],
                            "status": reason or "accepted_source_text",
                            "content_id": item.get("content_id") if isinstance(item, dict) else None})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ValueError, json.JSONDecodeError, OSError) as e:
            # Avoid leaking source content or link payloads into logs.
            reason = "source_fetch_or_parse_failure"
            status[reason] += 1
            details.append({"id": seed["id"], "source_url": seed["url"],
                            "sampling_stratum": seed["sampling_stratum"], "status": reason,
                            "error_class": type(e).__name__})
    return reports, {
        "schema": "aiba.govuk-corpus-acquisition-audit.v1",
        "requested_seed_count": len(seeds),
        "successful_article_text_count": len(reports),
        "statuses": dict(sorted(status.items())),
        "records": details,
        "retrieved_at": retrieved_at,
        "official_statement_not_independent_verification": True,
        "human_ground_truth_labels_created": 0,
        "automatic_alerts_created": 0,
    }


def private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=Path, required=True)
    p.add_argument("--private-workspace", type=Path, required=True)
    p.add_argument("--minimum-success", type=int, default=12)
    args = p.parse_args()
    manifest = json.loads(args.seeds.read_text(encoding="utf-8"))
    reports, audit = collect(manifest)
    # Persist diagnostics for failures even if the corpus is below acceptance.
    private_json(args.private_workspace / "acquisition_audit.json", audit)
    if len(reports) < args.minimum_success:
        print(json.dumps({"status": "below_source_acquisition_minimum",
                          "audit": {k: v for k, v in audit.items() if k != "records"}}, indent=2))
        raise SystemExit(2)
    prior_path = args.private_workspace / "lineage_splits.json"
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
    imported, splits, receipt = ingest(reports, prior)
    args.private_workspace.mkdir(parents=True, exist_ok=True)
    out = args.private_workspace / "reports.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in imported:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.chmod(0o600)
    private_json(prior_path, splits)
    private_json(args.private_workspace / "intake_receipt.json", receipt)
    # Publicly share only aggregate counts and URL/metadata, never raw article text.
    print(json.dumps({"acquisition": {k: v for k, v in audit.items() if k != "records"},
                      "intake": receipt}, indent=2))


if __name__ == "__main__":
    main()
