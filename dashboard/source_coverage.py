"""CAIRN nominal source geography and health — what a collector can/does cover.

This is a CAPABILITY ledger, *not* a geographic coverage probability map.
Source-published jurisdiction, issuer origin and sampled observation footprint
must never be conflated. Missing or quiet feeds do NOT mean no risk.
"""
from __future__ import annotations

SCHEMA="cairn.source-geography.v1"

# coverage_class:
# national_sample: a single national jurisdiction with meaningful incompleteness
# regional: bounded multi-country waters or aeronautical regions
# global_bounded: provider indexes worldwide but with threshold/window caps
# global_unlocated: world aggregate without valid incident or country locations
# narrative_only: descriptive reporting without sensor completeness claims
# market_selected: selected market expectations, no full territory claim
# unknown: require supplier documentation before making location assertions
#
# Countries list only *explicit source-jurisdiction codes*, not incident sites,
# satellite/probe locations or geographic extrapolations from headlines.
CATALOG={
 "usgs":("US",[],"global_bounded","Global M4.5+ earthquakes; past-day source cutoff","physical_seismic"),
 "eonet":("US",[],"global_bounded","World natural events; seven-day open-event sample","environmental_catalog"),
 "ioda":("US",[],"global_bounded","World internet-outage discovery; capped country queries","network_measurement"),
 "ripe":("NL",[],"global_unlocated","K-root global public ping cohort only; NOT country availability","network_aggregate"),
 "swpc":("US",[],"global_unlocated","Solar/geomagnetic bulletin context; not a located threat site","official_weather"),
 "commercial":(None,[],"narrative_only","Selected trade news; not observed port flow","media"),
 "official":("US/GB",[],"narrative_only","Selected U.S./U.K. advisories; narrative country coverage","official_notice"),
 "watchlist":(None,[],"market_selected","Selected market contracts only","market_quote"),
 "nga":("US",[],"regional","Maritime notice areas vary by bulletin; not global coverage","official_notice"),
 "amsa":("AU",[],"regional","NAVAREA X only","official_notice"),
 "live_airspace":("US",["US"],"national_sample","FAA U.S. temporary flight restriction sample","official_notice"),
 "live_maritime":("DK",[],"regional","Danish NIORD regional North Sea/Baltic notices","official_notice"),
 "nws":("US",["US"],"national_sample","Florida-area U.S. weather alert sample only","weather_notice"),
 "usace":("US",["US"],"national_sample","U.S. waterway notices in three sampled districts","official_notice"),
 "coops":("US",["US"],"national_sample","Three U.S. monitored port-level water stations","physical_station"),
 "faa_nas":("US",["US"],"national_sample","Selected U.S. FAA NAS system interruptions","aviation_operations"),
 "uk_tenders":("GB",["GB"],"national_sample","UK Find a Tender bounded OCDS releases","public_procurement"),
 "cbp_wait":("US",["US"],"national_sample","U.S. border crossings: port-local commercial wait estimates","transport_delay"),
 "wiki_edits":(None,[],"global_unlocated","14 Wikipedia language editions; language NOT editor origin","attention_proxy"),
 "bmkg_quake":("ID",["ID"],"national_sample","Indonesia BMKG M5+ last 15 earthquakes; overlaps USGS","physical_seismic"),
 "bmkg_nowcast":("ID",["ID"],"national_sample","Indonesia BMKG provincial severe-weather nowcast","weather_notice"),
 "inmet_br":("BR",["BR"],"national_sample","Brazil INMET official weather warnings","weather_notice"),
 "imd_in":("IN",["IN"],"national_sample","India IMD official alerts via WMO relay, no independent event","weather_notice"),
 "saws_za":("ZA",["ZA"],"national_sample","South Africa SAWS alerts via WMO relay","weather_notice"),
 "sg_mpa":("SG",["SG"],"national_sample","Singapore MPA monthly port arrivals, lagged NOT live","physical_maritime_lagged"),
}

def build(registry,generated_at=None):
    if not isinstance(registry,dict):registry={}
    statuses=registry.get("source_health") or {}
    counts=registry.get("snapshot_counts_by_mode") or {}
    if not isinstance(statuses,dict):statuses={}
    if not isinstance(counts,dict):counts={}
    all_modes=sorted(set(CATALOG)|set(statuses))
    rows=[]
    for mode in all_modes:
        origin,countries,kind,description,mechanism=CATALOG.get(mode,
            (None,[],"unknown","Publisher footprint unreviewed","unclassified"))
        record=statuses.get(mode,{})
        if not isinstance(record,dict):record={}
        status=record.get("status","not_measured")
        sampled_count=counts.get(mode)
        if type(sampled_count) is not int or sampled_count<0:
            sampled_count=None
        current=status in ("current","current_partial")
        if current and sampled_count is not None:
            visibility=("sampled_observations_present" if sampled_count>0
                        else "bounded_sample_zero_not_global_all_clear")
        elif current:
            visibility="sample_count_unknown"
        else:
            visibility="missing_or_stale_not_measured"
        rows.append({
            "mode":mode,"issuer_origin":origin,
            "declared_country_jurisdictions":countries,
            "coverage_class":kind,
            "coverage_description":description,
            "mechanism":mechanism,
            "publisher_health":status,
            "recent_source_records":sampled_count if current else None,
            "visibility":visibility,
            "source_checked_at":record.get("checked_at"),
            "scope_declared_not_completeness":True,
            "supports_absence_of_threat_inference":False,
            "has_event_site_coordinates":False,
        })
    country_map={}
    for row in rows:
        for code in row["declared_country_jurisdictions"]:
            country_map.setdefault(code,[]).append(row["mode"])
    country_index=[{"iso2":code,"source_modes":sorted(modes),
                   "source_mode_count":len(modes),
                   "country_coverage_verified":False}
                   for code,modes in sorted(country_map.items())]
    return {"schema":SCHEMA,"generated_at":generated_at,
            "status":"declared_capabilities_not_verified_completeness",
            "source_modes_total":len(rows),
            "currently_checked_modes":sum(x["publisher_health"] in ("current","current_partial") for x in rows),
            "sampled_modes_with_records":sum(x["visibility"]=="sampled_observations_present" for x in rows),
            "monitored_country_jurisdiction_count":len(country_index),
            "sources":rows,"country_jurisdictions":country_index,
            "unknown_or_unlocated_global_modes":[x["mode"] for x in rows if
                x["coverage_class"] in ("global_unlocated","narrative_only","market_selected")],
            "interpretation":[
               "Country lists identify authority-described jurisdiction, not data completeness or a live event location.",
               "A globally bounded feed is not dense monitoring of every country, town or point.",
               "Issuer origin is not geographic event coverage. WMO RSS relays are not second observers.",
               "A zero count in a bounded healthy sample is NOT an all-clear or proof against a hypothesis.",
               "Missing collectors cannot be recorded as zero observations or contradicting evidence.",
               "Neither more source modes nor more titles establishes independently observed physical mechanisms."
            ]}
