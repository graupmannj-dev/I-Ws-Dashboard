"""Source-grounded, time-decaying investigative clusters for Atlas.

These are NOT automatically classified hotspots, threats, or independently
confirmed events. The only map coordinates emitted for standing cases are
existing approximate theater anchors; other clusters remain unlocated.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import re
from collections import defaultdict

MAX_BINS = 36
MAX_EVIDENCE = 6
DAYS_RETAIN = 120
ACTIVE_HOURS = 72
NEW_HOURS = 36
WATCH_DAYS = 14
STOPWORDS = {
    "reports", "report", "official", "officials", "claims", "attack", "attacks",
    "strike", "strikes", "military", "forces", "force", "november", "confirms",
    "confirmed", "source", "sources", "after", "before", "amid", "tensions",
    "threat", "threats", "damage", "damaged", "closure", "closes", "closed",
    "warns", "warning", "follows", "against", "russian", "russia", "ukrainian",
    "ukraine", "maritime", "missile", "missiles", "region", "reported",
    "defence", "defense", "following", "northern", "southern", "western",
    "eastern", "security", "more", "near", "across", "with", "from",
    "into", "this", "that", "have", "been", "about", "under",
}

def parse(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def tokens(title):
    return set(x for x in re.findall(r"[a-zA-Z]{4,}", title.lower())
               if x not in STOPWORDS)


def _identity(key):
    return "dynamic:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:18]


def _assemble(key, label, rows, now, anchors, case_id=None, kind="case"):
    unique = {}
    for row in rows:
        root = row.get("information_root")
        stamp = parse(row.get("first_collected_at"))
        if not isinstance(root, str) or not root or stamp is None:
            continue
        if stamp > now or now-stamp > dt.timedelta(days=DAYS_RETAIN):
            continue
        prior = unique.get(root)
        if prior is None or stamp < parse(prior["first_collected_at"]):
            unique[root] = row
    if len(unique) < 2:
        return None
    ordered = sorted(unique.values(),
                     key=lambda x: parse(x["first_collected_at"]), reverse=True)
    within72 = [x for x in ordered if now-parse(x["first_collected_at"]) <=
                dt.timedelta(hours=ACTIVE_HOURS)]
    within14 = [x for x in ordered if now-parse(x["first_collected_at"]) <=
                dt.timedelta(days=WATCH_DAYS)]
    latest = parse(ordered[0]["first_collected_at"])
    active = len(within72) >= 2 and now-latest <= dt.timedelta(hours=NEW_HOURS)
    if active:
        state = "emerging"
    elif len(within14) >= 2 and now-latest <= dt.timedelta(days=WATCH_DAYS):
        state = "monitoring"
    else:
        state = "quiet"
    anchor = anchors.get(case_id) if case_id else None
    sources = [{
        "title": x["title"], "publisher": x["publisher"],
        "source_url": x["source_url"], "first_observed_at": x["first_collected_at"],
        "published_at": x.get("published_at"), "information_root": x["information_root"],
    } for x in ordered[:MAX_EVIDENCE]]
    return {
        "id": _identity(key), "key": key, "title": label,
        "case_id": case_id, "kind": kind, "state": state,
        "new_activity": active, "first_observed_at": min(
            x["first_collected_at"] for x in unique.values()),
        "last_observed_at": ordered[0]["first_collected_at"],
        "total_distinct_information_roots": len(unique),
        "active_72h_roots": len(within72),
        "sources": sources,
        "source_independence_verified": False, "event_occurrence_verified": False,
        "reviewed_warning": False, "automatic_severity_change": False,
        "lat": anchor[0] if anchor else None,
        "lon": anchor[1] if anchor else None,
        "geography_note": ("Approximate standing-theater reference only; NOT an incident location."
                           if anchor else "No source-verified map coordinates; list-only investigative bin."),
        "reason": ("At least two distinct information roots share a declared case label."
                   if kind == "case" else
                   "At least two distinct information roots contain matching distinctive title terms. This may be related reporting, not the same event."),
    }


def build(records, now, anchors, labels):
    """Identify distinct-root overlap without assigning inferred locations.

    Case hints are explicit intake metadata, and may reference a region not in
    the ten curated dossiers. Those unknown cases remain list-only.
    Title-overlap candidates are only an unlocated investigative fallback.
    """
    by_case = defaultdict(list)
    unassigned = []
    for x in records:
        if not isinstance(x, dict) or not parse(x.get("first_collected_at")):
            continue
        case = x.get("case_id")
        if isinstance(case, str) and case:
            by_case[case].append(x)
        else:
            unassigned.append(x)
    bins = []
    for case, items in sorted(by_case.items()):
        label = labels.get(case) or case.replace("_", " ").title()
        candidate = _assemble("case:"+case, label, items, now, anchors, case_id=case)
        if candidate:
            bins.append(candidate)
    # An unlocated place/topic can emerge even without one of the established
    # case IDs. Two distinctive shared words and two independent information
    # roots are necessary; never invent a marker from a title alone.
    pairs = defaultdict(list)
    for record in unassigned:
        words = sorted(tokens(record.get("title") or ""))[:16]
        for a,b in itertools.combinations(words,2):
            pairs[(a,b)].append(record)
    claimed = set()
    ranked = sorted(pairs.items(),key=lambda pair:
                    (-len({r.get("information_root") for r in pair[1]}), pair[0]))
    for (a,b),items in ranked:
        unique_roots = {r.get("information_root") for r in items}
        if len(unique_roots) < 2 or len(bins) >= MAX_BINS:
            continue
        # Avoid dozens of near-identical bins for the same reporting bundle.
        if len(unique_roots & claimed) >= 2:
            continue
        candidate = _assemble("topic:"+a+":"+b, a.title()+" / "+b.title(),
                              items, now, anchors, kind="unlocated_topic")
        if candidate:
            bins.append(candidate)
            claimed.update(unique_roots)
    rank = {"emerging":0, "monitoring":1, "quiet":2}
    bins.sort(key=lambda x:(rank[x["state"]],x["last_observed_at"],x["id"]),
              reverse=False)
    # Rank state first, and most recent inside each state.
    result=[]
    for status in ("emerging","monitoring","quiet"):
        candidates=[x for x in bins if x["state"]==status]
        candidates.sort(key=lambda x:x["last_observed_at"],reverse=True)
        result.extend(candidates)
    return {
        "schema": "aiba.dynamic-evidence-bins.v1",
        "status": "investigatory_overlap_not_verified_events",
        "retention_days": DAYS_RETAIN,
        "source_independence_proven": False,
        "automatic_warning_count": 0,
        "bins": result[:MAX_BINS],
        "emerging_count": sum(b["state"]=="emerging" for b in result),
        "monitoring_count": sum(b["state"]=="monitoring" for b in result),
        "quiet_count": sum(b["state"]=="quiet" for b in result),
        "truncated": len(result)>MAX_BINS,
    }
