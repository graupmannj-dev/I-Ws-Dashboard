"""Join bounded original-source inspection receipts to CAIRN's rule-screen.

No changes to numeric rule counts, signed ordinal balances or warnings. Each
source link gets a linked original-document receipt or explicit not-inspected
status. A matching title/signpost is not verified action/attribution.
"""
from __future__ import annotations
from copy import deepcopy

SCHEMA = "cairn.source-inspection.v1"


def attach(screen, source_receipts):
    result = deepcopy(screen)
    valid = (isinstance(source_receipts, dict) and
             source_receipts.get("schema") == SCHEMA and
             isinstance(source_receipts.get("inspections"), list))
    data = source_receipts["inspections"] if valid else []
    receipt_index = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        key = (row.get("case_id"), row.get("source_url"))
        if not key[0] or not key[1] or key in receipt_index:
            continue
        receipt_index[key] = row
    count_with_eligible = 0
    for cid, case in result.get("cases", {}).items():
        inspected = unread = linked = geographically_attributed = 0
        location_unknown = 0
        for rule in case.get("discriminators", []):
            for source in rule.get("sources", []):
                linked += 1
                receipt = receipt_index.get((cid, source.get("source_url")))
                if not receipt:
                    source["original_document_review"] = {
                        "status": "not_selected_for_bounded_fetch",
                        "event_verified": False,
                        "geography_verified": False,
                    }
                    unread += 1
                    continue
                if receipt.get("status") != "document_text_inspected":
                    source["original_document_review"] = {
                        "status": receipt.get("status", "source_unavailable"),
                        "reason": receipt.get("reason"),
                        "event_verified": False, "geography_verified": False,
                    }
                    unread += 1
                    continue
                loc = receipt.get("document_inspection", {}).get("case_attribution", {})
                rules = receipt.get("document_inspection", {}).get("source_text_rule_mentions", [])
                negated = receipt.get("document_inspection", {}).get("qualified_or_disputed_rule_mentions", [])
                text_support = ("same_rule_literal_language_in_body" if rule.get("id") in rules
                                else "qualified_or_disputed_in_body" if rule.get("id") in negated
                                else "no_matching_rule_language_found_in_body")
                source["original_document_review"] = {
                    "status": "document_text_inspected",
                    "text_rule_relation": text_support,
                    "source_text_sha256": receipt["document_inspection"].get("source_text_sha256"),
                    "source_text_chars_inspected": receipt["document_inspection"].get("source_text_chars_inspected"),
                    "geographic_attribution": loc,
                    "source_url": receipt["source_url"],
                    "event_verified": False, "geography_verified": False,
                }
                inspected += 1
                if loc.get("source_text_location_asserted"):
                    geographically_attributed += 1
                else:
                    location_unknown += 1
        archived = [r for r in data if isinstance(r, dict) and r.get("case_id") == cid]
        archived_views = []
        for r in archived:
            body = r.get("document_inspection") or {}
            geo = body.get("case_attribution") or {}
            archived_views.append({
                "title": r.get("title"), "source_url": r.get("source_url"),
                "first_observed_at": r.get("first_observed_at"),
                "status": r.get("status"),
                "source_rule": r.get("rule"), "reason": r.get("reason"),
                "source_text_location": geo.get("named_place"),
                "geography_status": geo.get("status"),
                "source_text_rule_mentions": body.get("source_text_rule_mentions", []),
                "event_verified": False, "location_verified": False,
            })
        case["original_source_inspection"] = {
            "status": "bounded_receipts_available" if valid else "not_collected_this_build",
            "archived_original_documents": archived_views,
            "source_rule_links_total": linked,
            "source_rule_links_inspected": inspected,
            "source_rule_links_not_inspected": unread,
            "rule_links_with_textual_place_mention": geographically_attributed,
            "rule_links_without_textual_event_location": location_unknown,
            "independent_event_confirmations": 0,
            "event_locations_verified": 0,
            "source_text_publication": "metadata_and_short_excerpt_only",
            "interpretation": ("Document retrieval verifies document text availability only. "
                "Reported locality in an action sentence is NOT a verified event site. "
                "Rules remain unverified, and source restrictions/non-HTML pages abstain."),
        }
        if inspected:
            count_with_eligible += 1
    result["original_source_inspection"] = {
        "status": "receipt_linked" if valid else "not_collected_this_build",
        "distinct_source_documents_attempted": source_receipts.get(
            "unique_source_documents_attempted", 0) if valid else None,
        "documents_inspected": source_receipts.get("status_counts", {}).get(
            "document_text_inspected", 0) if valid else None,
        "cases_with_inspected_source": count_with_eligible,
        "body_text_saved_or_published": False,
        "auto_confirmed_events": 0,
    }
    return result
