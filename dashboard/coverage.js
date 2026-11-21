/* CAIRN conservative geographic-coverage inventory: no all-clear. */
(() => {
"use strict";
const $=id=>document.getElementById(id);
const statuses=new Set(["current","current_partial"]);
const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const friendly={national_sample:"National bounded sample",regional:"Regional source",
  global_bounded:"Worldwide eligible, bounded events",global_unlocated:"Global aggregate; locations unverified",
  narrative_only:"Narrative context",market_selected:"Selected market contracts",unknown:"Source footprint unreviewed"};
const visibleStatus=r=>statuses.has(r.publisher_health)?r.publisher_health:"stale_or_unavailable";
let rows=[],countries=[];
function render(){
  const needle=$("coverageSearch").value.trim().toLowerCase();
  const kind=$("coverageClass").value,health=$("coverageStatus").value;
  const hits=rows.filter(r=>{
    if(kind!=="all"&&r.coverage_class!==kind)return false;
    if(health==="current"&&!statuses.has(r.publisher_health))return false;
    if(health==="missing"&&statuses.has(r.publisher_health))return false;
    if(health==="zero"&&r.visibility!=="bounded_sample_zero_not_global_all_clear")return false;
    return !needle||[
       r.mode,r.issuer_origin,r.mechanism,r.coverage_description,r.coverage_class,
       ...(r.declared_country_jurisdictions||[])].join(" ").toLowerCase().includes(needle);
  });
  $("coverageCount").textContent=hits.length+" / "+rows.length+" source mechanisms shown";
  const host=$("sourceList");host.replaceChildren();
  for(const r of hits){
    const card=document.createElement("details");card.className="source-card";
    const title=document.createElement("summary");
    const status=visibleStatus(r);
    title.innerHTML='<span class="source-head"><strong>'+esc(r.mode.replace(/_/g," "))+
      '</strong><span class="pill '+esc(status)+'">'+esc(status.replace(/_/g," "))+'</span></span>'+
      '<span class="source-sub">'+esc(r.mechanism)+' · '+esc(friendly[r.coverage_class]||"Coverage unreviewed")+
      ' · '+esc(r.issuer_origin||"Publisher origin unknown")+'</span>';
    const body=document.createElement("div");body.className="source-body";
    const count=r.recent_source_records===null?"Unavailable / not measured":r.recent_source_records+" records in bounded latest sample";
    body.innerHTML='<p>'+esc(r.coverage_description)+'</p>'+
      '<dl><dt>Publisher origin</dt><dd>'+esc(r.issuer_origin||"Unverified")+'</dd>'+
      '<dt>Jurisdiction labels</dt><dd>'+esc((r.declared_country_jurisdictions||[]).join(", ")||"Not country located")+'</dd>'+
      '<dt>Current count</dt><dd>'+esc(count)+'</dd>'+
      '<dt>Observation status</dt><dd>'+esc(r.visibility.replace(/_/g," "))+'</dd>'+
      '<dt>Source last checked</dt><dd>'+esc(r.source_checked_at||"Not checked")+'</dd>'+
      '<dt>Coverage completeness</dt><dd>Not established; declared source jurisdiction only</dd></dl>';
    const note=document.createElement("p");note.className="muted";
    note.textContent="Source age and event occurrence are separate. Missing, zero, or regional snapshots do not establish normal conditions.";
    body.appendChild(note);card.append(title,body);host.appendChild(card);
  }
  if(!hits.length){const empty=document.createElement("p");empty.className="muted";empty.textContent="No matching source modes. This is a filtered inventory, not an all-clear.";host.appendChild(empty);}
  const countryCodes=new Set(hits.flatMap(r=>r.declared_country_jurisdictions||[]));
  const country=$("countryList");country.replaceChildren();
  for(const code of [...countryCodes].sort()){
    const badge=document.createElement("span");badge.className="country";
    const n=hits.filter(r=>(r.declared_country_jurisdictions||[]).includes(code)).length;
    badge.textContent=code+" · "+n+" sources";country.appendChild(badge);
  }
  if(!country.childElementCount){const p=document.createElement("p");p.className="muted";p.textContent="No declared national jurisdictions in this filter.";country.appendChild(p);}
}
async function load(){
  try{
    const res=await fetch("coverage.json",{cache:"no-store"});
    if(!res.ok)throw Error("HTTP "+res.status);
    const data=await res.json();
    if(data.schema!=="cairn.source-geography.v1"||!Array.isArray(data.sources)||data.sources.length>400)
      throw Error("Unsupported or oversized geographic inventory");
    rows=data.sources;countries=data.country_jurisdictions||[];
    const numbers=[
      [data.source_modes_total,"Documented source modes"],
      [data.currently_checked_modes,"Recently checked sources"],
      [data.sampled_modes_with_records,"Recent samples with observations"],
      [data.monitored_country_jurisdiction_count,"Declared national jurisdictions (not complete coverage)"],
    ];
    const summary=$("coverageSummary");summary.replaceChildren();
    for(const [value,label] of numbers){
      const item=document.createElement("div");item.className="metric";
      const strong=document.createElement("strong");strong.textContent=value??"Unknown";
      const span=document.createElement("span");span.textContent=label;
      item.append(strong,span);summary.append(item);
    }
    $("coverageSearch").addEventListener("input",render);
    $("coverageClass").addEventListener("change",render);
    $("coverageStatus").addEventListener("change",render);
    render();
  }catch(e){
    $("coverageSummary").textContent="Coverage index unavailable — "+e.message;
    $("sourceList").textContent="Missing coverage data must not be interpreted as no observed risk.";
    $("countryList").textContent="Source coverage unavailable.";
  }
}
async function showPhysicalBaselines(){
  const target=$("metricDetails");
  try{
    const res=await fetch("metric_baselines.json",{cache:"no-store"});
    if(!res.ok)throw Error("HTTP "+res.status);
    const data=await res.json();
    if(data.schema!=="cairn.metric-cohort-baselines.v1"||
       !Array.isArray(data.series)||data.series.length>300)
      throw Error("Unsupported metric baseline artifact");
    target.replaceChildren();
    const summary=document.createElement("p");summary.className="muted";
    summary.textContent=(data.series_ready_for_descriptive_deviation||0)+
      " descriptive cohorts ready of "+data.series.length+
      " measured series. Historical comparison is not a conflict-warning score.";
    target.append(summary);
    for(const record of data.series.slice(0,40)){
      const line=document.createElement("div");line.className="metric-row";
      const a=document.createElement("strong");a.textContent=record.series||"unknown series";
      const desc=document.createElement("span");
      desc.textContent=(record.status||"unassessed")+
        " · "+(record.comparable_historical_points??0)+" matched prior periods"+
        " · latest "+(record.source_clock||"unavailable");
      line.append(a,desc);target.append(line);
    }
  }catch(error){
    target.textContent="Matched source history not available: "+error.message+
      ". No uncertainty or missingness is treated as a normal condition.";
  }
}
async function showSourceDependencies(){
  const target=$("dependencyDetails");
  try {
    const res=await fetch("source_dependency_audit.json",{cache:"no-store"});
    if(!res.ok)throw Error("HTTP "+res.status);
    const d=await res.json();
    if(d.schema!=="cairn.source-dependency-audit.v1")
      throw Error("Unsupported source-dependency audit");
    target.replaceChildren();
    const p=document.createElement("p");p.className="muted";
    p.textContent=d.comparison_available ?
      (d.candidate_common_event_pairs||[]).length+
      " possible shared physical earthquakes; "+(d.ambiguous_pair_candidates||[]).length+
      " ambiguous candidates. All require review. None automatically adds independent security evidence.":
      "Comparative USGS/BMKG observation coverage unavailable or stale; no implication of no earthquakes.";
    target.appendChild(p);
    for(const row of (d.candidate_common_event_pairs||[]).slice(0,25)){
      const line=document.createElement("div");line.className="metric-row";
      line.textContent=(row.source_ids||[]).join(" / ")+
        " · "+row.epicenter_distance_km+" km · "+
        row.origin_time_difference_seconds+" seconds · possible same quake, unreviewed";
      target.appendChild(line);
    }
  } catch(error){
    target.textContent="Cross-publisher audit not available: "+error.message+
      ". Missing assessment is not proof of independent events.";
  }
}
showSourceDependencies();
showPhysicalBaselines();
load();
})();