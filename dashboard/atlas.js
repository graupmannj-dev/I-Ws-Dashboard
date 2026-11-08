/* AIBA Atlas / zero external runtime dependencies.
 * Sourced chronology, schematic geography, no invented "Critical" judgments.
 */
(() => {
"use strict";

const $ = id => document.getElementById(id);
const DEG = Math.PI / 180;
const colors = {
  critical:"#f06570", active:"#ef6b52", high:"#f3a348", watch:"#edc852",
  low:"#57c99b", report:"#aab9cb"
};
const commandAreas = [
  {name:"USNORTHCOM",lat:49,lon:-104,west:-164,east:-50,south:16,north:72,color:"#659fd6"},
  {name:"USSOUTHCOM",lat:-16,lon:-62,west:-110,east:-31,south:-57,north:18,color:"#54c6a8"},
  {name:"USEUCOM",lat:52,lon:15,west:-15,east:49,south:31,north:74,color:"#ad97e2"},
  {name:"USAFRICOM",lat:-1,lon:16,west:-25,east:53,south:-36,north:37,color:"#e4c46e"},
  {name:"USCENTCOM",lat:28,lon:57,west:33,east:85,south:10,north:48,color:"#e7a97b"},
  {name:"USINDOPACOM",lat:19,lon:135,west:85,east:178,south:-51,north:62,color:"#71cad4"}
];
// Command boxes are schematic orientation only, not actual AOR borders.
const state = {
  atlas:null,countries:null,selected:null,selectionType:"hotspot",
  severity:"all",watchTab:"all",windowDays:7,
  friction:null,frictionShowAll:false,frictionRemoteStatus:"static fallback",
  dates:[],minDay:0,maxDay:0,startDay:0,endDay:0,
  rangeDrag:null,
  lon:52,lat:20,zoom:1,pins:[],reports:[],hitTargets:[],dimensions:{w:1,h:1,dpr:1,cx:0,cy:0,r:1},
  canvas:null,ctx:null,staticCanvas:null,staticValid:false,drag:null,lastFrame:0,
  animationId:0,showControls:true
};
function safe(value){return String(value??"").replace(/[&<>"']/g,s=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[s]));}
function safeUrl(value){return typeof value==="string"&&/^https:\/\//.test(value)?value:null;}
function dayNum(s){const n=Date.parse(String(s||"")+"T00:00:00Z");return Number.isFinite(n)?Math.floor(n/86400000):null;}
function dayString(n){return new Date(n*86400000).toISOString().slice(0,10);}
function shortDay(n){return new Date(n*86400000).toLocaleDateString("en-US",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"});}
function clamp(n,a,b){return Math.max(a,Math.min(b,n));}
function lighten(hex,amt){const val=parseInt(hex.slice(1),16),rgb=[val>>16,(val>>8)&255,val&255];return "rgb("+rgb.map(v=>clamp(v+amt,0,255)).join(",")+")";}
function proj(lon,lat){
  const lo=(lon-state.lon)*DEG, la=lat*DEG, ref=state.lat*DEG;
  const c=Math.cos(la),s=Math.sin(la);
  return {x:c*Math.sin(lo),y:Math.cos(ref)*s-Math.sin(ref)*c*Math.cos(lo),
          z:Math.sin(ref)*s+Math.cos(ref)*c*Math.cos(lo)};
}
function xy(p){const d=state.dimensions;return {x:d.cx+p.x*d.r,y:d.cy-p.y*d.r,z:p.z};}
function visible(lon,lat){const p=proj(lon,lat);return p.z>0.015?xy(p):null;}
function resize(){
  const wrap=$("globeWrap"), rect=wrap.getBoundingClientRect();
  const w=Math.max(200,Math.round(rect.width)),h=Math.max(280,Math.round(rect.height));
  const dpr=Math.min(window.devicePixelRatio||1,2);
  const canvas=$("globe");canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  state.canvas=canvas;state.ctx=canvas.getContext("2d");state.ctx.setTransform(dpr,0,0,dpr,0,0);
  state.dimensions={w,h,dpr,cx:w/2,cy:h/2+5,r:Math.min(h*.455,w*.455)*state.zoom};
  $("zoomLevel").textContent=state.zoom.toFixed(1)+"×";
  state.staticCanvas=document.createElement("canvas");
  state.staticCanvas.width=canvas.width;state.staticCanvas.height=canvas.height;
  state.staticValid=false;
}
function radius(){return state.dimensions.r;}
function horizonIntersection(a,b){
  const k=a.z/(a.z-b.z);
  let x=a.x+(b.x-a.x)*k,y=a.y+(b.y-a.y)*k;
  const norm=Math.hypot(x,y)||1;
  return {x:x/norm,y:y/norm,z:0};
}
function clipRing(points){
  const result=[];if(!points.length)return result;
  let prev=points[points.length-1];
  for(const cur of points){
    if((prev.z>=0)!=(cur.z>=0))result.push(horizonIntersection(prev,cur));
    if(cur.z>=0)result.push(cur);
    prev=cur;
  }
  return result;
}
function frontStroke(ctx,ring){
  if(ring.length<2)return;
  let prev=ring[ring.length-1],drawing=false;
  ctx.beginPath();
  for(const cur of ring){
    if(prev.z>=0 && cur.z>=0){
      if(!drawing){const q=xy(prev);ctx.moveTo(q.x,q.y);drawing=true;}
      const q=xy(cur);ctx.lineTo(q.x,q.y);
    }else if(prev.z>=0 && cur.z<0){
      const q=xy(horizonIntersection(prev,cur));
      if(!drawing){const p=xy(prev);ctx.moveTo(p.x,p.y);}
      ctx.lineTo(q.x,q.y);drawing=false;
    }else if(prev.z<0 && cur.z>=0){
      const q=xy(horizonIntersection(prev,cur));
      ctx.moveTo(q.x,q.y);const p=xy(cur);ctx.lineTo(p.x,p.y);drawing=true;
    }else drawing=false;
    prev=cur;
  }
  ctx.stroke();
}
function landGeometry(ctx,feature,fill=null,stroke=null){
  const geometry=feature.geometry;if(!geometry)return;
  const polygons=geometry.type==="Polygon"?[geometry.coordinates]:
                 geometry.type==="MultiPolygon"?geometry.coordinates:[];
  for(const poly of polygons){
    for(const path of poly.slice(0,1)){
      if(path.length<3)continue;
      const ring=path.map(v=>proj(v[0],v[1]));
      const clipped=clipRing(ring);
      if(clipped.length>2){
        ctx.beginPath();
        clipped.forEach((p,i)=>{const q=xy(p);i?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y);});
        ctx.closePath();
        ctx.fillStyle=fill||window.AtlasLayers.countryFill(feature.properties?.name)||"#263b4d";ctx.fill();
      }
      ctx.strokeStyle=stroke||"rgba(225,237,246,.60)";
      ctx.lineWidth=.67;
      frontStroke(ctx,ring);
    }
  }
}
function lineOfGeography(ctx,points,color,width,dash=[]){
  const ring=points.map(x=>proj(x[0],x[1]));
  ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);
  // Deliberately open path: do not connect across the dark hemisphere.
  let prev=null, drawing=false;ctx.beginPath();
  for(const p of ring){
    if(p.z>0){
      const q=xy(p);
      if(prev&&prev.z>0&&drawing){ctx.lineTo(q.x,q.y);}
      else{ctx.moveTo(q.x,q.y);drawing=true;}
    }else drawing=false;
    prev=p;
  }
  ctx.stroke();ctx.setLineDash([]);
}
function label(ctx,text,p,color){
  if(!p)return;
  ctx.save();ctx.font="600 10px Segoe UI, sans-serif";ctx.textAlign="center";
  const metrics=ctx.measureText(text),w=metrics.width+13;
  ctx.fillStyle="#0a1c2cdb";ctx.strokeStyle=color;ctx.lineWidth=.8;
  ctx.beginPath();ctx.roundRect(p.x-w/2,p.y-11,w,20,5);ctx.fill();ctx.stroke();
  ctx.fillStyle=color;ctx.fillText(text,p.x,p.y+3);ctx.restore();
}
function commandBoxes(ctx){
  if(!$("layerCommands").checked)return;
  for(const c of commandAreas){
    const corners=[];
    for(let lon=c.west;lon<=c.east;lon+=2)corners.push([lon,c.south]);
    corners.push([c.east,c.south]);
    for(let lat=c.south;lat<=c.north;lat+=2)corners.push([c.east,lat]);
    corners.push([c.east,c.north]);
    for(let lon=c.east;lon>=c.west;lon-=2)corners.push([lon,c.north]);
    corners.push([c.west,c.north]);
    for(let lat=c.north;lat>=c.south;lat-=2)corners.push([c.west,lat]);
    lineOfGeography(ctx,corners,c.color+"a8",1.1,[5,4]);
    label(ctx,c.name,visible(c.lon,c.lat),c.color);
  }
}
function paintStatic(){
  const d=state.dimensions, off=state.staticCanvas,c=off.getContext("2d");
  c.setTransform(d.dpr,0,0,d.dpr,0,0);c.clearRect(0,0,d.w,d.h);
  const r=d.r;
  const halo=c.createRadialGradient(d.cx,d.cy,r*.4,d.cx,d.cy,r*1.25);
  halo.addColorStop(0,"#273c51");halo.addColorStop(.8,"#1a2e43");halo.addColorStop(1,"#0a1726");
  c.fillStyle=halo;c.beginPath();c.arc(d.cx,d.cy,r*1.11,0,Math.PI*2);c.fill();
  const sea=c.createRadialGradient(d.cx-r*.35,d.cy-r*.46,r*.08,d.cx,d.cy,r*1.03);
  sea.addColorStop(0,"#273e52");sea.addColorStop(.60,"#172c3e");sea.addColorStop(.92,"#112232");sea.addColorStop(1,"#071522");
  c.fillStyle=sea;c.beginPath();c.arc(d.cx,d.cy,r,0,2*Math.PI);c.fill();
  c.save();c.beginPath();c.arc(d.cx,d.cy,r,0,2*Math.PI);c.clip();
  // Graticule provides orientation; not a claimed geospatial boundary.
  for(let lat=-60;lat<=60;lat+=30){const path=[];for(let lon=-180;lon<=180;lon+=2)path.push([lon,lat]);lineOfGeography(c,path,"#7b9bb123",.6);}
  for(let lon=-180;lon<=180;lon+=30){const path=[];for(let lat=-90;lat<=90;lat+=2)path.push([lon,lat]);lineOfGeography(c,path,"#7b9bb120",.6);}
  if(state.countries)for(const feature of state.countries.features)landGeometry(c,feature);
  commandBoxes(c);
  // Slight shadow on right edge supplies slate/3D curvature.
  const shade=c.createLinearGradient(d.cx-r,d.cy,d.cx+r,d.cy);
  shade.addColorStop(0,"#07111c10");shade.addColorStop(.51,"#06122104");shade.addColorStop(1,"#050c18ad");
  c.fillStyle=shade;c.fillRect(d.cx-r,d.cy-r,r*2,r*2);
  c.restore();
  c.strokeStyle="#a8c5db71";c.lineWidth=1.3;c.shadowColor="#85aaca55";c.shadowBlur=16;
  c.beginPath();c.arc(d.cx,d.cy,r,0,2*Math.PI);c.stroke();c.shadowBlur=0;
  state.staticValid=true;
}
function pointJitter(id){
  // Screen-only separation at an identical theater anchor; NOT geocoding.
  let h=0;for(let i=0;i<id.length;i++)h=(h*33+id.charCodeAt(i))>>>0;
  const a=(h%360)*DEG,rad=17+((h>>9)%22);
  return {x:Math.cos(a)*rad,y:Math.sin(a)*rad};
}
function dayWindow(){
  return {start:clamp(state.startDay,state.minDay,state.maxDay),
          end:clamp(state.endDay,state.minDay,state.maxDay)};
}
function currentReports(){
  const {start,end}=dayWindow();
  return state.atlas.reports.filter(r=>{const d=dayNum(r.date);return d!==null&&d>=start&&d<=end;});
}
function selectedHotspots(){
  const a=state.atlas?.hotspots||[];
  return a.filter(h=>(state.severity==="all"||h.severity===state.severity)
                   &&(!$("changedOnly").checked||h.new_evidence||h.new_analyst_lead||frictionIsReview(h.id)));
}
function drawFrame(timestamp){
  if(!state.canvas||!state.atlas||!state.countries)return;
  if(timestamp-state.lastFrame<30){state.animationId=requestAnimationFrame(drawFrame);return;}
  const delta=state.lastFrame?Math.min(64,timestamp-state.lastFrame):33;
  state.lastFrame=timestamp;
  if($("autoRotate").checked&&!state.drag){
    state.lon+=delta*.0025;state.staticValid=false;
  }
  if(!state.staticValid)paintStatic();
  const d=state.dimensions,c=state.ctx;
  c.clearRect(0,0,d.w,d.h);c.drawImage(state.staticCanvas,0,0,d.w,d.h);
  const hits=[];
  window.AtlasLayers.draw(c,visible,lineOfGeography,hits,(ctx,feature,fill,stroke)=>{
    if(feature.geometry.type==="LineString")lineOfGeography(ctx,feature.geometry.coordinates,stroke,2);
    else landGeometry(ctx,feature,fill,stroke);
  });
  if($("layerReports").checked){
    for(const report of currentReports()){
      const p=visible(report.lon,report.lat);
      if(!p)continue;
      const j=pointJitter(report.id),x=p.x+j.x,y=p.y+j.y;
      c.fillStyle="#bccbd8cf";c.strokeStyle="#eef4fae0";c.lineWidth=.95;
      c.beginPath();c.arc(x,y,3.9,0,2*Math.PI);c.fill();c.stroke();
      hits.push({type:"report",x,y,r:7.5,record:report});
    }
  }
  const occupied=[];
  if($("layerHotspots").checked){
    const hs=selectedHotspots();
    for(const h of hs){
      const p=visible(h.lon,h.lat);if(!p)continue;
      const col=colors[h.severity]||colors.watch;
      const sel=state.selected===h.id&&state.selectionType==="hotspot";
      const reportCount=state.atlas.reports.some(r=>r.hotspot_id===h.id&&dayNum(r.date)>=dayWindow().start&&dayNum(r.date)<=dayWindow().end);
      const historical=state.endDay!==state.maxDay;
      const alpha=(historical&&!reportCount)?.55:1;
      c.save();c.globalAlpha=alpha;
      if((h.new_evidence||h.new_analyst_lead)&&!historical&&!window.matchMedia("(prefers-reduced-motion: reduce)").matches){
        for(let i=0;i<2;i++){
          const phase=((timestamp/1800+i*.5)%1);
          c.beginPath();c.arc(p.x,p.y,12+phase*24,0,2*Math.PI);
          c.strokeStyle=col;c.globalAlpha=.57*(1-phase)*alpha;c.lineWidth=1.6;c.stroke();
        }
        c.globalAlpha=alpha;
      }
      c.shadowBlur=sel?18:11;c.shadowColor=col;
      c.fillStyle="#101c2b";c.strokeStyle=col;c.lineWidth=sel?3:2;
      c.beginPath();c.arc(p.x,p.y,sel?12:10,0,Math.PI*2);c.fill();c.stroke();
      c.fillStyle=col;c.beginPath();c.arc(p.x,p.y,sel?6:5.2,0,2*Math.PI);c.fill();
      c.shadowBlur=0;
      if($("layerLabels").checked){
        const txt=(h.name||"").split(" / ")[0];
        c.font="600 11px Segoe UI, system-ui";
        c.textAlign="left";const w=c.measureText(txt).width+12;
        const right=p.x+w+27<d.w;
        const x=right?p.x+17:p.x-w-17;
        const offsets=[0,-21,21,-42,42,-63,63];
        let placement=null;
        for(const dy of offsets){
          const y=p.y-11+dy, rect={x,y,w,h:20};
          const overlap=occupied.some(q=>!(rect.x>q.x+q.w+4||rect.x+rect.w+4<q.x||rect.y>q.y+q.h+4||rect.y+rect.h+4<q.y));
          if(!overlap&&y>=6&&y+20<=d.h-8){placement=rect;break;}
        }
        if(placement){
          if(Math.abs(placement.y-(p.y-11))>12){
            c.strokeStyle=col+"ad";c.lineWidth=.75;c.beginPath();c.moveTo(p.x,p.y);
            c.lineTo(right?placement.x:placement.x+placement.w,placement.y+10);c.stroke();
          }
          occupied.push(placement);
          c.fillStyle="#0b1d2beb";c.strokeStyle="#45647dc0";c.lineWidth=.65;
          c.beginPath();c.roundRect(placement.x,placement.y,w,20,4);c.fill();c.stroke();
          c.fillStyle="#e5f0f9";c.fillText(txt,placement.x+6,placement.y+14);
        }
      }
      c.restore();
      hits.push({type:"hotspot",x:p.x,y:p.y,r:16,record:h});
    }
  }
  // Hit-test hotspots first even if overlapping sourced-report grey dots.
  state.hitTargets=hits.filter(h=>h.type==="hotspot").concat(hits.filter(h=>h.type==="report"),hits.filter(h=>h.type==="layer"));
  state.animationId=requestAnimationFrame(drawFrame);
}
function updateDates(){
  const today=dayNum(state.atlas.asof)??Math.floor(Date.now()/86400000);
  const evidence=state.atlas.reports.map(x=>dayNum(x.date)).filter(x=>x!==null&&x<=today);
  state.minDay=Math.min(today,...evidence);
  state.maxDay=today;
  state.endDay=today;
  state.startDay=Math.max(state.minDay,today-6);
  const maximum=String(Math.max(1,today-state.minDay));
  for(const id of ["timeStart","timeEnd"]){
    const slider=$(id);slider.min="0";slider.max=maximum;slider.step="1";
  }
  const counts={};
  for(const r of state.atlas.reports){const d=dayNum(r.date);if(d!==null&&d<=today)counts[d]=(counts[d]||0)+1;}
  const hist=$("eventDensity");hist.replaceChildren();
  const range=Math.max(1,state.maxDay-state.minDay);
  for(const [day,n] of Object.entries(counts)){
    const bar=document.createElement("span");
    bar.style.left=((Number(day)-state.minDay)/range*100)+"%";
    bar.style.height=clamp(3+n*1.5,4,12)+"px";
    hist.appendChild(bar);
  }
  $("timelineStart").textContent=shortDay(state.minDay);
  $("timelineEnd").textContent=shortDay(state.maxDay);
  updateTimeline();
}
function updateTimeline(){
  const w=dayWindow(),extent=Math.max(1,state.maxDay-state.minDay);
  const left=(w.start-state.minDay)/extent*100;
  const right=(w.end-state.minDay)/extent*100;
  $("timeStart").value=String(w.start-state.minDay);
  $("timeEnd").value=String(w.end-state.minDay);
  const selection=$("timeSelection");
  selection.style.left=left+"%";
  selection.style.width=Math.max(0,right-left)+"%";
  selection.setAttribute("aria-valuemin","0");
  selection.setAttribute("aria-valuemax",String(state.maxDay-state.minDay-(w.end-w.start)));
  selection.setAttribute("aria-valuenow",String(w.start-state.minDay));
  selection.setAttribute("aria-valuetext",shortDay(w.start)+" through "+shortDay(w.end));
  $("timeStart").setAttribute("aria-valuetext",shortDay(w.start));
  $("timeEnd").setAttribute("aria-valuetext",shortDay(w.end));
  $("selectedStart").textContent="From "+shortDay(w.start);
  $("selectedEnd").textContent="Through "+shortDay(w.end);
  $("timelineCaption").textContent=shortDay(w.start)+" — "+shortDay(w.end)+" (UTC source dates)";
  const days=w.end-w.start+1;
  $("windowLabel").textContent=days+" calendar day"+(days===1?"":"s")+
    (state.windowDays==="custom"?" · Custom selection":" · "+(state.windowDays==="all"?"Full history":"Preset window"))+
    " · Drag the blue bar to move it";
  const n=currentReports().length;
  $("visibleCount").textContent=n+" dated reports visible";
  $("stepBack").disabled=w.start<=state.minDay;
  $("stepForward").disabled=w.end>=state.maxDay;
  for(const b of document.querySelectorAll("#timeWindows button"))
    b.classList.toggle("active",b.dataset.days===String(state.windowDays));
  state.staticValid=false;
  updateWatchlist();
}
function setWindow(w){
  state.windowDays=String(w);
  if(w==="all"){
    state.startDay=state.minDay;
    state.endDay=state.maxDay;
  }else{
    const days=Math.max(1,Math.floor(Number(w)||1));
    state.startDay=Math.max(state.minDay,state.endDay-days+1);
  }
  updateTimeline();
}
function shiftWindow(days){
  if(!Number.isFinite(days)||!days)return;
  const span=state.endDay-state.startDay;
  const start=clamp(state.startDay+Math.round(days),state.minDay,state.maxDay-span);
  state.startDay=start;state.endDay=start+span;
  updateTimeline();
}
function bindTimeRange(){
  $("timeStart").addEventListener("input",e=>{
    state.startDay=Math.min(state.endDay,state.minDay+Number(e.target.value));
    state.windowDays="custom";updateTimeline();
  });
  $("timeEnd").addEventListener("input",e=>{
    state.endDay=Math.max(state.startDay,state.minDay+Number(e.target.value));
    state.windowDays="custom";updateTimeline();
  });
  const bar=$("timeSelection");
  bar.addEventListener("pointerdown",e=>{
    if(e.button!==0)return;
    e.preventDefault();
    state.rangeDrag={x:e.clientX,start:state.startDay,end:state.endDay};
    bar.setPointerCapture(e.pointerId);
  });
  bar.addEventListener("pointermove",e=>{
    if(!state.rangeDrag)return;
    const width=$("timeRange").getBoundingClientRect().width;
    const total=state.maxDay-state.minDay;
    const delta=Math.round((e.clientX-state.rangeDrag.x)/Math.max(1,width)*total);
    const span=state.rangeDrag.end-state.rangeDrag.start;
    state.startDay=clamp(state.rangeDrag.start+delta,state.minDay,state.maxDay-span);
    state.endDay=state.startDay+span;
    updateTimeline();
  });
  const finish=()=>{state.rangeDrag=null;};
  bar.addEventListener("pointerup",finish);
  bar.addEventListener("pointercancel",finish);
  bar.addEventListener("lostpointercapture",finish);
  bar.addEventListener("keydown",e=>{
    let step=0;
    if(e.key==="ArrowLeft"||e.key==="ArrowDown")step=-1;
    if(e.key==="ArrowRight"||e.key==="ArrowUp")step=1;
    if(e.key==="PageDown")step=-7;
    if(e.key==="PageUp")step=7;
    if(e.key==="Home")step=state.minDay-state.startDay;
    if(e.key==="End")step=state.maxDay-state.endDay;
    if(step){
      e.preventDefault();
      shiftWindow(step);
    }
  });
}
function frictionCase(id){return (state.friction?.cases||[]).find(c=>c.id===id)||null;}
function frictionIsReview(id){const f=frictionCase(id);return !!f&&["multi_stream_review","source_review","baseline_review"].includes(f.triage);}
function frictionSources(c){
  const rows=(c?.source_evidence||[]).slice(0,5);
  if(!rows.length)return '<p class="sub">No new source record passed the change-detection gate.</p>';
  return '<p><b>Evidence and source clocks:</b></p><ul>'+rows.map(r=>
    '<li>'+(safeUrl(r.url)?'<a href="'+safe(r.url)+'" target="_blank" rel="noopener noreferrer">'+safe(r.title)+'</a>':safe(r.title))+
    '<span class="sub"> · '+safe(r.family)+' · original event '+safe(r.event_at||"not dated")+
    ' · captured '+safe(r.first_seen_at||"unknown")+'</span></li>').join("")+'</ul>';
}
function select(h,type="hotspot"){
  if(type==="layer"){window.AtlasLayers.show(h,h.layerKey);return;}
  state.selected=h.id;state.selectionType=type;
  if(type==="hotspot"){
    state.lon=h.lon;state.lat=clamp(h.lat*.55,-55,65);state.staticValid=false;
  }
  const panel=$("selectedDetail");panel.hidden=false;
  if(type==="hotspot"){
    const link='<a href="ops/">Full source-linked decision brief →</a>';
    const f=frictionCase(h.id);
    const frictionDetail=f?'<div class="friction-detail"><h4>Cross-source comparison · Shadow mode · '+safe(f.triage.replace(/_/g," "))+'</h4>'+
      '<p><b>What changed:</b> '+safe(f.what_changed)+'</p>'+
      '<p><b>Why it may matter:</b> '+safe(f.so_what)+'</p>'+
      '<p><b>Compared with conventional indicators:</b> '+safe(f.traditional_contrast||"No cross-check available")+'</p>'+
      '<p><b>Alternative:</b> '+safe(f.alternative)+'</p>'+
      '<p><b>Next observable signpost:</b> '+safe(f.next_signpost)+'</p>'+
      '<p class="sub">Collection gaps: '+safe((f.coverage_gaps||[]).join(", ")||"None declared")+
      '. Triage does not change standing threat severity.</p>'+frictionSources(f)+'</div>':'';
    panel.innerHTML=
      '<div class="detail-top"><div><h3>'+safe(h.name)+'</h3><span class="severity-tag '+safe(h.severity)+'">'+safe(h.state)+'</span></div>'+
      '<button class="detail-close" aria-label="Close detail" type="button">×</button></div>'+
      '<p class="sub">'+safe(h.area)+' · '+safe(h.coordinate_precision)+'</p>'+
      '<p><b>Scenario:</b> '+safe(h.scenario)+'</p>'+
      (h.what_changed?'<p><b>Observed change:</b> '+safe(h.what_changed)+'</p>':'')+
      (h.new_analyst_lead?'<p><b>New unreviewed OSINT lead:</b> '+safe(h.new_analyst_lead_summary)+' — requires independent source review; standing severity unchanged.</p>':'')+
      '<p><b>So what:</b> '+safe(h.so_what||h.description)+'</p>'+
      '<p><b>Next signpost:</b> '+safe(h.next)+'</p>'+
      '<p><b>Alternative:</b> '+safe(h.alternative)+'</p>'+
      '<p class="sub">Standing evidence as of '+safe(h.baseline_asof)+'; no automated escalation classification. '+safe(h.review_status)+'</p>'+frictionDetail+link;
  }else{
    const source=safeUrl(h.url)?'<a href="'+safe(h.url)+'" target="_blank" rel="noopener noreferrer">Open original source →</a>':'Source link unavailable';
    panel.innerHTML='<div class="detail-top"><h3>'+safe(h.title)+'</h3><button class="detail-close" aria-label="Close detail" type="button">×</button></div>'+
      '<p class="sub">'+safe(h.date)+' · '+safe(h.category)+' · '+safe(h.assessment)+'</p>'+
      '<p>'+safe(h.detail)+'</p><p><b>Geolocation:</b> '+safe(h.location_precision)+'</p>'+
      '<p class="sub">Source: '+safe(h.source)+' · Single source root, not independent corroboration.</p>'+source;
  }
  panel.querySelector(".detail-close").addEventListener("click",()=>{panel.hidden=true;state.selected=null;updateWatchlist();});
  updateWatchlist();
}
function validFriction(value){
  return !!value&&value.schema_version===1&&value.shadow_mode===true&&
    Array.isArray(value.cases)&&value.cases.length<=100&&
    value.cases.every(c=>c&&typeof c.id==="string"&&typeof c.triage==="string");
}
function renderFriction(){
  const f=state.friction;
  const summary=$("frictionSummary"),time=$("frictionTime");
  const list=$("frictionHighlights"),expand=$("frictionExpand");
  if(!validFriction(f)){
    summary.textContent="Structural-friction feeds have not produced a usable briefing.";
    time.textContent="Collection coverage unavailable, not an all-clear.";
    list.replaceChildren();expand.hidden=true;return;
  }
  const stamp=Date.parse(f.generated_at||"");
  const age=Number.isFinite(stamp)?(Date.now()-stamp)/3600000:Infinity;
  const fresh=age>=0&&age<=3&&f.fresh_snapshot!==false;
  const gaps=Array.isArray(f.coverage_gaps)?f.coverage_gaps:[];
  summary.textContent=f.executive_summary||"No source-separated synthesis available.";
  const skill=f.validation?.status||"not_estimable";
  time.textContent=(fresh?"Source briefing: ":"STALE SOURCE BRIEFING: ")+
    (f.generated_at||"unknown UTC time")+
    " · "+state.frictionRemoteStatus+
    " · "+(gaps.length?"Gaps: "+gaps.join(", "):"Monitored feeds reported")+
    " · Forecast skill: "+(skill==="not_estimable"?"not estimable":"descriptive labels only");
  const review=f.cases.filter(c=>["multi_stream_review","source_review","baseline_review"].includes(c.triage));
  const shown=state.frictionShowAll?f.cases:review.slice(0,3);
  if(!shown.length){
    list.innerHTML='<div class="friction-highlight"><span class="sub">No new structural-friction lead established. Standing watches continue; check coverage before interpreting silence.</span></div>';
  }else{
    list.innerHTML=shown.map(c=>
      '<div class="friction-highlight"><strong>'+safe(c.title)+'</strong>'+
      '<span class="sub">'+safe(c.what_changed)+'</span>'+
      '<span class="sub">'+safe(c.traditional_contrast||c.so_what)+'</span>'+
      '<span class="sub">Next: '+safe(c.next_signpost)+'</span></div>').join("");
  }
  expand.hidden=!f.cases.length;
  expand.textContent=state.frictionShowAll?"Show material changes only":"Show all theater syntheses";
  expand.setAttribute("aria-expanded",state.frictionShowAll?"true":"false");
  $("frictionBriefing").classList.toggle("expanded",state.frictionShowAll);
}
async function refreshFriction(){
  const url=state.atlas?.friction_live_url;
  if(!safeUrl(url))return;
  try{
    const opts={cache:"no-store"};
    if(typeof AbortSignal!=="undefined"&&typeof AbortSignal.timeout==="function")
      opts.signal=AbortSignal.timeout(12000);
    const response=await fetch(url,opts);
    if(!response.ok)throw Error("source status "+response.status);
    const fresh=await response.json();
    if(!validFriction(fresh))throw Error("invalid source schema");
    const before=Date.parse(state.friction?.generated_at||"");
    const after=Date.parse(fresh.generated_at||"");
    if(!Number.isFinite(after))throw Error("missing generation timestamp");
    if(!Number.isFinite(before)||after>=before){
      state.friction=fresh;
      state.frictionRemoteStatus="public evidence branch snapshot";
      renderFriction();updateWatchlist();
    }else{
      state.frictionRemoteStatus="site snapshot is newer than public branch";
      renderFriction();
    }
  }catch(error){
    state.frictionRemoteStatus="static fallback (live source unavailable)";
    renderFriction();
  }
}
function updateWatchlist(){
  if(!state.atlas)return;
  const list=$("watchlist");list.replaceChildren();
  const hs=selectedHotspots().filter(h=>state.watchTab==="all"||h.new_evidence||h.new_analyst_lead||frictionIsReview(h.id));
  const rank={critical:0,active:1,high:2,watch:3,low:4};
  hs.sort((a,b)=>Number(b.new_evidence||b.new_analyst_lead||frictionIsReview(b.id))-Number(a.new_evidence||a.new_analyst_lead||frictionIsReview(a.id))||(rank[a.severity]??4)-(rank[b.severity]??4)||a.name.localeCompare(b.name));
  $("watchCount").textContent="("+hs.length+")";
  $("watchFoot").textContent=state.atlas.algorithmic_unlocated_count+" GDELT + "+(state.atlas.unlocated_analyst_leads||[]).length+" analyst unlocated leads";
  if(!hs.length){list.innerHTML='<p class="empty">No watch areas match these filters. No Critical classification is inferred automatically.</p>';return;}
  for(const h of hs){
    const b=document.createElement("button");b.type="button";
    b.className="watch-card"+(state.selected===h.id&&state.selectionType==="hotspot"?" selected":"");
    const f=frictionCase(h.id);
    const review=frictionIsReview(h.id);
    b.innerHTML='<div class="watch-card-head"><strong>'+safe(h.name)+'</strong>'+
      '<span class="severity-tag '+safe(h.severity)+'">'+safe(h.state)+'</span></div>'+
      '<p>'+safe(review?f.what_changed:(h.what_changed||h.description||h.scenario))+'</p>'+
      '<small>Curated source date: '+safe(h.baseline_asof||"unknown")+'</small>'+
      (h.new_evidence?'<div class="card-new">NEW CASE-SPECIFIC SOURCE CHANGE</div>':'')+
      (h.new_analyst_lead?'<div class="card-new">NEW UNREVIEWED OSINT LEAD</div>':'')+
      (review?'<small>Cross-source shadow review · '+safe(f.triage.replace(/_/g,' '))+'</small>':'');
    b.addEventListener("click",()=>select(h));list.appendChild(b);
  }
}
function canvasPick(clientX,clientY){
  const rect=state.canvas.getBoundingClientRect(),x=clientX-rect.left,y=clientY-rect.top;
  for(const p of state.hitTargets){
    if(Math.hypot(p.x-x,p.y-y)<=p.r)return p;
  }
  return null;
}
function attachCanvas(){
  const wrap=$("globeWrap"),c=$("globe");
  c.addEventListener("pointerdown",event=>{
    if(event.button!==0)return;
    wrap.classList.add("dragging");
    state.drag={x:event.clientX,y:event.clientY,lon:state.lon,lat:state.lat,moved:false};
    c.setPointerCapture(event.pointerId);
  });
  c.addEventListener("pointermove",event=>{
    if(state.drag){
      const dx=event.clientX-state.drag.x,dy=event.clientY-state.drag.y;
      if(Math.abs(dx)+Math.abs(dy)>4)state.drag.moved=true;
      if(state.drag.moved){
        state.lon=state.drag.lon-dx/Math.max(radius(),1)*80;
        state.lat=clamp(state.drag.lat+dy/Math.max(radius(),1)*65,-72,72);
        state.staticValid=false;
      }
      $("mapTooltip").hidden=true;
      return;
    }
    const found=canvasPick(event.clientX,event.clientY);
    const tip=$("mapTooltip");tip.hidden=!found;
    if(found){
      const rect=wrap.getBoundingClientRect();
      tip.style.left=clamp(event.clientX-rect.left+14,8,rect.width-255)+"px";
      tip.style.top=clamp(event.clientY-rect.top-20,8,rect.height-95)+"px";
      const obj=found.record;
      tip.innerHTML=found.type==="hotspot"
        ?'<b>'+safe(obj.name)+'</b><span>'+safe(obj.state)+' · Approximate theater</span>'
        :'<b>'+safe(obj.title)+'</b><span>'+safe(obj.observed_at||obj.date)+' · '+(found.type==="layer"?"Source observation":"Theater-associated report")+'</span>';
    }
  });
  c.addEventListener("pointerup",event=>{
    if(!state.drag)return;
    const moved=state.drag.moved;
    state.drag=null;wrap.classList.remove("dragging");
    if(!moved){const found=canvasPick(event.clientX,event.clientY);if(found)select(found.record,found.type);}
  });
  c.addEventListener("pointercancel",()=>{state.drag=null;wrap.classList.remove("dragging");});
  c.addEventListener("pointerleave",()=>{$("mapTooltip").hidden=true;});
  c.addEventListener("wheel",event=>{
    event.preventDefault();
    const multiplier=clamp(Math.exp(-event.deltaY*.0015),.82,1.22);
    changeZoom(multiplier);
  },{passive:false});
  c.addEventListener("dblclick",event=>{
    event.preventDefault();
    changeZoom(1.48);
  });
}
function changeZoom(multiplier){
  const next=clamp(state.zoom*multiplier,.65,5.5);
  if(Math.abs(next-state.zoom)<.001)return;
  state.zoom=next;
  resize();
}
function setDiscoveryDrawer(open){
  $("discoveryDrawer").hidden=!open;
  $("discoveryToggle").setAttribute("aria-expanded",String(open));
  $("discoveryToggle").setAttribute("aria-label",
    open?"Hide unlocated discovery leads":"Show unlocated discovery leads");
}
function bindControls(){
  $("discoveryToggle").addEventListener("click",()=>{
    setDiscoveryDrawer($("discoveryDrawer").hidden);
  });
  $("discoveryClose").addEventListener("click",()=>{
    setDiscoveryDrawer(false);$("discoveryToggle").focus();
  });
  document.addEventListener("keydown",event=>{
    if(event.key==="Escape"&&!$("discoveryDrawer").hidden){
      setDiscoveryDrawer(false);$("discoveryToggle").focus();
    }
  });
  $("frictionExpand").addEventListener("click",()=>{
    state.frictionShowAll=!state.frictionShowAll;
    renderFriction();
  });
  for(const id of ["layerHotspots","layerReports","layerCommands","layerLabels","changedOnly"]){
    $(id).addEventListener("change",()=>{state.staticValid=false;updateWatchlist();});
  }
  $("autoRotate").addEventListener("change",()=>{});
  document.querySelectorAll("#severityControls [data-severity]").forEach(button=>{
    button.addEventListener("click",()=>{
      state.severity=button.dataset.severity;
      document.querySelectorAll("#severityControls [data-severity]").forEach(x=>x.classList.toggle("active",x===button));
      updateWatchlist();
    });
  });
  for(const b of document.querySelectorAll("#timeWindows [data-days]"))
    b.addEventListener("click",()=>setWindow(b.dataset.days));
  bindTimeRange();
  $("stepBack").addEventListener("click",()=>shiftWindow(-1));
  $("stepForward").addEventListener("click",()=>shiftWindow(1));
  $("tabAll").addEventListener("click",()=>{state.watchTab="all";updateTabs();});
  $("tabNew").addEventListener("click",()=>{state.watchTab="new";updateTabs();});
  const reset=()=>{state.lon=52;state.lat=20;state.zoom=1;resize();};
  $("resetView").addEventListener("click",reset);
  $("northView").addEventListener("click",reset);
  $("zoomIn").addEventListener("click",()=>changeZoom(1.28));
  $("zoomOut").addEventListener("click",()=>changeZoom(1/1.28));
  $("openControls").addEventListener("click",()=>{
    const on=$("sidebar").classList.toggle("mobile-open");
    $("openControls").setAttribute("aria-expanded",on?"true":"false");
  });
  $("collapseControls").addEventListener("click",()=>{
    if(window.innerWidth<=690){
      $("sidebar").classList.remove("mobile-open");
      $("openControls").setAttribute("aria-expanded","false");
    }else{
      const collapsed=$("sidebar").classList.toggle("sidebar-minimized");
      document.querySelector(".workspace").classList.toggle("sidebar-collapsed",collapsed);
      $("collapseControls").textContent=collapsed?"»":"«";
      $("collapseControls").setAttribute("aria-label",collapsed?"Expand controls":"Collapse controls");
      setTimeout(resize,0);
    }
  });
}
function updateTabs(){
  $("tabAll").classList.toggle("active",state.watchTab==="all");
  $("tabNew").classList.toggle("active",state.watchTab==="new");
  updateWatchlist();
}
function renderEvidenceIntake(){
  const a=state.atlas, status=a.status||{};
  const feeds=status.operational_feeds||{};
  const health=$("collectorHealth");
  const rows=[];
  for(const key of ["markets","official","commercial"]){
    const f=feeds[key]||{};
    const name=key.charAt(0).toUpperCase()+key.slice(1);
    const freshness=f.freshness||"not available";
    const checked=f.last_checked||"No successful collection timestamp";
    rows.push('<div class="intake-feed"><span>'+safe(name)+'</span><strong>'+safe(freshness.replace(/_/g," "))+'</strong></div>'+
      '<small>Checked: '+safe(checked)+'</small>');
  }
  const analyst=status.analyst_intake||{};
  rows.push('<div class="intake-feed"><span>ChatGPT report intake</span><strong>'+
    safe((analyst.status||"not_connected").replace(/_/g," "))+'</strong></div>'+
    '<small>Last handoff: '+safe(analyst.latest_collected_at||"None — scheduled chats do not automatically publish")+
    '; unique observations: '+safe(analyst.distinct_observations||0)+'</small>');
  rows.push('<p class="sub">GDELT dataset as of '+safe(a.asof)+
    '; site generated '+safe(a.generated_at)+'. Collection dates differ from report publication dates.</p>');
  health.innerHTML=rows.join("");
  const discoveries=$("discoveryLeads");
  const candidate=[...(a.unlocated_analyst_leads||[]).map(x=>({title:x.title,summary:x.summary,
    source_url:x.source_url,kind:"Analyst intake · unreviewed"})),
    ...(a.discovery_leads||[]).map(x=>({title:x.title,summary:x.summary,
    kind:"GDELT · unlocated media-coded lead"}))];
  $("discoveryCount").textContent=String(candidate.length);
  discoveries.innerHTML=candidate.length?candidate.slice(0,35).map(x=>
    '<div class="intake-discovery"><strong>'+safe(x.title)+'</strong>'+
    '<span class="sub">'+safe(x.kind)+'</span>'+
    '<span class="sub">'+safe(x.summary)+'</span>'+
    (safeUrl(x.source_url)?'<a href="'+safe(x.source_url)+'" target="_blank" rel="noopener noreferrer">Original source</a>':'<a href="classic.html">Original GDELT context</a>')+
    '</div>').join(""):'No unlocated leads in this publication.';
}
function updateKpis(){
  const a=state.atlas;
  $("kpiWatch").textContent=a.hotspots.length;
  $("kpiUpdates").textContent=a.hotspots.filter(x=>x.new_evidence||x.new_analyst_lead).length;
  $("kpiReports").textContent=a.reports.length;
  $("kpiAsOf").textContent=a.asof;
  $("dataNotice").textContent=a.geographic_notice+" "+a.algorithmic_caveat;
  if(a.algorithmic_unlocated_count) $("dataNotice").textContent+=" ("+a.algorithmic_unlocated_count+" unlocated GDELT leads).";
  renderEvidenceIntake();
}
async function init(){
  bindControls();
  attachCanvas();
  try{
    const [data,geo]=await Promise.all([
      fetch("atlas.json",{cache:"no-cache"}).then(r=>{if(!r.ok)throw Error("atlas.json "+r.status);return r.json();}),
      fetch("dashboard/countries.geojson").then(r=>{if(!r.ok)throw Error("countries.geojson "+r.status);return r.json();})
    ]);
    if(!Array.isArray(data.hotspots)||!Array.isArray(data.reports)||!Array.isArray(geo.features))throw Error("Unexpected feed schema");
    state.atlas=data;state.countries=geo;
    state.friction=validFriction(data.friction_briefs)?data.friction_briefs:null;
    renderFriction();
    void refreshFriction();
    setInterval(refreshFriction,300000);
    window.AtlasLayers.init(data.layer_feed,()=>{state.staticValid=false;});
    updateKpis();updateDates();resize();
    if(typeof ResizeObserver==="function"){
      new ResizeObserver(()=>resize()).observe($("globeWrap"));
    }else window.addEventListener("resize",resize);
    state.animationId=requestAnimationFrame(drawFrame);
  }catch(err){
    $("watchlist").innerHTML='<p class="empty">Map data unavailable. The classic watchboard remains accessible.</p>';
    $("dataNotice").textContent="Atlas collection error: "+String(err.message||err);
    $("timelineCaption").textContent="Timeline unavailable: source data could not be loaded.";
  }
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();