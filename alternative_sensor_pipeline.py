#!/usr/bin/env python3
"""CAIRN source-separated public sensor collectors, no credentials or paid APIs.

Collects only *source-observed* facts. USGS/EONET/NWS are contextual hazard
controls, NOT military preparation measurements. USACE notices are declared
restrictions, NOT vessel telemetry. NOAA CO-OPS is selected-station physical
telemetry, NOT a port closure or an anomaly absent comparable history.

Failures must retain old observations on disk, publish failure health, and
never become zero measurements or a fabricated all-clear.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import time
from statistics import median
from pathlib import Path
import urllib.parse
import urllib.request

from ops_pipeline import load_json, write_json
from cairn_national_sensors import (MODES as NATIONAL_MODES, SCOPE as NATIONAL_SCOPE,
                                    FEEDS as NATIONAL_FEEDS, RSS_MODES,
                                    xml_parse, adapter_for)
from cairn_singapore_port import (FEED as SG_MPA_FEED, SCOPE as SG_MPA_SCOPE,
                                  adapt as adapt_sg_mpa)
from cairn_brazil_power import (urls as ONS_URLS, SCOPE as ONS_SCOPE,
                                adapt as adapt_ons)
from cairn_grid_and_bgp import (urls as GRID_NET_URLS, SCOPE as GRID_NET_SCOPE,
                                taiwan as adapt_tw_power, ris as adapt_ris_bgp)

UTC=dt.timezone.utc
SCHEMA="cairn.alternative-sensors.v1"
MAX_BYTES=8_000_000  # bounded for full public RIPE built-in probe cohort
MAX_RECORDS=110
USER_AGENT="CAIRN-Public-Alternative-Sensors/1.0 (github.com/graupmannj-dev/I-Ws-Dashboard)"
WIKI_LANGS=("en","fr","es","ar","ru","zh","hi","id","ja","pt","tr","sw","ko","fa")
WIKI_HOSTS=frozenset(lang+".wikipedia.org" for lang in WIKI_LANGS)
MODES=("usgs","eonet","nws","usace","coops","swpc","ripe","uk_tenders","wiki_edits","cbp_wait","sg_mpa","ons_br","tw_power","ris_bgp")+NATIONAL_MODES
SCOPE={
    "usgs":"USGS M4.5+ earthquakes worldwide, rolling past day; source thresholds apply",
    "eonet":"NASA EONET open natural event catalog, recent 7 days; limit 110",
    "nws":"U.S. National Weather Service active Florida-area weather alerts, first 110 returned",
    "usace":"USACE NTNI active notices for sampled districts MVP/MVS/SWG; up to 110 total",
    "coops":"NOAA CO-OPS water levels at San Francisco, Key West and Sewells Point; stations only",
    "swpc":"NOAA SWPC issued recent solar/geomagnetic warnings; explanatory context only",
    "ripe":"RIPE Atlas built-in K-root ping #1001, global public-probe aggregate; not country coverage",
    "uk_tenders":"UK Find a Tender OCDS releases; latest bounded update-window sample, not all UK tenders",
    "wiki_edits":"Wikipedia main-namespace edit-count sample, 14 global language editions, three-hour window capped at 500 per wiki; not geographic location",
    "cbp_wait":"CBP primary public U.S. Canadian/Mexican border estimated waits, port-local time; not actual traffic volume",
    "sg_mpa":SG_MPA_SCOPE,
    "ons_br":ONS_SCOPE,
    **GRID_NET_SCOPE,
    **NATIONAL_SCOPE,
}
PORT_STATIONS={
    "9414290":"San Francisco, CA",
    "8724580":"Key West, FL",
    "8638610":"Sewells Point, VA",
}
HOST_ALLOW={
 "usgs":"earthquake.usgs.gov","eonet":"eonet.gsfc.nasa.gov",
 "nws":"api.weather.gov","usace":"ndc.ops.usace.army.mil",
 "coops":"api.tidesandcurrents.noaa.gov",
 "swpc":"services.swpc.noaa.gov","ripe":"atlas.ripe.net",
 "uk_tenders":"www.find-tender.service.gov.uk",
 "wiki_edits":"en.wikipedia.org",
 "cbp_wait":"bwt.cbp.gov","sg_mpa":"data.gov.sg",
 "ons_br":"apicarga.ons.org.br",
 "tw_power":"service.taipower.com.tw","ris_bgp":"stat.ripe.net",
 "bmkg_quake":"data.bmkg.go.id","bmkg_nowcast":"www.bmkg.go.id",
 "inmet_br":"apiprevmet3.inmet.gov.br",
 "imd_in":"cap-sources.s3.amazonaws.com",
 "saws_za":"cap-sources.s3.amazonaws.com",
}
MAX_URLS={"usgs":1,"eonet":1,"nws":1,"usace":3,"coops":3,"swpc":1,"ripe":1,
          "uk_tenders":1,"wiki_edits":len(WIKI_LANGS),"cbp_wait":1,"sg_mpa":1,
          "ons_br":4,"tw_power":1,"ris_bgp":6,
          **{mode:1 for mode in NATIONAL_MODES}}
MAX_RIPE_PROBES=60000


def iso(t):
    return t.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")


def parse_time(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        try:return dt.datetime.fromtimestamp(value/1000 if value>1e11 else value,UTC)
        except (ValueError,OverflowError,OSError):return None
    if not isinstance(value,str) or not value:return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except ValueError:return None


def clean(x,length=200):
    return " ".join(str(x or "").split())[:length]


def digest(x):
    return hashlib.sha256(str(x).encode()).hexdigest()[:24]


def source_url(url,mode):
    if not isinstance(url,str):return None
    p=urllib.parse.urlsplit(url)
    if p.scheme!="https" or p.hostname not in (HOST_ALLOW[mode],
                                                  "www.usgs.gov",
                                                  "eonet.gsfc.nasa.gov",
                                                  "www.weather.gov",
                                                  "water.noaa.gov",
                                                  "tidesandcurrents.noaa.gov",
                                                  "www.swpc.noaa.gov",
                                                  "fr.wikipedia.org","es.wikipedia.org",
                                                  "avisos.inmet.gov.br",
                                                  "dados.ons.org.br",*WIKI_HOSTS):
        return None
    if p.username or p.password or len(url)>1500:return None
    return url


def xml_get(url):
    """HTTPS bounded, parser-restricted RSS/Atom only (no DTD/entities)."""
    p=urllib.parse.urlsplit(url)
    if p.scheme!="https" or p.username or p.password:
        raise ValueError("Invalid HTTPS source")
    req=urllib.request.Request(url,headers={
        "User-Agent":USER_AGENT,"Accept":"application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req,timeout=18) as res:
        raw=res.read(4_000_001)
        kind=res.headers.get("content-type","").split(";")[0].lower()
        if kind=="text/html":
            raise ValueError("HTML challenge, not source RSS")
    return xml_parse(raw)


def json_get(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!="https" or p.username or p.password:
        raise ValueError("HTTPS source and no credentials required")
    req=urllib.request.Request(url,headers={
        "User-Agent":USER_AGENT,"Accept":"application/geo+json, application/json"
    })
    with urllib.request.urlopen(req,timeout=18) as res:
        raw=res.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError("Response exceeds bounded size")
        kind=res.headers.get("content-type","").split(";")[0].lower()
        if kind.startswith("text/html"):raise ValueError("HTML challenge, not source JSON")
        return json.loads(raw)


def urls(mode,now):
    if mode in NATIONAL_FEEDS:return [NATIONAL_FEEDS[mode]]
    if mode=="sg_mpa":return [SG_MPA_FEED]
    if mode=="ons_br":return ONS_URLS(now)
    if mode in ("tw_power","ris_bgp"):return GRID_NET_URLS(mode)
    if mode=="usgs":
        return ["https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"]
    if mode=="eonet":
        return ["https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7&limit=110"]
    if mode=="nws":
        return ["https://api.weather.gov/alerts/active?area=FL"]
    if mode=="usace":
        root="https://ndc.ops.usace.army.mil/ords/ntni/json_data/notices_by_district/"
        return [root+x for x in ("MVP","MVS","SWG")]
    if mode=="swpc":
        return ["https://services.swpc.noaa.gov/products/alerts.json"]
    if mode=="ripe":
        return ["https://atlas.ripe.net/api/v2/measurements/1001/latest/?"+
                urllib.parse.urlencode({"versions":1,"lookback_days":1,"public_only":"true"})]
    if mode=="cbp_wait":
        return ["https://bwt.cbp.gov/api/waittimes"]
    if mode=="uk_tenders":
        return ["https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?"+
                urllib.parse.urlencode({"limit":100,
                    "updatedFrom":(now-dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
                    "updatedTo":now.strftime("%Y-%m-%dT%H:%M:%S")})]
    if mode=="wiki_edits":
        root="/w/api.php?"
        args=urllib.parse.urlencode({
            "action":"query","list":"recentchanges","rcnamespace":0,
            "rcprop":"title|timestamp|ids","rclimit":500,
            "rcstart":iso(now),"rcend":iso(now-dt.timedelta(hours=3)),
            "format":"json","formatversion":2})
        return ["https://"+lang+".wikipedia.org"+root+args for lang in WIKI_LANGS]
    if mode=="coops":
        root="https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
        return [root+urllib.parse.urlencode({
          "date":"today","station":station,"product":"water_level","datum":"MLLW",
          "time_zone":"gmt","units":"metric","application":"CAIRN_public",
          "format":"json"
        }) for station in PORT_STATIONS]
    raise ValueError("unknown sensor")


def entry(mode,rid,title,url,checked,*,event_at=None,published=None,kind="source_observation",
          first_seen=None,measurement=None,geo=None,source_scope=None):
    if not rid or not source_url(url,mode):return None
    event=parse_time(event_at)
    pub=parse_time(published)
    first=parse_time(first_seen)
    for t in (event,pub,first):
        if t and t>checked+dt.timedelta(minutes=5):return None
    out={
        "id":f"{mode}:{clean(rid,130)}","provider":mode,"root":f"{mode}:{clean(rid,130)}",
        "kind":kind,"title":clean(title,240),"source_url":url,
        "observed_at":iso(checked),"event_at":iso(event) if event else None,
        "published_at":iso(pub) if pub else None,
        "first_seen_at":iso(first) if first else None,
        "claim_level":"national_grid_load_not_outage_or_intent" if mode=="tw_power"
                     else "sampled_asn_routes_not_country_outage" if mode=="ris_bgp"
                     else "verified_grid_load_not_outage_or_intent" if mode=="ons_br"
                     else "monthly_historical_port_throughput_not_current_disruption" if mode=="sg_mpa"
                     else "national_environmental_context_not_conflict_attribution" if mode in NATIONAL_MODES
                     else "estimated_border_waits_not_vehicle_volume_or_mobilization" if mode=="cbp_wait"
                     else "official_tender_release_not_fulfillment_or_intent" if mode=="uk_tenders"
                     else "public_edit_activity_not_event_confirmation" if mode=="wiki_edits"
                     else "environmental_context_not_hostile_attribution" if mode in ("usgs","eonet","nws","coops","swpc")
                     else "aggregated_network_measurement_no_attribution" if mode=="ripe"
                     else "issued_waterway_notice_not_actual_vessel_disruption",
        "source_scope":source_scope or SCOPE[mode],
    }
    if measurement is not None:out["source_measurement"]=measurement
    if geo is not None:out["geography"]=geo
    return out


def source_point(geo):
    # Source-location metadata for environmental context only. This is NOT
    # a geolocated military event, actor, or attributed threat.
    if not isinstance(geo,dict) or geo.get("type")!="Point":return None
    a=geo.get("coordinates")
    if not isinstance(a,list) or len(a)<2:return None
    lon,lat=a[:2]
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) for x in (lon,lat)):
        return None
    if not (-180<=lon<=180 and -90<=lat<=90):return None
    return {"kind":"source_reported_physical_location_not_threat_site",
            "latitude":round(lat,5),"longitude":round(lon,5),
            "precision":"source_supplied_point_only",
            "key":None,"verified_iso":False}


def adapt_usgs(data,checked,url):
    if not isinstance(data,dict) or data.get("type")!="FeatureCollection" or not isinstance(data.get("features"),list):
        raise ValueError("USGS GeoJSON schema mismatch")
    result=[]
    for x in data["features"]:
        if not isinstance(x,dict) or not x.get("id"):continue
        p=x.get("properties") or {}
        if not isinstance(p,dict):continue
        mag=p.get("mag")
        m={"name":"earthquake_magnitude","unit":"reported_magnitude","value":mag,
           "baseline_status":"not_calibrated"} if type(mag) in (int,float) else None
        site=source_url(p.get("url"),"usgs") or url
        record=entry("usgs",x["id"],p.get("title") or "USGS earthquake",site,checked,
                     event_at=p.get("time"),published=p.get("updated") or p.get("time"),
                     first_seen=p.get("time"),kind="measured_earthquake_context",
                     measurement=m,geo=source_point(x.get("geometry")))
        if record:result.append(record)
    return result


def adapt_eonet(data,checked,url):
    if not isinstance(data,dict) or not isinstance(data.get("events"),list):
        raise ValueError("EONET event schema mismatch")
    result=[]
    for x in data["events"]:
        if not isinstance(x,dict) or not x.get("id"):continue
        g=x.get("geometry") or []
        recent=[t for t in g if isinstance(t,dict) and parse_time(t.get("date"))]
        if not recent:continue
        latest=max(recent,key=lambda y:parse_time(y["date"]))
        categories=x.get("categories") or []
        cat=clean(categories[0].get("title"),70) if categories and isinstance(categories[0],dict) else "natural event"
        link=source_url(x.get("link"),"eonet") or url
        record=entry("eonet",x["id"],x.get("title") or cat,link,checked,
                     event_at=latest["date"],published=latest["date"],
                     first_seen=latest["date"],kind="cataloged_natural_hazard_context",
                     source_scope="NASA EONET open catalog, category "+cat,
                     geo=source_point(latest.get("geometry")))
        if record:result.append(record)
    return result


def adapt_nws(data,checked,url):
    if not isinstance(data,dict) or not isinstance(data.get("features"),list):
        raise ValueError("NWS alert GeoJSON schema mismatch")
    result=[]
    for x in data["features"]:
        if not isinstance(x,dict):continue
        p=x.get("properties") or {}
        if not isinstance(p,dict):continue
        rid=p.get("id") or x.get("id")
        site=source_url(p.get("@id") or p.get("id"),"nws") or url
        if not rid:continue
        issued=p.get("sent") or p.get("effective") or p.get("onset")
        title=(p.get("event") or "Weather alert")+" - "+clean(p.get("areaDesc"),100)
        record=entry("nws",digest(rid),title,site,checked,event_at=p.get("onset") or issued,
                     published=issued,first_seen=issued,kind="official_weather_alert_context",
                     source_scope="Active NWS marine alerts; severity "+clean(p.get("severity"),20))
        if record:result.append(record)
    return result


def _notice_items(data):
    if isinstance(data,dict):
        if data.get("type")=="FeatureCollection" and isinstance(data.get("features"),list):
            return data["features"]
        for key in ("items","features","notices","data"):
            if isinstance(data.get(key),list):return data[key]
    if isinstance(data,list):return data
    raise ValueError("USACE notice collection schema mismatch")


def adapt_usace(data,checked,url):
    result=[]
    for x in _notice_items(data):
        if not isinstance(x,dict):continue
        p=x.get("properties") or x
        if not isinstance(p,dict):continue
        # USACE provider field naming may differ between district feeds;
        # refuse a notice without a distinct declared ID.
        rid=next((str(p[k]) for k in ("controlnumber","notice_id","noticeId","NOTICE_ID","ntni_id","id","ID")
                  if p.get(k)),None)
        if not rid:continue
        title=next((p[k] for k in ("title","TITLE","subject","SUBJECT","notice_title")
                    if p.get(k)),None)
        if not title and p.get("waterways"):
            title=("NTNI notice "+clean(p.get("noticeno") or rid,60)+
                   " · "+clean(p["waterways"],145))
        if not title:continue
        link=source_url(p.get("noticelink") or p.get("url") or p.get("link")
                        or p.get("document_url"),"usace") or url
        at=next((p[k] for k in ("issuedate","issued_at","issue_date","issueDate",
                                 "publish_date","start_date")
                 if p.get(k)),None)
        record=entry("usace",rid,title,link,checked,
                     published=at,first_seen=at,
                     kind="official_waterway_navigation_notice",
                     source_scope=SCOPE["usace"])
        if record:result.append(record)
    # A syntactically valid empty notice feed may indeed be empty, but a
    # nonempty unparseable collection is never zero observations.
    if _notice_items(data) and not result:
        raise ValueError("USACE returned notices but no validated IDs/titles")
    return result


def adapt_coops(data,checked,url):
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):
        raise ValueError("CO-OPS water-level schema mismatch")
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    station=(query.get("station") or [None])[0]
    if station not in PORT_STATIONS:raise ValueError("Unknown configured station")
    fresh=[]
    for r in data["data"]:
        if not isinstance(r,dict):continue
        stamp=parse_time(str(r.get("t") or "").replace(" ","T")+"Z")
        try:value=float(r.get("v"))
        except (TypeError,ValueError):continue
        if not (-50<=value<=50) or not stamp or stamp>checked+dt.timedelta(minutes=5):
            continue
        fresh.append((stamp,value))
    if not fresh:raise ValueError("No validated CO-OPS station measurement")
    at,val=max(fresh,key=lambda x:x[0])
    if checked-at>dt.timedelta(hours=3):raise ValueError("CO-OPS station measurement stale")
    doc="https://tidesandcurrents.noaa.gov/waterlevels.html?id="+station
    obs=entry("coops",station+":"+at.strftime("%Y%m%dT%H%MZ"),
              PORT_STATIONS[station]+" observed water level (no anomaly classification)",
              doc,checked,event_at=iso(at),first_seen=iso(at),published=iso(at),
              kind="selected_port_water_level_measurement",
              measurement={"name":"observed_water_level","unit":"meters_MLLW",
                           "value":val,"station":station,
                           "baseline_status":"not_calibrated",
                           "metric_comparable_only_same_station_datum_and_sample_window":True},
              source_scope=SCOPE["coops"])
    return [obs] if obs else []


def adapt_swpc(data,checked,url):
    """Public SWPC bulletins. Naive provider issue_datetime is UTC by contract."""
    if not isinstance(data,list):
        raise ValueError("SWPC alerts expected JSON list")
    result=[]
    for item in data:
        if not isinstance(item,dict):continue
        product=clean(item.get("product_id"),40)
        issued=item.get("issue_datetime")
        if not isinstance(issued,str) or not product:continue
        # Only SWPC's documented UTC-without-offset field receives UTC.
        stamp=parse_time(issued) if issued.endswith(("Z","+00:00")) else (
            parse_time(issued.replace(" ","T")+"+00:00"))
        if not stamp or not dt.timedelta(0)<=checked-stamp<=dt.timedelta(hours=96):
            continue
        message=item.get("message")
        if not isinstance(message,str) or not message.strip():continue
        serial=re.search(r"Serial Number:\s*(\d+)",message,re.I)
        serial_id=serial.group(1) if serial else digest(message)
        rid=f"{product}:{serial_id}:{stamp.strftime('%Y%m%dT%H%M%SZ')}"
        headline=next((clean(line,140) for line in message.splitlines()
                       if re.match(r"^(?:ALERT|WARNING|WATCH|CONTINUED ALERT|EXTENDED WARNING):",
                                   line.strip(),re.I)),
                      f"SWPC space weather bulletin {product}")
        row=entry("swpc",rid,headline,
                  "https://www.swpc.noaa.gov/products/alerts-watches-and-warnings",
                  checked,event_at=iso(stamp),published=iso(stamp),
                  first_seen=iso(stamp),kind="issued_space_weather_bulletin",
                  source_scope=SCOPE["swpc"])
        if row:result.append(row)
    if data and not result and any(isinstance(x,dict) and
                                   x.get("issue_datetime") for x in data):
        # An older feed with no recent notices is valid empty, not false zero
        # measured space-weather activity.
        return []
    return result


def adapt_ripe(data,checked,url):
    """One explicitly named public measurement; publish aggregate only."""
    if isinstance(data,list):
        samples=data
    elif isinstance(data,dict) and isinstance(data.get("results"),list):
        samples=data["results"]
    elif isinstance(data,dict):
        samples=[]
        for value in data.values():
            if isinstance(value,list):samples.extend(value)
            elif isinstance(value,dict):samples.append(value)
    else:
        raise ValueError("RIPE latest envelope not recognized")
    if len(samples)>MAX_RIPE_PROBES:
        raise ValueError("RIPE probe cohort exceeds fixed upper limit; do not cut silently")
    valid=0
    good=[]
    for row in samples:
        if not isinstance(row,dict) or row.get("msm_id") not in (1001,"1001",None):
            continue
        stamp=parse_time(row.get("timestamp"))
        if not stamp or not dt.timedelta(0)<=checked-stamp<=dt.timedelta(hours=24):
            continue
        valid+=1
        avg=row.get("avg")
        if type(avg) in (int,float) and math.isfinite(avg) and 0<=avg<100000:
            good.append(float(avg))
    if valid<20 or len(good)<10:
        raise ValueError("RIPE insufficient recent public-probe observations for aggregate")
    value=round(median(good),3)
    # Hourly aggregate is an observation of a potentially CHANGING probe
    # cohort, not a matched-cohort deviation. Never publish an implied z-score.
    doc="https://atlas.ripe.net/measurements/1001/"
    at=checked.replace(minute=0,second=0,microsecond=0)
    row=entry("ripe",f"measurement:1001:{at.strftime('%Y%m%dT%H')}",
              f"RIPE Atlas K-root public probe aggregate ({len(good)} usable measurements)",
              doc,checked,kind="aggregate_public_network_ping",
              measurement={
                "name":"sample_median_ping_rtt","value":value,"unit":"ms",
                "measurement_id":1001,"sampled_probe_count":valid,
                "valid_rtt_count":len(good),"failed_or_invalid_rtt_count":valid-len(good),
                "baseline_status":"not_calibrated",
                "cohort_comparable_to_prior_snapshots":False,
                "individual_probe_records_published":False,
              },
              geo={"key":"ripe-msm:1001","kind":"global_public_probe_cohort",
                   "label":"K-root public ping aggregate",
                   "precision":"not_country_or_incident_location",
                   "latitude":None,"longitude":None,"verified_iso":False},
              source_scope=SCOPE["ripe"])
    return [row] if row else []



def adapt_uk_tenders(data,checked,url):
    """Official UK public contracting releases; no private vendor data."""
    if not isinstance(data,dict) or not isinstance(data.get("releases"),list):
        raise ValueError("UK tender OCDS release-package schema mismatch")
    result=[]
    for rel in data["releases"]:
        if not isinstance(rel,dict):continue
        rid=clean(rel.get("id"),125)
        ocid=clean(rel.get("ocid"),125)
        tender=rel.get("tender") if isinstance(rel.get("tender"),dict) else {}
        published=parse_time(rel.get("date"))
        if not rid or not ocid or not published or published>checked+dt.timedelta(minutes=5):
            continue
        title=clean(tender.get("title") or rel.get("tag") or "Public procurement release",180)
        buyer=rel.get("buyer") if isinstance(rel.get("buyer"),dict) else {}
        title=(title+" · "+clean(buyer.get("name"),60)).strip(" ·")
        doc=source_url(url,"uk_tenders")
        row=entry("uk_tenders",ocid+":"+rid,title,doc,checked,
            published=iso(published),first_seen=iso(published),
            kind="public_tender_release_not_evidence_of_urgent_need",
            source_scope=SCOPE["uk_tenders"])
        if row:result.append(row)
    if data["releases"] and not result:
        raise ValueError("Nonempty UK tender package has no dated identifiable releases")
    return result


def adapt_wiki_edits(data,checked,url):
    """Bounded *aggregate* public edit activity. Never retain accounts or IPs."""
    changes=(data.get("query") or {}).get("recentchanges") if isinstance(data,dict) else None
    if not isinstance(changes,list):
        raise ValueError("Wikipedia recentchanges schema mismatch")
    host=urllib.parse.urlsplit(url).hostname
    if host not in WIKI_HOSTS:
        raise ValueError("Unapproved Wikipedia language host")
    language=host.split(".")[0]
    by_title={}
    latest=None
    for change in changes:
        if not isinstance(change,dict) or not isinstance(change.get("title"),str):
            continue
        stamp=parse_time(change.get("timestamp"))
        if not stamp or stamp>checked+dt.timedelta(minutes=5) or checked-stamp>dt.timedelta(hours=4):
            continue
        title=clean(change["title"],150)
        if title:by_title[title]=by_title.get(title,0)+1
        latest=stamp if not latest or stamp>latest else latest
    # A valid empty window is NOT an outage; it is also not an all-clear.
    if not by_title:return []
    if not latest:raise ValueError("Wikipedia edit records have no valid timestamps")
    sample=sorted(by_title.items(),key=lambda x:(-x[1],x[0]))[:8]
    count=sum(by_title.values())
    doc="https://"+host+"/wiki/Special:RecentChanges"
    return [entry("wiki_edits",language+":"+checked.strftime("%Y%m%dT%H"),
        "Wikipedia "+language+" public article-edit activity (sampled)",
        doc,checked,event_at=iso(latest),published=iso(latest),first_seen=iso(latest),
        kind="bounded_public_edit_count_not_event_verification",
        measurement={"name":"sampled_edits_last_three_hours","value":count,"unit":"edits",
                     "distinct_articles_in_sample":len(by_title),
                     "most_edited_article_counts":[{"title":t,"count":n} for t,n in sample],
                     "maximum_returned_edits":500,"sample_cap_reached":len(changes)>=500,
                     "baseline_status":"not_calibrated"},
        source_scope=SCOPE["wiki_edits"])]


def adapt_cbp_wait(data,checked,url):
    """Primary U.S. CBP port wait feed, public *estimated* commercial delays.

    Port date/time strings are local wall-clock values without a trustworthy
    per-port UTC offset. Do NOT invent a UTC event time from these fields.
    """
    if not isinstance(data,list) or len(data)>MAX_RECORDS:
        raise ValueError("CBP port-wait list missing or exceeds bound")
    result=[]
    for port in data:
        if not isinstance(port,dict):continue
        ident=clean(port.get("port_number"),50)
        name=clean(port.get("port_name"),100)
        crossing=clean(port.get("crossing_name"),100)
        date_text=clean(port.get("date"),20)
        local_time=clean(port.get("time"),24)
        if not ident or not name:
            continue
        try:local_date=dt.datetime.strptime(date_text,"%m/%d/%Y").date()
        except ValueError:continue
        # U.S. port-local date may lag UTC by a day, but not multiple days.
        if not (checked.date()-dt.timedelta(days=1)<=local_date<=
                checked.date()+dt.timedelta(days=1)):
            continue
        if not re.fullmatch(r"\d{1,2}:\d{2}:\d{2}",local_time):
            continue
        lanes=port.get("commercial_vehicle_lanes") or {}
        if not isinstance(lanes,dict):lanes={}
        standard=lanes.get("standard_lanes") or {}
        if not isinstance(standard,dict):standard={}
        raw_delay=clean(standard.get("delay_minutes"),12)
        delay=int(raw_delay) if raw_delay.isdigit() and int(raw_delay)<=720 else None
        lanes_open=clean(standard.get("lanes_open"),12)
        lanes_open=int(lanes_open) if lanes_open.isdigit() and int(lanes_open)<=100 else None
        status=clean(port.get("port_status"),40)
        # Original publisher fields remain in local wall time; not asserted as
        # source-published UTC timestamps.
        rid=ident+":"+local_date.isoformat()+":"+local_time
        title="CBP estimated commercial border wait — "+name
        if crossing:title+=" / "+crossing
        row=entry("cbp_wait",rid,title,url,checked,
                  kind="published_commercial_wait_estimate_not_vehicle_volume",
                  geo={"key":"us-border-port:"+ident,"kind":"source_identified_port",
                       "label":name,"precision":"published_crossing_not_event_location",
                       "latitude":None,"longitude":None,"verified_iso":False},
                  measurement={"name":"published_commercial_standard_lane_wait",
                      "value":delay,"unit":"minutes","lanes_open":lanes_open,
                      "port_status":status,
                      "lane_status":clean(standard.get("operational_status"),50),
                      "reported_local_date":date_text,"reported_local_time":local_time,
                      "reported_lane_clock":clean(standard.get("update_time"),70),
                      "source_timezone_resolved":False,
                      "source_declared_border":clean(port.get("border"),55),
                      "baseline_status":"not_calibrated",
                      "not_a_vehicle_throughput_measurement":True},
                  source_scope=SCOPE["cbp_wait"])
        if row:result.append(row)
    if not result:
        raise ValueError("CBP returned no identifiable current-date port records")
    return result


ADAPTERS={"usgs":adapt_usgs,"eonet":adapt_eonet,"nws":adapt_nws,
          "usace":adapt_usace,"coops":adapt_coops,
          "swpc":adapt_swpc,"ripe":adapt_ripe,
          "uk_tenders":adapt_uk_tenders,"wiki_edits":adapt_wiki_edits,
          "cbp_wait":adapt_cbp_wait,
          "sg_mpa":lambda data,checked,url:adapt_sg_mpa(data,checked,url,entry),
          "ons_br":lambda data,checked,url:adapt_ons(data,checked,url,entry),
          "tw_power":lambda data,checked,url:adapt_tw_power(data,checked,url,entry),
          "ris_bgp":lambda data,checked,url:adapt_ris_bgp(data,checked,url,entry),
          **{mode:adapter_for(mode,entry) for mode in NATIONAL_MODES}}


def collect(state,clock=None,fetcher=json_get,selected=MODES):
    state=Path(state)
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    summary={}
    for mode in selected:
        if mode not in MODES:raise ValueError("Invalid source mode")
        source_urls=urls(mode,now)
        success=[]
        errors=[]
        # Each CO-OPS station is independently useful; one failed station
        # does not block successfully observed stations.
        for i,url in enumerate(source_urls[:MAX_URLS[mode]]):
            # Wikimedia throttles bursts across edition hosts from one runner IP.
            # Pace only real outbound reads. Offline fixtures remain instant.
            # Never bypass a 429; its source health stays partial/unavailable.
            if mode=="wiki_edits" and i and fetcher is json_get:
                time.sleep(7)
            try:
                if urllib.parse.urlsplit(url).hostname not in (WIKI_HOSTS
                                                             if mode=="wiki_edits" else (HOST_ALLOW[mode],)):
                    raise ValueError("Unapproved data-host endpoint")
                national_fetch=(xml_get if mode in RSS_MODES else json_get)
                # The injected fetcher is used in offline fixtures; production
                # uses XML only for declared national CAP/RSS modes.
                getter=national_fetch if fetcher is json_get else fetcher
                try:
                    payload=getter(url)
                except (urllib.error.URLError,TimeoutError):
                    # Official Taipower TLS can occasionally time out from shared
                    # runners. One bounded retry on the SAME original host.
                    # Never use mirrors or turn a timeout into zero demand.
                    if mode!="tw_power" or fetcher is not json_get:
                        raise
                    time.sleep(2)
                    payload=getter(url)
                parsed=ADAPTERS[mode](payload,now,url)
                success.extend(parsed)
            except (ValueError,TypeError,KeyError,TimeoutError,OSError,
                    urllib.error.URLError,json.JSONDecodeError) as exc:
                errors.append(clean(type(exc).__name__+": "+str(exc),180))
        # Provider responses are bounded and explicitly marked partial;
        # collection never silently truncates and claims exhaustive coverage.
        truncated=len(success)>MAX_RECORDS or len(errors)>0 or mode in ("usace","nws","eonet","coops","uk_tenders","wiki_edits","cbp_wait","sg_mpa","ons_br","tw_power","ris_bgp")+NATIONAL_MODES
        kept=success[:MAX_RECORDS]
        ok=len(errors)<len(source_urls)
        status="partial" if ok and truncated else "collected" if ok else "unavailable"
        report={
            "schema":SCHEMA,"mode":mode,"checked_at":iso(now),
            "status":status,"source_scope":SCOPE[mode],
            "truncated":truncated if ok else False,
            "source_queries_attempted":len(source_urls),
            "source_queries_ok":len(source_urls)-len(errors),
            "records":len(kept) if ok else None,
            "source_errors":errors[:6],
            "missingness":"provider_bounded_partial" if ok and truncated else
                "provider_bounded_not_exhaustive" if ok else "not_measured_not_zero",
            "source_dependency_class":(
                "national_public_power_snapshot_not_outage" if mode=="tw_power"
                else "ris_bgp_sampled_asn_updates_not_country_outage" if mode=="ris_bgp"
                else "official_regional_grid_load_not_outage" if mode=="ons_br"
                else "official_monthly_port_aggregate_not_real_time" if mode=="sg_mpa"
                else "national_official_hazard_bulletin_not_independent_incident" if mode in NATIONAL_MODES
                else "environmental_hazard_reporting" if mode in ("usgs","eonet","nws","swpc")
                else "official_navigation_notice" if mode=="usace"
                else "aggregate_public_network_ping" if mode=="ripe"
                else "official_cbp_border_wait_estimate" if mode=="cbp_wait"
                else "official_public_procurement_release" if mode=="uk_tenders"
                else "public_encyclopedia_edit_aggregate" if mode=="wiki_edits"
                else "station_physical_measurement"),
            "operational_warning_approved":False,
        }
        write_json(state/"health"/(mode+".json"),report)
        if ok:
            write_json(state/"latest"/(mode+".json"),{
                "schema":SCHEMA,"mode":mode,"observed_at":iso(now),
                "status":status,"source_scope":SCOPE[mode],
                "records":kept,"truncated":truncated,
                "source_queries_ok":report["source_queries_ok"],
            })
        summary[mode]=report
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",required=True,type=Path)
    p.add_argument("--sources",default=",".join(MODES),
                   help="Comma-separated fixed public collector names")
    args=p.parse_args()
    selection=tuple(x.strip() for x in args.sources.split(",") if x.strip())
    if not selection or any(x not in MODES for x in selection):
        p.error("Unsupported source")
    result=collect(args.state,selected=selection)
    print(json.dumps(result,indent=2))
    # Do not fail the entire collection or suppress other sources due to one
    # inaccessible provider; status on the evidence branch is authoritative.
    return 0


if __name__=="__main__":raise SystemExit(main())
