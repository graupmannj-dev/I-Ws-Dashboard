#!/usr/bin/env python3
"""Ephemeral, allowlisted original-document evidence snippets for local Phi.

This extractor is deliberately *not* a corroboration or event-verification
engine. Untrusted source passages are processed only in runner memory. Do not
serialize the returned passages to a public JSON file or GitHub Actions log.

The existing CAIRN original-source reader prevents arbitrary URLs, redirects,
private IP targets, unsafe content types and unbounded responses.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from scripts.cairn_source_inspection import _safe_source_url, read_original

MAX_DOCS = 4
MAX_PASSAGES = 2
MAX_PASSAGE_CHARS = 400
MAX_SUM_CHARS = 1100
EXCLUDE_TERMS = frozenset((
    "activity", "activities", "between", "could", "would", "without",
    "indicates", "relevant", "forces", "about", "rather", "report",
    "reported", "routine", "military", "source", "hypothesis",
))
INSTRUCTIONAL = re.compile(
    r"(?i)\b(?:ignore (?:all |any )?(?:previous|prior|system) instructions|"
    r"system prompt|developer message|you are (?:now|chatgpt)|"
    r"override (?:your |the )?(?:policy|rules|instructions)|"
    r"output only (?:this|the following)|"
    r"do not (?:mention|reveal) (?:these|this) instructions)\b"
)


def _stamp(now):
    value = now or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise ValueError("Source inspection clock must be timezone aware")
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _terms(text):
    return {x for x in re.findall(r"[a-zA-Z]{5,}", str(text).lower())
            if x not in EXCLUDE_TERMS}


def _snippets(body, terms, *, maximum=MAX_PASSAGES):
    """Favor specific source paragraphs over headline-only inference."""
    if not isinstance(body, str):
        return []
    passages = []
    for index, raw in enumerate(body.splitlines()[:90]):
        normalized = re.sub(r"\s+", " ", raw).strip()
        if len(normalized) < 55 or INSTRUCTIONAL.search(normalized):
            continue
        # A quoted source passage is source text, not evidence of occurrence.
        clipped = normalized[:MAX_PASSAGE_CHARS]
        score = len(_terms(clipped) & terms)
        passages.append((score, index, clipped))
    passages.sort(key=lambda item: (-item[0], item[1]))
    # If nothing is topically relevant, keep at most one context paragraph and
    # mark it explicitly as a low-relevance sample rather than a matched claim.
    return [(index, text, score > 0) for score, index, text in
            passages[:maximum if passages and passages[0][0] > 0 else 1]]


def collect(packet, *, fetch=read_original, now=None, max_docs=MAX_DOCS):
    """Return ephemeral bounded passages; no raw source body is returned.

    Input is the original evidence_packet, retaining evidence family keys,
    original URLs and observed timestamps. All assertions remain unverified.
    """
    if not isinstance(packet, dict) or not isinstance(packet.get("hypotheses"), list):
        raise ValueError("Invalid evidence packet")
    if not isinstance(packet.get("evidence_families"), list):
        raise ValueError("Missing source families")
    if not 1 <= max_docs <= MAX_DOCS:
        raise ValueError("Document budget must be bounded")
    at = _stamp(now)
    terms = _terms(" ".join(packet["hypotheses"]))
    receipts, passages = [], []
    seen_urls = set()
    attempted = 0
    total_chars = 0
    for family in packet["evidence_families"][:20]:
        if not isinstance(family, dict):
            continue
        key = family.get("evidence_key")
        if not isinstance(key, str) or not key or len(key) > 120:
            continue
        for item in (family.get("sources") or [])[:3]:
            if attempted >= max_docs or total_chars >= MAX_SUM_CHARS:
                break
            if not isinstance(item, dict):
                continue
            url = _safe_source_url(item.get("url"))
            if not url:
                continue
            if url in seen_urls:
                receipts.append({"evidence_key":key, "source_url":url,
                                 "status":"duplicate_source_document",
                                 "independent_information_root_confirmed":False})
                continue
            seen_urls.add(url)
            attempted += 1
            text, result = fetch(url)
            result = result if isinstance(result,dict) else {}
            status = result.get("status")
            if status != "document_text_inspected" or not isinstance(text,str):
                receipts.append({"evidence_key":key,"source_url":url,
                                 "status":"original_text_unavailable",
                                 "independent_information_root_confirmed":False})
                continue
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            link_terms = terms | _terms(family.get("family_title")) | _terms(item.get("title"))
            snippets = _snippets(text,link_terms)
            if not snippets:
                receipts.append({"evidence_key":key,"source_url":url,
                                 "status":"no_usable_source_passage",
                                 "source_body_sha256":content_hash,
                                 "independent_information_root_confirmed":False})
                continue
            count = 0
            for paragraph_index, excerpt, relevant in snippets:
                if total_chars + len(excerpt) > MAX_SUM_CHARS:
                    break
                identifier = "passage:" + hashlib.sha256(
                    (key+"\x1f"+url+"\x1f"+content_hash+"\x1f"+str(paragraph_index)).encode()
                    ).hexdigest()[:24]
                passages.append({
                    "passage_id":identifier, "evidence_key":key,
                    "source_url":url,
                    "source_title":str(item.get("title") or "")[:180],
                    "first_observed_at":str(item.get("first_observed_at") or "")[:50] or None,
                    "source_published_at":result.get("source_published_at"),
                    "inspected_at":at, "source_body_sha256":content_hash,
                    "excerpt_sha256":hashlib.sha256(excerpt.encode()).hexdigest(),
                    "excerpt":excerpt,
                    "topical_overlap": "lexical_overlap" if relevant else "not_established",
                    "content_path_verified":result.get("content_path_verified") is True,
                    "retrieval_kind":result.get("retrieval_kind"),
                    "source_truth_verified":False,
                    "event_occurred_verified":False,
                    "actor_intent_verified":False,
                    "independent_information_root_confirmed":False,
                })
                total_chars += len(excerpt)
                count += 1
            receipts.append({"evidence_key":key,"source_url":url,
                             "status":"source_passages_available" if count else "passage_budget_exhausted",
                             "passage_count":count,
                             "source_body_sha256":content_hash,
                             "source_published_at":result.get("source_published_at"),
                             "independent_information_root_confirmed":False})
        if attempted >= max_docs or total_chars >= MAX_SUM_CHARS:
            break
    return {
        "schema":"cairn.phi-source-grounding.v1",
        "case_id":packet.get("case_id"),
        "inspected_at":at,
        "source_urls_attempted":attempted,
        "source_passages":passages,
        "receipts":receipts,
        "full_original_documents_persisted":False,
        "original_source_text_is_untrusted":True,
        "independent_corroboration_established":False,
        "event_occurred_verified":False,
        "analyst_approved":False,
    }
