"""CAIRN: bounded official non-Western national observations (no paid keys).

These are independently issued *public authority products*, not a claim that
different publishers independently observed different physical events.
Official warnings are contextual, not automatically military indicators.
"""
from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
import hashlib
import math
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

UTC=dt.timezone.utc
RSS_MODES=frozenset(("bmkg_nowcast","inmet_br","imd_in","saws_za"))
MODES=("bmkg_quake",*sorted(RSS_MODES))
FEEDS={
 "bmkg_quake":"https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json",
 "bmkg_nowcast":"https://www.bmkg.go.id/alerts/nowcast/en",
 "inmet_br":"https://apiprevmet3.inmet.gov.br/avisos/rss",
 "imd_in":"https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml",
 "saws_za":"https://cap-sources.s3.amazonaws.com/za-saws-en/rss.xml",
}
SCOPE={
 "bmkg_quake":"Indonesia BMKG 15 latest magnitude-5+ earthquakes; not global; same physical events may appear in USGS",
 "bmkg_nowcast":"Indonesia BMKG active provincial nowcast RSS, source-reported only; not global",
 "inmet_br":"Brazil INMET official severe-weather RSS notices; provider-listed bounded sample",
 "imd_in":"India Meteorological Department CAP RSS relayed by WMO Alert Hub; India-only, not a second observer",
 "saws_za":"South African Weather Service CAP RSS relayed by WMO Alert Hub; South Africa-only",
}
PUBLISHERS={
 "bmkg_quake":"Indonesia BMKG",
 "bmkg_nowcast":"Indonesia BMKG",
 "inmet_br":"Brazil INMET",
 "imd_in":"India Meteorological Department via WMO",
 "saws_za":"South African Weather Service via WMO",
}
MAX_FEED_ITEMS=500
MAX_OBSERVATIONS=110


def _stamp(value):
    if not isinstance(value,str) or not value.strip():return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        if t.tzinfo is not None:return t.astimezone(UTC)
    except ValueError:pass
    try:
        t=parsedate_to_datetime(value)
        if t and t.tzinfo:return t.astimezone(UTC)
    except (TypeError,ValueError,IndexError,OverflowError):pass
    return None


def _iso(value):
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")


def _clean(value,limit=200):
    return " ".join(str(value or "").split())[:limit]


def _digest(*values):
    return hashlib.sha256("|".join(str(v) for v in values).encode()).hexdigest()[:28]


def _element_text(e,tag):
    """Find direct namespace-agnostic child (RSS or Atom), never broad XPath."""
    for child in e:
        if child.tag.rsplit("}",1)[-1]==tag:
            return _clean(child.text or "",600)
    return ""


def xml_parse(raw):
    """Refuse DTD/entities and oversize payload before calling ElementTree."""
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>4_000_000:
        raise ValueError("Bounded XML feed size exceeded or invalid bytes")
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b",raw,re.I):
        raise ValueError("XML DTD and entities prohibited")
    try:return ET.fromstring(raw)
    except ET.ParseError as exc:raise ValueError("XML feed schema/parser mismatch") from exc


def _entries(data):
    if not isinstance(data,ET.Element):raise ValueError("Expected parsed XML RSS or Atom feed")
    root=data.tag.rsplit("}",1)[-1].casefold()
    if root=="rss":
        channel=next((c for c in data if c.tag.rsplit("}",1)[-1]=="channel"),None)
        if channel is None:raise ValueError("RSS channel missing")
        found=[x for x in channel if x.tag.rsplit("}",1)[-1]=="item"]
    elif root=="feed":  # Atom allowed for alternate national authority catalogs
        found=[x for x in data if x.tag.rsplit("}",1)[-1]=="entry"]
    else:raise ValueError("Expected RSS or Atom root")
    if len(found)>MAX_FEED_ITEMS:raise ValueError("RSS provider supplied too many feed items")
    return found


def _rss_link(item):
    for el in item:
        if el.tag.rsplit("}",1)[-1]=="link":
            return _clean(el.attrib.get("href") or el.text or "",1000)
    return ""


def adapt_quake(data,checked,url,entry):
    """BMKG: M5+ epicenters and magnitudes, original UTC DateTime (not issue time)."""
    events=(data.get("Infogempa") or {}).get("gempa") if isinstance(data,dict) else None
    if not isinstance(events,list):raise ValueError("BMKG quake gempa list schema mismatch")
    if len(events)>50:raise ValueError("BMKG earthquake feed exceeded declared bound")
    result=[]
    for item in events:
        if not isinstance(item,dict):continue
        stamp=_stamp(item.get("DateTime"))
        if not stamp or stamp>checked+dt.timedelta(minutes=5):continue
        coords=item.get("Coordinates")
        if not isinstance(coords,str) or "," not in coords:continue
        try:
            lat,lon=(float(x.strip()) for x in coords.split(",")[:2])
            magnitude=float(item.get("Magnitude"))
        except (ValueError,TypeError):continue
        if not all(math.isfinite(v) for v in (lat,lon,magnitude)) or not (
            -90<=lat<=90 and -180<=lon<=180 and 0<=magnitude<=10):continue
        depth=None
        depth_match=re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*km\s*",str(item.get("Kedalaman") or ""),re.I)
        if depth_match:depth=float(depth_match.group(1))
        title="BMKG earthquake M"+str(magnitude)+" · "+_clean(item.get("Wilayah"),135)
        rid=_digest(_iso(stamp),round(lat,3),round(lon,3),magnitude)
        loc={"kind":"source_reported_earthquake_epicenter_not_threat_site",
             "latitude":round(lat,4),"longitude":round(lon,4),
             "precision":"source_supplied_earthquake_epicenter",
             "key":None,"verified_iso":False}
        row=entry("bmkg_quake",rid,title,url,checked,event_at=_iso(stamp),
                  kind="national_seismic_measurement_context",
                  geo=loc,source_scope=SCOPE["bmkg_quake"],
                  measurement={"name":"earthquake_magnitude","value":magnitude,
                               "unit":"source_reported_magnitude",
                               "depth_km":depth,"baseline_status":"not_calibrated",
                               "possible_same_physical_event_as_usgs":True})
        if row:result.append(row)
    if events and not result:raise ValueError("BMKG nonempty quake list has no validated events")
    return result


def adapt_rss(mode,data,checked,url,entry):
    """Official/wmo-relayed RSS notices, bounded and not military intent evidence.

    Different relay mirrors of the same originating notice do not constitute
    independent corroboration; scope is explicit via provider mode.
    """
    if mode not in RSS_MODES:raise ValueError("Unsupported national feed")
    items=_entries(data)
    records=[]
    stale_count=0
    malformed_count=0
    for item in items:
        title=_element_text(item,"title")
        identity=_element_text(item,"guid") or _element_text(item,"id") or _rss_link(item)
        published=_stamp(_element_text(item,"pubDate") or
                         _element_text(item,"published") or
                         _element_text(item,"updated"))
        if published is None or not identity or not title:
            malformed_count+=1
            continue
        if published>checked+dt.timedelta(minutes=5):
            malformed_count+=1
            continue
        # Old historical notices may still appear in a feed; not active threats.
        if checked-published>dt.timedelta(days=7):
            stale_count+=1
            continue
        original=_rss_link(item)
        # Only secure trusted publishers and the authorized WMO relay are
        # linked; original unvalidated or HTTP links are not persisted.
        trusted={urlsplit(url).hostname}
        if mode=="bmkg_nowcast":trusted.update(("www.bmkg.go.id","bmkg.go.id"))
        if mode=="inmet_br":trusted.update(("apiprevmet3.inmet.gov.br","avisos.inmet.gov.br"))
        if mode in ("imd_in","saws_za"):
            trusted.update(("cap-sources.s3.amazonaws.com",))
        parsed=urlsplit(original)
        source=(original if parsed.scheme=="https" and parsed.hostname in trusted
                and not parsed.username and not parsed.password and len(original)<1200 else url)
        rid=_digest(mode,identity)
        row=entry(mode,rid,_clean(title,220),source,checked,published=_iso(published),
                  first_seen=_iso(published),kind="national_official_weather_notice_context",
                  source_scope=SCOPE[mode],
                  measurement={"name":"issued_warning_document","unit":"notice",
                     "issuer":PUBLISHERS[mode],
                     "wmo_relay_not_independent_observer":mode in ("imd_in","saws_za"),
                     "calibration_status":"not_calibrated"})
        if row:records.append(row)
    if items and not records and malformed_count and not stale_count:
        raise ValueError("National RSS contains no valid timestamped identified notices")
    return records[:MAX_OBSERVATIONS]


def adapter_for(mode,entry):
    if mode=="bmkg_quake":
        return lambda data,checked,url:adapt_quake(data,checked,url,entry)
    if mode in RSS_MODES:
        return lambda data,checked,url:adapt_rss(mode,data,checked,url,entry)
    raise ValueError("Unknown national source mode")
