"""Conservative, source-aware possible event/report links.

Distinct concepts:
* Publisher/reporting office location is NOT reported event location.
* Exact same source document is ONE underlying source, not corroboration.
* Similar reporting can suggest a common event, not demonstrate it.
* Two different event locations can be related reporting about distinct events.
No warning, actor attribution, geocoded pin or independent source claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import datetime as dt
import hashlib
import math
import re
from urllib.parse import urlsplit, parse_qsl, urlencode

MAX_SOURCE_RECORDS=2000
MAX_DISPLAY_GROUPS=20
MAX_COMPARISONS=90000
MAX_DOC_MEMBERS=8
MAX_SEMANTIC_HOURS=48
MAX_RELATED_HOURS=72
CLOSE_EVENT_KM=75
MAX_CONFLICT_EVENT_KM=150
SCHEMA="aiba.report-event-resolution-shadow.v1"
STATUS={
    "shared_source_document_unreviewed",
    "possible_same_event_unreviewed",
    "related_reporting_unreviewed",
}
NOISE={
    "the","a","an","and","or","for","from","to","of","in","at","on",
    "with","as","by","is","are","after","before","into","over","under",
    "about","reported","reports","reporting","says","said","new","latest",
    "now","today","this","that","here","there","near","update","updated",
    "official","notice","notification","warning","noticearea",
    "country","regional","source","report","reuters","ap","associated",
    "press","faa","tfr","ioda","navarea","theory","will","would",
    "may","can","expected","possible","amid","during","its",
    "following","months","hours","monday","tuesday","wednesday",
    "thursday","friday","saturday","sunday","november","december",
    "january","february","march","april","june","july","august",
    "september","october","year","utc","2026","2025",
}
# Typical high-frequency generic categories do NOT anchor individual events.
GENERIC={"russia","ukraine","china","taiwan","israel","iran","united","states",
         "military","government","security","conflict","war","shipping",
         "market","maritime","aircraft","flight","region","border"}


def tokens(value):
    if not isinstance(value,str):
        return set()
    return {v for v in re.findall(r"[a-z0-9]{3,}",value.lower())
            if v not in NOISE and not v.isdecimal()}


def utc(value):
    if not isinstance(value,str) or len(value)>40:return None
    try:
        parsed=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:return None
    if parsed.tzinfo is None or parsed.utcoffset()!=dt.timedelta(0):return None
    return parsed.astimezone(dt.timezone.utc)


def observed_time(row):
    for key in ("event_at","source_published_at","first_observed_at"):
        v=utc(row.get(key))
        if v:return v
    return None


def report_document(row):
    """Only source-specific links count; IODA/official homepages do not."""
    raw=row.get("source_url")
    if not isinstance(raw,str) or len(raw)>2000:return None
    try: parts=urlsplit(raw)
    except ValueError:return None
    if parts.scheme!="https" or not parts.hostname or parts.username or parts.password:return None
    path=parts.path.rstrip("/")
    fragment=parts.fragment.rstrip("/")
    # SPA source message URL fragments are document-specific. Preserve them.
    specific=bool(path and len(path)>5) or bool(fragment and len(fragment)>7)
    if not specific:return None
    query=urlencode(sorted((k,v) for k,v in parse_qsl(parts.query)
                            if k.lower() not in {"utm_source","utm_medium","utm_campaign",
                                                   "utm_content","fbclid","gclid","oc"}))
    return parts.hostname.lower()+path+("?"+query if query else "")+("#"+fragment if fragment else "")


def reported_site(row):
    """Only an explicit provenance-marked EVENT site, never publisher city."""
    obj=row.get("reported_event_location")
    if not isinstance(obj,dict) or obj.get("role")!="reported_event_site" or (
        obj.get("basis") not in {"source_declared","source_record_geometry"}
    ):
        return None
    lat,lon=obj.get("lat"),obj.get("lon")
    if (type(lat) not in (int,float) or type(lon) not in (int,float) or
        not math.isfinite(lat) or not math.isfinite(lon) or
        not -90<=lat<=90 or not -180<=lon<=180):
        return None
    return float(lat),float(lon)


def kilometers(a,b):
    la1,lo1=a;la2,lo2=b
    phi1,phi2=math.radians(la1),math.radians(la2)
    dphi=phi2-phi1;dlambda=math.radians(lo2-lo1)
    h=math.sin(dphi/2)**2+math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 12742*math.asin(min(1,math.sqrt(h)))


def shared_subject(a,b):
    ta,tb=tokens(a.get("title")),tokens(b.get("title"))
    common=ta&tb
    if len(common)<3:return None
    distinctive=common-GENERIC
    if len(distinctive)<2:return None
    score=len(common)/len(ta|tb) if ta|tb else 0
    return {"similarity":round(score,3),"common_terms":sorted(distinctive)[:6],
            "common_count":len(common)}


def safe_link(row):
    return {
        "observation_id":str(row.get("id") or "")[:140],
        "title":str(row.get("title") or "")[:240],
        "source_family":str(row.get("source_family") or "")[:80],
        "provider":str(row.get("provider") or "")[:80],
        "source_url":row.get("source_url") if isinstance(row.get("source_url"),str)
                     and row["source_url"].startswith("https://") else None,
        "first_observed_at":row.get("first_observed_at"),
        "source_published_at":row.get("source_published_at"),
        "geography":row.get("geography"),
        "reporting_origin":str(row.get("reporting_origin") or "")[:100] or None,
        # NEVER export event-site coordinate as a map pin from this candidate
        # matching layer. A source-asserted site may be imprecise.
        "status":"unreviewed_source_report",
    }


def match_pair(a,b):
    """Return an unreviewed possible same event / related subject, or None."""
    doca,docb=report_document(a),report_document(b)
    if doca and doca==docb:
        return None  # clustered by document before pairwise matching
    sa,sb=observed_time(a),observed_time(b)
    if not sa or not sb:return None
    delta=abs((sa-sb).total_seconds())/3600
    if delta>MAX_RELATED_HOURS:return None
    sub=shared_subject(a,b)
    if not sub:return None
    # Generic text overlap must not manufacture a match.
    if sub["similarity"]<0.48 or sub["common_count"]<4:return None
    pos1,pos2=reported_site(a),reported_site(b)
    distance=kilometers(pos1,pos2) if pos1 and pos2 else None
    same_origin=bool(a.get("information_root") and
                     a.get("information_root")==b.get("information_root"))
    high_similarity=sub["similarity"]>=0.72 and sub["common_count"]>=5
    close_event=distance is not None and distance<=CLOSE_EVENT_KM
    far_event=distance is not None and distance>MAX_CONFLICT_EVENT_KM
    # Two independently reported sites far apart cannot be declared one
    # local event, even when publishers choose near-identical headlines.
    if far_event:
        kind="related_reporting_unreviewed" if high_similarity else None
        reason="substantive_overlap_but_distinct_reported_event_sites"
    elif delta<=MAX_SEMANTIC_HOURS and (high_similarity or (
            close_event and sub["similarity"]>=0.55)):
        kind="possible_same_event_unreviewed"
        reason=("similar_content_and_nearby_reported_event_sites" if close_event else
                "similar_content_and_time_event_site_unverified")
    elif high_similarity:
        kind="related_reporting_unreviewed"
        reason="similar_reporting_outside_same_event_time_gate"
    else:
        return None
    if not kind:return None
    return {
        "status":kind,"match_basis":reason,
        "semantic_similarity":sub["similarity"],
        "shared_content_terms":sub["common_terms"],
        "first_observation_separation_hours":round(delta,2),
        "reported_event_site_separation_km":round(distance,1) if distance is not None else None,
        "reported_event_site_comparison_available":distance is not None,
        "reporting_origin_used_as_event_site":False,
        "shared_information_root":same_origin,
        "independent_corroboration_established":False,
        "source_reports":[safe_link(a),safe_link(b)],
        "review_requirements":[
            "Confirm both items describe the same actor/action/incident, not just the same topic",
            "Distinguish publisher location from explicitly reported event location",
            "Check copied/syndicated primary sources and actual observation times",
            "Review contradictory event dates, locations and alternative interpretations",
        ],
        "warning_level_change":False,
    }


def build(recent, now=None):
    """A bounded source report-entity resolution layer, not threat fusion."""
    records=sorted((r for r in recent.values() if isinstance(r,dict)),
                   key=lambda r:(r.get("first_observed_at") or "",r.get("id") or ""),
                   reverse=True)
    inputs=len(records)
    truncated=inputs>MAX_SOURCE_RECORDS
    records=records[:MAX_SOURCE_RECORDS]
    docs=defaultdict(list)
    for row in records:
        d=report_document(row)
        if d:docs[d].append(row)
    documents=[]
    for doc,members in sorted(docs.items()):
        if len(members)<2:continue
        members.sort(key=lambda x:(x.get("first_observed_at") or "",x.get("id") or ""),reverse=True)
        # Hash keys, not raw query strings or long URL secrets.
        documents.append({
            "id":"document:"+hashlib.sha256(doc.encode()).hexdigest()[:20],
            "status":"shared_source_document_unreviewed",
            "match_basis":"same_specific_source_document_not_independent_observations",
            "source_reports":[safe_link(x) for x in members[:MAX_DOC_MEMBERS]],
            "report_count_total":len(members),
            "source_reports_truncated":len(members)>MAX_DOC_MEMBERS,
            "shared_information_root":True,
            "independent_corroboration_established":False,
            "reporting_origin_used_as_event_site":False,
            "warning_level_change":False,
            "review_requirements":[
                "Verify document identity and any underlying primary source",
                "Do not treat geometries/sections of one notice as independent events",
            ]
        })
    # Compare cross-document pairs within time/topic blocks. The strict
    # cap is explicit, never silently described as exhaustive.
    checked=0; comparisons_capped=False
    proposals=[]
    for i,a in enumerate(records):
        for b in records[i+1:]:
            if checked>=MAX_COMPARISONS:
                comparisons_capped=True
                break
            checked+=1
            da,db=report_document(a),report_document(b)
            if da and db and da==db:continue
            match=match_pair(a,b)
            if match:
                match["id"]="relation:"+hashlib.sha256(
                    "|".join(sorted((str(a.get("id")),str(b.get("id"))))).encode()
                ).hexdigest()[:20]
                proposals.append(match)
        if comparisons_capped:break
    # Important: the list is just a sorted shortlist of suggestions.
    proposals.sort(key=lambda p:(p["status"]!="possible_same_event_unreviewed",
                                 -p["semantic_similarity"],
                                 p["first_observation_separation_hours"],p["id"]))
    documents.sort(key=lambda x:(-x["report_count_total"],x["id"]))
    selected_docs=documents[:8]
    selected_pairs=proposals[:MAX_DISPLAY_GROUPS-len(selected_docs)]
    result={
        "schema":SCHEMA,
        "status":"unreviewed_report_relationships_only",
        "records_available":inputs,
        "records_examined":len(records),
        "input_truncated":truncated,
        "pairwise_comparisons_examined":checked,
        "pairwise_comparisons_capped":comparisons_capped,
        "same_document_group_count_total":len(documents),
        "cross_document_relation_count_total":len(proposals),
        "possible_same_event_count_total":sum(
            x["status"]=="possible_same_event_unreviewed" for x in proposals),
        "related_reporting_count_total":sum(
            x["status"]=="related_reporting_unreviewed" for x in proposals),
        "candidate_groups":selected_docs+selected_pairs,
        "candidate_groups_truncated":(
            len(documents)+len(proposals)>len(selected_docs)+len(selected_pairs)),
        "reporting_origins_are_not_event_locations":True,
        "geographic_proximity_only_for_explicit_reported_event_sites":True,
        "source_independence_unverified":True,
        "not_a_preparations_sensor_or_warning":True,
        "automatic_alerts_created":0,
        "automatic_severity_changes":0,
        "forecast_probability":None,
    }
    return result
