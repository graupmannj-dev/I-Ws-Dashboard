/* Measured overlays. Independent of historical report-date controls. */
window.AtlasLayers = (() => {
  'use strict';
  const definitions = {
    aircraft: ['ADS-B aircraft', '#70d9ff'], ships: ['AIS vessels', '#64e4c0'],
    airspace: ['Airspace restrictions', '#ffab62'], maritime: ['Maritime restrictions', '#db9aff'],
    advisories: ['US travel advisories', '#edc852'], embassies: ['US embassy status', '#ef879b']
  };
  const advisoryColors = {1:'#57c99b', 2:'#edc852', 3:'#f3a348', 4:'#f06570'};
  const aliases = {'United States of America':'United States', 'Dem. Rep. Congo':'Democratic Republic of the Congo',
    'Central African Rep.':'Central African Republic', 'Dominican Rep.':'Dominican Republic',
    'S. Sudan':'South Sudan', 'Eq. Guinea':'Equatorial Guinea', 'Bosnia and Herz.':'Bosnia and Herzegovina',
    'eSwatini':'Eswatini', 'Czechia':'Czech Republic', 'Timor-Leste':'Timor-Leste (East Timor)'};
  let payload = {layers:{}}, invalidate = () => {}, endpoint = 'layers.json', failed = false;
  const histories = new Map();
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const validPoint = r => Number.isFinite(r.lon) && Number.isFinite(r.lat) && Math.abs(r.lon)<=180 && Math.abs(r.lat)<=90;
  const enabled = key => $('layer-'+key)?.checked;
  function recent(stamp, seconds) {
    const age = (Date.now()-Date.parse(stamp))/1000;
    return Number.isFinite(age) && age >= -60 && age <= seconds;
  }
  function validGeometry(geometry) {
    if(!geometry)return true;
    if(!['Polygon','MultiPolygon','LineString'].includes(geometry.type))return false;
    let count=0;
    function walk(points) {
      if(!Array.isArray(points)||!points.length||++count>100000)return false;
      if(typeof points[0]==='number')return points.length===2&&validPoint({lon:points[0],lat:points[1]});
      return points.every(walk);
    }
    return walk(geometry.coordinates);
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
      (!validPoint(row)&&!row.geometry&&key!=='advisories'?'<p>No precise geometry supplied; listed without an invented map location.</p>':'')+source;
    panel.querySelector('button').onclick=()=>{panel.hidden=true;};
  }
  function renderStatus() {
    const container=$('layerStatus');container.replaceChildren();
    for(const [key,[title,color]] of Object.entries(definitions)) {
      if(!enabled(key))continue;
      const layer=payload.layers[key], rows=records(key);
      const block=document.createElement('div');block.className='feed-status';
      const fresh=layer&&recent(layer.checked_at,key==='aircraft'||key==='ships'?600:172800);
      const status=failed?'Feed unavailable':!layer?'Not connected':!fresh&&layer.checked_at?'Stale — measurements hidden':String(layer.status).replaceAll('_',' ');
      const heading=document.createElement('strong');heading.style.color=color;
      heading.textContent=title+' · '+rows.length+' active';block.append(heading);
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
        if(row.geometry && ['airspace','maritime'].includes(key))geometry(ctx,{geometry:row.geometry},color+'55',color);
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
  async function refresh() {
    try {
      const response=await fetch(endpoint,{cache:'no-store',signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw Error('Feed request failed');
      const next=await response.json();
      if(next.version!==1 || !next.layers || typeof next.layers!=='object')throw Error('Invalid layer schema');
      for(const layer of Object.values(next.layers))if(!Array.isArray(layer.records))throw Error('Invalid records');
      payload=next;failed=false;
      for(const key of ['aircraft','ships'])for(const row of records(key)) {
        const id=key+':'+row.id, history=histories.get(id)||[];
        if(history.at(-1)?.observed_at!==row.observed_at)history.push(row);
        histories.set(id,history.filter(r=>recent(r.observed_at,600)).slice(-60));
      }
    } catch(_) {failed=true;}
    for(const [key,history] of histories)if(!history.some(r=>recent(r.observed_at,600)))histories.delete(key);
    renderStatus();invalidate();
  }
  function init(config,onChange) {
    endpoint=config?.url||'layers.json';invalidate=onChange;
    const parent=$('measuredLayerControls');
    for(const [key,[title,color]] of Object.entries(definitions)) {
      const label=document.createElement('label');label.className='toggle-row';
      label.innerHTML='<input type="checkbox" id="layer-'+key+'"><span>'+title+'</span><i class="legend-swatch" style="background:'+color+'"></i>';
      label.querySelector('input').onchange=()=>{renderStatus();invalidate();};parent.append(label);
    }
    refresh().finally(()=>setTimeout(function poll(){refresh().finally(()=>setTimeout(poll,30000));},30000));
    // Aging applies even while a request is outstanding.
    setInterval(()=>{renderStatus();invalidate();},60000);
  }
  return {init,draw,countryFill,show};
})();
