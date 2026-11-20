/* Public CAIRN source health, no threat classification or all-clear claims. */
(() => {
"use strict";
const $=id=>document.getElementById(id);
const BASE="https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/";
const NAMES={amsa:"AMSA NAVAREA X",commercial:"Commercial media sampling",
  ioda:"IODA connectivity",live_airspace:"FAA temporary flight restrictions",
  live_maritime:"Danish NIORD maritime notices",nga:"NGA broadcast warnings",
  official:"U.S. / U.K. official advisories",watchlist:"Prediction-market contracts",
  faa_nas:"FAA NAS airport operations",
  gdelt:"GDELT news/event index",wikipedia:"Wikipedia public attention",
  usgs:"USGS earthquake measurements",eonet:"NASA EONET natural events",
  nws:"NOAA/NWS marine weather alerts",usace:"USACE navigation notices",
  coops:"NOAA CO-OPS monitored port stations",
  swpc:"NOAA space-weather alerts",ripe:"RIPE Atlas public network aggregate"};
const FRESH_HOURS={amsa:6,commercial:48,ioda:6,live_airspace:2,live_maritime:2,
  nga:6,official:12,watchlist:12,faa_nas:25/60,gdelt:48,wikipedia:72,
  usgs:8,eonet:8,nws:8,usace:12,coops:8,swpc:8,ripe:8};
// A source's ROLE and its HEALTH are separate. News can corroborate a lead,
// but syndicated reports do not by themselves constitute independent sensors.
const SOURCE_META={
  amsa:{role:"Alternative indicator",description:
    "The Australian Maritime Safety Authority publishes navigational warnings for NAVAREA X. Its notices document navigation hazards or restrictions within a regional coverage area, not globally."},
  commercial:{role:"Context and corroboration",description:
    "Samples trade press and syndicated reports about shipping, aviation and commercial risk. Articles provide leads and background, but repeated reporting is not independently observed activity."},
  ioda:{role:"Alternative indicator",description:
    "Georgia Tech's IODA system detects unusual internet connectivity changes using network measurements. A connectivity anomaly does not establish its cause, intentional interference or attribution."},
  live_airspace:{role:"Alternative indicator",description:
    "FAA Temporary Flight Restrictions describe officially restricted U.S. airspace and affected periods. Restrictions may be routine; the feed is U.S.-only and does not establish preparations or hostile intent."},
  live_maritime:{role:"Alternative indicator",description:
    "Danish Maritime Authority NIORD notices describe maritime hazards, exercise areas and navigation restrictions in nearby waters. Different notices may refer to separate exercises and should not be counted as independent corroboration of one event."},
  nga:{role:"Alternative indicator",description:
    "U.S. National Geospatial-Intelligence Agency maritime navigational warnings identify hazards and restrictions communicated for safe navigation. Collector availability and geographic coverage may be incomplete."},
  official:{role:"Context and corroboration",description:
    "U.S. State Department and U.K. FCDO advisories summarize travel and safety concerns. These official statements offer institutional context but are not direct evidence that a specific operational event occurred."},
  watchlist:{role:"Alternative indicator",description:
    "Selected prediction-market contracts provide prices and timelines reflecting participants' expectations about specific outcomes. Prices are neither objective conflict probabilities nor independent evidence that an event occurred."},
  faa_nas:{role:"Alternative indicator",description:
    "The FAA National Airspace System feed reports selected U.S. airport operational events such as ground stops and disruption notices. It is a monitored sample, not national completeness or an assessment of cause."},
  usgs:{role:"Environmental context / independent physical mechanism",description:
    "The US Geological Survey provides timestamped worldwide earthquake measurements from a magnitude-filtered past-day feed. Seismic activity can explain infrastructure disturbances but does not establish any hostile action."},
  eonet:{role:"Environmental context / competing explanation",description:
    "NASA EONET catalogs natural events and supporting imagery links. This seven-day bounded feed is incomplete and does not establish a military cause."},
  nws:{role:"Environmental context / competing explanation",description:
    "National Weather Service marine alerts describe active U.S. weather hazards that may explain restrictions, outages or maritime diversion. This bounded marine subset is not worldwide weather monitoring."},
  usace:{role:"Alternative indicator — official navigation restrictions",description:
    "U.S. Army Corps of Engineers navigation notices describe restrictions affecting inland waterways and locks. A notice is not evidence that actual vessel throughput changed."},
  coops:{role:"Alternative indicator — selected physical port telemetry",description:
    "NOAA CO-OPS supplies observed water levels for three selected U.S. stations. Readings have no anomaly classification until comparable station-specific baselines exist."},
  swpc:{role:"Environmental explanation",description:
    "NOAA SWPC issues solar and geomagnetic warnings that can provide benign context for communications or navigation anomalies. These bulletins are not direct evidence of hostile preparations."},
  ripe:{role:"Public network measurement",description:
    "RIPE Atlas publishes public ping results to a global reference target; CAIRN keeps only aggregate latency and the public sampled-probe denominator. This is not country-level connectivity coverage or an attributable outage."},
  gdelt:{role:"Context and corroboration",description:
    "GDELT indexes worldwide news coverage, reported events and media attention. CAIRN uses it primarily to establish background and compare developing reporting, not as a direct operational sensor or independently verified event record."},
  wikipedia:{role:"Alternative attention proxy",description:
    "Wikipedia activity can reflect changes in public attention to a topic. Attention changes are indirect signals, not evidence that the underlying reported event is true."},
};

const parseTime=v=>typeof v==="string"&&Number.isFinite(Date.parse(v))?Date.parse(v):null;
const format=v=>parseTime(v)===null?"Unavailable":new Date(v).toISOString().replace("T"," ").replace(".000Z"," UTC");
const statusOf=(raw,at)=>{
  const checked=parseTime(raw.checked_at||raw.snapshot_at);
  const age=checked===null?Infinity:(at-checked)/3600000;
  if(checked===null)return "unknown";
  if(age < -0.1 || age > (FRESH_HOURS[raw.mode]||2))return "stale";
  if(raw.status==="current_partial"||raw.truncated_or_partial||raw.provider_status==="partial")return "partial";
  if(raw.status==="current"||raw.status==="collected")return "good";
  return "stale";
};
function draw(rows,source){
  const host=$("sourceRows");host.replaceChildren();
  const counts={good:0,partial:0,stale:0,unknown:0};
  const now=Date.now();
  for(const [mode,item] of Object.entries(rows).sort(([a],[b])=>a.localeCompare(b))){
    const r={...item,mode};
    const code=statusOf(r,now);counts[code]++;
    const tr=document.createElement("tr");
    const meta=SOURCE_META[mode]||{role:"Unclassified source",description:
      "No verified description for this collector is available."};
    const name=document.createElement("td");
    const nameLabel=document.createElement("strong");
    nameLabel.textContent=NAMES[mode]||mode;
    const role=document.createElement("span");role.className="source-role";
    role.textContent=meta.role;
    const description=document.createElement("span");
    description.className="source-description";
    description.textContent=meta.description;
    name.append(nameLabel,role,description);
    const scope=document.createElement("td");scope.textContent=r.source_scope||"Coverage not characterized";
    const st=document.createElement("td"),pill=document.createElement("span");
    pill.className="source-status-pill "+code;
    pill.textContent={good:"Recent check",partial:"Partial / sampled",stale:"Stale / unavailable",unknown:"Unknown"}[code];
    st.appendChild(pill);
    const detail=document.createElement("span");detail.className="source-sub";
    detail.textContent=(r.provider_status||r.status||"No provider health")+
      " · "+(r.missingness||"Coverage not fully characterized");
    st.appendChild(detail);
    const check=document.createElement("td");check.textContent=format(r.checked_at);
    // A successful check is not proof that a usable sample was captured.
    const sample=document.createElement("td");sample.textContent=format(r.snapshot_at);
    tr.append(name,scope,st,check,sample);host.appendChild(tr);
  }
  if(!host.children.length){
    const tr=document.createElement("tr"),td=document.createElement("td");
    td.colSpan=5;td.textContent="No validated source records available; status is unknown.";
    tr.appendChild(td);host.appendChild(tr);
  }
  const summary=$("sourceSummary");summary.replaceChildren();
  for(const [code,label] of [["good","Recent"],["partial","Partial"],["stale","Stale"],["unknown","Unknown"]]){
    const item=document.createElement("span");
    item.textContent=label+": "+counts[code];
    summary.appendChild(item);
  }
  $("sourceAsOf").textContent="Source: "+source+" · checked against current clock "+
    new Date(now).toISOString().replace("T"," ").replace(".000Z"," UTC")+
    ". Collection timestamps are not source publication times.";
}
async function get(url){
  const response=await fetch(url,{cache:"no-store"});
  if(!response.ok)throw new Error("Source status HTTP "+response.status);
  return response.json();
}
async function refresh(){
  $("sourceRefresh").disabled=true;
  const rows={};let note="published Atlas snapshot";
  try{
    const atlas=await get("atlas.json");
    if(atlas.status?.gdelt){
      const gd=atlas.status.gdelt;
      const checked=typeof gd==="object"?(gd.checked_at||gd.collected_at||gd.fetched_at):null;
      rows.gdelt={mode:"gdelt",status:typeof gd==="object"?(gd.status||"unknown"):String(gd),
        provider_status:"historical_media_context",
        checked_at:checked||null,snapshot_at:checked||null,
        source_scope:"News/event-index background; not a direct physical sensor",
        missingness:"Collection timestamps are unknown unless explicitly provided"};
    }
    if(atlas.status?.wikipedia){
      rows.wikipedia={mode:"wikipedia",status:String(atlas.status.wikipedia),
        provider_status:String(atlas.status.wikipedia),
        source_scope:"Public attention context; scope and timing vary",
        missingness:"No source timestamp provided in this summary"};
    }
    for(const entry of atlas.visibility_funnel?.provider_health||[]){
      if(entry&&typeof entry.name==="string")rows[entry.name]={
        status:entry.status,provider_status:entry.status,checked_at:entry.asof,
        snapshot_at:entry.snapshot_at||null,source_scope:entry.scope,
        missingness:"Published snapshot; may now be stale"};
    }
  }catch(_){}
  // Current sensor checks may be newer than the last Pages publication.
  if(location.hostname!=="localhost"&&location.hostname!=="127.0.0.1"){
    const [registry,faa]=await Promise.allSettled([
      get(BASE+"latest/behavioral_registry.json"),get(BASE+"health/faa_nas.json")]);
    if(registry.status==="fulfilled"&&registry.value?.schema==="aiba.behavioral-observations.v1"){
      for(const [name,health] of Object.entries(registry.value.source_health||{})){
        if(health&&typeof health==="object"&&name in FRESH_HOURS){
          rows[name]={...health,mode:name};
        }
      }
      note="live public evidence-branch collector health";
    }
    if(faa.status==="fulfilled"&&faa.value?.schema==="aiba.faa-nas-health.v1"){
      const f=faa.value;
      rows.faa_nas={status:f.status,provider_status:f.status,checked_at:f.checked_at,
        snapshot_at:f.checked_at,source_scope:f.source_scope,
        missingness:"Selected airport sample; no all-clear inference",mode:"faa_nas"};
    }else{
      rows.faa_nas={status:"unavailable",provider_status:"unavailable",mode:"faa_nas",
        source_scope:"FAA NAS monitored U.S. airport records",missingness:"No current health record"};
    }
  }
  // Legacy GDELT/Wikipedia build context is represented explicitly, even
  // when Atlas has no source-verified last collection timestamp.
  // Do not substitute publication time for a successful source pull.
  // Missing provider rows are coverage gaps, not an absent surveillance need.
  for(const mode of Object.keys(FRESH_HOURS)){
    if(!(mode in rows)){
      rows[mode]={mode,status:"unavailable",provider_status:"never_checked_or_missing",
        source_scope:"No validated source scope in this snapshot",
        missingness:"not_measured_not_zero"};
    }
  }
  draw(rows,note);
  $("sourceRefresh").disabled=false;
}
$("sourceRefresh").addEventListener("click",refresh);
refresh();
})();