#!/usr/bin/env python3
"""CAIRN public alternative sensor collection: bounded, source-separated, honest.

Seven independent *provider API streams*; not seven independent confirmations
of anything. Environmental hazards are potential confounders, never conflict
signals. No military movement inference, device tracking or person-level data.
In all modes source absence is UNKNOWN, not a measured zero.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ops_pipeline import write_json

UTC=dt.timezone.utc
SCHEMA="cairn.alternative-source-collection.v1"
MODES=("usgs_quakes","nasa_eonet","noaa_swpc","nws_alerts",
       "usace_navigation","noaa_ports","ripe_atlas")
FRESH_HOURS={"usgs_quakes":6,"nasa_eonet":6,"noaa_swpc":8,"nws_alerts":6,
             "usace_navigation":8,"noaa_ports":3,"ripe_atlas":8}
SOURCE_SCOPE={
  "usgs_quakes":"Global USGS M4.5+ earthquake feed; past seven days",
  "nasa_eonet":"NASA-curated natural hazard events, bounded 7-day sample",
  "noaa_swpc":"NOAA geomagnetic/space weather bulletins; global effects vary",
  "nws_alerts":"Active U.S. NWS public weather warnings, bounded first page",
  "usace_navigation":"USACE active U.S. waterway/lock navigation notices, bounded sample",
  "noaa_ports":"Four named U.S. NOAA port environmental observation stations",
  "ripe_atlas":"RIPE Atlas builtin 1001 K-root ping, aggregate of sampled public probes",
}
SOURCE_ROLE={
  "usgs_quakes":"environmental_control",
  "nasa_eonet":"environmental_control",
  "noaa_swpc":"environmental_control",
  "nws_alerts":"environmental_control",
  "usace_navigation":"issued_navigation_notice",
  "noaa_ports":"physical_station_measurement",
  "ripe_atlas":"public_network_measurement_aggregate",
}
USER_AGENT="CAIRN-public-source-collector/1.0 (https://github.com/graupmannj-dev/I-Ws-Dashboard)"
USGS="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
EONET="https://eonet.gsfc.nasa.gov/api/v3/events?"+urlencode(
    {"status":"all","days":7,"limit":100})
SWPC="https://services.swpc.noaa.gov/products/alerts.json"
NWS="https://api.weather.gov/alerts/active?"+urlencode({"limit":100})
USACE_ROOT="https://ndc.ops.usace.army.mil/ords/ntni/json_data/notices_geoJson"
RIPE="https://atlas.ripe.net/api/v2/measurements/1001/latest/?"+urlencode(
    {"versions":1,"lookback_days":1,"public_only":"true"})
PORT_STATIONS={
  "9414290":"San Francisco CA","8638610":"Sewells Point VA",
  "8771450":"Galveston TX","9447130":"Seattle WA",
}
CAPS={"usgs_quakes":120,"nasa_eonet":100,"noaa_swpc":55,"nws_alerts":100,
      "usace_navigation":160,"noaa_ports":len(PORT_STATIONS),"ripe_atlas":1}
MAX_BYTES=8_000_000
MAX_RIPE_PROBES=6500


def utcnow():
    return dt.datetime.now(UTC).replace(microsecond=0)


def iso(value):
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00","Z")


def parse_time(value):
    if value is None or isinstance(value,bool):
        return None
    if isinstance(value,(float,int)):
        if not math.isfinite(value):
            return None
        if value>1e11:
            value=value/1000
        try:return dt.datetime.fromtimestamp(value,UTC)
        except (OverflowError,ValueError,OSError):return None
    if not isinstance(value,str) or len(value)>60:
        return None
    text=value.strip()
    if not text:
        return None
    try:
        d=dt.datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError:
        return None
    # NOAA SWPC issue_datetime is conventionally UTC without a zone.
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


def source_time(value,now):
    d=parse_time(value)
    if d is None or d>now+dt.timedelta(minutes=5):
        return None
    return iso(d)


def safe_text(value,maxlen=180):
    return re.sub(r"\s+"," ",str(value or "")).strip()[:maxlen]


def geography(key=None,label=None,kind="source_scope",precision="source_not_event_location"):
    return {"key":key,"kind":kind,"label":label,"precision":precision,
            "verified_iso":False,"latitude":None,"longitude":None}


def rec(mode,id,title,url,now,*,event_at=None,published_at=None,
        root=None,geo=None,kind=None,measurement=None,source_dependency=None):
    if not isinstance(id,str) or not id or len(id)>170:
        raise ValueError("Invalid original source ID")
    if not isinstance(url,str) or not url.startswith("https://"):
        raise ValueError("Source link must be HTTPS")
    entry={
        "id":id,"root":root or f"{mode}:{id}",
        "title":safe_text(title,240),"source_url":url,
        "provider":mode,"kind":kind or SOURCE_ROLE[mode],
        "collected_at":iso(now),
        "event_at":source_time(event_at,now),
        "source_published_at":source_time(published_at,now),
        "geography":geo or geography(),
        "source_role":SOURCE_ROLE[mode],
        "source_dependency":source_dependency or mode,
        "alert_eligible":False,
    }
    if measurement is not None:
        entry["observed_measurement"]=measurement
    return entry


def fetch_json(url,max_bytes=MAX_BYTES):
    request=Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json"})
    with urlopen(request,timeout=18) as response:
        buf=response.read(max_bytes+1)
        if len(buf)>max_bytes:
            raise ValueError("Provider response exceeds bounded size; no silent truncation")
        return json.loads(buf.decode("utf-8"))


def require_list(payload,key=None):
    rows=payload.get(key) if key and isinstance(payload,dict) else payload
    if not isinstance(rows,list):
        raise ValueError("Unexpected provider schema; expected array")
    return rows


def usgs(data,now):
    if not isinstance(data,dict) or data.get("type")!="FeatureCollection":
        raise ValueError("USGS feed missing GeoJSON FeatureCollection")
    raw=require_list(data,"features")
    rows=[]
    for item in raw:
        if not isinstance(item,dict):continue
        prop=item.get("properties") or {}
        if not isinstance(prop,dict):continue
        ident=item.get("id")
        magnitude=prop.get("mag")
        if not isinstance(ident,str) or not isinstance(magnitude,(int,float)) or isinstance(magnitude,bool) or not math.isfinite(magnitude) or magnitude<4.5:
            continue
        url=prop.get("url")
        if not isinstance(url,str) or not url.startswith("https://earthquake.usgs.gov/"):
            continue
        label=safe_text(prop.get("place"),110)
        rows.append(rec("usgs_quakes",f"usgs:{ident}",
            f"USGS M{magnitude:.1f} earthquake · {label}",url,now,
            event_at=prop.get("time"),published_at=prop.get("updated"),
            geo=geography("earthquake:"+ident,label,"reported_hazard_location",
                "usgs_source_geometry_not_cairn_hostile_event"),
            kind="measured_seismic_hazard",
            measurement={"name":"earthquake_magnitude","value":float(magnitude),
                         "unit":"USGS_magnitude_scale","reference_baseline_ready":False},
            source_dependency=f"usgs:earthquake:{ident}"))
    return rows,{"total_received":len(raw)}


def eonet(data,now):
    if not isinstance(data,dict):
        raise ValueError("NASA EONET response is not an object")
    raw=require_list(data,"events")
    rows=[]
    for event in raw:
        if not isinstance(event,dict):continue
        ident=event.get("id")
        if not isinstance(ident,str) or not re.fullmatch("[A-Za-z0-9_-]{2,70}",ident):
            continue
        categories=event.get("categories")
        category=safe_text(categories[0].get("title") if isinstance(categories,list) and categories and isinstance(categories[0],dict) else "",65)
        geo_history=event.get("geometry")
        latest=geo_history[-1] if isinstance(geo_history,list) and geo_history and isinstance(geo_history[-1],dict) else {}
        title=safe_text(event.get("title"),180)
        rows.append(rec("nasa_eonet",f"eonet:{ident}",
            "NASA natural hazard · "+title,
            "https://eonet.gsfc.nasa.gov/api/v3/events/"+ident,now,
            event_at=latest.get("date"),published_at=latest.get("date"),
            geo=geography("eonet:"+ident,category or title,
               "curated_natural_hazard","NASA_source_hazard_geometry_not_threat_site"),
            kind="curated_environmental_hazard",
            source_dependency="NASA_EONET_curated_from_multiple_original_agencies"))
    return rows,{"total_received":len(raw)}


def swpc(data,now):
    raw=require_list(data)
    rows=[]
    for item in raw:
        if not isinstance(item,dict):continue
        product=safe_text(item.get("product_id"),30)
        issued=source_time(item.get("issue_datetime"),now)
        message=item.get("message")
        if not product or not issued or not isinstance(message,str):
            continue
        # Source data can include older bulletins; limit to a recent 96h context.
        at=parse_time(issued)
        if not dt.timedelta(0)<=now-at<=dt.timedelta(hours=96):
            continue
        serial=re.search(r"Serial Number:\s*(\d+)",message,re.I)
        serial_id=serial.group(1) if serial else hashlib.sha256(message.encode()).hexdigest()[:12]
        ident=f"swpc:{product}:{serial_id}:{issued[:10]}"
        headline=next((safe_text(line,120) for line in message.splitlines()
                       if re.match(r"^(?:ALERT|WARNING|WATCH|CONTINUED ALERT|EXTENDED WARNING):",line.strip(),re.I)),
                      f"Space-weather bulletin {product}")
        rows.append(rec("noaa_swpc",ident,headline,
            "https://www.swpc.noaa.gov/products/alerts-watches-and-warnings",
            now,event_at=issued,published_at=issued,
            geo=geography("space-weather:global","Space-weather domain",
                "regional_to_global_possible_effects","not_causal_attribution"),
            kind="issued_space_weather_bulletin",
            source_dependency=f"swpc:message:{ident}"))
    return rows,{"total_received":len(raw)}


def nws(data,now):
    if not isinstance(data,dict) or data.get("type")!="FeatureCollection":
        raise ValueError("NWS alert feed missing FeatureCollection")
    raw=require_list(data,"features")
    rows=[]
    for feature in raw:
        prop=feature.get("properties") if isinstance(feature,dict) else None
        if not isinstance(prop,dict):continue
        ident=prop.get("id")
        if not isinstance(ident,str) or not ident.startswith("https://api.weather.gov/"):
            continue
        sent=source_time(prop.get("sent"),now)
        if not sent:continue
        region=safe_text(prop.get("areaDesc"),90)
        event=safe_text(prop.get("event"),100)
        rows.append(rec("nws_alerts","nws:"+hashlib.sha256(ident.encode()).hexdigest()[:26],
            "NWS "+event+" · "+region,ident,now,
            published_at=sent, event_at=None,
            geo=geography(None,region,"source_declared_alert_area",
                "weather_alert_area_not_independent_event_location"),
            kind="weather_warning_or_watch_not_observed_hazard",
            source_dependency=f"nws:source_alert:{ident}"))
    return rows,{"total_received":len(raw),"next_page_present":bool(data.get("pagination",{}).get("next")) if isinstance(data.get("pagination"),dict) else False}


def usace(data,now,url):
    # The official endpoint is nominally GeoJSON. Oracle ORDS deployments
    # sometimes wrap features as items; refuse any other undocumented shape.
    if not isinstance(data,dict):
        raise ValueError("USACE response is not a JSON object")
    if data.get("type")=="FeatureCollection":
        raw=require_list(data,"features")
    elif isinstance(data.get("items"),list):
        raw=data["items"]
    else:raise ValueError("USACE changed response schema")
    rows=[]
    for feature in raw:
        if not isinstance(feature,dict):continue
        prop=feature.get("properties") if isinstance(feature.get("properties"),dict) else feature
        ident=next((str(prop[k]).strip() for k in (
            "notice_id","NOTICE_ID","notice_no","NOTICE_NO",
            "notice_number","NOTICE_NUMBER","id","ID")
            if prop.get(k) not in (None,"")),None)
        if not ident:continue
        title=next((prop[k] for k in ("title","TITLE","subject","SUBJECT",
             "notice_title","NOTICE_TITLE","description","DESCRIPTION")
             if isinstance(prop.get(k),str) and prop[k].strip()),"U.S. waterway navigation notice")
        waterway=next((prop[k] for k in ("waterway","WATERWAY","waterway_name",
                "WATERWAY_NAME","river","RIVER") if isinstance(prop.get(k),str)),None)
        rows.append(rec("usace_navigation",
            "usace:"+hashlib.sha256(ident.encode()).hexdigest()[:24],
            "USACE waterway · "+safe_text(title,160),url,now,
            geo=geography("usace-waterway:"+safe_text(waterway,80).casefold() if waterway else None,
               safe_text(waterway,80) or None,"official_notice_scope",
               "navigation_notice_area_not_verified_disruption"),
            kind="official_navigation_notice",
            root="usace:original_notice:"+ident,
            source_dependency="usace:original_notice:"+ident))
    if raw and not rows:raise ValueError("USACE notice identities not recognized; refuse false normal")
    return rows,{"total_received":len(raw),
                 "next_page_present":bool(data.get("hasMore") or data.get("next"))}


def port_url(station):
    return "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"+urlencode({
        "date":"latest","station":station,"product":"wind",
        "units":"metric","time_zone":"gmt","application":"CAIRN",
        "format":"json"})


def noaa_station(data,now,station,label):
    if not isinstance(data,dict) or not isinstance(data.get("data"),list):
        raise ValueError("NOAA station response missing wind data")
    points=data["data"]
    if not points:return [],{"total_received":0}
    recent=points[-1]
    t=source_time(recent.get("t") if isinstance(recent,dict) else None,now)
    try:
        speed=float(recent.get("s"))
        gust=float(recent.get("g")) if recent.get("g") not in (None,"","-") else None
    except (TypeError,ValueError):
        raise ValueError("NOAA wind observation invalid")
    if not math.isfinite(speed) or speed<0 or speed>140 or (gust is not None and not math.isfinite(gust)):
        raise ValueError("NOAA wind outside physical plausibility bounds")
    if not t or now-parse_time(t)>dt.timedelta(hours=3):
        raise ValueError("NOAA latest wind datum is stale")
    moment=parse_time(t)
    bucket=moment.strftime("%Y%m%dT%H")  # one station observation per hour
    row=rec("noaa_ports",f"noaa-port:{station}:wind:{bucket}",
        f"NOAA observed port wind · {label}: {speed:.1f} m/s",
        "https://tidesandcurrents.noaa.gov/stationhome.html?id="+station,
        now,event_at=t,published_at=None,
        geo=geography("noaa-station:"+station,label,"fixed_physical_station",
            "observed_weather_station_not_port_throughput"),
        kind="measured_port_wind",
        measurement={"name":"mean_wind_speed","value":speed,"unit":"m/s",
                     "observed_time":t,"station_id":station,
                     "reference_baseline_ready":False},
        source_dependency="noaa:coops:station:"+station)
    return [row],{"total_received":len(points)}


def ripe(data,now):
    if not isinstance(data,(list,dict)):
        raise ValueError("RIPE Atlas latest response has unknown shape")
    # API may return a mapping keyed by public probe ID or an array. The
    # published result never includes probe identifiers, IPs or locations.
    if isinstance(data,dict):
        if isinstance(data.get("results"),list):
            samples=data["results"]
        else:
            samples=[]
            for value in data.values():
                samples.extend(value if isinstance(value,list) else [value])
    else:samples=data
    if len(samples)>MAX_RIPE_PROBES:
        raise ValueError("RIPE probe sample exceeds bounded cohort; no arbitrary head")
    all_rtt=[]
    valid=0
    failures=0
    for item in samples:
        if not isinstance(item,dict):continue
        if item.get("msm_id") not in (1001,"1001",None):
            continue
        ts=parse_time(item.get("timestamp"))
        if not ts or not dt.timedelta(0)<=now-ts<=dt.timedelta(hours=24):
            continue
        valid+=1
        avg=item.get("avg")
        if isinstance(avg,(int,float)) and not isinstance(avg,bool) and math.isfinite(avg) and 0<=avg<100000:
            all_rtt.append(float(avg))
        else:failures+=1
    if valid<20:
        raise ValueError("RIPE current public sample below minimum 20 probes")
    if not all_rtt:
        raise ValueError("RIPE sample contains no valid RTT values")
    bucket=now.strftime("%Y%m%dT%H")
    row=rec("ripe_atlas",f"ripe-atlas:1001:{bucket}",
        f"RIPE Atlas public ping aggregate · K-root: {median(all_rtt):.1f} ms",
        "https://atlas.ripe.net/measurements/1001/",now,
        event_at=None, geo=geography("ripe-msm:1001","Global K-root public measurement",
             "multi_probe_measurement_cohort","not_specific_to_a_country_or_incident"),
        kind="aggregated_public_network_ping",
        measurement={"name":"sample_median_ping_rtt","value":round(median(all_rtt),3),
            "unit":"ms","measurement_id":1001,"valid_rtt_count":len(all_rtt),
            "sampled_probe_count":valid,"invalid_rtt_count":failures,
            "reference_baseline_ready":False},
        source_dependency="ripe:atlas:ping:1001")
    return [row],{"total_received":len(samples),"sampled_probe_count":valid,
                  "rtt_count":len(all_rtt),"privacy":"individual_probe_ids_not_published"}


def collect(state,clock=utcnow,fetcher=fetch_json):
    state=Path(state)
    now=clock()
    now=now.astimezone(UTC)
    result={"schema":SCHEMA,"checked_at":iso(now),"source_health":{},"source_rows":{}}
    for mode in MODES:
        requests=0
        success=0
        errors=[]
        records=[]
        received=0
        partial=False
        try:
            if mode=="usgs_quakes":
                urls=[USGS]
            elif mode=="nasa_eonet":
                urls=[EONET]
            elif mode=="noaa_swpc":
                urls=[SWPC]
            elif mode=="nws_alerts":
                urls=[NWS]
            elif mode=="usace_navigation":
                urls=[USACE_ROOT+"/"+now.strftime("%d%m%Y")]
            elif mode=="ripe_atlas":
                urls=[RIPE]
            else:
                urls=[port_url(s) for s in PORT_STATIONS]
            for url in urls:
                requests+=1
                try:
                    raw=fetcher(url)
                    if mode=="usgs_quakes":items,meta=usgs(raw,now)
                    elif mode=="nasa_eonet":items,meta=eonet(raw,now)
                    elif mode=="noaa_swpc":items,meta=swpc(raw,now)
                    elif mode=="nws_alerts":items,meta=nws(raw,now)
                    elif mode=="usace_navigation":items,meta=usace(raw,now,url)
                    elif mode=="ripe_atlas":items,meta=ripe(raw,now)
                    else:
                        station=next(s for s in PORT_STATIONS if "station="+s in url)
                        items,meta=noaa_station(raw,now,station,PORT_STATIONS[station])
                    records.extend(items)
                    received+=meta.get("total_received",len(items))
                    partial=partial or bool(meta.get("next_page_present"))
                    success+=1
                except (ValueError,TypeError,KeyError,OSError,TimeoutError,RuntimeError,UnicodeError,json.JSONDecodeError) as error:
                    errors.append(type(error).__name__+":"+safe_text(error,125))
            # No provider should report all-clear after unobserved source failure.
            if not success:
                raise ValueError("All source queries failed")
            if len(records)>CAPS[mode]:
                records=records[:CAPS[mode]]
                partial=True
            if success<requests:
                partial=True
            # Existing stable IDs must not silently change source provenance.
            unique={}
            for item in records:
                if item["id"] in unique and unique[item["id"]]!=item:
                    raise ValueError("Conflicting same-source record identity")
                unique[item["id"]]=item
            records=list(unique.values())
            mode_status="partial" if partial else "collected"
            snapshot={
                "schema":SCHEMA,"source":mode,"observed_at":iso(now),
                "status":mode_status,"records":records,
                "source_scope":SOURCE_SCOPE[mode],"source_role":SOURCE_ROLE[mode],
                "source_queries_attempted":requests,"source_queries_ok":success,
                "records_received_before_cap":received,
                "bounded_cap":CAPS[mode],"truncated":partial,
                "alert_eligible":False,"source_coverage_globally_complete":False,
                "missing_is_zero":False,
            }
            write_json(state/"latest"/f"{mode}.json",snapshot)
            health_status=mode_status
        except (ValueError,TypeError,RuntimeError) as error:
            records=[]
            errors.append(type(error).__name__+":"+safe_text(error,125))
            health_status="unavailable"
            # The previous successful snapshot is not overwritten.
        health={
            "checked_at":iso(now),"status":health_status,
            "source_queries_attempted":requests,"source_queries_ok":success,
            "records":len(records) if success else None,
            "truncated":partial,
            "source_scope":SOURCE_SCOPE[mode],"source_role":SOURCE_ROLE[mode],
            "missingness":"provider_bounded_not_exhaustive" if success and not partial else
               "partial_sampling_not_globally_complete" if success else
               "not_measured_not_zero",
            "errors":errors[:5],
            "source_coverage_globally_complete":False,
            "alert_eligible":False,
        }
        write_json(state/"health"/f"{mode}.json",health)
        result["source_health"][mode]=health
        result["source_rows"][mode]=len(records)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state",required=True,type=Path)
    args=parser.parse_args()
    response=collect(args.state)
    print(json.dumps({"checked_at":response["checked_at"],
                      "source_rows":response["source_rows"],
                      "source_health":{k:{
                          "status":v["status"],"records":v["records"],
                          "queries_ok":v["source_queries_ok"],
                          "queries_attempted":v["source_queries_attempted"]}
                      for k,v in response["source_health"].items()}},indent=2))
    # Individual providers fail independently. Fail CI on TOTAL unavailability
    # only after all source-health files have been persisted.
    return int(not any(v["source_queries_ok"] for v in response["source_health"].values()))


if __name__=="__main__":
    raise SystemExit(main())
