from pathlib import Path
p=Path(__file__).resolve().parent/'aiba_v4.py'
s=p.read_text()
s=s.replace('<div class="kpis" id="kpis"></div><div class="columns">', '<div class="kpis" id="kpis"></div><section class="panel pad" style="margin-bottom:16px" id="earlySection" aria-label="Pre-convergence signals"></section><div class="columns">')
s=s.replace('const D=JSON.parse(document.getElementById(\'payload\').textContent);let selected=null, filter=\'all\';', "const D=JSON.parse(document.getElementById('payload').textContent);let selected=null, filter='all';")
marker='function init(){el(\'asof\')'
assert marker in s
extra=r'''function renderEarly(){const box=el('earlySection');if(!box)return;const P=D.preconvergence||{};const f=P.flags||[];let h=`<div class="pair"><div><div class="eyebrow">AIBA / PRIOR-CONVERGENCE</div><h2 style="margin:5px 0">Quiet divergences and sequence anomalies</h2></div><span class="tag">${safe(P.data_start||'—')} – ${safe(P.data_end||'—')}</span></div><p class="small">Signal discrepancies are investigatory cues, not predicted attack dates. Historical forecast contracts must match their stated outcome. This pane may be older than the latest hotspot evidence.</p>`;h+=`<div class="inline"><span class="tag">${safe(P.coverage?.dated_rows||0)} historical paired dates</span><span class="tag">${safe(P.coverage?.scorable_days||0)} dates with trailing baseline</span><span class="tag">${safe(f.length)} quiet-divergence flags</span></div>`;h+=f.map(x=>`<details style="border-top:1px solid var(--line);padding:12px 0;margin-top:10px"><summary style="cursor:pointer;color:var(--accent)">${safe(x.date)} · ${safe(x.signal)}</summary><div class="small" style="padding-top:9px">Attention robust surprise: ${safe(x.attention_robust_z)}σ; associated invasion-contract price change: ${safe(x.market_change_pp)} percentage points.</div><p class="small">${safe(x.causal_warning)} ${safe(x.independence)}.</p><p class="small">What to verify: ${safe(x.next)}</p><div class="inline">${(x.source_urls||[]).filter(u=>u.startsWith('https://')).map(u=>`<a href="${safe(u)}" target="_blank" rel="noreferrer">Source ↗</a>`).join(' ')}</div></details>`).join('');h+=`<p class="small" style="margin-top:14px"><b>Unassessed:</b> Unexpected source ordering, flight-versus-diplomatic latency and spatial risk propagation still need paired timestamped time series; these are not silently coded as normal.</p>`;box.innerHTML=h}
'''
s=s.replace(marker,extra+marker)
s=s.replace('el(\'q\').addEventListener(\'input\',renderList);init();', "el('q').addEventListener('input',renderList);renderEarly();init();")
s=s.replace('    # Filter exact matches by country pair aliases?', "    early_path=DATA/'preconvergence.json'\n    early=json.loads(early_path.read_text(encoding='utf-8')) if early_path.exists() else {}\n    # Filter exact matches by country pair aliases?")
s=s.replace('"asof":asof.isoformat(),"hotspots":candidates,', '"asof":asof.isoformat(),"hotspots":candidates,"preconvergence":early,')
if 'def run_data_collection(' in s: raise ValueError('Already patched?')
p.write_text(s)
print('dashboard patched')
