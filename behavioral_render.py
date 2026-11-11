#!/usr/bin/env python3
"""Publish a read-only, dated AIBA behavioral triage panel.

Unlocated sources remain unlocated; provider failures remain visible.
This page is a bounded briefing, never an automatic executive warning.
"""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

from behavioral_fusion import SCHEMA
from behavioral_registry import when, iso
from ops_pipeline import load_json, write_json

UTC=dt.timezone.utc


def esc(value):
    return html.escape(str(value if value is not None else ""),quote=True)


def link(url,label):
    try:
        v=urlsplit(str(url))
        if v.scheme=="https" and v.hostname and not v.username and not v.password:
            return f'<a rel="noopener noreferrer" target="_blank" href="{esc(url)}">{esc(label)}</a>'
    except (ValueError,TypeError):
        pass
    return esc(label)


def render(state,site,clock=None):
    now=(clock or (lambda:dt.datetime.now(UTC)))().astimezone(UTC)
    state,site=Path(state),Path(site)
    source=load_json(state/"latest"/"behavioral_fusion.json",{}) or {}
    original=when(source.get("generated_at"))
    valid=(source.get("schema")==SCHEMA and
           isinstance(source.get("review_groups"),list) and
           isinstance(source.get("new_single_source_leads"),list))
    age=(now-original).total_seconds()/3600 if original else None
    current=bool(valid and age is not None and 0<=age<=6)
    if valid:
        payload={**source,"site_generated_at":iso(now),
                 "site_source_age_hours":round(age,2) if age is not None else None,
                 "site_snapshot_fresh":current}
        groups=source["review_groups"][:25]
        leads=source["new_single_source_leads"][:50]
        health=source.get("collection_coverage") or {}
    else:
        payload={
            "schema":SCHEMA,"site_generated_at":iso(now),"generated_at":None,
            "site_snapshot_fresh":False,"site_source_age_hours":None,
            "review_groups":[],"new_single_source_leads":[],
            "collection_coverage":{},
            "status":"No behavioral fusion source has been collected."}
        groups=[];leads=[];health={}
    warning=("FRESH SOURCE SNAPSHOT (not a current threat assessment)" if current else
             "NO RECENT VALID SOURCE SNAPSHOT — historical context only; do not infer calm")
    health_rows=[]
    for mode in ("ioda","nga","amsa","official","commercial","watchlist","live_airspace","live_maritime"):
        row=health.get(mode) or {}
        health_rows.append(
            "<tr><td>"+esc(mode.upper())+"</td><td>"+
            esc(row.get("status") or "not collected")+"</td><td>"+
            esc(row.get("snapshot_at") or "unavailable")+"</td><td>"+
            esc(row.get("source_scope") or "not yet measured")+"</td></tr>"
        )
    group_items=[]
    for group in groups:
        place=(group.get("geography") or {}).get("label") or "Unlocated"
        refs=group.get("source_links") or []
        sources="".join(
            "<li>"+link(s.get("url"),s.get("provider") or s.get("family"))+
            " · "+esc(s.get("family"))+
            " · observed "+esc(s.get("first_observed_at"))+
            " · published "+esc(s.get("published_at") or "unknown")+"</li>"
            for s in refs[:16]
        )
        group_items.append(
            '<article class="group"><h3>'+esc(place)+'</h3><p class="sub">'+
            esc(group.get("source_family_count"))+
            ' distinct source families · '+esc(group.get("status"))+
            '</p><p>'+esc(group.get("assessment"))+'</p><ul>'+sources+
            '</ul><p class="sub">No actor-level attribution, causal independence, '
            'or military preparation has been confirmed.</p></article>'
        )
    singles=[]
    for s in leads:
        place=(s.get("geography") or {}).get("label") or "Location not verified"
        singles.append(
            "<li>"+link(s.get("source_url"),s.get("title") or s.get("observation_id"))+
            " · "+esc(s.get("source_family"))+
            " · "+esc(place)+
            " · first observed "+esc(s.get("first_observed_at"))+
            "</li>"
        )
    doc='''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIBA | Behavioral Investigative Leads</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101720;color:#e6eaf1;font:14px/1.55 system-ui,sans-serif}
main{max-width:1180px;margin:auto;padding:24px}a{color:#a9d0f7}h1{font-size:25px}h2{font-size:18px}h3{font-size:16px;margin:0}
.sub{font-size:12px;color:#a9b5c5}.notice{padding:12px;border:1px solid #6c5e40;background:#2e2b26;border-radius:8px}
section,.group{margin:16px 0;border:1px solid #354355;border-radius:10px;background:#1c2632;padding:17px}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:8px;text-align:left;border-bottom:1px solid #344151}
ul{padding-left:22px}li{padding:5px 0;overflow-wrap:anywhere}
@media(max-width:650px){main{padding:14px}table{display:block;overflow:auto}h1{font-size:21px}}
</style></head><body><main>
<p><a href="../">Global AIBA Atlas</a> · <a href="../ops/">Existing decision briefs</a></p>
<h1>Behavioral Discovery &amp; Multisource Triage</h1>
<p class="notice">'''+esc(warning)+'''<br>
Source-separated OSINT research leads only. No automatic Critical/Watch severity change, confirmed threat, or forecast probability.</p>
<p class="sub">Source reconciliation: '''+esc(payload.get("generated_at") or "none")+'''; page generated: '''+esc(iso(now))+'''.
Source-relative timestamps are not necessarily event-onset timestamps. Provider geographical scope varies.</p>
<section><h2>Cross-family geographic review candidates ('''+esc(len(groups))+''')</h2>
<p>Only exact provider-declared geographic overlap between distinct source families is surfaced here. Common cause and relevance remain unverified.</p>
'''+("".join(group_items) if group_items else
     '<p class="sub">No eligible new cross-family geographic co-occurrence; this does not mean no ongoing threat.</p>')+'''
</section>
<section><h2>New individual source observations ('''+esc(len(leads))+''')</h2>
<p>Includes sources outside established watches and observations without validated geographic coordinates.</p>
'''+("<ul>"+"".join(singles)+"</ul>" if singles else
     '<p class="sub">No new source observations since the preceding valid baseline, or the snapshot is unavailable.</p>')+'''
</section>
<section><h2>Collection coverage and missingness</h2>
<p>Available sources cover bounded portions of worldwide activity. Missing or partial providers are not treated as normal conditions.</p>
<table><thead><tr><th>Provider</th><th>Status</th><th>Source snapshot</th><th>Actual coverage limit</th></tr></thead>
<tbody>'''+''.join(health_rows)+'''</tbody></table>
</section>
<section><h2>Method and constraints</h2>
<p>GDELT remains a parallel contextual media-event stream; UCDP is a retrospective outcome dataset. Neither is required for behavioral source ingestion. A collection-time coincidence is not verified military preparation.</p>
<p><a href="behavioral_fusion.json">Read source-timed machine-readable audit</a>. The GitHub evidence-branch history records non-events and source health only insofar as they were actually measured; evaluation requires a separately defined risk set and outcome-label review.</p></section>
</main></body></html>'''
    target=site/"behavior"
    target.mkdir(parents=True,exist_ok=True)
    (target/"index.html").write_text(doc,encoding="utf-8")
    write_json(target/"behavioral_fusion.json",payload)
    return payload


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state",type=Path,required=True)
    p.add_argument("--site",type=Path,required=True)
    a=p.parse_args()
    result=render(a.state,a.site)
    print(json.dumps({"source_generated_at":result.get("generated_at"),
                      "fresh":result["site_snapshot_fresh"],
                      "review_groups":len(result["review_groups"]),
                      "new_single_leads":len(result["new_single_source_leads"])}))
