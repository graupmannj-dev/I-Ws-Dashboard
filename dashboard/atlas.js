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
  behavior:null,behaviorRemoteStatus:"published site snapshot",
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
function drawSourceGeometry(ctx,feature,fill,stroke,key,row,hits){
  // Separate sourced restriction geometry from the standing country layer.
  // Native GeoJSON polygons, MultiPolygons and open LineStrings are supported;
  // explicit source radius/bounding boxes are normalized in layers.js.
  const geometry=feature.geometry;if(!geometry)return;
  ctx.save();
  ctx.lineWidth=1.8;ctx.strokeStyle=stroke;ctx.fillStyle=fill;
  if(geometry.type==="LineString"){
    lineOfGeography(ctx,geometry.coordinates,stroke,2.2,[5,3]);
    const points=geometry.coordinates.map(v=>proj(v[0],v[1]));
    for(let i=1;i<points.length;i++){
      if(points[i-1].z<0||points[i].z<0)continue;
      hits.push({type:"region",key,segment:[xy(points[i-1]),xy(points[i])],
        record:{...row,layerKey:key}});
    }
  }else{
    const polygons=geometry.type==="Polygon"?[geometry.coordinates]:
                   geometry.type==="MultiPolygon"?geometry.coordinates:[];
    for(const poly of polygons){
      if(!Array.isArray(poly)||!poly.length)continue;
      const clipped=poly.map(ring=>clipRing(ring.map(v=>proj(v[0],v[1]))))
        .filter(v=>v.length>=3);
      if(!clipped.length)continue;
      const projected=clipped.map(ring=>ring.map(xy));
      ctx.beginPath();
      for(const ring of projected){
        ring.forEach((pt,i)=>i?ctx.lineTo(pt.x,pt.y):ctx.moveTo(pt.x,pt.y));
        ctx.closePath();
      }
      ctx.fill("evenodd");
      ctx.setLineDash([5,3]);ctx.stroke();ctx.setLineDash([]);
      hits.push({type:"region",key,polygon:projected[0],holes:projected.slice(1),
        record:{...row,layerKey:key}});
    }
  }
  ctx.restore();
}
function inScreenRing(point,ring){
  if(!ring||ring.length<3)return false;
  let inside=false;
  for(let i=0,j=ring.length-1;i<ring.length;j=i++){
    const a=ring[i],b=ring[j];
    if(((a.y>point.y)!==(b.y>point.y))&&
      point.x<(b.x-a.x)*(point.y-a.y)/(b.y-a.y)+a.x)inside=!inside;
  }
  return inside;
}
function regionHit(item,x,y){
  if(item.polygon)
    return inScreenRing({x,y},item.polygon)&&
      !(item.holes||[]).some(ring=>inScreenRing({x,y},ring));
  if(item.segment){
    const [a,b]=item.segment,dx=b.x-a.x,dy=b.y-a.y;
    const span=dx*dx+dy*dy;
    const t=span?clamp(((x-a.x)*dx+(y-a.y)*dy)/span,0,1):0;
    return Math.hypot(a.x+t*dx-x,a.y+t*dy-y)<=7;
  }
  return false;
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
                   &&(!$("changedOnly").checked||h.new_evidence||frictionIsReview(h.id)));
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
  window.AtlasLayers.draw(c,visible,lineOfGeography,hits,drawSourceGeometry);
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
      if((h.new_evidence||frictionIsReview(h.id))&&!historical&&!window.matchMedia("(prefers-reduced-motion: reduce)").matches){
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
  state.hitTargets=hits.filter(h=>h.type==="hotspot").concat(
    hits.filter(h=>h.type==="report"),hits.filter(h=>h.type==="layer"),
    hits.filter(h=>h.type==="region"));
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
function frictionIsReview(id){
  const f=frictionCase(id);
  // A novel source alone is an investigative record, not an executive change.
  return !!f&&f.executive_eligible===true;
}
function frictionSources(c){
  const rows=(c?.source_evidence||[]).slice(0,5);
  if(!rows.length)return '<p class="sub">No new source record passed the change-detection gate.</p>';
  return '<p><b>Evidence and source clocks:</b></p><ul>'+rows.map(r=>
    '<li>'+(safeUrl(r.url)?'<a href="'+safe(r.url)+'" target="_blank" rel="noopener noreferrer">'+safe(r.title)+'</a>':safe(r.title))+
    '<span class="sub"> · '+safe(r.family)+' · original event '+safe(r.event_at||"not dated")+
    ' · captured '+safe(r.first_seen_at||"unknown")+'</span></li>').join("")+'</ul>';
}
function select(h,type="hotspot"){
  if(type==="layer"||type==="region"){window.AtlasLayers.show(h,h.layerKey);return;}
  state.selected=h.id;state.selectionType=type;
  if(type==="hotspot"){
    state.lon=h.lon;state.lat=clamp(h.lat*.55,-55,65);state.staticValid=false;
  }
  const panel=$("selectedDetail");panel.hidden=false;
  if(type==="hotspot"){
    const link='<a href="ops/">Full source-linked decision brief →</a>';
    const f=frictionCase(h.id);
    const frictionDetail=f?'<div class="friction-detail"><h4>'+
      (f.executive_eligible===true?'Early indicator assessment':'Investigatory source context')+
      ' · Shadow mode</h4>'+
      '<p><b>What changed:</b> '+safe(f.what_changed)+'</p>'+
      '<p><b>Why this matters:</b> '+safe(f.so_what)+'</p>'+
      '<p><b>Baseline comparison:</b> '+safe(f.baseline_context||"Not yet characterized")+'</p>'+
      '<p><b>Materiality basis:</b> '+safe(f.materiality_rationale||"Not assessed")+'</p>'+
      '<p><b>Evidence against / uncertainties:</b> '+safe(f.counter_evidence||"Not yet assessed")+'</p>'+
      '<p><b>Conventional comparison:</b> '+safe(f.traditional_contrast||"No current cross-check")+'</p>'+
      '<p><b>Alternative:</b> '+safe(f.alternative)+'</p>'+
      '<p><b>Next observable signpost:</b> '+safe(f.next_signpost)+'</p>'+
      '<p class="sub">Collection gaps: '+safe((f.coverage_gaps||[]).join(", ")||"None declared")+
      '. No automatic change to standing severity.</p>'+frictionSources(f)+'</div>':'';
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
  const review=f.cases.filter(c=>c.executive_eligible===true);
  const investigatory=f.cases.filter(c=>["multi_stream_review","source_review","baseline_review"].includes(c.triage)&&!c.executive_eligible);
  const shown=state.frictionShowAll?f.cases:review.slice(0,3);
  if(!shown.length){
    list.innerHTML='<div class="friction-highlight"><span class="sub">No source signal yet clears the executive materiality gate. '+
      investigatory.length+' investigatory leads retained below; absence of promotion is not an all-clear.</span></div>';
  }else{
    list.innerHTML=shown.map(c=>
      '<div class="friction-highlight"><strong>'+safe(c.title)+'</strong>'+
      '<span class="sub">'+safe(c.executive_eligible?'EARLY INDICATOR · '+(c.publication_basis||"provisional"):'INVESTIGATORY · not promoted')+'</span>'+
      '<span class="sub"><b>Change:</b> '+safe(c.what_changed)+'</span>'+
      '<span class="sub"><b>So what:</b> '+safe(c.so_what)+'</span>'+
      '<span class="sub"><b>Compared to baseline:</b> '+safe(c.baseline_context||"Not characterized")+'</span>'+
      '<span class="sub"><b>Alternative:</b> '+safe(c.alternative)+'</span>'+
      '<span class="sub"><b>Next signpost:</b> '+safe(c.next_signpost)+'</span></div>').join("");
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
      renderFriction();updateWatchlist();updateKpis();
    }else{
      state.frictionRemoteStatus="site snapshot is newer than public branch";
      renderFriction();
    }
  }catch(error){
    state.frictionRemoteStatus="static fallback (live source unavailable)";
    renderFriction();
  }
}
/* Unified global behavioral discovery, read-only shadow-mode source evidence.
 * Never infer an incident point, approved warning, foreign actor or attack date.
 */
function validReportRelations(value){
  if(value==null)return true; // Older published source snapshots
  const statuses=["shared_source_document_unreviewed",
    "possible_same_source_story_unreviewed",
    "possible_same_event_unreviewed","related_reporting_unreviewed"];
  return value.schema==="aiba.report-event-resolution-shadow.v1"&&
    value.status==="unreviewed_report_relationships_only"&&
    value.source_independence_unverified===true&&
    value.reporting_origins_are_not_event_locations===true&&
    value.not_a_preparations_sensor_or_warning===true&&
    value.automatic_alerts_created===0&&
    value.automatic_severity_changes===0&&value.forecast_probability===null&&
    Number.isInteger(value.records_examined)&&value.records_examined>=0&&
    Number.isInteger(value.eligible_event_reporting_records)&&
    Number.isInteger(value.routine_notice_market_or_measurement_records_excluded_from_text_event_matching)&&
    value.eligible_event_reporting_records+
      value.routine_notice_market_or_measurement_records_excluded_from_text_event_matching===
      value.records_examined&&
    Array.isArray(value.candidate_groups)&&value.candidate_groups.length<=20&&
    value.candidate_groups.every(g=>g&&statuses.includes(g.status)&&
      g.independent_corroboration_established===false&&
      g.warning_level_change===false&&
      g.reporting_origin_used_as_event_site===false&&
      Array.isArray(g.source_reports)&&g.source_reports.length>=2&&
      g.source_reports.length<=8&&g.source_reports.every(x=>
        x&&x.status==="unreviewed_source_report"));
}
function validBehavior(value){
  return !!value&&value.schema==="aiba.behavioral-convergence-shadow.v1"&&
    value.status==="read_only_shadow_evidence"&&
    value.approved_warning_count===0&&value.automated_severity_changes===0&&
    value.forecast_probability==null&&value.source_continuity_proven===false&&
    value.map_coordinates_inferred===false&&
    typeof value.source_generated_at==="string"&&
    Array.isArray(value.review_groups)&&value.review_groups.length<=25&&
    value.review_groups.every(g=>g&&g.status==="cross_family_cooccurrence_unreviewed"&&g.warning_level_change===false)&&
    Array.isArray(value.new_single_source_leads)&&value.new_single_source_leads.length<=50&&
    value.new_single_source_leads.every(l=>l&&l.status==="single_source_unreviewed")&&
    (value.discovery_visibility==null||(
      value.discovery_visibility.schema==="aiba.behavioral-discovery-visibility.v1"&&
      value.discovery_visibility.source_coverage_is_globally_complete===false))&&
    (value.recent_source_observations==null||(
      Array.isArray(value.recent_source_observations)&&
      value.recent_source_observations.length<=24&&
      value.recent_source_observations.every(l=>l&&
        l.status==="recent_source_observation_unreviewed"&&
        Number.isFinite(Date.parse(l.first_observed_at)))))&&
    validReportRelations(value.report_relationships)&&
    typeof value.collection_coverage==="object"&&value.collection_coverage!==null;
}
function normalizeLiveBehavior(raw){
  // Existing source-separated fusion output, never an approved warning.
  if(!raw||raw.schema!=="aiba.behavioral-convergence-shadow.v1"||
     raw.approved_warning_count!==0||raw.automated_severity_changes!==0||
     raw.forecast_probability!=null||raw.prediction_horizon!=null||
     !Array.isArray(raw.review_groups)||raw.review_groups.length>25||
     !Array.isArray(raw.new_single_source_leads)||raw.new_single_source_leads.length>50||
     !raw.collection_coverage||typeof raw.collection_coverage!=="object"||
     Array.isArray(raw.collection_coverage)||Object.keys(raw.collection_coverage).length>30)
    return null;
  const vis=raw.discovery_visibility;
  const recent=raw.recent_source_observations;
  if(vis!=null || recent!=null){
    if(!vis||vis.schema!=="aiba.behavioral-discovery-visibility.v1"||
       vis.source_coverage_is_globally_complete!==false||
       vis.new_or_collocated_not_same_as_verified_threat!==true||
       !Array.isArray(recent)||recent.length>24||
       vis.recent_observations_sampled!==recent.length ||
       !["latest_registry_record_count","latest_registry_newly_observed_count",
         "recent_unique_record_count_72h","recent_unlocated_count_72h",
         "latest_unlocated_record_count",
         "shared_exact_geography_keys_across_behavior_families"].every(
           key=>Number.isInteger(vis[key])&&vis[key]>=0&&vis[key]<=100000) ||
       recent.some(x=>!x||x.status!=="recent_source_observation_unreviewed"))
      return null;
  }
  const at=Date.parse(raw.generated_at||"");
  const registryAt=Date.parse(raw.registry_asof||"");
  if(!Number.isFinite(at)||!Number.isFinite(registryAt)||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(raw.generated_at)||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(raw.registry_asof)||
      at>Date.now()+120000||at<registryAt||at-registryAt>900000)return null;
  const groupTotal=raw.review_groups_count_total;
  const leadTotal=raw.new_single_source_count_total;
  if(!Number.isInteger(groupTotal)||groupTotal<raw.review_groups.length||groupTotal>100000||
     !Number.isInteger(leadTotal)||leadTotal<raw.new_single_source_leads.length||leadTotal>100000)return null;
  for(const g of raw.review_groups){
    if(!g||g.status!=="cross_family_cooccurrence_unreviewed"||
       g.warning_level_change!==false||!Array.isArray(g.distinct_source_families)||
       g.distinct_source_families.length<2||!Array.isArray(g.source_links)||
       Date.parse(g.last_observed_at||"")>at)return null;
  }
  for(const l of raw.new_single_source_leads){
    if(!l||l.status!=="single_source_unreviewed"||
       Date.parse(l.first_observed_at||"")>at)return null;
  }
  const limited=v=>typeof v==="string"?v.slice(0,800):"";
  const geo=v=>({
    label:limited(v?.label||"Location not verified"),
    scope_key:limited(v?.key||"")||null,
    precision:limited(v?.precision||"not_geocoded"),
    verified_iso:v?.verified_iso===true,
    // Deliberately omit lat/lon even where another upstream field contains
    // a centroid. A source-defined region is NOT a verified incident point.
  });
  const groups=raw.review_groups.map(g=>({
    id:limited(g.id),geography:geo(g.geography),status:g.status,
    warning_level_change:false,assessment:limited(g.assessment),
    source_family_count:Number(g.source_family_count)||g.distinct_source_families.length,
    distinct_source_families:g.distinct_source_families.slice(0,12).map(limited),
    distinct_provider_count:Number(g.distinct_provider_count)||0,
    source_root_count:Number(g.source_root_count)||0,
    first_observed_at:limited(g.first_observed_at),
    last_observed_at:limited(g.last_observed_at),
    source_links:g.source_links.slice(0,12).map(x=>({
      url:safeUrl(x?.url),provider:limited(x?.provider),family:limited(x?.family),
      first_observed_at:limited(x?.first_observed_at),
      published_at:limited(x?.published_at),
    })),
  }));
  const leads=raw.new_single_source_leads.map(l=>({
    observation_id:limited(l.observation_id),title:limited(l.title),
    source_family:limited(l.source_family),source_url:safeUrl(l.source_url),
    first_observed_at:limited(l.first_observed_at),
    source_published_at:limited(l.source_published_at),
    geography:geo(l.geography),
    requires_geolocation:l.requires_geolocation===true,
    status:"single_source_unreviewed",
  }));
  const safeRecent=Array.isArray(recent)?recent.map(l=>({
    observation_id:limited(l.observation_id),title:limited(l.title),
    source_family:limited(l.source_family),provider:limited(l.provider),
    source_url:safeUrl(l.source_url),
    first_observed_at:limited(l.first_observed_at),
    source_published_at:limited(l.source_published_at),
    geography:geo(l.geography),
    requires_geolocation:l.requires_geolocation===true,
    status:"recent_source_observation_unreviewed",
  })):[];
  if(safeRecent.some(l=>!Number.isFinite(Date.parse(l.first_observed_at))||
       Date.parse(l.first_observed_at)>at))return null;
  const safeVis=vis?{
    schema:"aiba.behavioral-discovery-visibility.v1",
    latest_registry_record_count:vis.latest_registry_record_count,
    latest_registry_newly_observed_count:vis.latest_registry_newly_observed_count,
    recent_unique_record_count_72h:vis.recent_unique_record_count_72h,
    recent_unlocated_count_72h:vis.recent_unlocated_count_72h,
    latest_unlocated_record_count:vis.latest_unlocated_record_count,
    shared_exact_geography_keys_across_behavior_families:
      vis.shared_exact_geography_keys_across_behavior_families,
    recent_observations_sampled:safeRecent.length,
    exact_geography_match_required_for_cross_family:true,
    new_this_collection_required_for_cross_family_nomination:true,
    source_coverage_is_globally_complete:false,
  }:null;
  let relationship=null;
  const incoming=raw.report_relationships;
  if(incoming!=null){
    if(!incoming||incoming.schema!=="aiba.report-event-resolution-shadow.v1"||
       incoming.status!=="unreviewed_report_relationships_only"||
       incoming.source_independence_unverified!==true||
       incoming.reporting_origins_are_not_event_locations!==true||
       incoming.not_a_preparations_sensor_or_warning!==true||
       incoming.automatic_alerts_created!==0||
       incoming.automatic_severity_changes!==0||
       incoming.forecast_probability!=null||
       !Array.isArray(incoming.candidate_groups)||incoming.candidate_groups.length>20)return null;
    const statusSet=["shared_source_document_unreviewed",
      "possible_same_source_story_unreviewed",
      "possible_same_event_unreviewed","related_reporting_unreviewed"];
    const safeCandidates=[];
    for(const g of incoming.candidate_groups){
      if(!g||!statusSet.includes(g.status)||
         g.independent_corroboration_established!==false||
         g.warning_level_change!==false||
         g.reporting_origin_used_as_event_site!==false||
         !Array.isArray(g.source_reports)||g.source_reports.length<2||
         g.source_reports.length>8)return null;
      const reports=[];
      for(const r of g.source_reports){
        if(!r||r.status!=="unreviewed_source_report"||
           Date.parse(r.first_observed_at||"")>at ||
           !Number.isFinite(Date.parse(r.first_observed_at||"")))return null;
        reports.push({
          observation_id:limited(r.observation_id),title:limited(r.title),
          source_family:limited(r.source_family),provider:limited(r.provider),
          source_url:safeUrl(r.source_url),geography:geo(r.geography),
          reporting_origin:limited(r.reporting_origin),
          first_observed_at:limited(r.first_observed_at),
          source_published_at:limited(r.source_published_at),
          status:"unreviewed_source_report",
        });
      }
      const distance=g.reported_event_site_separation_km;
      const sim=g.semantic_similarity;
      if((distance!=null&&(!Number.isFinite(distance)||distance<0||distance>20020))||
         (sim!=null&&(!Number.isFinite(sim)||sim<0||sim>1)))return null;
      safeCandidates.push({
        id:limited(g.id),status:g.status,match_basis:limited(g.match_basis),
        semantic_similarity:sim==null?null:sim,
        reported_event_site_separation_km:distance==null?null:distance,
        reported_event_site_comparison_available:
          g.reported_event_site_comparison_available===true,
        shared_information_root:g.shared_information_root===true,
        independent_corroboration_established:false,
        warning_level_change:false,reporting_origin_used_as_event_site:false,
        source_reports:reports,
      });
    }
    const count=x=>Number.isInteger(x)&&x>=0&&x<=100000?x:null;
    const examined=count(incoming.records_examined);
    const eligible=count(incoming.eligible_event_reporting_records);
    const excluded=count(incoming.routine_notice_market_or_measurement_records_excluded_from_text_event_matching);
    if(examined===null||eligible===null||excluded===null||eligible+excluded!==examined)
      return null;
    relationship={
      schema:incoming.schema,status:incoming.status,
      records_examined:examined,
      eligible_event_reporting_records:eligible,
      routine_notice_market_or_measurement_records_excluded_from_text_event_matching:excluded,
      same_document_group_count_total:count(incoming.same_document_group_count_total),
      possible_same_source_story_count_total:count(incoming.possible_same_source_story_count_total),
      possible_same_event_count_total:count(incoming.possible_same_event_count_total),
      related_reporting_count_total:count(incoming.related_reporting_count_total),
      input_truncated:incoming.input_truncated===true,
      pairwise_comparisons_capped:incoming.pairwise_comparisons_capped===true,
      candidate_groups_truncated:incoming.candidate_groups_truncated===true,
      reporting_origins_are_not_event_locations:true,
      source_independence_unverified:true,
      not_a_preparations_sensor_or_warning:true,
      automatic_alerts_created:0,automatic_severity_changes:0,
      forecast_probability:null,candidate_groups:safeCandidates,
    };
  }
  const health={};
  for(const [name,row] of Object.entries(raw.collection_coverage)){
    if(!row||typeof row!=="object"||Array.isArray(row))return null;
    health[limited(name)]={
      status:limited(row.status||"unknown"),
      missingness:limited(row.missingness||"unknown"),
      source_scope:limited(row.source_scope||"unverified scope"),
      snapshot_at:limited(row.snapshot_at),
    };
  }
  return {
    schema:raw.schema,status:"read_only_shadow_evidence",
    source_generated_at:raw.generated_at,site_snapshot_fresh:false,
    cross_family_count_total:groupTotal,single_source_count_total:leadTotal,
    review_groups:groups,new_single_source_leads:leads,
    collection_coverage:health,
    provider_baselines:state.behavior?.provider_baselines||{},
    discovery_visibility:safeVis,recent_source_observations:safeRecent,
    report_relationships:relationship,
    approved_warning_count:0,automated_severity_changes:0,
    source_continuity_proven:false,forecast_probability:null,
    map_coordinates_inferred:false,
  };
}
async function refreshBehavior(){
  const url=state.atlas?.behavior_live_url;
  if(!safeUrl(url))return;
  try{
    const opts={cache:"no-store"};
    if(typeof AbortSignal!=="undefined"&&typeof AbortSignal.timeout==="function")
      opts.signal=AbortSignal.timeout(12000);
    const response=await fetch(url,opts);
    if(!response.ok)throw Error("behavioral source response "+response.status);
    const raw=await response.json(),candidate=normalizeLiveBehavior(raw);
    if(!validBehavior(candidate))throw Error("invalid behavioral evidence schema");
    const previous=Date.parse(state.behavior?.source_generated_at||"");
    const next=Date.parse(candidate.source_generated_at);
    if(!Number.isFinite(previous)||next>previous){
      state.behavior=candidate;
      state.behaviorRemoteStatus="public evidence branch snapshot";
      updateBehaviorTabCount();
      if(state.watchTab==="behavior"||state.watchTab==="evaluation")updateWatchlist();
    }else{
      state.behaviorRemoteStatus="published site snapshot retained";
      if(state.watchTab==="behavior"||state.watchTab==="evaluation")updateWatchlist();
    }
  }catch(error){
    state.behaviorRemoteStatus="source branch refresh unavailable; last published snapshot retained";
    if(state.watchTab==="behavior")renderBehaviorList();
  }
}
function behaviorAge(){
  const then=Date.parse(state.behavior?.source_generated_at||"");
  return Number.isFinite(then)?(Date.now()-then)/60000:Infinity;
}
function updateBehaviorTabCount(){
  const b=state.behavior;
  const total=b?(b.cross_family_count_total||0)+(b.single_source_count_total||0):0;
  const observed=b?.discovery_visibility?.recent_unique_record_count_72h;
  $("behaviorTabCount").textContent=b?(
    Number.isInteger(observed)?"("+total+" new / "+observed+" observed)":"("+total+")"):"";
}
function behaviorHealthTable(b){
  const health=b.collection_coverage||{};
  const baselines=b.provider_baselines||{};
  const rows=Object.entries(health).map(([name,info])=>{
    const base=baselines[name]||{};
    const degraded=info.status!=="current"||info.missingness!=="none";
    return '<tr><th scope="row">'+safe(name)+'</th><td>'+safe(info.status||"unknown")+
      (degraded?' · bounded/unavailable':'')+'</td><td>'+safe(info.source_scope||"not established")+
      '</td><td>'+safe(base.comparable_days??"—")+
      ' days; median '+safe(base.median_records??"unavailable")+
      '</td></tr>';
  }).join("");
  return '<details class="behavior-health"><summary>Source coverage and reference baselines ('+
    Object.keys(health).length+' providers)</summary>'+
    '<p>Provider completeness is not verified; partial or missing observations are never treated as a zero-event interval.</p>'+
    '<div class="behavior-table-scroll"><table><thead><tr><th>Feed</th><th>Status</th><th>Scope</th><th>Baseline</th></tr></thead><tbody>'+
    (rows||'<tr><td colspan="4">No source health available.</td></tr>')+
    '</tbody></table></div></details>';
}
function selectBehavior(row,kind){
  const panel=$("selectedDetail");panel.hidden=false;
  const isGroup=kind==="group";
  const area=row.geography||{};
  const named=area.label||"Location not independently verified";
  const age=behaviorAge();
  const freshness=age>=0&&age<=90?"recent source snapshot":"historical or stale source snapshot";
  const title=isGroup?("Cross-family review · "+named):(row.title||row.observation_id||"Single-source lead");
  const links=isGroup?(row.source_links||[]):[{url:row.source_url,provider:row.source_family,
    first_observed_at:row.first_observed_at,published_at:row.source_published_at}];
  const details=links.slice(0,12).map(item=>
    '<li>'+(safeUrl(item.url)?'<a href="'+safe(item.url)+'" target="_blank" rel="noopener noreferrer">'+
      safe(item.provider||item.family||"Original source")+'</a>':safe(item.provider||"Source unlinked"))+
    '<span class="sub"> · observed '+safe(item.first_observed_at||"unknown")+
    ' · published '+safe(item.published_at||"unknown")+'</span></li>').join("");
  panel.innerHTML='<div class="detail-top"><div><h3>'+safe(title)+'</h3>'+
    '<span class="behavior-status">UNREVIEWED · '+safe(freshness)+'</span></div>'+
    '<button class="detail-close" type="button" aria-label="Close behavioral detail">×</button></div>'+
    '<p><b>Source-defined geography:</b> '+safe(named)+
    ' · '+safe(area.precision||"not geocoded")+'</p>'+
    '<p>'+safe(isGroup?row.assessment:
      "One source observation only. Additional independent evidence is needed before a hypothesis can be issued.")+'</p>'+
    (isGroup?'<p><b>Evidence families:</b> '+safe((row.distinct_source_families||[]).join(", "))+
      ' · '+safe(row.source_root_count||"unknown")+' distinct reported source roots (causal independence not verified).</p>':'')+
    '<p><b>First observed:</b> '+safe(row.first_observed_at||"unknown")+
    ' · <b>Last observed:</b> '+safe(row.last_observed_at||row.first_observed_at||"unknown")+'</p>'+
    '<p class="sub">No automatic change to standing severity or warning probability. '+
    'A provider-declared geographic scope is not a confirmed event position; no map marker inferred.</p>'+
    '<ul>'+details+'</ul>'+
    '<a href="behavior/">Detailed behavioral source coverage →</a>';
  panel.querySelector(".detail-close").addEventListener("click",()=>{panel.hidden=true;state.selected=null;});
}
function openReportRelationship(group){
  const panel=$("selectedDetail");panel.hidden=false;
  const names={
    shared_source_document_unreviewed:"One shared source document",
    possible_same_source_story_unreviewed:"Possibly the same syndicated article",
    possible_same_event_unreviewed:"Possible reports of the same event",
    related_reporting_unreviewed:"Related reports — event identity uncertain",
  };
  const sourceRows=group.source_reports||[];
  const articles=sourceRows.map(r=>'<li><strong>'+safe(r.title||"Untitled report")+
    '</strong> · '+safe(r.provider||"Unknown provider")+
    (safeUrl(r.source_url)?' · <a target="_blank" rel="noopener noreferrer" href="'+
      safe(r.source_url)+'">Original source</a>':'')+
    '<small>Source observed '+safe(r.first_observed_at||"unknown")+
    ' · publisher origin '+safe(r.reporting_origin||"unrecorded")+
    ' · source geography '+safe(r.geography?.label||"not verified")+'</small></li>').join("");
  const loc=group.reported_event_site_comparison_available?
    ('Source-declared event sites approximately '+safe(group.reported_event_site_separation_km)+
      ' km apart (not independently located).'):
    'No two explicitly source-declared event sites were available to measure proximity.';
  panel.innerHTML='<div class="detail-top"><div><h3>'+
    safe(names[group.status]||"Unreviewed source relationship")+'</h3>'+
    '<span class="behavior-status">POSSIBLE · NOT VERIFIED</span></div>'+
    '<button type="button" class="detail-close" aria-label="Close possible relationship">×</button></div>'+
    '<p><b>Why surfaced:</b> '+safe(group.match_basis||"Unverified relationship")+'</p>'+
    '<p>'+loc+'</p><p><b>Publisher location does not identify event location.</b> '+
    'Shared subjects, overlapping geography or a shared source URL never establish independent corroboration or military intent.</p>'+
    '<ul>'+articles+'</ul>'+
    '<p class="sub">Analyst must compare primary sources, actual incident chronology, geographic claims and alternative explanations. '+
    'Standing watch severity and issued warning counts are unchanged.</p>';
  panel.querySelector(".detail-close").addEventListener("click",()=>{panel.hidden=true;});
}
function renderBehaviorList(){
  const list=$("watchlist");list.classList.add("behavior-view");list.replaceChildren();
  $("watchPanelTitle").firstChild.textContent="Behavioral signals ";
  $("frictionBriefing").hidden=true;
  $("watchDetailLink").href="behavior/";
  $("watchDetailLink").textContent="Detailed source records →";
  const b=state.behavior;
  if(!b){
    $("watchCount").textContent="(unavailable)";
    $("watchFoot").textContent="No current source evidence; not an all-clear.";
    list.innerHTML='<p class="behavior-disclaimer">SHADOW MODE · No automatic warning classifications</p>'+
      '<p class="behavior-empty">A validated behavioral source snapshot is unavailable. Source collection may be delayed or incomplete; no absence of activity can be inferred.</p>'+
      '<a href="behavior/">Open original behavioral source table →</a>';
    return;
  }
  const age=behaviorAge(),recent=age>=0&&age<=90;
  const visibility=b.discovery_visibility;
  const context=b.recent_source_observations||[];
  $("watchCount").textContent=visibility?
    "("+b.cross_family_count_total+" cross-family / "+visibility.recent_unique_record_count_72h+" observed)":
    "("+(b.cross_family_count_total+b.single_source_count_total)+")";
  $("watchFoot").textContent="Investigatory sources, not issued forecasts.";
  const frag=document.createElement("div");
  frag.className="behavior-panel-body";
  const introduction=document.createElement("div");
  introduction.className="behavior-overview"+(recent?"":" stale");
  const stamp=Number.isFinite(age)&&age>=0?Math.round(age)+" minutes old":"clock/source time inconsistent";
  introduction.innerHTML='<strong>Behavioral discovery · SHADOW ONLY</strong>'+
    '<span class="behavior-status">'+(recent?"SOURCE SNAPSHOT WITHIN 90 MIN":"STALE OR UNVERIFIED SNAPSHOT")+'</span>'+
    '<p>As of '+safe(b.source_generated_at)+' · '+safe(stamp)+
    ' · '+safe(state.behaviorRemoteStatus)+'. Unreviewed source observations, not confirmed preparations or attack forecasts.</p>'+
    '<div class="behavior-counts"><span><b>'+safe(b.cross_family_count_total)+'</b> cross-family reviews</span>'+
    '<span><b>'+safe(b.single_source_count_total)+'</b> new source leads</span></div>'+
    (recent?'':'<p class="behavior-caution">Historical context only: source freshness failed the 90-minute pilot gate. No current all-clear may be inferred.</p>');
  frag.appendChild(introduction);
  if(visibility){
    const funnel=document.createElement("div");funnel.className="behavior-funnel";
    funnel.innerHTML='<h3>Observation-to-review pipeline</h3>'+
      '<p><b>'+safe(visibility.latest_registry_record_count)+'</b> current normalized records · '+
      '<b>'+safe(visibility.recent_unique_record_count_72h)+'</b> unique observations over 72h · '+
      '<b>'+safe(visibility.latest_registry_newly_observed_count)+'</b> new this collection</p>'+
      '<p><b>'+safe(visibility.recent_unlocated_count_72h)+'</b> of the recent records lack a comparable geographic key; '+
      '<b>'+safe(visibility.shared_exact_geography_keys_across_behavior_families)+
      '</b> exact place keys have more than one behavioral source family.</p>'+
      '<p class="behavior-caution">Cross-family nominations require both a matching source geography and a new record in this collection. '+
      'These counts diagnose the gate; they do not certify source independence, benign conditions, or threat preparation.</p>';
    frag.appendChild(funnel);
  }
  const relationships=b.report_relationships;
  if(relationships){
    const head=document.createElement("h3");head.className="behavior-section-title";
    head.textContent="Possible event/report links · NOT corroboration";
    frag.appendChild(head);
    const explain=document.createElement("p");explain.className="behavior-empty";
    explain.textContent=relationships.records_examined+" monitored source observations; "+
      relationships.eligible_event_reporting_records+
      " eligible for incident-report text matching. "+
      (relationships.same_document_group_count_total||0)+
      " repeated source-document groups · "+
      (relationships.possible_same_source_story_count_total||0)+
      " possible same-story syndications · "+
      (relationships.possible_same_event_count_total||0)+
      " possible same-event pairs · "+
      (relationships.related_reporting_count_total||0)+
      " related-reporting pairs. Publisher origin and event site are different fields.";
    frag.appendChild(explain);
    if(relationships.input_truncated||relationships.pairwise_comparisons_capped||
       relationships.candidate_groups_truncated){
      const caution=document.createElement("p");caution.className="behavior-caution";
      caution.textContent="Matching is bounded or truncated; this is NOT an exhaustive deduplication.";
      frag.appendChild(caution);
    }
    if(!relationships.candidate_groups.length){
      const p=document.createElement("p");p.className="behavior-empty";
      p.textContent="No report relationships cleared the current conservative candidate threshold.";
      frag.appendChild(p);
    }
    for(const g of relationships.candidate_groups){
      const item=document.createElement("button");item.type="button";
      item.className="watch-card relationship-card";
      const label=g.status==="shared_source_document_unreviewed"?
        "SHARED SOURCE":g.status==="possible_same_source_story_unreviewed"?
        "POSSIBLE SYNDICATION":g.status==="possible_same_event_unreviewed"?
        "POSSIBLE SAME EVENT":"RELATED REPORTING";
      const row=g.source_reports[0];
      item.innerHTML='<div class="watch-card-head"><strong>'+
        safe(row?.title||"Unreviewed report relationship")+
        '</strong><span class="behavior-status">'+safe(label)+'</span></div>'+
        '<p>'+safe(g.match_basis||"Needs review")+
        ' · '+safe(g.source_reports.length)+' displayed source records</p>'+
        '<small>Not evidence of independent confirmation or imminent action</small>';
      item.addEventListener("click",()=>openReportRelationship(g));
      frag.appendChild(item);
    }
  }
  const groups=b.review_groups;
  const groupTitle=document.createElement("h3");groupTitle.className="behavior-section-title";groupTitle.textContent="Cross-family observations";frag.appendChild(groupTitle);
  if(!groups.length){
    const p=document.createElement("p");p.className="behavior-empty";
    p.textContent="No newly nominated co-occurrences in this source snapshot. This is not evidence of no threat.";frag.appendChild(p);
  }
  for(const row of groups){
    const button=document.createElement("button");button.type="button";button.className="watch-card behavior-card";
    const loc=row.geography?.label||"Location not verified";
    button.innerHTML='<div class="watch-card-head"><strong>'+safe(loc)+'</strong>'+
      '<span class="behavior-status">REVIEW</span></div>'+
      '<p>'+safe(row.assessment||"Co-occurring sources; causal independence not established.")+'</p>'+
      '<small>'+safe((row.distinct_source_families||[]).join(" · "))+'</small>'+
      '<small>First observed '+safe(row.first_observed_at||"unavailable")+'</small>';
    button.addEventListener("click",()=>selectBehavior(row,"group"));
    frag.appendChild(button);
  }
  const leadTitle=document.createElement("h3");leadTitle.className="behavior-section-title";leadTitle.textContent="New single-source leads";frag.appendChild(leadTitle);
  if(!b.new_single_source_leads.length){
    const p=document.createElement("p");p.className="behavior-empty";
    p.textContent="No new source-only leads in this snapshot; observation coverage remains bounded.";frag.appendChild(p);
  }
  for(const row of b.new_single_source_leads){
    const button=document.createElement("button");button.type="button";button.className="watch-card behavior-card";
    button.innerHTML='<div class="watch-card-head"><strong>'+safe(row.title||row.observation_id)+'</strong>'+
      '<span class="behavior-status">SOURCE</span></div>'+
      '<p>'+safe(row.source_family||"Unclassified source family")+' · '+
      safe(row.geography?.label||"Location not verified")+'</p>'+
      '<small>Observed '+safe(row.first_observed_at||"unknown")+
      (row.requires_geolocation?' · GEOGRAPHY UNVERIFIED':'')+'</small>';
    button.addEventListener("click",()=>selectBehavior(row,"lead"));
    frag.appendChild(button);
  }
  if(context.length){
    const historical=document.createElement("h3");historical.className="behavior-section-title";
    historical.textContent="Recent source observations · 72h (NOT warnings)";
    frag.appendChild(historical);
    const note=document.createElement("p");note.className="behavior-empty";
    note.textContent="Observed records retained from the prior 72 hours, shown even when nothing is new in the latest collection. " +
      "A bounded source sample; no hostile intent or incident location is inferred.";
    frag.appendChild(note);
    for(const row of context){
      const btn=document.createElement("button");btn.type="button";
      btn.className="watch-card behavior-history-card";
      btn.innerHTML='<div class="watch-card-head"><strong>'+safe(row.title||row.observation_id)+
        '</strong><span class="behavior-status">OBSERVED</span></div>'+
        '<p>'+safe(row.source_family||"source")+" · "+safe(row.provider||"provider unknown")+
        ' · '+safe(row.geography?.label||"Location not verified")+'</p>'+
        '<small>First observed '+safe(row.first_observed_at||"unknown")+
        (row.requires_geolocation?" · GEOGRAPHY UNVERIFIED":"")+'</small>';
      btn.addEventListener("click",()=>selectBehavior(row,"lead"));
      frag.appendChild(btn);
    }
  }else if(visibility&&visibility.recent_unique_record_count_72h>0){
    const p=document.createElement("p");p.className="behavior-empty";
    p.textContent="Recent observations exist but no inspectable sample was published. This is a publication/visibility gap.";
    frag.appendChild(p);
  }
  const health=document.createElement("div");
  health.innerHTML=behaviorHealthTable(b);frag.appendChild(health);
  const note=document.createElement("p");note.className="behavior-disclaimer";
  note.textContent="No behavioral observations are plotted as event coordinates, promoted to hotspot severity, or scored as validated early warnings.";
  frag.appendChild(note);
  list.appendChild(frag);
}
/* Public AIBA performance-readiness tab. Private tipper ledgers are NOT
 * imported by Pages; no 0/0 rate or "all quiet" is ever inferred.
 */
function validEvaluation(value){
  if(!value||value.schema!=="aiba.atlas-public-evaluation-readiness.v1"||
     value.status!=="prospective_skill_not_established"||
     value.public_forecast_ledger!=="not_connected"||
     value.publication_of_private_ledger!==false||
     value.production_warning_updates!==false||
     value.forecast_probability!==null||
     value.claims_of_predictive_skill!==false||
     !value.observation||!value.verification_gates||!value.metrics)return false;
  if(Object.values(value.metrics).some(x=>x!==null))return false;
  if(Object.values(value.verification_gates).some(x=>x!=="not_connected"))return false;
  return value.observation.worldwide_source_completeness_verified===false&&
    value.observation.unobserved_intervals_are_negative_events===false;
}
function renderEvaluationList(){
  const list=$("watchlist");list.replaceChildren();
  list.classList.add("behavior-view","evaluation-view");
  $("watchPanelTitle").firstChild.textContent="Warning evaluation ";
  $("watchCount").textContent="";
  $("frictionBriefing").hidden=true;
  $("watchDetailLink").href="https://github.com/graupmannj-dev/I-Ws-Dashboard/blob/main/docs/AIBA_PROSPECTIVE_SHADOW_PILOT.md";
  $("watchDetailLink").textContent="Evaluation protocol →";
  $("watchFoot").textContent="Read-only public review · no private forecast content.";
  const e=state.atlas?.warning_evaluation;
  if(!validEvaluation(e)){
    list.innerHTML='<p class="evaluation-caution"><b>Evaluation data unavailable.</b> No prospectively verified forecast outcomes can be established. This is not a zero-event result.</p>';
    return;
  }
  const b=validBehavior(state.behavior)?state.behavior:null;
  const age=b?behaviorAge():Infinity;
  const current=Number.isFinite(age)&&age>=0&&age<=90;
  const health=b?.collection_coverage||{};
  const observed=b?Object.keys(health).length:e.observation.source_adapters_reported;
  const impaired=b?Object.values(health).filter(r=>
    !r||r.status!=="current"||r.missingness!=="none").length:
    e.observation.source_adapters_bounded_or_degraded;
  const observedAsOf=b?.source_generated_at||e.observation.behavioral_source_asof;
  const frag=document.createElement("div");frag.className="evaluation-panel-body";
  const hero=document.createElement("section");hero.className="evaluation-hero";
  hero.innerHTML='<strong>Prospective I&W evaluation</strong>'+
    '<span class="evaluation-state">SKILL NOT YET ESTABLISHED</span>'+
    '<p>The source engine can nominate investigative signals; it has not supplied an independently verified prospective forecast dataset to this public dashboard. Signed mechanism tests are not operational predictions.</p>';
  frag.appendChild(hero);
  const title=document.createElement("h3");title.className="behavior-section-title";
  title.textContent="Current collection readiness";frag.appendChild(title);
  const ready=document.createElement("section");ready.className="evaluation-readiness";
  const ageLabel=Number.isFinite(age)&&age>=0?Math.round(age)+" min old":
    (observedAsOf?"snapshot freshness unverified":"source snapshot unavailable");
  ready.innerHTML='<div class="evaluation-sensor-status">'+
    '<strong>'+(current?"Snapshot recent":"Snapshot stale or unavailable")+'</strong>'+
    '<span>'+safe(observedAsOf||"No observed source time")+'</span></div>'+
    '<p>Last source timestamp: '+safe(ageLabel)+
    '. The 90-minute freshness gate checks snapshot age, <b>not source completeness</b>.</p>'+
    '<p>Source adapters represented: <b>'+safe(observed??"unavailable")+'</b>'+
    '; bounded or degraded: <b>'+safe(impaired??"unavailable")+'</b>.</p>'+
    '<p class="evaluation-note">Unobserved time/geography remains UNKNOWN. Collection gaps cannot be scored as quiet periods.</p>';
  frag.appendChild(ready);
  const scores=document.createElement("h3");scores.className="behavior-section-title";
  scores.textContent="Warning performance · not estimable";frag.appendChild(scores);
  const tiles=document.createElement("div");tiles.className="evaluation-metrics";
  const items=[
    ["Verified pre-news lead time","median_verified_prepublication_lead_seconds"],
    ["False alarms per analyst-day","false_alarms_per_analyst_day"],
    ["Missed-event recall","recall_against_registered_outcomes"],
    ["Forecast calibration","brier_calibration_score"],
  ];
  for(const [name,key] of items){
    const tile=document.createElement("div");tile.className="evaluation-metric";
    // The v1 public contract requires null metrics; a number from an
    // external or unchecked summary cannot be rendered as validated skill.
    const value=e.metrics[key];
    tile.innerHTML='<small>'+safe(name)+'</small><strong>'+
      (value===null?"—":"Unavailable")+'</strong><span>Not independently verified</span>';
    tiles.appendChild(tile);
  }
  frag.appendChild(tiles);
  const gate=document.createElement("h3");gate.className="behavior-section-title";
  gate.textContent="Evidence needed before claiming skill";frag.appendChild(gate);
  const gates=document.createElement("ol");gates.className="evaluation-gates";
  for(const text of [
    "Freeze genuinely prospective source-coverage frames and monitored risk sets.",
    "Independently timestamp real, analyst-reviewed actor/action/horizon forecasts.",
    "Establish original public-report chronology, not GDELT ingestion time.",
    "Adjudicate outcome and non-event windows against independent sources.",
    "Count misses, exposure time, outages and analyst burden before calculating skill.",
  ]){
    const li=document.createElement("li");li.textContent=text;gates.appendChild(li);
  }
  frag.appendChild(gates);
  const link=document.createElement("p");link.className="evaluation-note";
  link.innerHTML='Private ledger scoring and witness workflows stay off this public site. '+
    '<a href="https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/aiba-shadow-readiness-manual.yml" target="_blank" rel="noopener noreferrer">Manual source readiness check</a>'+
    ' · <a href="https://github.com/graupmannj-dev/I-Ws-Dashboard/blob/main/docs/AIBA_SIGNED_TIPPER_LEDGER_ANCHORS.md" target="_blank" rel="noopener noreferrer">Witness protocol</a>';
  frag.appendChild(link);
  list.appendChild(frag);
}
function updateWatchlist(){
  if(!state.atlas)return;
  if(state.watchTab==="behavior"){renderBehaviorList();return;}
  if(state.watchTab==="evaluation"){renderEvaluationList();return;}
  const list=$("watchlist");list.classList.remove("behavior-view","evaluation-view");list.replaceChildren();
  $("watchPanelTitle").firstChild.textContent="Watchlist ";
  $("watchDetailLink").href="ops/";
  $("watchDetailLink").textContent="Full analysis →";
  $("frictionBriefing").hidden=false;
  const hs=selectedHotspots().filter(h=>state.watchTab==="all"||h.new_evidence||frictionIsReview(h.id));
  const rank={critical:0,active:1,high:2,watch:3,low:4};
  hs.sort((a,b)=>Number(b.new_evidence||frictionIsReview(b.id))-Number(a.new_evidence||frictionIsReview(a.id))||(rank[a.severity]??4)-(rank[b.severity]??4)||a.name.localeCompare(b.name));
  $("watchCount").textContent="("+hs.length+")";
  $("watchFoot").textContent=state.atlas.algorithmic_unlocated_count+" GDELT + "+(state.atlas.unlocated_analyst_leads||[]).length+" analyst unlocated leads";
  if(!hs.length){
    if(state.watchTab==="new"){
      const box=document.createElement("div");box.className="behavior-funnel";
      box.innerHTML='<h3>No reviewed case-specific developments in this snapshot</h3>'+
        '<p>The Recent changes view only includes evidence that cleared the existing curated watch-case review or friction-review gates. '+
        'Unreviewed observations are not automatically promoted to geopolitical developments.</p>';
      const b=state.behavior;
      if(b?.discovery_visibility){
        const p=document.createElement("p");
        p.textContent=b.discovery_visibility.recent_unique_record_count_72h+
          " unique source observations exist in the separate 72-hour behavioral history.";
        box.appendChild(p);
      }
      const open=document.createElement("button");open.type="button";
      open.className="outline-btn";open.textContent="Inspect recent source observations";
      open.addEventListener("click",()=>{state.watchTab="behavior";updateTabs();});
      box.appendChild(open);list.appendChild(box);
    }else list.innerHTML='<p class="empty">No watch areas match these filters. No Critical classification is inferred automatically.</p>';
    return;
  }
  for(const h of hs){
    const b=document.createElement("button");b.type="button";
    b.className="watch-card"+(state.selected===h.id&&state.selectionType==="hotspot"?" selected":"");
    const f=frictionCase(h.id);
    const review=frictionIsReview(h.id);
    b.innerHTML='<div class="watch-card-head"><strong>'+safe(h.name)+'</strong>'+
      '<span class="severity-tag '+safe(h.severity)+'">'+safe(h.state)+'</span></div>'+
      '<p>'+safe(review?f.so_what:(h.what_changed||h.description||h.scenario))+'</p>'+
      '<small>Curated source date: '+safe(h.baseline_asof||"unknown")+'</small>'+
      (h.new_evidence?'<div class="card-new">NEW CASE-SPECIFIC SOURCE CHANGE</div>':'')+
      (h.new_analyst_lead?'<div class="card-new">UNREVIEWED OSINT LEAD · INVESTIGATORY ONLY</div>':'')+
      (review?'<small>Early indicator · '+safe(f.publication_basis||"provisional")+' · '+safe(f.baseline_context||"baseline unavailable")+'</small>':'');
    b.addEventListener("click",()=>select(h));list.appendChild(b);
  }
}
function canvasPick(clientX,clientY){
  const rect=state.canvas.getBoundingClientRect(),x=clientX-rect.left,y=clientY-rect.top;
  for(const p of state.hitTargets){
    if(p.type==="region"){
      if(regionHit(p,x,y))return p;
    }else if(Math.hypot(p.x-x,p.y-y)<=p.r)return p;
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
        state.lat=clamp(state.drag.lat+dy/Math.max(radius(),1)*65,-89.5,89.5);
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
        :'<b>'+safe(obj.title)+'</b><span>'+safe(obj.observed_at||obj.date||obj.valid_from||"")+
          ' · '+(found.type==="region"?"Source-defined restriction area":found.type==="layer"?"Source observation":"Theater-associated report")+'</span>';
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
    // Keep the clicked geographic location in view while zooming.
    const point=geographicPointAt(event.clientX,event.clientY);
    if(point)centerOnPosition(point[0],point[1],state.zoom*1.65);
    else changeZoom(1.65);
  });
}
function geographicPointAt(clientX,clientY){
  const rect=state.canvas.getBoundingClientRect(),d=state.dimensions;
  const xp=(clientX-rect.left-d.cx)/d.r;
  const yp=(d.cy-(clientY-rect.top))/d.r;
  const rho=Math.hypot(xp,yp);
  if(rho>1)return null;
  const centerLat=state.lat*DEG;
  const surface=Math.sqrt(Math.max(0,1-rho*rho));
  const latitude=Math.asin(clamp(surface*Math.sin(centerLat)+yp*Math.cos(centerLat),-1,1));
  const longitude=state.lon*DEG+
    Math.atan2(xp,surface*Math.cos(centerLat)-yp*Math.sin(centerLat));
  return [longitude/DEG,latitude/DEG];
}
function changeZoom(multiplier){
  const next=clamp(state.zoom*multiplier,.65,40);
  if(Math.abs(next-state.zoom)<.001)return;
  state.zoom=next;
  resize();
}
function centerOnPosition(lon,lat,zoom=null){
  if(!Number.isFinite(lon)||!Number.isFinite(lat)||
     Math.abs(lon)>180||Math.abs(lat)>90)return;
  state.lon=((lon+180)%360+360)%360-180;
  state.lat=clamp(lat,-89.5,89.5);
  if(Number.isFinite(zoom))state.zoom=clamp(zoom,.65,40);
  resize();
}
function geographicCenter(points){
  // Spherical vector mean prevents antimeridian polygons averaging to 0E.
  let x=0,y=0,z=0;
  for(const [lon,lat] of points){
    if(!Number.isFinite(lon)||!Number.isFinite(lat))continue;
    const lo=lon*DEG,la=lat*DEG;
    x+=Math.cos(la)*Math.cos(lo);
    y+=Math.cos(la)*Math.sin(lo);
    z+=Math.sin(la);
  }
  const len=Math.hypot(x,y,z);
  if(len<1e-6)return points[0]||null;
  return [Math.atan2(y,x)/DEG,Math.atan2(z,Math.hypot(x,y))/DEG];
}
function focusRestriction(row){
  const source=row?.geometry;
  const geometry=window.AtlasLayers.drawableGeometry(source);
  const points=[];
  function walk(part){
    if(!Array.isArray(part))return;
    if(part.length===2&&typeof part[0]==="number"&&typeof part[1]==="number")
      points.push(part);
    else for(const child of part)walk(child);
  }
  if(geometry)walk(geometry.coordinates);
  if(!points.length&&Number.isFinite(row.lon)&&Number.isFinite(row.lat))
    points.push([row.lon,row.lat]);
  if(!points.length)return;
  const center=geographicCenter(points);
  if(!center)return;
  // Geometric angular extent, not invented positions. Pick a zoom that makes
  // the actual published outline occupy a legible fraction of the canvas.
  const lon=center[0]*DEG,lat=center[1]*DEG;
  let theta=0;
  for(const [lo,la] of points){
    const cos=Math.sin(lat)*Math.sin(la*DEG)+
              Math.cos(lat)*Math.cos(la*DEG)*Math.cos((lo*DEG)-lon);
    theta=Math.max(theta,Math.acos(clamp(cos,-1,1)));
  }
  const desired=clamp(.36/Math.max(.00002,Math.sin(Math.min(theta,Math.PI/2))),1,40);
  centerOnPosition(center[0],center[1],desired);
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
  $("tabBehavior").addEventListener("click",()=>{state.watchTab="behavior";updateTabs();});
  $("tabEvaluation").addEventListener("click",()=>{state.watchTab="evaluation";updateTabs();});
  $("openEvaluation").addEventListener("click",()=>{
    state.watchTab="evaluation";updateTabs();
    if(window.innerWidth<=1050)document.querySelector(".watch-panel").scrollIntoView({block:"nearest",behavior:"smooth"});
  });
  $("openBehavior").addEventListener("click",()=>{
    state.watchTab="behavior";updateTabs();
    if(window.innerWidth<=1050)document.querySelector(".watch-panel").scrollIntoView({block:"nearest",behavior:"smooth"});
  });
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
  for(const [id,tab] of [["tabAll","all"],["tabNew","new"],["tabBehavior","behavior"],["tabEvaluation","evaluation"]]){
    const active=state.watchTab===tab;
    $(id).classList.toggle("active",active);
    $(id).setAttribute("aria-pressed",String(active));
  }
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
  $("kpiUpdates").textContent=a.hotspots.filter(x=>x.new_evidence||frictionIsReview(x.id)).length;
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
    state.behavior=validBehavior(data.behavioral_discovery)?data.behavioral_discovery:null;
    updateBehaviorTabCount();
    void refreshBehavior();
    setInterval(refreshBehavior,300000);
    renderFriction();
    void refreshFriction();
    setInterval(refreshFriction,300000);
    window.AtlasLayers.init(data.layer_feed,()=>{state.staticValid=false;},focusRestriction);
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
/* FAA NAS official operational disruption monitor. Do not interpret disruption
 * or multi-airport impact as evidence of military, cyber or foreign activity.
 * Never show green/all-clear when the upstream source is missing or stale. */
async function refreshFaaNas() {
  const heading=$("faaNasSummary"), line=$("faaNasTime");
  if(!heading||!line)return;
  const set=(message,detail)=>{heading.textContent=message;line.textContent=detail;};
  // Offline browser tests and local previews have no persisted FAA NAS data branch.
  // Do not initiate external fetches or create false error alerts in that mode.
  if(location.hostname==="127.0.0.1"||location.hostname==="localhost"){
    set("FAA NAS source is not connected in this offline preview",
        "Live source status is available on the published site after the first collector run");
    return;
  }
  const base="https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/aiba-feed-data/observations/";
  try {
    const [sourceResponse,healthResponse]=await Promise.all([
      fetch(base+"latest/faa_nas.json",{cache:"no-store"}),
      fetch(base+"health/faa_nas.json",{cache:"no-store"})
    ]);
    if(!sourceResponse.ok||!healthResponse.ok)throw Error("sensor not available on public evidence branch");
    const data=await sourceResponse.json(),health=await healthResponse.json();
    if(!data||data.schema!=="aiba.faa-nas-systemic-disruption.v1"||
       !health||health.schema!=="aiba.faa-nas-health.v1"||
       typeof data.monitored_airport_count!=="number"||
       typeof data.national_stop_airports!=="number"||
       !Array.isArray(data.airports)||data.hostile_actor_evidence!==false||
       data.military_warning_level_change!==false)throw Error("unrecognized sensor payload");
    const sampleTime=Date.parse(String(data.checked_at||""));
    const healthTime=Date.parse(String(health.checked_at||""));
    const age=Date.now()-sampleTime;
    const recentlyCollected=Number.isFinite(sampleTime)&&age>=-300000&&age<=25*60000;
    const sourceHealthy=health.status==="collected"&&Number.isFinite(healthTime)&&
                        (Date.now()-healthTime)<=25*60000;
    if(!recentlyCollected||!sourceHealthy){
      set("FAA sensor stale or unavailable; no all-clear inference",
          "Last valid sample: "+String(data.checked_at||"unknown")+
          " · last source check: "+String(health.checked_at||"unknown"));
      return;
    }
    let title;
    if(data.status==="multi_airport_national_stop_language"){
      title="FAA NAS: NATIONAL STOP language in "+data.national_stop_airports+
          " monitored airport records — systemic disruption requires review";
    }else if(data.status==="single_airport_national_stop_language"){
      title="FAA NAS: national-stop language reported at one monitored airport";
    }else if(data.status==="multiple_airport_ground_stops"){
      title="FAA NAS: simultaneous ground-stop records at "+data.active_ground_stop_airports+" monitored airports";
    }else if(data.status==="no_systemic_disruption_in_monitored_sample"){
      title="No cross-airport disruption pattern in this FAA sample (not a national all-clear)";
    }else{
      throw Error("unknown systemic disruption category");
    }
    set(title,"Observed "+String(data.checked_at)+
        " · "+data.monitored_airport_count+" monitored airports · FAA single-source operational effect, cause unknown");
  } catch(_err){
    set("FAA NAS sensor unavailable; no all-clear inference",
        "Independent source status unavailable — consult the official FAA NAS feed");
  }
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",refreshFaaNas);
else refreshFaaNas();
setInterval(refreshFaaNas,120000);
})();