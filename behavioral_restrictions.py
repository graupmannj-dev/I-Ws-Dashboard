#!/usr/bin/env python3
"""Map already-collected FAA / Danish authority restrictions into behavioral evidence.

NO new provider queries. Source-defined notice geometries are boundaries of
notices, not locations of military actions, and no geographic country is
inferred from the headline. Versions retain one underlying information root.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from dashboard.live_layer_snapshots import geometry_is_valid, coord

UTC=dt.timezone.utc
SOURCES={"live_airspace":("airspace","faa","airspace_restriction"),
         "live_maritime":("maritime","niord","maritime_restriction")}


def hash_obj(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                            ensure_ascii=False,allow_nan=False).encode()).hexdigest()[:24]


def aware(raw):
    if not isinstance(raw,str):
        return None
    try:
        x=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
    except ValueError:
        return None
    return x.astimezone(UTC) if x.tzinfo else None


def iso(value):
    return value.replace(microsecond=0).isoformat().replace("+00:00","Z")


def geographic_scope(row):
    """Explicit notice geometry only; never invent an incident centroid."""
    geometry=row.get("geometry")
    if geometry is not None:
        if not geometry_is_valid(geometry):
            return None
        kind=geometry["type"]
        digest=hash_obj(geometry)
        return {"key":"source-footprint:"+digest,
                "kind":"source_notice_footprint",
                "label":f"Official {kind} notice area",
                "precision":"provider_defined_notice_boundary_not_event_point",
                "geometry_type":kind,
                "geometry_sha256_prefix":digest,
                "verified_iso":False,
                "latitude":None,"longitude":None}
    lon,lat=row.get("lon"),row.get("lat")
    if coord(lon,lat):
        return {"key":f"source-notice-point:{lat:.5f}:{lon:.5f}",
                "kind":"source_notice_point",
                "label":"Official notice position",
                "precision":"provider_defined_notice_point_not_incident",
                "geometry_type":"Point",
                "geometry_sha256_prefix":None,
                "verified_iso":False,
                "latitude":lat,"longitude":lon}
    return {"key":None,"kind":"unlocated","label":None,
            "precision":"notice_geography_unavailable",
            "geometry_type":None,"geometry_sha256_prefix":None,
            "verified_iso":False,"latitude":None,"longitude":None}


def adapt(mode,row,checked):
    if mode not in SOURCES:
        raise ValueError("Unsupported restrictions mode")
    if not isinstance(row,dict) or not isinstance(row.get("id"),str):
        return None,"invalid_restriction_row"
    layer,provider,family=SOURCES[mode]
    identity=row["id"].strip()
    title=str(row.get("title") or "").strip()
    source_url=row.get("url")
    if not identity or len(identity)>180 or not title or len(title)>240:
        return None,"missing_notice_id_or_title"
    if not isinstance(source_url,str) or len(source_url)>2048:
        return None,"missing_source_https"
    url=urlsplit(source_url)
    if url.scheme!="https" or not url.hostname or url.username or url.password:
        return None,"missing_source_https"
    geography=geographic_scope(row)
    if geography is None:
        return None,"invalid_notice_geometry"
    start=aware(row.get("valid_from"))
    end=aware(row.get("valid_until"))
    if row.get("valid_from") is not None and not start:
        return None,"unparseable_valid_from"
    if row.get("valid_until") is not None and not end:
        return None,"unparseable_valid_until"
    if start and end and end<=start:
        return None,"reversed_validity"
    if start and checked>end if end else False:
        # Expired notices may still be present in the upstream list.
        # Preserve them as reference observations, not fresh in-force restrictions.
        state="expired_present_in_source"
    elif start and start>checked:
        state="scheduled_not_yet_effective"
    elif (start is None or start<=checked) and (end is None or checked<end):
        state="within_published_validity_window_not_verified_active"
    else:
        state="not_verifiably_active"
    # Provider 'date' is a heterogeneous updated-at field. FAA exposes
    # local/naive strings; do not treat that as UTC source publication.
    updated=aware(row.get("date"))
    if updated and updated>checked+dt.timedelta(minutes=5):
        return None,"source_update_in_future"
    semantic={
        "title":title,"valid_from":iso(start) if start else None,
        "valid_until":iso(end) if end else None,
        "geometry_sha":geography["geometry_sha256_prefix"],
        "point_key":geography["key"] if geography["kind"]=="source_notice_point" else None,
        "in_force":bool(row.get("in_force")) if "in_force" in row else None,
    }
    revision=hash_obj(semantic)
    # A changed notice version gets a new record ID but remains the
    # SAME information root. A region containing 20 FAA polygons is
    # not 20 independent explanations.
    rid=f"{provider}:{identity}:{revision}"
    return {
        "id":rid,"provider":provider,"family":family,
        "title":title,"source_url":source_url,
        "source_published_at":None,
        "source_updated_at":iso(updated) if updated else None,
        "event_at":None,"collected_at":iso(checked),
        "first_seen_at":None,
        "root":f"{provider}:{identity}",
        "source_version":revision,
        "geography":geography,
        "scheduled_valid_from":iso(start) if start else None,
        "scheduled_valid_until":iso(end) if end else None,
        "restriction_time_state":state,
        "kind":"official_restriction_notice",
        "claim_level":"official_scheduled_restriction_not_evidence_of_military_preparation",
    },None


def adapt_layer(snapshot,mode):
    if mode not in SOURCES:
        raise ValueError("Unknown provider mode")
    key=SOURCES[mode][0]
    layers=snapshot.get("layers",{}) if isinstance(snapshot,dict) else {}
    layer=layers.get(key,{})
    checked=aware(layer.get("checked_at"))
    if not checked:
        raise ValueError("Restriction snapshot missing provider check timestamp")
    records=layer.get("records")
    if not isinstance(records,list):
        raise ValueError("Restriction layer lacks records list")
    if len(records)>1200:
        raise ValueError("Restriction source exceeds bounded records")
    result=[];reasons={}
    for row in records:
        adapted,error=adapt(mode,row,checked)
        if error:
            reasons[error]=reasons.get(error,0)+1
        else:
            result.append(adapted)
    if reasons and not result and records:
        raise ValueError("All restriction rows failed source/schema checks")
    return result,reasons
