"""Public Asian grid telemetry and RIPE RIS routing-update context.

Taipower: public Taiwan nationwide 10-minute load snapshot; timestamp is
dataset release time, NOT independently established measurement time.
RIS: sampled route announcements about selected public ASNs; target
operator registration is not the observation's physical event location.
"""
from __future__ import annotations
import datetime as dt
import math
import re
from urllib.parse import urlencode,parse_qs,urlsplit
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
TAIPOWER_URL="https://service.taipower.com.tw/data/opendata/apply/file/d006020/001.json"
TAIPOWER_DOC="https://data.gov.tw/en/datasets/162595"
RIPE_ROOT="https://stat.ripe.net/data/bgp-update-activity/data.json?"
# Public AS network examples only; AS ownership and current operation may
# change. These are NOT country-level probes or assertions of outages.
RIPE_ASNS={"AS4134":"CN","AS9829":"IN","AS4766":"KR","AS7552":"VN",
           "AS5713":"ZA","AS7303":"AR"}
SCOPE={
 "tw_power":"Taiwan Taipower public nationwide current load snapshot and publisher release clock, not power-station or local outage data",
 "ris_bgp":"RIPE RIS public route-announcement update samples on six non-Western operated networks; ASNs not country-wide outage detection",
}

def urls(mode):
    if mode=="tw_power":return [TAIPOWER_URL]
    if mode=="ris_bgp":
        return [RIPE_ROOT+urlencode({"resource":asn,"num_hours":6,
                 "max_samples":24,"hide_empty_samples":"false"})
                for asn in RIPE_ASNS]
    raise ValueError("Unsupported source")

def taiwan_release(value):
    """ROC calendar source publication time in Asia/Taipei, not load event time."""
    if not isinstance(value,str):return None
    m=re.fullmatch(r"\s*(\d{2,3})\.(\d{1,2})\.(\d{1,2})"
                   r"\([^)]{1,4}\)(\d{1,2}):(\d{2})\s*",value)
    if not m:return None
    year,month,day,hour,minute=map(int,m.groups())
    try:return dt.datetime(year+1911,month,day,hour,minute,
                           tzinfo=ZoneInfo("Asia/Taipei")).astimezone(UTC)
    except ValueError:return None

def taiwan(data,checked,url,entry):
    if not isinstance(data,dict) or data.get("success") not in (True,"true"):
        raise ValueError("Taipower official JSON missing success")
    records=data.get("records")
    if not isinstance(records,list) or not 2<=len(records)<=10 or not all(
            isinstance(x,dict) for x in records):
        raise ValueError("Taipower numeric/publish record list invalid")
    clock=taiwan_release(records[1].get("publish_time"))
    if not clock or not dt.timedelta(0)<=checked-clock<=dt.timedelta(hours=9):
        raise ValueError("Taipower source release timestamp stale or future")
    raw=records[0].get("curr_load")
    try:
        if type(raw) not in (str,int,float):raise ValueError("Invalid load type")
        load=float(raw)
    except (ValueError,TypeError):raise ValueError("Taipower current load not numeric")
    if not math.isfinite(load) or not 0<=load<=10000:
        raise ValueError("Taipower current load out of bounds")
    pct=records[0].get("curr_util_rate")
    try:util=float(pct)
    except (TypeError,ValueError):util=None
    if util is not None and (not math.isfinite(util) or not 0<=util<=100):util=None
    when=clock.isoformat().replace("+00:00","Z")
    record=entry("tw_power",clock.strftime("%Y%m%dT%H%MZ"),
        "Taipower nationwide publicly reported current electricity load",
        TAIPOWER_URL,checked,published=when,
        kind="national_grid_load_aggregate_not_outage",
        geo={"key":"country:TW","kind":"national_aggregate_without_incident_site",
             "label":"Taiwan","precision":"national_not_facility",
             "latitude":None,"longitude":None,"verified_iso":True},
        measurement={"name":"nationwide_reported_current_load",
             "value":round(load*10,2),"unit":"MW",
             "source_value_10k_kilowatts":load,
             "reported_utilization_percent":util,
             "source_published_clock":when,
             "measurement_clock_distinct_from_release_not_verified":True,
             "observation_coverage":"single_national_snapshot_not_24h",
             "baseline_status":"not_calibrated",
             "not_grid_frequency_or_outage_attribution":True},
        source_scope=SCOPE["tw_power"])
    return [record] if record else []

def _parse(value):
    if not isinstance(value,str):return None
    try:
        v=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return v.astimezone(UTC) if v.tzinfo else None
    except ValueError:return None

def ris(data,checked,url,entry):
    query=parse_qs(urlsplit(url).query)
    asn=(query.get("resource") or [""])[0]
    if asn not in RIPE_ASNS:raise ValueError("Unapproved RIPE target ASN")
    if not isinstance(data,dict) or data.get("status")!="ok":
        raise ValueError("RIPEstat routing API status invalid")
    d=data.get("data")
    if not isinstance(d,dict) or str(d.get("resource")).upper() not in (asn,asn[2:]):
        raise ValueError("RIPEstat returned wrong resource identity")
    if d.get("resource_type") not in ("asn","ASN"):
        raise ValueError("RIPEstat resource type must be ASN")
    ending=_parse(d.get("query_endtime"))
    if not ending or not dt.timedelta(0)<=checked-ending<=dt.timedelta(hours=10):
        raise ValueError("RIPEstat sampling query end timestamp invalid")
    updates=d.get("updates")
    if not isinstance(updates,list) or len(updates)>24:
        raise ValueError("RIPEstat bounded aggregate update sample invalid")
    total=0
    for u in updates:
        if not isinstance(u,dict):raise ValueError("RIPEstat malformed sample")
        n=u.get("announcements")
        if type(n) is not int or not 0<=n<=10_000_000:
            raise ValueError("RIPEstat announcement count missing or unbounded")
        total+=n
    observed_end=ending.isoformat().replace("+00:00","Z")
    key=asn+":"+ending.strftime("%Y%m%dT%H")
    record=entry("ris_bgp",key,"RIPE RIS sampled BGP announcements: "+asn,
      url,checked,kind="sampled_asn_bgp_route_updates_not_network_outage",
      geo={"key":"asn:"+asn[2:],"kind":"network_resource_not_event_location",
        "label":asn,"precision":"routing_target_not_country_incident",
        "latitude":None,"longitude":None,"verified_iso":False},
      measurement={"name":"sampled_6h_bgp_announcements",
        "value":total,"unit":"announcements",
        "target_asn":asn,"registered_network_country_hint":RIPE_ASNS[asn],
        "source_window_end":observed_end,
        "window_hours_requested":6,"returned_sampling_buckets":len(updates),
        "withdrawals_unavailable_for_asn":True,
        "collector_peers_are_not_geo_deduplicated":True,
        "country_impact_not_established":True,
        "baseline_status":"not_calibrated"},
      source_scope=SCOPE["ris_bgp"])
    return [record] if record else []
