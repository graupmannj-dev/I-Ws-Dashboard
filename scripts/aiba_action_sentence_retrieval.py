#!/usr/bin/env python3
"""High-coverage source-assertion evidence retrieval; NOT event extraction.

This research-only second lane complements AIBA's strict subject/action/object
extractor. It nominates *literal source sentences* about actions or threatened
actions for human review, preserving original offsets and modality caveats.
No actor, culprit, incident site, independent corroboration, event merge or
warning status is inferred from the text. Default evaluation is DEV ONLY.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from scripts.aiba_real_report_eval import read_jsonl, validate_reports
from behavioral_claim_extraction import extract_report

SCHEMA = "aiba.action-sentence-retrieval-shadow.v1"
MAX_REPORTS = 250
MAX_SENTENCES_PER_REPORT = 24
MAX_SENTENCE_CHARS = 850
SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]|$)")
ACTION = re.compile(
    r"\b(?:struck|strikes?|strike|attacks?|attacked|attacking|"
    r"shot\s+down|shoot(?:ing)?\s+down|shoots\s+down|"
    r"intercept(?:ed|ing|ion|ions)?|destroy(?:ed|ing|s)?|"
    r"neutralis(?:ed|ing|e|es)|neutraliz(?:ed|ing|e|es)|"
    r"bomb(?:ed|ing|s)?|shell(?:ed|ing|s)?|"
    r"target(?:ed|ing|s)?|launched|fired|seized|detained|"
    r"killed|conducted\s+(?:air\s+)?strikes?|carried\s+out\s+(?:air\s+)?strikes?)\b",
    re.I)
DIRECT = re.compile(
    r"\b(?:struck|attacked|shot\s+down|intercepted|destroyed|"
    r"neutralised|neutralized|bombed|shelled|seized|detained|killed)\b",
    re.I)
NEGATION = re.compile(r"\b(?:did not|didn't|not|never|denied|refuted|"
                      r"falsely claimed|no evidence|untrue|false allegation)\b", re.I)
FUTURE = re.compile(r"\b(?:will|would|could|might|may\s+(?:be|have)|"
                    r"plans?\s+to|expected\s+to|set\s+to|aims?\s+to|"
                    r"scheduled\s+to|intended\s+to|threatened\s+to)\b", re.I)
EXERCISE = re.compile(r"\b(?:exercise|exercises|trial|trials|testing|"
                      r"test\s+range|training|simulation|simulated)\b", re.I)
ATTRIBUTION = re.compile(r"\b(?:reportedly|allegedly|according\s+to|"
                         r"claimed|claims|reported|sources\s+said)\b", re.I)
POLICY = re.compile(r"\b(?:legislation|recruitment|housing|contracts?|"
                    r"capability|investment|procurement|strategy|"
                    r"programme|program|reform|review)\b", re.I)


def _modality(sentence):
    flags = []
    for name, pattern in (
        ("negated_or_contested_language", NEGATION),
        ("future_conditional_or_planned_language", FUTURE),
        ("exercise_training_or_test_context", EXERCISE),
        ("attributed_or_alleged_language", ATTRIBUTION),
        ("policy_or_capability_context", POLICY),
    ):
        if pattern.search(sentence):
            flags.append(name)
    return flags


def retrieve(row):
    """Literal offset-preserving candidate sentences in a supplied report."""
    if not isinstance(row, dict):
        return {"status": "abstained", "reason": "invalid_record", "candidates": []}
    source = row.get("source_text")
    if not isinstance(source, str) or not source.strip():
        return {"status": "abstained", "reason": "source_body_unavailable", "candidates": []}
    if len(source) > 12000:
        return {"status": "abstained", "reason": "source_body_over_limit", "candidates": []}
    candidates = []
    total_eligible = 0
    for match in SENTENCE.finditer(source):
        text = match.group()
        s = text.strip()
        if not 20 <= len(s) <= MAX_SENTENCE_CHARS:
            continue
        if not ACTION.search(s):
            continue
        total_eligible += 1
        if len(candidates) >= MAX_SENTENCES_PER_REPORT:
            continue
        offset = match.start() + len(text) - len(text.lstrip())
        span = {"start": offset, "end": offset + len(s), "text": s}
        if source[span["start"]:span["end"]] != s:
            raise ValueError("candidate evidence span mismatch")
        flags = _modality(s)
        uid = hashlib.sha256(
            (row["id"] + "\x1f" + str(offset) + "\x1f" + s).encode()).hexdigest()[:24]
        candidates.append({
            "candidate_id": uid,
            "status": "unreviewed_source_action_language",
            "evidence_span": span,
            "action_terms": list(dict.fromkeys(x.lower() for x in ACTION.findall(s)))[:8],
            "has_direct_action_verb": bool(DIRECT.search(s)),
            "modality_flags": flags,
            "claim_verified": False, "event_occurrence_verified": False,
            "actor_attributed": False,
            "event_time_inferred": False, "event_site_inferred": False,
            "independent_corroboration_established": False,
            "warning_level_change": False,
        })
    return {"status": "source_sentence_candidates_unreviewed" if candidates else "abstained",
            "reason": None if candidates else "no_action_language_found",
            "observation_id": row.get("id"), "source_url": row.get("source_url"),
            "sampling_stratum": row.get("sampling_stratum"),
            "split": row.get("split"),
            "candidate_count": len(candidates),
            "eligible_sentence_count": total_eligible,
            "candidate_cap_reached": total_eligible > MAX_SENTENCES_PER_REPORT,
            "candidates": candidates, "warning_level_change": False}


def build(reports, *, only_development=True):
    validate_reports(reports)
    if len(reports) > MAX_REPORTS:
        raise ValueError("sentence retrieval report cap exceeded")
    subset = [r for r in reports if not only_development or r.get("split") == "development"]
    results = []
    by_stratum = Counter()
    by_stratum_reports = Counter()
    by_modality = Counter()
    default_claims = 0
    source_reports_with_candidates = 0
    for r in subset:
        result = retrieve(r)
        results.append(result)
        by_stratum_reports[str(r.get("sampling_stratum") or "unknown")] += 1
        by_stratum[str(r.get("sampling_stratum") or "unknown")] += result.get("candidate_count", 0)
        default_claims += len(extract_report(r).get("claims", []))
        source_reports_with_candidates += bool(result.get("candidates"))
        for c in result.get("candidates", []):
            by_modality.update(c["modality_flags"] or ["no_explicit_modality_flag"])
    return {
        "schema": SCHEMA,
        "evaluation_split": "development_only" if only_development else "all_splits_explicitly_requested",
        "report_count": len(subset),
        "reports_with_candidate_sentences": source_reports_with_candidates,
        "candidate_sentence_count": sum(len(r.get("candidates", [])) for r in results),
        "baseline_structured_claim_count": default_claims,
        "candidate_sentences_by_sampling_stratum": dict(sorted(by_stratum.items())),
        "reports_by_sampling_stratum": dict(sorted(by_stratum_reports.items())),
        "modality_flag_counts": dict(sorted(by_modality.items())),
        "reports": results,
        "human_ground_truth_labels_created": 0,
        "event_identities_verified": 0, "automatic_event_merges": 0,
        "automatic_alerts_created": 0, "warning_level_change": False,
        "limitations": [
            "This is a high-recall lexical candidate retrieval lane, not actor-action-object extraction.",
            "Action words can describe forecasts, quotations, exercises, policy or attacks in other times.",
            "Sentence-level counts are NOT recall or detection success without independent annotations.",
            "Default runs on development only to preserve heldout evaluation integrity.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reports", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--include-heldout", action="store_true",
                   help="Only use after freezing evaluation predictions and human labels")
    args = p.parse_args()
    result = build(read_jsonl(args.reports), only_development=not args.include_heldout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output.chmod(0o600)
    print(json.dumps({k: v for k, v in result.items() if k != "reports"}, indent=2))


if __name__ == "__main__":
    main()
