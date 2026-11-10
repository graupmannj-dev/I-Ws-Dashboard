#!/usr/bin/env python3
"""AIBA v4: global, open-source hotspot *nomination* engine.

Use downloaded GDELT 1.0 Daily Event CSV.ZIP files to surface previously
unlisted country pairs and country-level activity changes. GDELT consists
of media-coded events: its anomalies are DISCOVERY leads, not independent
corroboration of military preparations or probabilities of war.

The included standalone HTML is a dated snapshot. Re-run this script on a
network-enabled computer to refresh the GDELT collection and dashboard.
"""
import argparse
import csv
import datetime as dt
import html
import io
import json
import math
import pathlib
import sys
import urllib.request
import zipfile
from collections import Counter, defaultdict
from scripts.gdelt_event_profile import ROOT_LABEL, classify_actors

HERE=pathlib.Path(__file__).resolve().parent
CACHE=HERE/'cache'
DATA=HERE/'data'
OUT=HERE/'output'
GDELT_ROOT='https://data.gdeltproject.org/events/'
# Root scope and actor-case assignment must match the six-root shadow profile.
# GDELT actor country codes mostly resemble ISO alpha-3 but not guaranteed.
COUNTRIES={'ETH':'Ethiopia','ERI':'Eritrea','SUD':'Sudan','PAK':'Pakistan','AFG':'Afghanistan','DRC':'DR Congo','RWA':'Rwanda','THA':'Thailand','CAM':'Cambodia','RUS':'Russia','USA':'United States','IRN':'Iran','CHN':'China','TWN':'Taiwan','PRK':'North Korea','KOR':'South Korea','UKR':'Ukraine','ISR':'Israel','IND':'India','VEN':'Venezuela','GUY':'Guyana','MYA':'Myanmar','MLI':'Mali','BFI':'Burkina Faso'}

def iso_date(s): return dt.date.fromisoformat(s)
def dates_back(last, n):
    return [last-dt.timedelta(days=i) for i in range(n-1,-1,-1)]

def archive_rows(path):
    """Validate the entire archive, including CRC, schema and nonempty content."""
    expected = path.name.removesuffix('.zip')
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != [expected]:
            raise ValueError('Unexpected archive member')
        count = 0
        with archive.open(expected) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding='utf-8', errors='strict'), delimiter='\t'):
                if len(row) not in (57, 58) or not row[0].isdigit():
                    raise ValueError('Invalid GDELT record schema')
                dt.datetime.strptime(row[1], '%Y%m%d')
                if (not row[28].isdigit() and row[26:29] != ['---', '---', '--']) or row[29] not in ('1', '2', '3', '4'):
                    raise ValueError('Invalid CAMEO fields')
                count += 1
                yield row
        if count == 0:
            raise ValueError('Empty archive')


def download_days(asof, days, cache_dir=CACHE):
    cache_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for day in dates_back(asof, days):
        stamp = day.strftime('%Y%m%d')
        path = cache_dir / f'{stamp}.export.CSV.zip'
        try:
            if path.exists():
                try:
                    for _ in archive_rows(path): pass
                    continue
                except Exception:
                    path.unlink()
            request = urllib.request.Request(f'{GDELT_ROOT}{path.name}', headers={'User-Agent': 'AIBA/5.0 public OSINT research'})
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read()
            # A temporary directory keeps the expected archive basename for validation.
            import tempfile
            with tempfile.TemporaryDirectory(dir=cache_dir) as tmp:
                candidate = pathlib.Path(tmp) / path.name
                candidate.write_bytes(content)
                for _ in archive_rows(candidate): pass
                candidate.replace(path)
            results.append((stamp, len(content)))
            print(f'Downloaded {stamp}: {len(content)/1e6:.1f} MB', file=sys.stderr)
        except Exception as exc:
            print(f'NO DATA {stamp}: {type(exc).__name__} {exc}', file=sys.stderr)
    return results


def ingest(cache_dir=CACHE, asof=None, audit=None):
    """Commit daily counts only after every row and ZIP CRC validates."""
    records=Counter(); daily_totals=Counter(); roots=defaultdict(Counter); availability=set(); samples=defaultdict(list)
    for path in sorted(cache_dir.glob('*.export.CSV.zip')):
        try:
            day=dt.datetime.strptime(path.name[:8], '%Y%m%d').date()
            if asof and day not in dates_back(asof, 35): continue
            local=Counter(); local_roots=defaultdict(Counter); local_samples=defaultdict(list); total=0; row_count=0; uncoded=0
            for row in archive_rows(path):
                row_count += 1
                root=row[28].strip()
                if root == '--': uncoded += 1
                if root not in ROOT_LABEL: continue
                total += 1
                key=classify_actors(root,row[7],row[17])
                if key is None: continue
                local[(day,key)] += 1
                local_roots[key][root] += 1
                if len(local_samples[key])<8 and row[-1].startswith(('https://','http://')):
                    local_samples[key].append(row[-1])
            if total <= 0: raise ValueError('No usable coercion/conflict events')
            records.update(local); daily_totals[day]=total
            for key, counts in local_roots.items(): roots[key].update(counts)
            for key, urls in local_samples.items(): samples[key]=(samples[key]+urls)[:8]
            availability.add(day)
            if audit is not None: audit[day.isoformat()]={"rows":row_count,"uncoded_rows":uncoded,"selected_events":total}
        except Exception as exc:
            print(f'IGNORED {path.name}: {exc}',file=sys.stderr)
    return records,daily_totals,roots,sorted(availability),samples

def beta_binomial_sf(y, n, a, b):
    """Pr(Y>=y) under Beta-Binomial(n,a,b). Uses scipy if available;
    fallback exact log-sum-exp for modest n."""
    if y<=0:return 1.0
    if n<y:return 0.0
    try:
        from scipy.stats import betabinom
        return float(betabinom.sf(y-1,n,a,b))
    except ImportError:
        def lg(x):return math.lgamma(x)
        def logp(k):return (lg(n+1)-lg(k+1)-lg(n-k+1)+lg(a+k)+lg(b+n-k)-lg(a+b+n)-lg(a)-lg(b)+lg(a+b))
        values=[logp(k) for k in range(y,n+1)]
        if not values:return 0.0
        top=max(values)
        return min(1.0, math.exp(top)*sum(math.exp(v-top) for v in values))

def analyze(records,daily_totals,roots,available,samples,asof,baseline_days=28,window_days=7,minimum=9):
    """Discover country-pair media-event-share anomalies, no fixed theater list.

    Use effective-sample discount of 5% to avoid wildly overconfident
    Bayesian tail probabilities from correlated news-coded events.
    This 5% factor is a conservative HEURISTIC, not calibrated.
    """
    available=set(available)
    recent=dates_back(asof,window_days)
    baseline=dates_back(asof-dt.timedelta(days=window_days),baseline_days)
    completeness={'recent_days':sum(x in available for x in recent),
                  'baseline_days':sum(x in available for x in baseline)}
    if completeness['recent_days']<window_days or completeness['baseline_days']<baseline_days:
        return [], completeness
    total_base=sum(daily_totals.get(d,0) for d in baseline)
    total_recent=sum(daily_totals.get(d,0) for d in recent)
    if total_base<=0 or total_recent<=0:return [],completeness
    all_keys=set(k for d,k in records)
    entries=[]
    for key in all_keys:
        a=sum(records.get((d,key),0) for d in baseline)
        b=sum(records.get((d,key),0) for d in recent)
        if b<minimum:continue
        p0=(a+.5)/(total_base+20.)
        p1=(b+.5)/(total_recent+20.)
        ratio=p1/p0
        # downstream media dependence is substantial; downsample effective count
        eff=.05
        y=max(0,round(b*eff))
        n=max(y,round(total_recent*eff))
        alpha=.5+a*eff; beta=10+max(0,total_base-a)*eff
        tail=beta_binomial_sf(y,n,alpha,beta)
        # Nomination only, never an automated red/critical alert
        if ratio<1.65 or tail>0.025:continue
        pair=key[1]
        label=('–'.join(COUNTRIES.get(c,c) for c in pair) if key[0]=='BILAT'
               else f'{COUNTRIES.get(pair[0],pair[0])} (domestic activity)')
        entries.append({
            'id':'gdelt_'+key[0]+'_'+'_'.join(pair),'name':label,'region':'Global / discovered',
            'scope':'Algorithmic lead','scenario':('Possible emerging bilateral confrontation' if key[0]=='BILAT' else 'Possible change in domestic violent-event activity'),
            'state':'Unverified media anomaly','trajectory':'Increasing coverage share',
            'horizon':'Unestimated','confidence':'Low until corroborated','asof':asof.isoformat(),
            'location':label,
            'summary':f'GDELT-coded coercive/conflict events involving {label} increased from {a} in the preceding {baseline_days} days to {b} in the latest {window_days} days. These periods are unequal and the relevant comparison is coverage-normalized share, not raw totals.',
            'analysis':f'Media-coded share ratio {ratio:.1f}×; exploratory overdispersed Bayesian tail {tail:.3g}. This is an attention/event-coding anomaly, NOT evidence of imminent hostilities, independent confirmation or a probability of war.',
            'next':'Check event identities, dates, official positions and independent commercial/institutional actions before promoting to Watch.',
            'alternatives':'News-volume shifts, recurring event duplication, source selection, and domestic events mislabeled as interstate may explain the anomaly.',
            'signals':[{'date':asof.isoformat(),'category':'Media-coded event data','title':'GDELT bilateral anomaly','assessment':'Automated nomination only','details':f'{b} events latest {window_days} days; {a} previous {baseline_days} days. Coverage share ratio {ratio:.2f}. Bayesian tail {tail:.4g}; algorithm not calibrated for real-world conflict onset.','source':'GDELT daily event files','url':'https://data.gdeltproject.org/events/','root':'GDELT event aggregation'}],
            'aiba_gaps':['Independent official reporting','Commercial behavior','Humanitarian protective actions'],
            'metrics':{'recent':b,'baseline':a,'ratio':round(ratio,3),'tail':round(tail,5),'root_breakdown':dict(roots.get(key,{})),'coverage_total_recent':total_recent,'coverage_total_baseline':total_base},
            'sample_article_urls':samples.get(key,[])[:6]
        })
    entries.sort(key=lambda x:(x['metrics']['tail'],-x['metrics']['recent']))
    return entries[:30],completeness

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AIBA 5.0 | Global Hotspot Discovery</title>
<style>
:root{color-scheme:dark;--bg:#10131a;--panel:#1b202b;--panel2:#232a37;--text:#e6ebf4;--muted:#a2adbf;--line:#354052;--accent:#d7aa6b;--red:#dc7779;--amber:#dfb362;--teal:#77c9b1;--blue:#85abd9}*{box-sizing:border-box}body{font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:var(--bg);color:var(--text)}button,input,select{font:inherit}a{color:#b3d2ff}a:hover{text-decoration:underline}.wrap{max-width:1460px;margin:auto;padding:25px 24px 54px}.mast{display:flex;align-items:flex-start;gap:18px;justify-content:space-between;flex-wrap:wrap}.eyebrow{color:var(--accent);font-weight:700;letter-spacing:2px;font-size:11px;text-transform:uppercase}h1{font-size:30px;letter-spacing:-.7px;margin:6px 0 1px}h2{font-size:19px;margin:0 0 10px}h3{font-size:15px;margin:0 0 6px}.small,.sub{font-size:12px;color:var(--muted)}.sub{margin:2px 0 14px}.meta{border:1px solid var(--line);border-radius:9px;padding:12px 15px;min-width:220px;background:var(--panel)}.meta strong{font-size:14px;display:block;margin-top:3px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.kpi{border:1px solid var(--line);border-radius:11px;padding:16px;background:var(--panel)}.kpi b{display:block;font-size:28px;margin:5px 0 0}.kpi small{color:var(--muted)}.notice{border:1px solid #634a34;background:#2c261e;padding:13px 15px;border-radius:10px;margin:16px 0;color:#eddbc5}.columns{display:grid;grid-template-columns:380px minmax(0,1fr);gap:15px;align-items:start}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}.pad{padding:16px}.side{position:sticky;top:10px;max-height:calc(100vh - 22px);overflow:auto}.filters{display:flex;gap:7px;flex-wrap:wrap;padding-bottom:12px}.filter{border:1px solid var(--line);color:var(--muted);border-radius:7px;background:transparent;padding:7px 10px;cursor:pointer}.filter.active{color:#13151b;background:var(--accent);border-color:var(--accent);font-weight:700}.search{width:100%;background:var(--panel2);border:1px solid var(--line);padding:10px;border-radius:8px;color:var(--text);outline:0;margin-bottom:12px}.candidate{display:block;background:none;border:0;border-top:1px solid var(--line);color:inherit;width:100%;text-align:left;padding:13px 16px;cursor:pointer}.candidate:hover,.candidate.active{background:#303847}.candidate strong{display:block;font-size:14px}.status{font-size:11px;font-weight:700;border-radius:999px;padding:3px 8px;display:inline-block;margin-top:6px;border:1px solid}.risk{color:var(--red);border-color:#815255;background:#462c31}.watch{color:var(--amber);border-color:#806a45;background:#3b3426}.stable{color:var(--teal);border-color:#42675f;background:#233932}.unsure{color:#b5bdd5;border-color:#59637c;background:#323848}.inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.tag{display:inline-block;border:1px solid var(--line);border-radius:5px;padding:3px 7px;color:var(--muted);font-size:11px}.topline{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.titleline{font-size:25px;font-weight:750;letter-spacing:-.5px}.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.slot{padding:12px;background:var(--panel2);border-radius:8px}.slot strong{font-size:14px;display:block;margin-top:4px}.slot small{color:var(--muted)}.section{border-top:1px solid var(--line);padding-top:15px;margin-top:16px}.section p{margin:7px 0}.signal{padding:12px 0;border-bottom:1px solid var(--line)}.signal:last-child{border:0}.sigdate{color:var(--muted);font-variant-numeric:tabular-nums;font-size:11px}.signal a{font-size:12px}.signal .badge{font-size:10px;color:var(--muted);background:#303849;border:1px solid var(--line);padding:2px 5px;border-radius:5px}.pair{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.footer{margin-top:27px;border-top:1px solid var(--line);padding:22px 0;color:var(--muted);font-size:12px}.point{color:var(--accent);margin-right:5px}.method{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.method article{border:1px solid var(--line);background:var(--panel);padding:15px;border-radius:10px}.empty{padding:20px;color:var(--muted);text-align:center}.dataexport{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:7px;padding:7px 10px;cursor:pointer}.collapsible{background:var(--panel2);border:1px solid var(--line);color:var(--text);padding:10px;width:100%;text-align:left;border-radius:8px;cursor:pointer}.hidden{display:none!important}@media(max-width:920px){.columns{grid-template-columns:1fr}.side{position:static;max-height:420px}.kpis{grid-template-columns:repeat(2,1fr)}.method{grid-template-columns:1fr}}@media(max-width:500px){.wrap{padding:18px 13px}.kpis{gap:7px}.kpi{padding:12px}.titleline{font-size:20px}.grid2{grid-template-columns:1fr}}
</style></head><body><div class="wrap"><header class="mast"><div><div class="eyebrow">AIBA / I&W · Global discovery and fusion</div><h1>Global Early Warning</h1><p class="sub">Dynamic hotspot nominations · Existing watch retained · Evidence, uncertainty, and counter-signals preserved</p></div><div class="meta"><span class="small">LAST LOCAL GENERATION</span><strong id="asof">—</strong><span class="small" id="collection">No automated feed data</span></div></header>
<div class="notice" id="notice">Dated offline snapshot. Algorithmic discovery leads are unverified until corroborated. This file does not fetch new information while open.</div>
<div class="kpis" id="kpis"></div><section class="panel pad" style="margin-bottom:16px" id="earlySection" aria-label="Pre-convergence signals"></section><div class="columns"><aside class="panel side"><div class="pad"><h2>Hotspot nomination queue</h2><p class="small">Search worldwide candidates. Newly discovered leads never automatically become critical alerts.</p><input class="search" id="q" aria-label="Search hotspots" placeholder="Search region, scenario, country…"><div class="filters" id="filters"></div><div class="small" id="resultCount"></div></div><div id="candidateList"></div></aside><main class="panel pad" id="detail"></main></div>
<section class="section" style="margin-top:20px"><h2>Discovery method · Why this is different</h2><div class="method"><article><h3>1 · Wide-area detection</h3>Open-data changes in country pairs and conflict-event locations nominate candidates without requiring the region to exist on a predefined watchlist. Raw GDELT counts measure media-coded activity, <b>not war probability</b>.</article><article><h3>2 · Source independence and costly behavior</h3>Diplomatic, military, corporate, humanitarian, shipping, insurance, connectivity, and unofficial signals are grouped by their originating events. Derivative headlines do not count as independent confirmations.</article><article><h3>3 · Dynamic regimes and silent divergence</h3>Display absolute severity and novel change separately. Flag shifts in forecast, commercial, or civilian behavior while conventional signals remain flat. Record unknowns as <b>not collected</b>, never as negative indicators.</article></div></section>
<div class="footer"><div>Global Discovery v5.0 · Local snapshot generator · Not a live hosted service · No numerical probability of conflict claimed</div><div style="margin-top:6px">Collection: GDELT 1.0 daily ZIP files (optional) + manually source-verified watch cases. Source and metric definitions are included in the downloaded package.</div></div></div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const D=JSON.parse(document.getElementById('payload').textContent);let selected=null, filter='all';
const el=id=>document.getElementById(id);const safe=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;');
const safeUrl=u=>/^https?:\/\//i.test(String(u))?safe(u):'#';
const stateClass=(s)=>/active conflict|hybrid warning|escalation watch/i.test(s)?'risk':/tension|fragile|activity|coercion/i.test(s)?'watch':/media anomaly/i.test(s)?'unsure':'stable';
function kpi(label,n,extra){return `<div class="kpi"><small>${safe(label)}</small><b>${safe(n)}</b><small>${safe(extra)}</small></div>`}
function renderEarly(){const box=el('earlySection');if(!box)return;const P=D.preconvergence||{};const f=P.flags||[];let h=`<div class="pair"><div><div class="eyebrow">AIBA / PRIOR-CONVERGENCE</div><h2 style="margin:5px 0">Quiet divergences and sequence anomalies</h2></div><span class="tag">${safe(P.data_start||'—')} – ${safe(P.data_end||'—')}</span></div><p class="small">Signal discrepancies are investigatory cues, not predicted attack dates. Historical forecast contracts must match their stated outcome. This pane may be older than the latest hotspot evidence.</p>`;h+=`<div class="inline"><span class="tag">${safe(P.coverage?.dated_rows||0)} historical paired dates</span><span class="tag">${safe(P.coverage?.scorable_days||0)} dates with trailing baseline</span><span class="tag">${safe(f.length)} quiet-divergence flags</span></div>`;h+=f.map(x=>`<details style="border-top:1px solid var(--line);padding:12px 0;margin-top:10px"><summary style="cursor:pointer;color:var(--accent)">${safe(x.date)} · ${safe(x.signal)}</summary><div class="small" style="padding-top:9px">Attention robust surprise: ${safe(x.attention_robust_z)}σ; associated invasion-contract price change: ${safe(x.market_change_pp)} percentage points.</div><p class="small">${safe(x.causal_warning)} ${safe(x.independence)}.</p><p class="small">What to verify: ${safe(x.next)}</p><div class="inline">${(x.source_urls||[]).filter(u=>u.startsWith('https://')).map(u=>`<a href="${safe(u)}" target="_blank" rel="noreferrer">Source ↗</a>`).join(' ')}</div></details>`).join('');const W=P.live_attention||{};const wr=W.results?.recent_flags||[];h+=`<div class="section"><h3>Recent public-attention anomalies · source coverage ${safe(W.completeness?.success||0)}/${safe(W.completeness?.attempted||0)}</h3><p class="small">Wikimedia attention-only flags are not forecast divergence unless matched with a dated prediction contract. Source requested through ${safe(W.requested_through||'not fetched')}.</p>${wr.length?wr.slice(-10).map(x=>`<div class="signal"><strong>${safe(x.date)} · ${safe(x.name)}</strong><p class="small">Attention surprise ${safe(x.robust_z)}σ · ${safe(x.interpretation)}</p></div>`).join(''):'<p class="small">No attention flags shown. Consult coverage below; missing observations are not normal readings.</p>'}</div>`;h+=`<details><summary>Wikimedia collection status</summary><pre>${safe(JSON.stringify(W.pages||{status:W.status},null,2))}</pre></details>`;h+=`<p class="small" style="margin-top:14px"><b>Unassessed:</b> Unexpected source ordering, flight-versus-diplomatic latency and spatial risk propagation still need paired timestamped time series; these are not silently coded as normal.</p>`;box.innerHTML=h}
function init(){el('asof').textContent=D.generated;el('collection').textContent=D.collection_summary;el('notice').textContent=D.notice;const age=(Date.now()-Date.parse(D.generated))/86400000;if(age>2)el('notice').textContent+=' STALE BUILD: '+Math.floor(age)+' days since generation. Collection may have failed; check Actions.';const standing=D.hotspots.filter(h=>h.scope==='Standing watch').length;const newFound=D.hotspots.filter(h=>h.scope==='New discovery').length;const algorithmic=D.hotspots.filter(h=>h.scope==='Algorithmic lead').length;const allSources=D.hotspots.reduce((a,h)=>a+(h.signals||[]).length,0);
el('kpis').innerHTML=kpi('Standing theaters',standing,'Prior watch preserved')+kpi('Curated watch candidates',newFound,'Added from global scan')+kpi('Algorithmic unverified leads',algorithmic,'Only when GDELT input complete')+kpi('Dated supporting records',allSources,'Not all independent');el('filters').innerHTML=[['all','All'],['New discovery','New candidates'],['Standing watch','Standing'],['Algorithmic lead','Algorithmic']].map(([v,n])=>`<button class="filter ${v===filter?'active':''}" data-filter="${safe(v)}">${n}</button>`).join('');document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;init()}));renderList()}
function renderList(){let q=el('q').value.toLowerCase().trim();let rows=D.hotspots.filter(h=>(filter==='all'||h.scope===filter)&&((h.name+' '+h.scenario+' '+h.region).toLowerCase().includes(q)));el('resultCount').textContent=`${rows.length} matching hotspots`;el('candidateList').innerHTML=rows.map(h=>`<button class="candidate ${h.id===selected?'active':''}" data-id="${safe(h.id)}"><strong>${safe(h.name)}</strong><div class="inline"><span class="status ${stateClass(h.state)}">${safe(h.state)}</span><span class="tag">${safe(h.scope)}</span></div><div class="small" style="margin-top:6px">${safe(h.scenario)}</div></button>`).join('')||'<div class="empty">No matching candidates</div>';document.querySelectorAll('[data-id]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.id)));if(!selected||!D.hotspots.some(h=>h.id===selected)){if(rows.length)selected=rows[0].id;else selected=null;}if(selected&&rows.some(h=>h.id===selected))drawDetail();else el('detail').innerHTML='<div class="empty">Select a hotspot.</div>'}
function show(id){selected=id;renderList()}
function drawDetail(){const h=D.hotspots.find(x=>x.id===selected);if(!h)return;const daysOld=Math.floor((Date.parse(D.asof+'T00:00:00Z')-Date.parse(h.asof+'T00:00:00Z'))/86400000);const ev=[...(h.signals||[])].sort((a,b)=>b.date.localeCompare(a.date));const roots=[...new Set(ev.map(s=>s.root))];const known=(h.signals||[]).filter(s=>/Confirmed|Observed|Reported|Warning|specific|Counter/i.test(s.assessment)).length;
let result=`<div class="topline"><div><div class="eyebrow">${safe(h.region)} · ${safe(h.scope)}</div><div class="titleline">${safe(h.name)}</div><p class="sub">${safe(h.scenario)}</p></div><span class="status ${stateClass(h.state)}">${safe(h.state)}</span></div>${Math.max(daysOld,Math.floor((Date.now()-Date.parse(h.asof+'T00:00:00Z'))/86400000))>7?`<p class="notice">Dossier sources are ${safe(daysOld)} days old. The GDELT automation does not automatically reconfirm this narrative assessment; check original sources.</p>`:''}<p class="small">${safe(h.verification_status||'Provisional algorithmic anomaly; requires corroboration')}</p><p>${safe(h.summary)}</p><div class="grid2"><div class="slot"><small>TRAJECTORY</small><strong>${safe(h.trajectory)}</strong></div><div class="slot"><small>RELEVANT HORIZON</small><strong>${safe(h.horizon)}</strong></div><div class="slot"><small>EVIDENCE CONFIDENCE</small><strong>${safe(h.confidence)}</strong></div><div class="slot"><small>LATEST SOURCE OBSERVATION</small><strong>${safe(h.asof)}</strong></div></div><div class="section"><h3>Integrated analytic judgment</h3><p>${safe(h.analysis)}</p><h3 style="margin-top:13px">Competing interpretation</h3><p>${safe(h.alternatives)}</p><h3 style="margin-top:13px">What would change the assessment?</h3><p>${safe(h.next)}</p></div><div class="section"><h3>Evidence chronology · ${ev.length} dated observations</h3><p class="small">${roots.length} reported source-root group(s). Same underlying claims should not be counted multiple times.</p>`;
result+=ev.map(s=>`<div class="signal"><div class="pair"><span class="sigdate">${safe(s.date)} · ${safe(s.category)}</span><span class="badge">${safe(s.assessment)}</span></div><div style="font-weight:650;margin:5px 0">${safe(s.title)}</div><p class="small" style="font-size:13px">${safe(s.details)}</p><div class="small">Origin: ${safe(s.root)} · <a href="${safeUrl(s.url)}" target="_blank" rel="noreferrer">${safe(s.source)} ↗</a></div></div>`).join('');result+='</div>';
const connected=D.hotspots.filter(o=>o.id!==h.id&&o.region===h.region);
if(connected.length){result+=`<div class="section"><h3>Spillover / connected hotspot network</h3><p class="small">Shared regional geography invites monitoring for spillover, but is not proof that separate incidents are coordinated.</p><div class="inline">${connected.map(o=>`<button class="dataexport" data-linked="${safe(o.id)}">${safe(o.name)} ↗</button>`).join('')}</div></div>`}
result+=`<div class="section"><h3>Uncollected AIBA / additional validation</h3><p class="small">These are data gaps, <b>not reassuring null readings</b>.</p><div class="inline">${(h.aiba_gaps||[]).map(x=>`<span class="tag">${safe(x)}</span>`).join('')}</div></div>`;
if(h.metrics){result+=`<div class="section"><h3>Algorithmic screening statistics (discovery only)</h3><p>${safe(h.metrics.recent)} GDELT-coded events in recent window versus ${safe(h.metrics.baseline)} in earlier baseline period; normalized media-event share ratio ${safe(h.metrics.ratio)}×. Exploratory posterior predictive upper tail ${safe(h.metrics.tail)}. <b>These are not estimates of the probability of a military attack.</b></p></div>`}
result+=`<div class="section"><button class="dataexport" id="copy">Copy hotspot evidence record</button><span class="small" id="copyFeedback" style="margin-left:10px"></span></div>`;el('detail').innerHTML=result;document.querySelectorAll('[data-linked]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.linked)));el('copy').addEventListener('click',()=>{const text=JSON.stringify(h,null,2);if(navigator.clipboard){navigator.clipboard.writeText(text).then(()=>el('copyFeedback').textContent='Copied').catch(()=>el('copyFeedback').textContent='Clipboard unavailable')}else el('copyFeedback').textContent='Clipboard unavailable in this viewer';})}
el('q').addEventListener('input',renderList);renderEarly();init();
</script></body></html>'''

def build(out=OUT, asof=None, cache=CACHE, offline=True, baseline_days=28,window_days=7, strict=False, live_attention=None, suppress_incomplete_discovery=False):
    out.mkdir(parents=True,exist_ok=True)
    asof=asof or dt.date.today()
    seed=json.loads((DATA/'verified_hotspots.json').read_text())
    audit={}
    records,totals,roots,avail,samples=ingest(cache, asof,audit)
    discovery,completeness=analyze(records,totals,roots,avail,samples,asof,baseline_days,window_days)
    complete = (completeness['recent_days'] == window_days and completeness['baseline_days'] == baseline_days)
    if suppress_incomplete_discovery and not complete:
        # Missing source days cannot be interpreted as zero events or normal conditions.
        discovery = []
    if strict and (completeness['recent_days'] != window_days or completeness['baseline_days'] != baseline_days):
        raise ValueError('REFUSING TO PUBLISH: require all 7 recent and 28 baseline valid daily archives')
    early_path=DATA/'preconvergence.json'
    early=json.loads(early_path.read_text(encoding='utf-8')) if early_path.exists() else {}
    early['live_attention']=live_attention or {'pages':{}, 'results':{}, 'completeness':{'success':0,'attempted':0}, 'status':'not collected in this build'}
    for item in seed:
        item['verification_status']='Curated source-linked assessment; not independently reverified by this build'
        item['source_age_days']=(asof-dt.date.fromisoformat(item['asof'])).days
    # Filter exact matches by country pair aliases? Prefer preserving same geography if source classification differs;
    # seed matches kept independent with discovery lead label, no automatic merge.
    candidates=seed+discovery
    payload={"generated":dt.datetime.now().astimezone().isoformat(timespec='seconds'),
             "asof":asof.isoformat(),"hotspots":candidates,"preconvergence":early,
             "collection_summary":f"GDELT: {len(avail)} cached days / {completeness['recent_days']} of {window_days} recent, {completeness['baseline_days']} of {baseline_days} baseline",
             "data_completeness":completeness,
             "gdelt_daily_audit":audit,
             "discovery_status":"scored" if completeness == {"recent_days":7,"baseline_days":28} else "missing_data",
             "notice":("This is a source-linked and dated intelligence snapshot. Country-pair discovery anomalies are provisional media-coded leads, not confirmed military threats. "
                       +( "GDELT scanning is enabled for complete local data." if completeness == {"recent_days":7,"baseline_days":28} else "GDELT discovery unavailable: missing or invalid input days; no inference of normal conditions."))
             }
    (out/'hotspots.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    # protect script tag against JSON injection
    encoded=json.dumps(payload,ensure_ascii=True).replace('</','<\\/')
    (out/'Global_AIBA_4_Watchboard.html').write_text(HTML.replace('__PAYLOAD__',encoded),encoding='utf-8')
    fields=['id','name','region','scope','state','trajectory','scenario','asof','horizon','confidence','source_count','unique_roots']
    with (out/'hotspot_register.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for h in candidates:
            w.writerow({**{k:h.get(k,'') for k in fields},'source_count':len(h.get('signals',[])),'unique_roots':len(set(x['root'] for x in h.get('signals',[])))})
    return payload

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--as-of',default=(dt.datetime.now(dt.timezone.utc).date()-dt.timedelta(days=1)).isoformat(),help='Last COMPLETE UTC day of GDELT collection, YYYY-MM-DD')
    ap.add_argument('--download-days',type=int,default=0,help='Download past N days from public GDELT archive (network required)')
    ap.add_argument('--cache-dir',type=pathlib.Path,default=CACHE)
    ap.add_argument('--output-dir',type=pathlib.Path,default=OUT)
    ap.add_argument('--baseline-days',type=int,default=28)
    args=ap.parse_args();asof=iso_date(args.as_of)
    if args.download_days:download_days(asof,args.download_days,args.cache_dir)
    result=build(args.output_dir,asof,args.cache_dir,baseline_days=args.baseline_days)
    c=result['data_completeness']; print(f'Created: {args.output_dir / "Global_AIBA_4_Watchboard.html"}\n'
         f'{len(result["hotspots"])} hotspots: {sum(h["scope"]=="New discovery" for h in result["hotspots"])} manually discovered; '
         f'{sum(h["scope"]=="Algorithmic lead" for h in result["hotspots"])} data-discovered.\n'
         f'GDELT coverage: recent {c["recent_days"]}/7; baseline {c["baseline_days"]}/{args.baseline_days}.')
if __name__=='__main__':main()
