/* CAIRN source-honest hypothesis viewer. No implied probability calculation. */
(() => {
"use strict";
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = value => {
  try {const u = new URL(value);return u.protocol === "https:" && !u.username && !u.password ? u.href : null;}
  catch {return null;}
};
let rows = [], selected = null;
const labels = {supports:"Supports hypothesis", contradicts:"Contradicts hypothesis",
  context:"Context / explanation",not_assessed:"Direction not reviewed"};
const order = {supports:0,contradicts:1,context:2,not_assessed:3};

function caseLabel(c) {
  const b=c.balance||{};
  return b.direction==="not_assessed" ? "No reviewed directional evidence (analyst-approved)" :
    b.direction==="leans_support" ? "Review balance: leans supporting" :
    b.direction==="leans_contradict" ? "Review balance: leans contradicting" :
    "Review balance: mixed";
}

const machineLabels = {possible_support:"Possible supporting signpost — unverified",
  possible_counter:"Possible counter-indicator — unverified",
  requires_interpretation:"Ambiguous / source reading required", context:"Context only"};

function gdeltSection(c){
  const g=c.gdelt_media_trend||{}, count=g.recent_coded_records;
  if(g.status!=="measured"){
    return '<section class="gdelt-media"><h3>GDELT actor-pair comparison</h3>'+
      '<p class="muted">Not measured: the complete daily event archive or case comparison is unavailable. Missing GDELT is not a zero reading.</p></section>';
  }
  const desc={higher_coded_share:"Higher media-coded share",
    lower_coded_share:"Lower media-coded share",
    equal_coded_share:"Equal media-coded share"}[g.trend]||"Trend unavailable";
  const days=Array.isArray(g.daily_counts)?g.daily_counts.slice(-7):[];
  const daily=days.map(d=>'<span class="gdelt-day"><small>'+escapeHtml(d.date||"")+'</small><strong>'+
    escapeHtml(d.coded_records??"—")+'</strong></span>').join("");
  const u=safeUrl(g.source_url);
  return '<section class="gdelt-media"><h3>GDELT exact actor-pair trend <span class="pill context">Descriptive media-coded data</span></h3>'+
    '<p class="muted">Source through '+escapeHtml(g.source_clock||"unknown")+' · seven complete recent UTC days vs preceding 28 days'+
    ' · actor codes '+escapeHtml((g.matched_actor_pairs||[]).map(x=>x.join("–")).join(", "))+'</p>'+
    '<div class="gdelt-stats"><div><small>Recent coded records (7 days)</small><strong>'+escapeHtml(count??"—")+'</strong></div>'+
    '<div><small>Prior coded records (28 days)</small><strong>'+escapeHtml(g.baseline_coded_records??"—")+'</strong></div>'+
    '<div><small>Recent share / baseline share</small><strong>'+
      escapeHtml((100*g.recent_share).toFixed(3))+'% / '+escapeHtml((100*g.baseline_share).toFixed(3))+'%</strong></div>'+
    '<div><small>Change in media-coded share</small><strong>'+
      escapeHtml(desc)+' ('+escapeHtml(g.media_share_change_percentage_points??"—")+' pp)</strong></div></div>'+
    '<p class="muted">Daily GDELT-coded records, last seven complete UTC days:</p>'+
    '<div class="gdelt-days">'+daily+'</div>'+
    '<p class="muted">This is a directional change in <strong>GDELT media coding</strong>, NOT an analyst-approved direction of the military hypothesis. Coverage, actor coding, duplication, news selection and non-independent reports limit inference. Coded records are not distinct observed events. '+
      (u?'<a href="'+escapeHtml(u)+'" target="_blank" rel="noopener noreferrer">GDELT event archive</a>.':'')+'</p></section>';
}


const interpretationLabels={
  competing_candidates_present:"Candidates associated with both explanations",
  escalation_signposts_nominated:"Escalation-related candidate signposts; alternatives unresolved",
  alternative_signposts_nominated:"Alternative-explanation candidate signposts; escalation not excluded",
  ambiguous_or_context_only:"Only ambiguous/contextual case-associated observations",
  no_matching_case_records_in_window:"No discriminating source-linked observations in this window"
};
function competingSection(c){
  const d=c.competing_screen||{};
  if(d.status!=="screened"){
    return '<section class="competing-screen"><h3>Competing-explanation screen</h3>'+
      '<p class="muted">Source archive is unavailable. No assessment was made; absence of data is not contradictory evidence.</p></section>';
  }
  const summary=d.summary||{},rules=Array.isArray(d.discriminators)?d.discriminators:[],
    coverage=Array.isArray(d.source_baseline_readiness)?d.source_baseline_readiness:[],
    gdelt=d.gdelt_context||{};
  const ruleCard=r=>{
    const links=(Array.isArray(r.sources)?r.sources:[]).map(x=>{
      const url=safeUrl(x.source_url);
      return '<li><span class="auto-meta">'+escapeHtml(x.screening_bucket||"unclassified")+
        ' · '+escapeHtml(x.event_verification||"not verified")+
        ' · '+escapeHtml(x.case_association||"unverified case association")+'</span>'+
        (url?'<a href="'+escapeHtml(url)+'" target="_blank" rel="noopener noreferrer">'+
          escapeHtml(x.title||"Source document")+'</a>':escapeHtml(x.title||"Source document"))+
        '<small>'+escapeHtml(x.source_mode||"unknown source")+
        ' · First ingested '+escapeHtml(x.first_observed_at||"time unavailable")+'</small>'+
        '<p class="muted">'+escapeHtml(x.reason||"Needs review")+'</p></li>';
    }).join("");
    return '<details class="discriminator-rule"><summary><strong>'+escapeHtml(r.label||r.id)+'</strong>'+
      '<span class="pill context">'+escapeHtml(r.candidate_count||0)+' nominated · '+
      escapeHtml(r.ambiguous_count||0)+' ambiguous</span></summary>'+
      '<div class="discriminator-content"><p>'+escapeHtml(r.discriminator||"Evidence discriminator not specified")+'</p>'+
      '<p class="muted">'+escapeHtml(r.status||"unassessed")+
      ' · No match does not mean the observation was absent in the theater.</p>'+
      (links?'<ol class="auto-candidates">'+links+'</ol>':
        '<p class="muted">No matching, source-linked observation in the retained window.</p>')+
      '</div></details>';
  };
  const escalation=rules.filter(r=>r.role==="escalation_candidate").map(ruleCard).join("");
  const alternatives=rules.filter(r=>r.role==="alternative_candidate").map(ruleCard).join("");
  const contextual=rules.filter(r=>r.role==="context_candidate").map(ruleCard).join("");
  const coverageRows=coverage.map(v=>'<tr><td>'+escapeHtml(v.mode||"unknown")+
    '</td><td>'+escapeHtml(v.current_source_status||"unknown")+
    '</td><td>'+escapeHtml(v.comparable_days??"not recorded")+
    '</td><td>'+escapeHtml(v.status==="provider_descriptive_baseline_available"?
      "Provider-level comparison only":"Insufficient for baseline")+'</td></tr>').join("");
  return '<section class="competing-screen" aria-label="Machine hypothesis discriminator workbench">'+
    '<h3>Hypothesis-specific discriminator workbench <span class="pill context">Provisional screening</span></h3>'+
    '<p class="muted">Evaluated '+escapeHtml(d.evaluated_at||"unknown")+
      ' · '+escapeHtml(c.discriminator_window_days||7)+'-day source observation window</p>'+
    '<div class="competing-summary"><div><small>Escalation signpost nominations</small><strong>'+
      escapeHtml(summary.escalation_signpost_nominations||0)+'</strong></div>'+
      '<div><small>Alternative-explanation nominations</small><strong>'+
      escapeHtml(summary.alternative_signpost_nominations||0)+'</strong></div>'+
      '<div><small>Ambiguous / unverified nominations</small><strong>'+
      escapeHtml(summary.ambiguous_signpost_nominations||0)+'</strong></div></div>'+
    '<p><strong>Preliminary pattern:</strong> '+
      escapeHtml(interpretationLabels[summary.competing_pattern]||
        "Unclassified source candidates")+'</p>'+
    '<p class="muted">Case-linked source documents: '+
      escapeHtml(summary.source_documents_case_associated||0)+
      '. Documents and nominations can overlap. Source independence and incident occurrence have not been established.</p>'+
    '<p class="muted"><strong>Competing explanation:</strong> '+
      escapeHtml(d.alternative_explanation||"No documented alternative")+'</p>'+
    '<div class="discriminator-columns"><div><h4>What might distinguish escalation</h4>'+
      escalation+'</div><div><h4>What might favor alternative explanations</h4>'+
      alternatives+'</div></div>'+
    (contextual?'<div class="discriminator-context"><h4>Context and confounding mechanisms (not directional evidence)</h4>'+
      contextual+'</div>':'')+
    '<details class="coverage-details"><summary>Source-health and baseline readiness ('+
      escapeHtml(coverage.length)+ ' source types)</summary>'+
      '<p class="muted">These are provider-wide collection baselines, NOT calibrated event frequencies in this theater. A stale or incomplete baseline is unknown, not negative evidence.</p>'+
      '<table><thead><tr><th>Source</th><th>Health</th><th>Comparable days</th><th>Baseline</th></tr></thead>'+
      '<tbody>'+coverageRows+'</tbody></table></details>'+
    '<p class="muted">GDELT context: '+escapeHtml(gdelt.status||"unavailable")+
      (gdelt.status==="measured"?' · '+escapeHtml(gdelt.media_coded_share_trend||"no trend"):'' )+
      '. It measures reporting share, not preference for the military-escalation hypothesis.</p>'+
    '<p class="muted"><strong>Interpretation boundary:</strong> No automated claim is a validated event, independent corroboration, attack probability, approved directional review, or operational warning. Read the linked primary source and test the stated alternative before changing a judgment.</p>'+
    '</section>';
}
function evidenceHistory(c){
  const a=c.automated_screen||{}, sources=Array.isArray(a.historical_sources)?a.historical_sources:[];
  const n=a.historical_case_roots||0;
  const rendered=sources.map(r=>{
    const u=safeUrl(r.source_url), name=escapeHtml(r.title||"Source record");
    return '<li><span class="auto-meta">'+escapeHtml(machineLabels[r.preliminary_direction]||"Requires verification")+
      ' · '+escapeHtml(r.provenance||"Unknown provenance")+'</span>'+
      (u?'<a href="'+escapeHtml(u)+'" target="_blank" rel="noopener noreferrer">'+name+'</a>':name)+
      '<small>'+escapeHtml(r.source_mode||"Unclassified source")+' · first collected '+
      escapeHtml(r.first_observed_at||"unknown")+'</small>'+
      '<p>'+escapeHtml(r.rationale||"No source-level validation")+'</p></li>';
  }).join("");
  return '<section class="auto-review"><h3>Rolling case-linked evidence history <span class="pill context">Seven-day source archive</span></h3>'+
    '<p class="muted">'+escapeHtml(n)+' distinct case-associated information roots in the latest archived seven days'+
    ' · '+escapeHtml(a.history_window_hours||168)+'-hour window. Association does not establish a real event or independent corroboration.</p>'+
    (sources.length?'<ol class="auto-candidates">'+rendered+'</ol>':
      '<p class="muted">No source-linked observations matched this hypothesis in the retained archive. This does not mean no relevant real-world observations exist.</p>')+
    (a.historical_sources_truncated?'<p class="muted">More case-linked records exist than shown; this list is capped.</p>':'')+
    '<p class="muted">Public analyst-intake records are distinguishable from collector-verified observations and are not assigned supporting direction without reading the original source.</p></section>';
}
function autoSection(c){
  const a=c.automated_screen||{};
  if(a.status!=="screened")
    return '<section class="auto-review"><h3>Automated incoming-evidence screen</h3>'+
      '<p class="muted">Current source snapshot unavailable. No machine review was completed; absence of a result is not negative evidence.</p></section>';
  const candidates=Array.isArray(a.candidates)?a.candidates:[];
  const links=candidates.map(f=>{
    const u=safeUrl(f.source_url);
    const name=escapeHtml(f.title||"Source observation");
    return '<li><span class="auto-meta">'+escapeHtml(machineLabels[f.preliminary_direction]||"Preliminary context")+
      ' · '+escapeHtml(f.match_basis||"unspecified association")+'</span>'+
      (u?'<a href="'+escapeHtml(u)+'" target="_blank" rel="noopener noreferrer">'+name+'</a>':name)+
      '<small>'+escapeHtml(f.provider||"Provider unknown")+' · First ingested '+
      escapeHtml(f.first_observed_at||"unknown")+' · '+escapeHtml(f.source_health||"health unknown")+'</small>'+
      '<p>'+escapeHtml(f.rationale||"No machine-readable discriminator")+'</p></li>';
  }).join("");
  return '<section class="auto-review"><h3>Automated incoming-evidence screen <span class="pill context">Machine preliminary · not analyst approved</span></h3>'+
    '<p class="muted">Screened '+escapeHtml(a.screened_at||"unknown")+
    ' · new-first-ingested lookback: '+escapeHtml(c.automated_window_hours||9)+' hours'+
    ' · source snapshot: '+escapeHtml(c.automated_source_snapshot_at||"not recorded")+'</p>'+
    '<p>'+escapeHtml(a.new_matching_records||0)+' new eligible source roots associated with this hypothesis'+
    ' · '+escapeHtml(a.possible_support||0)+' possible supporting'+
    ' · '+escapeHtml(a.possible_counter||0)+' possible counter'+
    ' · '+escapeHtml(a.unavailable_source_matches||0)+' matches with unavailable source health.</p>'+
    (candidates.length?'<ol class="auto-candidates">'+links+'</ol>':
      '<p class="muted">No new eligible matching records in this window. This is NOT evidence against the hypothesis or evidence of adequate global coverage.</p>')+
    (a.candidates_truncated?'<p class="muted">Additional candidates omitted from this bounded display.</p>':'')+
    '<p class="muted">Text signposts are investigative leads, not validated events, independent corroboration, probabilities or approved warnings. The analyst-reviewed evidence balance below remains separate.</p></section>';
}
function pill(value,cls) {
  return '<span class="pill '+escapeHtml(cls||"")+'">'+escapeHtml(value)+'</span>';
}
function listCases() {
  const query=$("caseSearch").value.trim().toLowerCase(),filter=$("caseFilter").value;
  const shown=rows.filter(c=>(filter==="all" ||
      (filter==="reviewed"&&c.balance.direction!=="not_assessed") ||
      (filter==="unassessed"&&c.balance.direction==="not_assessed") ||
      (filter==="machine"&&(c.automated_screen?.new_matching_records||0)>0) ||
      (filter==="discriminators"&&(
        (c.competing_screen?.summary?.escalation_signpost_nominations||0)+
        (c.competing_screen?.summary?.alternative_signpost_nominations||0)+
        (c.competing_screen?.summary?.ambiguous_signpost_nominations||0)>0))) &&
    (!query||([c.title,c.hypothesis,c.standing_state,...c.families.map(f=>f.title)]
      .join(" ").toLowerCase().includes(query))));
  $("caseCount").textContent=shown.length+" of "+rows.length+" hypotheses";
  const host=$("caseList");host.replaceChildren();
  for(const c of shown) {
    const b=document.createElement("button");b.type="button";
    b.className="case-tile"+(selected===c.id?" active":"");
    b.setAttribute("aria-pressed",selected===c.id?"true":"false");
    const header=document.createElement("strong");header.textContent=c.title||c.id;
    const desc=document.createElement("span");desc.textContent=c.hypothesis||"Hypothesis not specified";
    const meta=document.createElement("small");
    meta.textContent=(c.family_count||0)+" evidence families · "+caseLabel(c)+
      (c.automated_screen?.status==="screened"?" · "+(c.automated_screen.new_matching_records||0)+" new machine-screened roots":"")+
      (c.gdelt_media_trend?.status==="measured"?" · GDELT: "+(
        {higher_coded_share:"higher",lower_coded_share:"lower",equal_coded_share:"unchanged"}[c.gdelt_media_trend.trend]||"measured"
      )+" media-coded share":"")+
      (c.competing_screen?.status==="screened"?" · Discriminator scan complete":"");
    b.append(header,desc,meta);b.addEventListener("click",()=>showCase(c.id));
    host.appendChild(b);
  }
  if(!shown.length){const p=document.createElement("p");p.className="muted";p.textContent="No matching hypotheses.";host.appendChild(p);}
}
function familyCard(f){
  const health=f.health||{}, review=f.review||{},sources=Array.isArray(f.sources)?f.sources:[];
  const direction=f.direction||"not_assessed";
  const providers=sources.map(s=>s.provider).filter(Boolean);
  const reasons=review.rationale?'<p class="review-reason"><strong>Reviewer rationale:</strong> '+escapeHtml(review.rationale)+'</p>':
    '<p class="muted">No directional assessment on file. Source novelty or topic association is not evidence of this hypothesis.</p>';
  const links=sources.map(s=>{
    const u=safeUrl(s.source_url);
    return '<li>'+ (u?'<a href="'+escapeHtml(u)+'" target="_blank" rel="noopener noreferrer">'+
      escapeHtml(s.title||"Original source")+'</a>':escapeHtml(s.title||"Unlinked source"))+
      '<span class="source-meta">'+escapeHtml(s.provider||"Unknown publisher")+
      ' · '+escapeHtml(s.observed_at||"Date not verified")+
      ' · '+escapeHtml(s.assessment||"No event validation")+'</span></li>';
  }).join("");
  return '<details class="evidence-card"><summary><span class="evidence-heading">'+
    '<strong>'+escapeHtml(f.title||f.evidence_key)+'</strong>'+
    '<span>'+pill(labels[direction]||"Unassessed","direction "+direction)+
    pill(health.status||"unknown","health "+(health.status||"unknown"))+'</span>'+
    '</span><span class="evidence-sub">'+escapeHtml(f.source_mechanism||"Unclassified observation")+
    ' · '+escapeHtml(providers.filter((x,i,a)=>a.indexOf(x)===i).join(", ")||"Publisher unspecified")+'</span></summary>'+
    '<div class="evidence-body">'+reasons+
    '<dl><dt>Source check</dt><dd>'+escapeHtml(health.checked_at||"No live check")+
    '</dd><dt>Collection scope</dt><dd>'+escapeHtml(health.coverage||"Unknown")+
    '</dd><dt>Information roots</dt><dd>'+escapeHtml(f.source_root_count ?? "unknown")+
    ' (independence not assumed)</dd><dt>Links to hypotheses</dt><dd>'+
    escapeHtml((f.linked_hypotheses||[]).join(", "))+'</dd></dl>'+
    (review?'<p class="review-meta">Ordinal strength '+escapeHtml(review.strength)+
      '/3 · dependency group '+escapeHtml(review.dependency_group)+
      ' · reviewed '+escapeHtml(review.reviewed_at)+'</p>':'')+
    '<h4>Source records ('+sources.length+')</h4><ul class="source-links">'+links+'</ul></div></details>';
}
function showCase(id){
  selected=id;listCases();const c=rows.find(x=>x.id===id);
  const host=$("caseDetail");if(!c)return;
  const balance=c.balance||{},score=balance.signed_ordinal_balance;
  const assessed=typeof score==="number"&&Number.isFinite(score);
  const at=assessed ? Math.max(0,Math.min(100,50+score*45)) : 50;
  const groups={supports:[],contradicts:[],context:[],not_assessed:[]};
  for(const f of c.families||[]) (groups[f.direction]||groups.not_assessed).push(f);
  const sections=Object.keys(groups).sort((a,b)=>order[a]-order[b]).filter(k=>groups[k].length)
    .map(k=>'<section class="evidence-section"><h3>'+escapeHtml(labels[k])+
      ' <span>'+groups[k].length+'</span></h3>'+
      groups[k].map(familyCard).join("")+'</section>').join("");
  host.innerHTML='<p class="eyebrow">SOURCE-DATED HYPOTHESIS · '+escapeHtml(c.dossier_asof||"DATE UNKNOWN")+'</p>'+
    '<h2>'+escapeHtml(c.title||c.id)+'</h2>'+
    '<p class="scenario">'+escapeHtml(c.hypothesis||"Hypothesis unspecified")+'</p>'+
    '<p>'+escapeHtml(c.overview||"No analysis on file")+'</p>'+gdeltSection(c)+competingSection(c)+autoSection(c)+evidenceHistory(c)+
    '<section class="balance"><div class="balance-title"><h3>Direction of reviewed evidence</h3>'+
      pill(caseLabel(c),assessed?(score>0.2?"supports":score< -0.2?"contradicts":"context"):"not_assessed")+
      '</div><div class="balance-track" role="img" aria-label="'+
      escapeHtml(assessed?"Ordinal evidence balance "+score:"Evidence not directionally reviewed")+'">'+
      '<span class="balance-mid"></span>'+(assessed?'<span class="balance-marker" style="left:'+at+'%"></span>':'')+
      '</div><div class="balance-axis"><span>Contradicting</span><span>Undetermined</span><span>Supporting</span></div>'+
      '<p class="muted">'+(assessed?('Reviewed ordinal strengths: '+balance.support_strength+
        ' supporting / '+balance.contradict_strength+' contradicting. '):'No reviewer-approved signed evidence has been attached. ')+
        'This is not a probability or automated threat rating.</p>'+
      (balance.conflicting_dependency_groups_excluded?
        '<p class="muted">'+balance.conflicting_dependency_groups_excluded+' dependency conflicts excluded pending resolution.</p>':'')+
    '</section>'+
    '<div class="panel-grid"><section><h3>Alternative explanatory hypotheses</h3>'+
      ((c.alternatives||[]).length?
        '<ol>'+c.alternatives.slice(0,3).map(x=>'<li>'+escapeHtml(x)+'</li>').join("")+'</ol>':
        '<p class="muted">No sourced alternatives entered; analyst review required.</p>')+
      '</section><section><h3>Potential discriminating evidence</h3>'+
        '<p>'+escapeHtml(c.next_discriminators||"No discriminating observations specified.")+'</p></section></div>'+
    '<div class="evidence-top"><h3>Families of evidence</h3><p>'+
      escapeHtml(c.family_count)+' linked families · '+escapeHtml(c.reviewed_family_count)+
      ' with analyst-reviewed roles. Source health is distinct from hypothesis support.</p></div>'+
      sections+'<footer class="disclaimer">Historical dossiers and unreviewed source-family case hints are not current intelligence assessments. Missing feeds cannot contradict a hypothesis without an explicit expectation and adequate coverage.</footer>';
  host.scrollTop=0;
}
async function start(){
  try{
    const res=await fetch("hypotheses.json",{cache:"no-store"});
    if(!res.ok)throw Error("HTTP "+res.status);
    const payload=await res.json();
    if(payload.schema!=="cairn.hypothesis-evidence.v1"||!Array.isArray(payload.hypotheses))
      throw Error("Unsupported hypothesis index");
    rows=payload.hypotheses.map(c=>({...c,
      automated_window_hours:payload.automated_screen?.window_hours,
      automated_source_snapshot_at:payload.automated_screen?.source_snapshot_at,
      discriminator_window_days:payload.discriminator_screen?.source_lookback_days}));
    $("snapshotStatus").textContent=(payload.hypothesis_count||0)+" scenarios · "+
      (payload.reviewed_hypotheses||0)+" with explicit review · "+
      (payload.generated_at||"Unknown build time")+" · Automated: "+
      (payload.automated_screen?.status==="screened"?"screened "+payload.automated_screen.screened_at:"source snapshot unavailable")+
      " · GDELT case comparisons: "+(payload.gdelt_case_status?.measured_case_count||0)+"/"+(payload.hypothesis_count||0)+
      " · Competing-explanation scans: "+(payload.discriminator_screen?.hypothesis_count||0);
    const initial=new URLSearchParams(window.location.search).get("id");
    $("caseSearch").addEventListener("input",listCases);
    $("caseFilter").addEventListener("change",listCases);
    showCase(rows.some(c=>c.id===initial)?initial:rows[0]?.id);
  }catch(error){
    $("snapshotStatus").textContent="Hypothesis index unavailable";
    $("caseList").textContent="Source-backed hypothesis data could not be loaded: "+error.message;
    $("caseDetail").textContent="Missing or invalid publication is not an all-clear.";
  }
}
start();
})();
