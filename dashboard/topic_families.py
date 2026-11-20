"""Analytical *topic* families: similar reports, not merged incidents.

A shared country, source class and explicit operational activity can be a useful
analytical reading group even when dates, polygons and individual notices differ.
Topic membership is NOT independent corroboration or evidence of one event.

Only source-declared country headings in official restriction notices qualify.
Ambiguous titles remain original source-root candidates. Notice IDs/URLs remain
intact; all eligible evidence appears in notice-level nested drilldowns.
"""
from __future__ import annotations

from collections import defaultdict
import datetime as dt
import hashlib
import re

try:
    from .evidence_facets import facets, qualified_metric
except ImportError:
    from evidence_facets import facets, qualified_metric

# An explicit positive allowlist prevents a headline's first clause (a port,
# region, publisher or phenomenon) being silently treated as a country.
# Extend via source-adapter evidence and tests, not free-form text similarity.
COUNTRIES = frozenset(name.replace("_", " ") for name in (
    "Denmark Norway Sweden Finland Iceland Germany Poland Netherlands Belgium "
    "France Spain Portugal Italy Greece Turkey Ukraine Russia Belarus Estonia "
    "Latvia Lithuania Romania Bulgaria Croatia Albania Montenegro Slovenia "
    "Slovakia Hungary Serbia Ireland Austria Switzerland Cyprus Malta "
    "Japan China Taiwan Philippines Indonesia Malaysia Singapore Thailand "
    "Vietnam India Pakistan Bangladesh Sri_Lanka Myanmar Cambodia "
    "Australia New_Zealand Canada Mexico Brazil Argentina Chile Peru "
    "Colombia Venezuela Morocco Algeria Tunisia Egypt Libya Kenya Tanzania "
    "Mozambique Angola Namibia Nigeria Ghana Senegal South_Africa "
    "Saudi_Arabia United_Arab_Emirates Iran Iraq Israel Jordan Oman Qatar "
    "Bahrain Kuwait Yemen South_Korea North_Korea United_States United_Kingdom"
).split())
TITLE_COUNTRY = re.compile(r"^([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,3})\.\s")
FIRING = re.compile(r"\b(?:firing exercises?|gunnery practice|live[- ]fire exercises?|weapons? firing exercises?)\b", re.I)

TOPIC_MAX_NOTICES = 160
TOPIC_MAX_SOURCE_ROWS = 550
TOPIC_MAX_SOURCE_PER_NOTICE = 130
TOPIC_MAX_WINDOWS_PER_NOTICE = 30


def topic_key(row):
    """Return (country, stable activity slug) from explicit official metadata."""
    if (row.get("source_family") != "maritime_restriction" or
            row.get("source_kind") != "official_restriction_notice"):
        return None
    title = row.get("title")
    if not isinstance(title, str):
        return None
    match = TITLE_COUNTRY.match(title)
    if not match or match.group(1) not in COUNTRIES:
        return None
    if FIRING.search(title):
        return match.group(1), "maritime-firing-exercises"
    return None


def family_id(country, activity):
    key=f"analytical_topic:v1:{country.casefold()}:{activity}"
    return "family:"+hashlib.sha256(key.encode()).hexdigest()[:20]


def activity_label(slug):
    return {"maritime-firing-exercises": "maritime firing exercises"}[slug]


def parse_at(value):
    if not isinstance(value,str):
        return None
    try:
        x=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return x.astimezone(dt.timezone.utc) if x.tzinfo else None
    except ValueError:
        return None


def region_from_title(title):
    # Geographical text in notices is descriptive, not an event-site assertion.
    pieces=title.split(". ")
    if len(pieces)<3:
        return "Area not specified"
    text=pieces[1].strip().strip(".")
    return text[:110] or "Area not specified"


def build_topics(rows, now, source_health=None):
    """Return (analytical topics, roots eligible for hiding in compact triage).

    All original records remain in archived evidence and nested notice groups.
    No claim is made that notice fragments are independent corroboration.
    """
    by_topic=defaultdict(list)
    all_by_root=defaultdict(set)
    for row in rows:
        all_by_root[row["information_root"]].add(row["id"])
        found=topic_key(row)
        if found:
            by_topic[found].append(row)
    topics=[]
    covered=set()
    for (country,activity),members in sorted(by_topic.items()):
        # A single isolated observation is still visible in the ordinary
        # source-root lane. One multi-fragment official notice may form a
        # subject family, because the reader should not see 10 duplicate rows.
        if len(members)<2:
            continue
        by_notice=defaultdict(list)
        for row in members:
            by_notice[row["source_url"]].append(row)
        original_notice_count=len(by_notice)
        source_count=len(members)
        time_first=min(parse_at(x["first_observed_at"]) for x in members)
        time_last=max(parse_at(x["first_observed_at"]) for x in members)
        if time_last>now:
            continue
        if now-time_last<=dt.timedelta(hours=36):
            lifecycle="emerging"
        elif now-time_last<=dt.timedelta(days=14):
            lifecycle="monitoring"
        else:
            lifecycle="quiet"
        notices=[]
        for url,fragments in by_notice.items():
            fragments.sort(key=lambda r:(r["first_observed_at"],r["id"]),reverse=True)
            latest=fragments[0]
            windows=sorted({
                (r.get("scheduled_valid_from") or "", r.get("scheduled_valid_until") or "")
                for r in fragments if r.get("scheduled_valid_from") or r.get("scheduled_valid_until")
            })
            notice={
                "id": "notice:"+hashlib.sha256(url.encode()).hexdigest()[:20],
                "title": latest["title"], "source_url":url,
                "area_label":region_from_title(latest["title"]),
                "first_observed_at":min(r["first_observed_at"] for r in fragments),
                "last_new_observation_at":max(r["first_observed_at"] for r in fragments),
                "source_record_count":len(fragments),
                "information_root_count":len({r["information_root"] for r in fragments}),
                "publisher_names":sorted({r["provider"] for r in fragments if r.get("provider")}),
                "validity_windows":[{"from":v[0] or None,"until":v[1] or None}
                                    for v in windows[:TOPIC_MAX_WINDOWS_PER_NOTICE]],
                "validity_windows_truncated":len(windows)>TOPIC_MAX_WINDOWS_PER_NOTICE,
                "records":fragments[:TOPIC_MAX_SOURCE_PER_NOTICE],
                "records_truncated":len(fragments)>TOPIC_MAX_SOURCE_PER_NOTICE,
            }
            notices.append(notice)
        notices.sort(key=lambda n:(n["last_new_observation_at"],n["id"]),reverse=True)
        topic_roots={r["information_root"] for r in members}
        topic_ids={r["id"] for r in members}
        # Suppress original top-level root cards only when *all* their
        # observations appear in this topic. If a root is mixed, leave it
        # available separately to prevent concealing unrelated material.
        for root in topic_roots:
            if all_by_root[root].issubset(topic_ids):
                covered.add(root)
        publishers=sorted({r["provider"] for r in members if r.get("provider")})
        topics.append({
            "id":family_id(country,activity),
            "kind":"analytical_topic_family",
            "title":f"{country} · {activity_label(activity)}",
            "activity":activity,
            "country":country,
            "state":lifecycle,"new_activity":lifecycle=="emerging",
            "first_observed_at":time_first.isoformat(),
            "last_observed_at":time_last.isoformat(),
            "notice_count":original_notice_count,
            "source_record_count":source_count,
            "information_root_count":len(topic_roots),
            "source_families":["maritime_restriction"],
            "providers":publishers,"case_hints":sorted({
                r["case_hint"] for r in members if r.get("case_hint")
            }),
            "geography_label":f"{country} · multiple official notice areas",
            "geography_precision":"country_in_official_notice_title_not_incident_location",
            "map_eligible":False,
            "source_independence_established":False,
            "event_occurrence_verified":False,"warning_approved":False,
            "corroboration":{
                "status":"same_issuer_topic_not_independent_confirmation",
                "independent_roots":None,
                "notice_count":original_notice_count,
                "issuer_count":len(publishers),
            },
            "anomaly_metric":qualified_metric(members),
            "evidence_facets":facets(members,source_health),
            "notice_groups":notices[:TOPIC_MAX_NOTICES],
            "notice_groups_truncated":len(notices)>TOPIC_MAX_NOTICES,
            "sources":members[:min(TOPIC_MAX_SOURCE_ROWS,len(members))],
            "sources_truncated":source_count>TOPIC_MAX_SOURCE_ROWS,
            "reason":"Analytical reading group: same source-declared country, maritime restriction class and firing-exercise activity. Distinct dates and areas remain separate notices; one issuer is not independent corroboration.",
        })
    return topics, covered
