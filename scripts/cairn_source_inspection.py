#!/usr/bin/env python3
"""Bounded read-only original-document inspection for CAIRN's hypothesis panel.

A successful HTTP retrieval proves ONLY that the document was accessible and
contains literal text; it does not establish an incident occurred. Original
source bodies are processed in memory and NOT published or persisted. One
short evidence excerpt/hash and report-level metadata per selected document.
No arbitrary URL fetching, redirects, credentials, private networks, or APIs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import sys
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard.hypothesis_discriminator_engine import assess, _check_config
from dashboard.source_geo_claims import inspect_text

SCHEMA = "cairn.source-inspection.v1"
ALLOWED_HOSTS = frozenset((
    "www.gov.uk", "www.reuters.com", "www.criticalthreats.org",
    "www.nato.int", "www.state.gov", "www.dvidshub.net",
    "www.ukmto.org", "niord.dma.dk", "www.valitsus.ee",
    "www.imo.org", "www.defense.gov", "www.mfa.gov.cn",
    "www.theguardian.com", "www.adnoc.ae", "www.arnnewscentre.ae",
    "travel.state.gov",
))
MAX_DOWNLOAD = 450_000
MAX_TEXT = 12_000
MIN_NARRATIVE_CHARS = 180
DEFAULT_DOCS = 12
MAX_DOCS = 18
USER_AGENT = "CAIRN-Source-Inspection/0.1 (public-document research; limited read-only)"
BANNED_PATH_SUFFIXES = (".pdf", ".jpg", ".png", ".zip", ".xml", ".rss", ".json", ".csv")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("redirect_not_permitted")


class NarrativeParagraphs(HTMLParser):
    """Text-only source paragraphs; ignore scripts/navigation/quotes/media."""
    EXCLUDED = {"script", "style", "noscript", "blockquote", "nav", "footer",
                "figure", "figcaption", "aside", "table", "svg", "iframe", "form",
                "head", "button"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.pdepth = 0
        self.frags = []
        self.paragraphs = []
    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        if tag == "p":
            self.pdepth += 1
            if self.pdepth == 1:
                self.frags = []
    def handle_endtag(self, tag):
        if tag == "p" and self.pdepth:
            if self.pdepth == 1 and not any(t in self.EXCLUDED for t in self.stack):
                text = re.sub(r"\s+", " ", "".join(self.frags)).strip()
                if 35 <= len(text) <= 1800:
                    self.paragraphs.append(text)
            self.pdepth -= 1
            self.frags = []
        if tag in self.stack:
            # Browser HTML is often malformed. Remove the nearest matching tag
            # and its descendants rather than enabling parent-inherited leaks.
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]
    def handle_data(self, data):
        if self.pdepth and not any(t in self.EXCLUDED for t in self.stack):
            self.frags.append(data)


def _safe_source_url(url):
    if not isinstance(url, str) or len(url) > 1600:
        return None
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if (u.scheme != "https" or u.hostname not in ALLOWED_HOSTS
            or u.port not in (None, 443) or u.username or u.password
            or len(u.path.strip("/")) < 9
            or u.path.lower().endswith(BANNED_PATH_SUFFIXES)):
        return None
    return url


def _dns_public_only(host):
    """Defence in depth; never fetch an IP literal or a private IP resolution."""
    if not host in ALLOWED_HOSTS:
        raise ValueError("non_allowlisted_host")
    for address in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("host_resolves_to_nonpublic_address")


def _load_bytes(url, accept, timeout):
    host = urllib.parse.urlsplit(url).hostname
    _dns_public_only(host)
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                    "Accept": accept})
    with opener.open(request, timeout=timeout) as resp:
        if resp.status != 200:
            raise ValueError("non_200_source_response")
        content_type = resp.headers.get("Content-Type", "").lower().split(";")[0]
        if content_type not in ("text/html", "application/json", "text/plain",
                                "application/xhtml+xml"):
            raise ValueError("unsupported_source_content_type")
        data = resp.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError("source_response_exceeds_byte_limit")
    return data, content_type


def _narrative(html_text):
    parser = NarrativeParagraphs()
    parser.feed(html_text)
    paragraphs = []
    used = 0
    for p in parser.paragraphs:
        if used + len(p) + 1 > MAX_TEXT:
            break
        paragraphs.append(p)
        used += len(p) + 1
    return "\n".join(paragraphs)


def read_original(url, *, timeout=7):
    """Bounded real HTTP; returns ephemeral permitted narrative text only."""
    original = _safe_source_url(url)
    if not original:
        return None, {"status": "not_fetched_disallowed_or_nondocument_url"}
    parsed = urllib.parse.urlsplit(original)
    if parsed.hostname == "www.gov.uk" and parsed.path.startswith((
            "/government/news/", "/government/speeches/",
            "/government/case-studies/")):
        try:
            from scripts.aiba_govuk_corpus import api_get, to_source
            # Existing official GOV.UK API adapter verifies canonical path,
            # source licensing exclusions, API identity and narrative length.
            item = api_get(parsed.path)
            seed = {"url": "https://www.gov.uk" + parsed.path,
                    "sampling_stratum": "operational_context",
                    "episode_hint": "cairn-document-inspection"}
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            doc, error = to_source(seed, item, now)
            if error:
                return None, {"status": "source_content_not_retrievable",
                              "reason": error}
            return doc["source_text"], {
                "status": "document_text_inspected",
                "retrieval_kind": "govuk_verified_content_api",
                "source_published_at": doc.get("source_published_at"),
                "source_credit": "UK Government / Open Government Licence v3 subject to exceptions",
                "content_path_verified": True,
            }
        except (ValueError, KeyError, TimeoutError, OSError, urllib.error.URLError,
                json.JSONDecodeError) as exc:
            return None, {"status": "source_content_not_retrievable",
                          "reason": "govuk_" + type(exc).__name__}
    try:
        binary, ctype = _load_bytes(original, "text/html,application/xhtml+xml", timeout)
        if ctype not in ("text/html", "application/xhtml+xml"):
            return None, {"status": "source_content_not_retrievable",
                          "reason": "not_a_narrative_html_page"}
        narrative = _narrative(binary.decode("utf-8", errors="replace"))
        if len(narrative) < MIN_NARRATIVE_CHARS:
            return None, {"status": "source_content_not_retrievable",
                          "reason": "insufficient_narrative_text"}
        return narrative, {"status": "document_text_inspected",
                           "retrieval_kind": "bounded_original_html",
                           "content_path_verified": False,
                           "source_published_at": None,
                           "source_credit": "External source content examined ephemerally; rights not independently established"}
    except urllib.error.HTTPError as exc:
        return None, {"status": "source_content_not_retrievable",
                      "reason": "http_" + str(exc.code)}
    except (ValueError, TimeoutError, OSError, urllib.error.URLError) as exc:
        return None, {"status": "source_content_not_retrievable",
                      "reason": type(exc).__name__}


def _select(config, registry, archive, at, maximum):
    dossier = [{"id": case} for case in config["cases"]]
    scan = assess(dossier, registry, archive, {}, {}, config, at=at)
    by_case = {}
    for case_id, case in scan["cases"].items():
        seen = set()
        options = []
        for rule in case["discriminators"]:
            for x in rule["sources"]:
                url = x.get("source_url")
                if url in seen or not _safe_source_url(url):
                    continue
                seen.add(url)
                options.append({
                    "case_id": case_id, "source_url": url,
                    "source_record_id": x["record_id"],
                    "rule": rule["id"], "first_observed_at": x["first_observed_at"],
                    "source_mode": x["source_mode"],
                })
        # Prioritize a source-specific official/analyst article over a
        # current provider landing page or recurrent navigation warning.
        def rank(o):
            url = o["source_url"]
            is_document = "/news/" in url or "/world/" in url or "/government/" in url
            return (0 if is_document else 1, 0 if o["source_mode"] == "analyst" else 1,
                    o["source_url"])
        by_case[case_id] = sorted(options, key=rank)
    selected = []
    used = set()
    for _ in range(maximum):
        progressed = False
        for cid in sorted(by_case):
            if len(selected) >= maximum:
                break
            while by_case[cid] and (by_case[cid][0]["source_url"] in used):
                by_case[cid].pop(0)
            if by_case[cid]:
                item = by_case[cid].pop(0)
                selected.append(item)
                used.add(item["source_url"])
                progressed = True
        if not progressed or len(selected) >= maximum:
            break
    return selected, scan


def inspect(registry, archive, config, *, at=None, maximum=DEFAULT_DOCS, fetch=read_original,
            pause=None):
    if not 1 <= maximum <= MAX_DOCS:
        raise ValueError("source retrieval budget exceeded")
    _check_config(config)
    now = at or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if isinstance(now, str):
        now = dt.datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("retrieval clock must be timezone aware")
    selected, scan = _select(config, registry, archive, now, maximum)
    rows = []
    counts = {"document_text_inspected": 0, "source_content_not_retrievable": 0,
              "not_fetched_disallowed_or_nondocument_url": 0}
    for item in selected:
        url, cid = item["source_url"], item["case_id"]
        body, outcome = fetch(url)
        outcome = dict(outcome)
        status = outcome.get("status", "source_content_not_retrievable")
        if status not in counts:
            status = "source_content_not_retrievable"
            outcome["status"] = status
        counts[status] += 1
        entry = {**item,
                 "status": status, "retrieval_kind": outcome.get("retrieval_kind"),
                 "source_published_at": outcome.get("source_published_at"),
                 "reason": outcome.get("reason"),
                 "source_credit": outcome.get("source_credit"),
                 "content_path_verified": outcome.get("content_path_verified") is True,
                 "event_occurred_verified": False, "actor_verified": False,
                 "independent_corroboration": False, "warning_approved": False}
        if status == "document_text_inspected" and isinstance(body, str):
            rule_templates = {
                key: config["templates"][key] for key in
                (config["cases"][cid]["escalation"] +
                 config["cases"][cid]["alternatives"] +
                 config["cases"][cid].get("context", []))}
            entry["document_inspection"] = inspect_text(body, cid, rule_templates)
            entry["document_inspection"]["source_text_copied_to_public_artifact"] = False
            # Full source body never escapes the local fetch invocation.
        else:
            entry["document_inspection"] = None
        rows.append(entry)
        if pause:
            pause()
    count_case = {}
    for cid in config["cases"]:
        eligible = [x for x in rows if x["case_id"] == cid]
        count_case[cid] = {
            "attempted": len(eligible),
            "inspected": sum(x["status"] == "document_text_inspected" for x in eligible),
            "source_text_location_attributions": sum(
                x.get("document_inspection", {}).get("case_attribution", {}).get(
                    "source_text_location_asserted", False)
                for x in eligible if x["document_inspection"]),
        }
    return {
        "schema": SCHEMA, "status": "screened" if selected else "no_eligible_document_urls",
        "generated_at": now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "candidate_documents_considered": scan["source_records_in_window"],
        "candidate_input_truncated": scan["candidate_input_truncated"],
        "unique_source_documents_attempted": len(selected),
        "retrieval_budget": maximum,
        "status_counts": counts,
        "cases": count_case, "inspections": rows,
        "source_bodies_saved": False, "source_bodies_published": False,
        "automated_event_verifications": 0, "approved_warnings": 0,
        "limitations": [
            "A successfully opened original article is not independently corroborated event occurrence.",
            "Title-to-source text and action-sentence matching are lexical, not verified actor/event semantics.",
            "Country-only, publisher location, article dateline, and theater anchor do not locate an incident.",
            "Named locality is text-specified area only; no incident coordinate is fabricated.",
            "Source blocks, copyright, access limits, and non-HTML documents cause explicit abstention.",
            "This prototype never collects full historical source versions or attests source rights.",
        ],
    }


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--config", type=Path, default=Path("data/hypothesis_discriminators.json"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--maximum", type=int, default=DEFAULT_DOCS)
    args = ap.parse_args()
    result = inspect(_read(args.registry), _read(args.archive),
                     _read(args.config), maximum=args.maximum)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("CAIRN original source inspection:",result["unique_source_documents_attempted"],
          "attempted,",result["status_counts"]["document_text_inspected"],
          "original texts examined,",
          result["status_counts"]["source_content_not_retrievable"],
          "access failures; no incidents independently verified")


if __name__ == "__main__":
    main()
