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
from statistics import median
from pathlib import Path
import urllib.parse
import urllib.request

from ops_pipeline import load_json, write_json

UTC=dt.timezone.utc
SCHEMA="cairn.alternative-sensors.v1"
MAX_BYTES=8_000_000  # bounded for full public RIPE built-in probe cohort
MAX_RECORDS=110
USER_AGENT="CAIRN-Public-Alternative-Sensors/1.0 (github.com/graupmannj-dev/I-Ws-Dashboard)"
MODES=("usgs","eonet","nws","usace","coops","swpc","ripe")
SCOPE={
    "usgs":"USGS M4.5+ earthquakes worldwide, rolling past day; source thresholds apply",
    "eonet":"NASA EONET open natural event catalog, recent 7 days; limit 110",
    "nws":"U.S. National Weather Service active Florida-area weather alerts, first 110 returned",
    "usace":"USACE NTNI active notices for sampled districts MVP/MVS/SWG; up to 110 total",
    "coops":"NOAA CO-OPS water levels at San Francisco, Key West and Sewells Point; stations only",
    "swpc":"NOAA SWPC issued recent solar/geomagnetic warnings; explanatory context only",
    "ripe":"RIPE Atlas built-in K-root ping #1001, global public-probe aggregate; not country coverage",
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
}
MAX_URLS={"usgs":1,"eonet":1,"nws":1,"usace":3,"coops":3,"swpc":1,"ripe":1}
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
                                                  "www.swpc.noaa.gov"):
        return None
    if p.username or p.password or len(url)>1500:return None
    return url


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
        "claim_level":"environmental_context_not_hostile_attribution" if mode in ("usgs","eonet","nws","coops","swpc")
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


ADAPTERS={"usgs":adapt_usgs,"eonet":adapt_eonet,"nws":adapt_nws,
          "usace":adapt_usace,"coops":adapt_coops,
          "swpc":adapt_swpc,"ripe":adapt_ripe}


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
        for url in source_urls[:MAX_URLS[mode]]:
            try:
                if urllib.parse.urlsplit(url).hostname!=HOST_ALLOW[mode]:
                    raise ValueError("Unapproved data-host endpoint")
                parsed=ADAPTERS[mode](fetcher(url),now,url)
                success.extend(parsed)
            except (ValueError,TypeError,KeyError,TimeoutError,OSError,
                    urllib.error.URLError,json.JSONDecodeError) as exc:
                errors.append(clean(type(exc).__name__+": "+str(exc),180))
        # Provider responses are bounded and explicitly marked partial;
        # collection never silently truncates and claims exhaustive coverage.
        truncated=len(success)>MAX_RECORDS or len(errors)>0 or mode in ("usace","nws","eonet","coops")
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
                "environmental_hazard_reporting" if mode in ("usgs","eonet","nws","swpc")
                else "official_navigation_notice" if mode=="usace"
                else "aggregate_public_network_ping" if mode=="ripe"
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
