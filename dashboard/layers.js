/* Measured overlays. Independent of historical report-date controls. */
window.AtlasLayers = (() => {
  'use strict';
  const definitions = {
    aircraft: ['ADS-B aircraft', '#70d9ff'], ships: ['AIS vessels', '#64e4c0'],
    airspace: ['Airspace restrictions', '#ffab62'], maritime: ['Maritime restrictions', '#db9aff'],
    advisories: ['US travel advisories', '#edc852'], embassies: ['US embassy status', '#ef879b']
  };
  // Keep traffic adapters available for a future opt-in; omit their UI for now.
  const hiddenLayers = new Set(['aircraft', 'ships']);
  const advisoryColors = {1:'#57c99b', 2:'#edc852', 3:'#f3a348', 4:'#f06570'};
  const aliases = {'United States of America':'United States', 'Dem. Rep. Congo':'Democratic Republic of the Congo',
    'Central African Rep.':'Central African Republic', 'Dominican Rep.':'Dominican Republic',
    'S. Sudan':'South Sudan', 'Eq. Guinea':'Equatorial Guinea', 'Bosnia and Herz.':'Bosnia and Herzegovina',
    'eSwatini':'Eswatini', 'Czechia':'Czech Republic', 'Timor-Leste':'Timor-Leste (East Timor)'};
  let payload = {layers:{}}, invalidate = () => {}, focus = () => {}, 
      endpoint = 'layers.json', liveEndpoint = null, failed = false,
      fallbackPayload=null, streamPayload=null, lastFallbackFetch=0,
      sourceStatus="Waiting for restriction observations";
  const histories = new Map();
  const shapeCache = new WeakMap();
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validPoint = r => Number.isFinite(r.lon) && Number.isFinite(r.lat) && Math.abs(r.lon)<=180 && Math.abs(r.lat)<=90;
  const enabled = key => !hiddenLayers.has(key) && $('layer-'+key)?.checked;
  function recent(stamp, seconds) {
    const age = (Date.now()-Date.parse(stamp))/1000;
    return Number.isFinite(age) && age >= -60 && age <= seconds;
  }
  function validGeometry(geometry) {
    if(!geometry)return true;
    if(!geometry || typeof geometry!=="object" || Array.isArray(geometry))return false;
    if(geometry.type==="Circle"){
      return Array.isArray(geometry.center)&&geometry.center.length===2&&
        validPoint({lon:geometry.center[0],lat:geometry.center[1]})&&
        Number.isFinite(geometry.radius_km)&&geometry.radius_km>0&&geometry.radius_km<=3500;
    }
    if(geometry.type==="BBox"||geometry.type==="Rectangle"){
      const corners=geometry.coordinates;
      if(!Array.isArray(corners)||corners.length!==2||
          !corners.every(x=>Array.isArray(x)&&x.length===2&&validPoint({lon:x[0],lat:x[1]})))return false;
      const west=corners[0][0],east=corners[1][0],south=corners[0][1],north=corners[1][1];
      return south<north&&((east>=west?east-west:east+360-west)>0)&&
        (east>=west?east-west:east+360-west)<=180;
    }
    if(!["Polygon","MultiPolygon","LineString"].includes(geometry.type))return false;
    let count=0;
    function walk(points) {
      if(!Array.isArray(points)||!points.length||++count>20000)return false;
      if(typeof points[0]==="number")
        return points.length===2&&validPoint({lon:points[0],lat:points[1]});
      return points.every(walk);
    }
    return walk(geometry.coordinates);
  }
  function drawableGeometry(source){
    if(!source || !validGeometry(source))return null;
    if(!["Circle","BBox","Rectangle"].includes(source.type))return source;
    const cached=shapeCache.get(source);if(cached)return cached;
    let ring=[];
    const rad=Math.PI/180;
    const normalizeLon=lon=>((lon+180)%360+360)%360-180;
    if(source.type==="Circle"){
      // The radius and center must be supplied by the source. Great-circle
      // sampling renders that exact source-defined area on the 3D globe.
      const lon=source.center[0]*rad,lat=source.center[1]*rad;
      const dist=source.radius_km/6371.0088,steps=96;
      for(let i=0;i<steps;i++){
        const bearing=2*Math.PI*i/steps;
        const y=Math.asin(Math.max(-1,Math.min(1,
          Math.sin(lat)*Math.cos(dist)+Math.cos(lat)*Math.sin(dist)*Math.cos(bearing))));
        const x=lon+Math.atan2(Math.sin(bearing)*Math.sin(dist)*Math.cos(lat),
          Math.cos(dist)-Math.sin(lat)*Math.sin(y));
        ring.push([normalizeLon(x/rad),y/rad]);
      }
    }else{
      const [[west,south],[east,north]]=source.coordinates;
      const right=east>=west?east:east+360;
      const step=3;
      const nLon=Math.max(1,Math.ceil((right-west)/step));
      const nLat=Math.max(1,Math.ceil((north-south)/step));
      for(let i=0;i<=nLon;i++)ring.push([normalizeLon(west+(right-west)*i/nLon),south]);
      for(let i=1;i<=nLat;i++)ring.push([normalizeLon(right),south+(north-south)*i/nLat]);
      for(let i=1;i<=nLon;i++)ring.push([normalizeLon(right-(right-west)*i/nLon),north]);
      for(let i=1;i<nLat;i++)ring.push([normalizeLon(west),north-(north-south)*i/nLat]);
    }
    if(ring.length>=3)ring.push([...ring[0]]);
    const converted={type:"Polygon",coordinates:[ring]};
    shapeCache.set(source,converted);
    return converted;
  }
  function active(key, row) {
    if(!row || typeof row!=='object' || !validGeometry(row.geometry))return false;
    if (key==='aircraft' || key==='ships') return recent(row.observed_at, 600) && validPoint(row);
    if (key==='advisories') return [1,2,3,4].includes(row.level) && typeof row.country==='string';
    if(key==='embassies' && row.notice_only)return true;
    return Date.parse(row.valid_from)<=Date.now() && (Date.parse(row.valid_until)>Date.now() || (!row.valid_until && row.in_force===true));
  }
  function records(key) {
    const layer=payload.layers[key];
    if(failed || !layer || !['snapshot','streaming','partial'].includes(layer.status) || !recent(layer.checked_at, key==='aircraft'||key==='ships'?600:172800))return [];
    return (layer.records||[]).filter(r=>active(key,r));
  }
  function countryFill(name) {
    if(enabled('embassies') && records('embassies').some(r=>(r.country||'').toLowerCase()===(aliases[name]||name).toLowerCase()))return '#ef879b99';
    if(!enabled('advisories'))return null;
    const row=records('advisories').find(r=>r.country.toLowerCase()===(aliases[name]||name).toLowerCase());
    return row?advisoryColors[row.level]+'99':null;
  }
  function show(row,key) {
    const panel=$('selectedDetail');panel.hidden=false;
    let source='Source link unavailable';
    try {const u=new URL(row.url);if(u.protocol==='https:')source='<a target="_blank" rel="noopener noreferrer" href="'+esc(u.href)+'">Open official/provider source →</a>';} catch(_) {}
    panel.innerHTML='<div class="detail-top"><h3>'+esc(row.title||row.country)+'</h3><button class="detail-close" aria-label="Close detail">×</button></div>'+
      '<p>'+esc(definitions[key][0])+'</p><p>'+esc(row.detail||'')+'</p>'+
      '<p class="sub">'+esc(row.source||'')+' · Source date: '+esc(row.observed_at||row.date||'not supplied')+'</p>'+
      (row.valid_from?'<p>Effective: '+esc(row.valid_from)+' — '+esc(row.valid_until||'Until withdrawn; source rechecked')+'</p>':'')+
      (key==='advisories'?'<p>State Department Level '+esc(row.level)+'. Embassy departure or evacuation status is a separate layer.</p>':'')+
      (!validPoint(row)&&!row.geometry&&key!=='advisories'?'<p>No precise geometry supplied; listed without an invented map location.</p>':'')+
      ((row.geometry&&validGeometry(row.geometry))||validPoint(row)?
        '<p><button type="button" class="focus-restriction">Focus on sourced area</button></p>':'')+
      source;
    panel.querySelector('.detail-close').onclick=()=>{panel.hidden=true;};
    const locate=panel.querySelector('.focus-restriction');
    if(locate)locate.onclick=()=>{focus(row);panel.hidden=true;};
  }
  function renderStatus() {
    const freshness=$('restrictionLiveStatus');
    if(freshness)freshness.textContent=sourceStatus;
    const container=$('layerStatus');container.replaceChildren();
    for(const [key,[title,color]] of Object.entries(definitions)) {
      if(!enabled(key))continue;
      const layer=payload.layers[key], rows=records(key);
      const block=document.createElement('div');block.className='feed-status';
      const fresh=layer&&recent(layer.checked_at,key==='aircraft'||key==='ships'?600:172800);
      const status=failed?'Feed unavailable':!layer?'Not connected':!fresh&&layer.checked_at?'Stale — measurements hidden':String(layer.status).replaceAll('_',' ');
      const heading=document.createElement('strong');heading.style.color=color;
      const mapped=rows.filter(r=>r.geometry&&validGeometry(r.geometry)||validPoint(r)).length;
      heading.textContent=title+' · '+rows.length+' active · '+mapped+' mapped';block.append(heading);
      const text=document.createElement('p');text.textContent=status+(layer?.checked_at?' · checked '+new Date(layer.checked_at).toLocaleString():'')+'. '+(layer?.message||'Source not connected');block.append(text);
      if(key==='embassies'){const p=document.createElement('p');p.textContent='Pink countries have departure/operations notices. Automated notices require source review; they do not establish a full evacuation.';block.append(p);}
      if(key==='advisories') {const legend=document.createElement('p');legend.textContent='1 Normal precautions · 2 Increased caution · 3 Reconsider travel · 4 Do not travel. Uncolored = no matched current record.';block.append(legend);}
      for(const row of rows.slice(0,200)) {
        const button=document.createElement('button');button.type='button';button.className='feed-notice';
        button.textContent=row.title||row.id;button.onclick=()=>show(row,key);block.append(button);
      }
      if(rows.length>200){const p=document.createElement('p');p.textContent='First 200 listed; all valid records remain on the globe.';block.append(p);}
      container.append(block);
    }
  }
  function draw(ctx, visible, line, hits, geometry) {
    for(const [key,[,color]] of Object.entries(definitions)) {
      if(!enabled(key))continue;
      for(const row of records(key)) {
        if(row.geometry && ['airspace','maritime'].includes(key)){
          const shape=drawableGeometry(row.geometry);
          if(shape)geometry(ctx,{geometry:shape},color+'3b',color,key,row,hits);
        }
        const history=histories.get(key+':'+row.id)||[];
        if(history.length>1)line(ctx,history.map(r=>[r.lon,r.lat]),color+'90',1);
        if(!validPoint(row))continue;
        const p=visible(row.lon,row.lat);if(!p)continue;
        ctx.save();ctx.translate(p.x,p.y);ctx.rotate((Number.isFinite(row.heading)?row.heading:0)*Math.PI/180);
        ctx.fillStyle=color;ctx.strokeStyle='#091a28';ctx.lineWidth=1;
        ctx.beginPath();
        if(key==='aircraft'){ctx.moveTo(0,-7);ctx.lineTo(5,5);ctx.lineTo(0,2);ctx.lineTo(-5,5);}
        else if(key==='ships'){ctx.moveTo(0,-6);ctx.lineTo(4,0);ctx.lineTo(4,5);ctx.lineTo(-4,5);ctx.lineTo(-4,0);}
        else ctx.arc(0,0,6,0,Math.PI*2);
        ctx.closePath();ctx.fill();ctx.stroke();ctx.restore();
        hits.push({type:'layer',key,x:p.x,y:p.y,r:9,record:{...row,layerKey:key}});
      }
    }
  }
  function validPayload(next){
    if(next?.version!==1 || !next.layers || typeof next.layers!=='object')return false;
    return Object.values(next.layers).every(layer=>layer&&
      ['snapshot','streaming','partial','unavailable','not_configured'].includes(layer.status)&&
      Array.isArray(layer.records)&&layer.records.length<=3000);
  }
  function asOf(value){
    const when=Date.parse(value||"");
    return Number.isFinite(when)?when:null;
  }
  function mergeSnapshots(){
    const stamp=asOf(streamPayload?.generated_at);
    const liveAge=stamp===null?Infinity:(Date.now()-stamp)/60000;
    const liveValid=liveAge>=-2&&liveAge<=90;
    if(!fallbackPayload&&!liveValid){
      streamPayload=null;
      payload={layers:{}};failed=true;
      sourceStatus="No usable restriction feed; both primary and near-live sources unavailable";return;
    }
    payload={...fallbackPayload,layers:{...(fallbackPayload?.layers||{})}};
    if(liveValid){
      for(const key of ['airspace','maritime']){
        const newer=streamPayload.layers[key];
        if(!newer)continue;
        const old=payload.layers[key];
        const fresh=asOf(newer.checked_at);
        if(fresh!==null&&(asOf(old?.checked_at)??-Infinity)<=fresh)
          payload.layers[key]=newer;
      }
      sourceStatus="Periodic GitHub snapshot · sampled "+Math.max(0,Math.round(liveAge))+
        " min ago (target ~15 min; not continuous)";
    }else{
      streamPayload=null;
      sourceStatus="Static site fallback · near-live restriction snapshot unavailable/stale";
    }
    failed=false;
  }
  async function fetchSnapshot(url){
    const opts={cache:'no-store'};
    if(typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function')
      opts.signal=AbortSignal.timeout(15000);
    const response=await fetch(url,opts);
    if(!response.ok)throw Error('HTTP '+response.status);
    return response.json();
  }
  async function refresh(){
    // Pages remains valid even when the public evidence branch is inaccessible.
    // A restricted live endpoint can replace the static fallback via AIBA_LAYER_FEED_URL.
    const isStreamEndpoint=/(^|\/)api\/layers(?:\?.*)?$/.test(endpoint);
    const shouldRefreshFallback=!fallbackPayload || isStreamEndpoint ||
                                Date.now()-lastFallbackFetch>30*60000;
    const tasks=[];
    if(shouldRefreshFallback)tasks.push(fetchSnapshot(endpoint).then(next=>{
      if(!validPayload(next))throw Error('invalid primary map schema');
      fallbackPayload=next;lastFallbackFetch=Date.now();
    }).catch(()=>{if(isStreamEndpoint)fallbackPayload=null;}));
    if(liveEndpoint&&!isStreamEndpoint)tasks.push(fetchSnapshot(liveEndpoint).then(next=>{
      if(next.kind!=='aiba_restriction_snapshot'||!validPayload(next) ||
         typeof next.generated_at!=='string'||
         !('airspace' in next.layers)||!('maritime' in next.layers))throw Error('invalid public branch snapshot');
      streamPayload=next;
    }).catch(()=>{streamPayload=null;}));
    await Promise.all(tasks);
    mergeSnapshots();
    for(const key of ['aircraft','ships'].filter(key=>enabled(key)))
      for(const row of records(key)){
        const id=key+':'+row.id,history=histories.get(id)||[];
        if(history.at(-1)?.observed_at!==row.observed_at)history.push(row);
        histories.set(id,history.filter(r=>recent(r.observed_at,600)).slice(-60));
      }
    for(const [key,history] of histories)
      if(!history.some(r=>recent(r.observed_at,600)))histories.delete(key);
    renderStatus();invalidate();
  }
  function init(config,onChange,onFocus) {
    endpoint=config?.url||'layers.json';
    liveEndpoint=config?.live_url||null;
    invalidate=onChange;
    focus=typeof onFocus==='function'?onFocus:()=>{};
    // Public traffic overlays require an explicitly configured real /api/layers
    // service. They remain opt-in, and never show tracks from stale static Pages.
    if(/(^|\/)api\/layers(?:\?.*)?$/.test(endpoint)){
      hiddenLayers.delete('aircraft');
      hiddenLayers.delete('ships');
    }
    const parent=$('measuredLayerControls');
    for(const [key,[title,color]] of Object.entries(definitions)) {
      if(hiddenLayers.has(key))continue;
      const label=document.createElement('label');label.className='toggle-row';
      label.innerHTML='<input type="checkbox" id="layer-'+key+'"'+
        (key==='airspace'||key==='maritime'?' checked':'')+
        '><span>'+title+'</span><i class="legend-swatch" style="background:'+color+'"></i>';
      label.querySelector('input').onchange=()=>{renderStatus();invalidate();};parent.append(label);
    }
    refresh().finally(()=>setTimeout(function poll(){refresh().finally(()=>setTimeout(poll,60000));},60000));
    // Aging applies even while a request is outstanding.
    setInterval(()=>{renderStatus();invalidate();},60000);
  }
  return {init,draw,countryFill,show,validGeometry,drawableGeometry,refresh};
})();
