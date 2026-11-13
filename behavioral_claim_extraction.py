"""Bounded, evidence-spanned *candidate* claims from supplied primary-report text.

This is a deterministic high-precision pilot, not NLP inference. It never fetches
URLs, infers event sites from publisher origins, or changes warnings. Only
provided source text is examined; missing body text is an explicit abstention.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from urllib.parse import urlsplit

SCHEMA = "aiba.event-claim-extraction-shadow.v1"
MAX_REPORTS = 250
MAX_TEXT = 12000
MAX_CLAIMS_PER_REPORT = 8
MAX_SENTENCES = 100

# Intentionally small, auditable vocabulary: add verbs only with labeled tests.
VERBS = {
    "struck": "strike", "hit": "strike", "attacked": "attack",
    "shelled": "shell", "bombed": "bomb", "intercepted": "intercept",
    "detained": "detain", "seized": "seize", "closed": "close",
}
VERB_PATTERN = re.compile(r"\b(" + "|".join(VERBS) + r")\b", re.I)
NEGATION = re.compile(r"\b(?:did not|didn't|never|no evidence|falsely claimed|denied|refuted|not)\b", re.I)
UNCERTAIN = re.compile(r"\b(?:allegedly|reportedly|may have|might have|unconfirmed|claims?|said|according to)\b", re.I)
SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]|$)")
WORD = re.compile(r"\b[\w][\w'/-]*\b")
ISO_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
EVENT_REPORT_KINDS = {
    "field_event_report", "primary_event_report",
    "eyewitness_event_report", "source_event_report",
}


def _valid_source(url):
    if not isinstance(url, str) or len(url) > 2000:
        return False
    try:
        p = urlsplit(url)
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def _utc(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _site(row):
    # Source-supplied event-site geometry only. Never use reporting_origin,
    # coarse geography, event-text place names, or notice footprints.
    s = row.get("reported_event_location")
    if not isinstance(s, dict) or s.get("role") != "reported_event_site":
        return None
    if s.get("basis") not in ("source_declared", "source_record_geometry"):
        return None
    import math
    lat, lon = s.get("lat"), s.get("lon")
    if (type(lat) not in (float, int) or type(lon) not in (float, int)
            or not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        return None
    return {"role": "reported_event_site", "basis": s["basis"],
            "lat": float(lat), "lon": float(lon), "verification": "unreviewed_source_metadata"}


def _phrase(span):
    return span.strip(" ,;:.-!?\t\r\n")[:160]


def _extract_sentence(sentence, start):
    """Return explicit subject/verb/object candidate or abstain.

    Use a visible actor phrase before a controlled verb and visible object
    after it; do not interpret passive voice, coordinated verbs, or quotations.
    """
    original = sentence
    s = sentence.strip()
    offset = start + len(sentence) - len(sentence.lstrip())
    if len(s) < 15 or len(s) > 350:
        return None
    if s.startswith(('"', "'", "“", "‘")) or '"' in s or "“" in s:
        return None  # quoted/embedded claims need attribution handling
    matches = list(VERB_PATTERN.finditer(s))
    if len(matches) != 1:
        return None
    m = matches[0]
    left, right = _phrase(s[:m.start()]), _phrase(s[m.end():])
    # Attribution lead-ins do not identify the actor of the embedded act.
    if re.search(r"\b(?:said|claimed|reported|announced|warned|stated|according to)\b", left, re.I):
        return None
    # Hypothetical or conditional activity is not a past incident.
    if re.search(r"\b(?:will|would|could|should|might|plans? to|expected to)\b", left, re.I):
        return None
    # Passive-voice objects are not actors; parsing these needs a separate rule.
    if re.search(r"\b(?:was|were|is|are|been|being)$", left, re.I):
        return None
    # Modifiers qualify the claim, not the actor.
    left = re.sub(r"\s+(?:reportedly|allegedly|may have|might have)$", "", left, flags=re.I)

    # Conservative actor/object constraints; no pronoun actor hallucination.
    if not left or not right or len(left.split()) > 8 or len(right.split()) > 22:
        return None
    if len(WORD.findall(left)) < 1 or len(WORD.findall(right)) < 1:
        return None
    if left.lower() in {"it", "they", "he", "she", "we", "someone", "sources"}:
        return None
    if NEGATION.search(s):
        return None  # explicit denial is not the asserted affirmative event
    status = "attributed_or_uncertain" if UNCERTAIN.search(s) else "source_asserted_unverified"
    return {
        "actor_text": left,
        "action": VERBS[m.group().lower()],
        "action_text": m.group(),
        "object_text": right,
        "assertion_status": status,
        "evidence_span": {"start": offset, "end": offset + len(s), "text": s},
        "extraction_method": "bounded_literal_clause_v1",
        "event_time": None, "event_time_basis": "not_extracted",
        "event_site": None,
    }


def extract_report(row):
    """Extract from a supplied, source-associated body; never headline alone."""
    if not isinstance(row, dict):
        return {"status": "abstained", "reason": "invalid_record"}
    rid = str(row.get("id") or "")[:140]
    url = row.get("source_url")
    base = {"observation_id": rid, "source_url": url if _valid_source(url) else None,
            "status": "abstained", "claims": [], "warning_level_change": False,
            "independent_corroboration_established": False}
    if not rid or not _valid_source(url):
        return {**base, "reason": "missing_source_identity"}
    if row.get("source_family") != "commercial_media" and row.get("source_kind") not in EVENT_REPORT_KINDS:
        return {**base, "reason": "not_event_reporting"}
    body = row.get("source_text")
    if not isinstance(body, str) or not body.strip():
        return {**base, "reason": "source_body_unavailable"}
    if len(body) > MAX_TEXT:
        return {**base, "reason": "source_body_over_limit"}
    claim_list = []
    for m in list(SENTENCE.finditer(body))[:MAX_SENTENCES]:
        claim = _extract_sentence(m.group(), m.start())
        if claim is None:
            continue
        # Publication time is not event time. Only explicitly supplied event_at
        # is propagated as unverified metadata, not inferred from article date.
        event_at = _utc(row.get("event_at"))
        if event_at:
            claim["event_time"] = event_at
            claim["event_time_basis"] = "source_supplied_event_at_unreviewed"
        claim["event_site"] = _site(row)
        claim["claim_id"] = hashlib.sha256(
            (rid + "\x1f" + str(claim["evidence_span"]["start"]) + "\x1f" +
             claim["evidence_span"]["text"]).encode()).hexdigest()[:24]
        claim_list.append(claim)
        if len(claim_list) >= MAX_CLAIMS_PER_REPORT:
            break
    return {**base, "status": "candidate_claims_unreviewed" if claim_list else "abstained",
            "reason": None if claim_list else "no_supported_explicit_claim",
            "claims": claim_list, "truncated": len(list(SENTENCE.finditer(body))) > MAX_SENTENCES,
            "source_body_used": True}


def build(rows):
    """Shadow-only bounded summary. No cross-document event merge or alerts."""
    if not isinstance(rows, list):
        raise ValueError("reports must be a list")
    if len(rows) > MAX_REPORTS:
        raise ValueError("report cap exceeded: do not silently sample")
    results = [extract_report(r) for r in rows]
    return {"schema": SCHEMA, "status": "experimental_unreviewed",
            "report_count": len(results),
            "candidate_claim_count": sum(len(r["claims"]) for r in results),
            "abstention_count": sum(r["status"] == "abstained" for r in results),
            "reports": results, "automatic_alerts_created": 0,
            "warning_level_change": False,
            "limitations": [
                "Only user/provider-supplied report bodies; no article fetching.",
                "Literal English subject-action-object clauses only; omissions are expected.",
                "Extracted clauses are unverified source assertions, not verified events.",
                "No source independence, event merging, geocoding, or alert promotion."
            ]}
