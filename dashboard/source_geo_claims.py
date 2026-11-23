"""Conservative textual incident-locality attribution for source-inspection receipts.

A place in a source sentence is NOT an independently verified event site,
a geocoded point, or an actor's nationality. Avoid datelines, publisher addresses,
country-only actor mentions, unbounded text inference and positional guesses.
"""
from __future__ import annotations

import hashlib
import re

SCHEMA = "cairn.source-geography.v1"
MAX_BODY = 14000
MAX_SENTENCES = 90
ACTIVITY = re.compile(
    r"\b(?:struck|strike|strikes|attack(?:ed|s)?|shell(?:ed|ing)?|"
    r"incursions?|intercept(?:ed|ion)?|launch(?:ed|es)?|firing|"
    r"closed|closure|suspend(?:ed|sion)?|evacuat(?:ed|ion)|"
    r"deploy(?:ed|ment)|mobiliz(?:ed|ation)|blockade|"
    r"explosion|missile|drone|tankers?|vessels?|ship(?:ping)?|"
    r"military exercise|firing exercise|border crossing)\b", re.I)
UNCERTAIN = re.compile(
    r"\b(?:alleg(?:ed|edly)?|claim(?:ed|s)?|report(?:ed|edly)?|"
    r"said|according to|denied|disputed|suspected|unconfirmed)\b", re.I)
NEGATED = re.compile(r"\b(?:no|not|without|denied|disputed|false)\b", re.I)
BACKGROUND = re.compile(r"\b(?:historically|in 20(?:0\d|1\d)|years ago|previously)\b", re.I)
CASE_GAZETTEER = {
    # Real OGL-licensed historical source corpus only. These are NOT standing
    # CAIRN scenarios and never join live warning screens.
    "govuk_yemen_historical": [
        ("Red Sea", "MARITIME_AREA", r"\bred sea\b"),
        ("Bab al-Mandab", "MARITIME_AREA", r"\b(?:bab[- ]?al[- ]?mandab|bab el mandeb)\b"),
        ("Hodeidah", "YE", r"\b(?:hodeidah|hudaydah)\b"),
        ("Sanaa", "YE", r"\b(?:sanaa|san.?a)\b"),
        ("Yemen", "YE", r"\byemen(?:i)?\b"),
    ],
    "govuk_ukraine_historical": [
        ("Kyiv", "UA", r"\b(?:kyiv|kiev)\b"),
        ("Kharkiv", "UA", r"\bkharkiv\b"),
        ("Odesa", "UA", r"\b(?:odesa|odessa)\b"),
        ("Ukraine", "UA", r"\bukrain(?:e|ian)\b"),
    ],
    "iran_gulf": [
        ("Strait of Hormuz", "MARITIME_AREA", r"\b(?:strait of hormuz|hormuz strait|hormuz)\b"),
        ("Khasab", "OM", r"\bkhasab\b"),
        ("Bahrain", "BH", r"\bbahrain\b"),
        ("Persian Gulf", "MARITIME_AREA", r"\bpersian gulf\b"),
        ("Qeshm", "IR", r"\bqeshm\b"),
    ],
    "taiwan": [
        ("Taiwan Strait", "MARITIME_AREA", r"\btaiwan strait\b"),
        ("Kinmen", "TW", r"\bkinmen\b"),
        ("Matsu", "TW", r"\bmatsu(?: islands)?\b"),
        ("Taiwan", "TW", r"\btaiwan\b"),
    ],
    "russia_nato": [
        ("Poland", "PL", r"\bpoland|polish (?:airspace|border|territory)\b"),
        ("Lithuania", "LT", r"\blithuania\b"),
        ("Latvia", "LV", r"\blatvia\b"),
        ("Estonia", "EE", r"\bestonia\b"),
        ("Kaliningrad", "RU", r"\bkaliningrad\b"),
        ("Baltic Sea", "MARITIME_AREA", r"\bbaltic sea\b"),
        ("Finland", "FI", r"\bfinland|finnish waters\b"),
    ],
    "korea": [
        ("DMZ", "BORDER_AREA", r"\bdmz\b|\bdemilitarized zone\b"),
        ("Seoul", "KR", r"\bseoul\b"),
        ("Pyongyang", "KP", r"\bpyongyang\b"),
        ("North Korea", "KP", r"\bnorth korea\b"),
        ("South Korea", "KR", r"\bsouth korea\b"),
    ],
    "horn_ethiopia_eritrea": [
        ("Badme", "BORDER_AREA", r"\bbadme\b"),
        ("Rama", "ET", r"\brama\b"),
        ("Tigray", "ET", r"\btigray\b"),
        ("Eritrea", "ER", r"\beritrea(?:n)?\b"),
        ("Ethiopia", "ET", r"\bethiopia(?:n)?\b"),
    ],
    "horn_ethiopia_sudan": [
        ("Al-Fashaga", "BORDER_AREA", r"\bal[- ]fashaga\b"),
        ("Sudan", "SD", r"\bsudan(?:ese)?\b"),
        ("Ethiopia", "ET", r"\bethiopia(?:n)?\b"),
    ],
    "horn_ethiopia_kenya_moyale": [
        ("Moyale", "BORDER_AREA", r"\bmoyale\b"),
        ("Kenya", "KE", r"\bkenya(?:n)?\b"),
        ("Ethiopia", "ET", r"\bethiopia(?:n)?\b"),
    ],
    "afpak": [
        ("Torkham", "BORDER_AREA", r"\btorkham\b"),
        ("Spin Boldak", "BORDER_AREA", r"\bspin boldak\b"),
        ("Durand Line", "BORDER_AREA", r"\bdurand line\b"),
        ("Afghanistan", "AF", r"\bafghanistan|afghan\b"),
        ("Pakistan", "PK", r"\bpakistan(?:i)?\b"),
    ],
    "drc_rwanda": [
        ("Goma", "CD", r"\bgoma\b"),
        ("North Kivu", "CD", r"\bnorth kivu\b"),
        ("Rwanda", "RW", r"\brwanda(?:n)?\b"),
        ("DR Congo", "CD", r"\b(?:drc|dr congo|democratic republic of (?:the )?congo)\b"),
    ],
    "thailand_cambodia": [
        ("Preah Vihear", "BORDER_AREA", r"\bpreah vihear\b"),
        ("Ta Moan", "BORDER_AREA", r"\bta moan\b"),
        ("Thailand", "TH", r"\bthailand|thai border\b"),
        ("Cambodia", "KH", r"\bcambodia(?:n)?\b"),
    ],
}
# Country mentions are often *actors*, not incident sites. Keep them separate
# from bounded named places unless explicitly marked as a location in source.
COARSE = {"Yemen", "Ukraine", "Taiwan", "Eritrea", "Ethiopia", "Sudan", "Kenya", "Afghanistan",
          "Pakistan", "Rwanda", "DR Congo", "Thailand", "Cambodia",
          "North Korea", "South Korea", "Poland", "Lithuania", "Latvia",
          "Estonia", "Finland", "Bahrain"}


def _sentences(body):
    # Sentence splitting only; no multilingual or linguistic-role claims.
    return [(m.start(), re.sub(r"\s+", " ", m.group()).strip())
            for m in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", body[:MAX_BODY])]
    

def attribute(text, case_id):
    """Evidence-spanned locality mentions; never returns a point location."""
    base = {"schema": SCHEMA, "case_id": case_id, "status": "unknown",
            "named_place": None, "reported_country_or_area": None,
            "spatial_precision": None, "reported_event_site_verified": False,
            "coordinates": None, "source_text_location_asserted": False,
            "evidence_span": None, "multiple_place_candidates": [],
            "reason": "No eligible source statement about a named place"}
    if not isinstance(text, str) or not text.strip():
        return {**base, "status": "source_text_unavailable"}
    matches = []
    background = []
    for offset, sentence in _sentences(text)[:MAX_SENTENCES]:
        if len(sentence) > 650:
            continue
        sites = []
        for label, iso, pattern in CASE_GAZETTEER.get(case_id, []):
            if re.search(pattern, sentence, re.I):
                sites.append((label, iso))
        if not sites:
            continue
        if not ACTIVITY.search(sentence) or BACKGROUND.search(sentence):
            background.extend(sites)
            continue
        # Explicit local/place names outrank country-only mentions, which may
        # be the actors in the sentence, not the physical event site.
        concrete = [(label, iso) for label, iso in sites if label not in COARSE]
        if not concrete:
            background.extend(sites)
            continue
        for label, iso in concrete:
            matches.append((label, iso, offset, sentence))
    distinct = sorted({(v[0], v[1]) for v in matches})
    if not matches:
        if background:
            return {**base, "status": "actor_or_context_mentions_only",
                    "multiple_place_candidates": sorted({x[0] for x in background})[:8],
                    "reason": "Only broad country/actor references or non-action context; no report-supported event locality"}
        return base
    if len(distinct) > 1:
        return {**base, "status": "multiple_localities_ambiguous",
                "multiple_place_candidates": [label for label, _ in distinct][:8],
                "reason": "Multiple possible places in action-bearing source sentences; avoid guessing an event site"}
    label, iso, offset, sentence = matches[0]
    uncertain = bool(UNCERTAIN.search(sentence) or NEGATED.search(sentence))
    span = sentence[:160]
    # Do not copy copyrighted source prose to a public JSON response. The
    # original document and a deterministic sentence digest permit audit.
    evidence = {"sentence_start": offset,
                "sentence_sha256": hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
                "quote_excerpt": " ".join(span.split()[:14])[:105]}
    return {**base, "status": ("reported_locality_claim_unresolved" if uncertain
                               else "named_place_in_action_statement"),
            "named_place": label, "reported_country_or_area": iso,
            "spatial_precision": "named_area_only_not_event_point",
            "source_text_location_asserted": True,
            "evidence_span": evidence, "multiple_place_candidates": [label],
            "reason": "Location appears in action-bearing sentence; no independent event-site validation"}


def inspect_text(text, case_id, rules):
    """Compare versioned discriminators to *source paragraphs*, not title."""
    loc = attribute(text, case_id)
    matched = []
    negated = []
    spans = []
    for offset, sentence in _sentences(text)[:MAX_SENTENCES]:
        if len(sentence) > 650:
            continue
        for key, cfg in rules.items():
            if re.search(cfg["pattern"], sentence, re.I):
                if (key, offset) not in spans:
                    spans.append((key, offset))
                if NEGATED.search(sentence) or UNCERTAIN.search(sentence):
                    negated.append(key)
                else:
                    matched.append(key)
    return {
        "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_text_chars_inspected": len(text),
        "case_attribution": loc,
        "source_text_rule_mentions": sorted(set(matched)),
        "qualified_or_disputed_rule_mentions": sorted(set(negated)),
        "unreviewed": True, "event_occurrence_verified": False,
        "event_actor_identified": False, "independent_corroboration": False,
    }
