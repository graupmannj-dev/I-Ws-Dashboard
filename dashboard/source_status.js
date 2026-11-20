/* Public AIBA source health, no threat classification or all-clear claims. */
(() => {
"use strict";
const $=id=>document.getElementById(id);
const BASE="https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/";
const NAMES={amsa:"AMSA NAVAREA X",commercial:"Commercial media sampling",
  ioda:"IODA connectivity",live_airspace:"FAA temporary flight restrictions",
  live_maritime:"Danish NIORD maritime notices",nga:"NGA broadcast warnings",
  official:"U.S. / U.K. official advisories",watchlist:"Prediction-market contracts",
  faa_nas:"FAA NAS airport operations"};
const FRESH_HOURS={amsa:6,commercial:48,ioda:6,live_airspace:2,live_maritime:2,
  nga:6,official:12,watchlist:12,faa_nas:25/60};
const parseTime=v=>typeof v==="string"&&Number.isFinite(Date.parse(v))?Date.parse(v):null;
const format=v=>parseTime(v)===null?"Unavailable":new Date(v).toISOString().replace("T"," ").replace(".000Z"," UTC");
const statusOf=(raw,at)=>{
  const checked=parseTime(raw.checked_at||raw.snapshot_at);
  const age=checked===null?Infinity:(at-checked)/3600000;
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
    const name=document.createElement("td");name.textContent=NAMES[mode]||mode;
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
    const sample=document.createElement("td");sample.textContent=format(r.snapshot_at||r.checked_at);
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
    for(const entry of atlas.visibility_funnel?.provider_health||[]){
      if(entry&&typeof entry.name==="string")rows[entry.name]={
        status:entry.status,provider_status:entry.status,checked_at:entry.asof,
        snapshot_at:entry.asof,source_scope:entry.scope,
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
  draw(rows,note);
  $("sourceRefresh").disabled=false;
}
$("sourceRefresh").addEventListener("click",refresh);
refresh();
})();