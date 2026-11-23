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
function sourceInspection(report){
  const s=report||{};
  if(!s.status||s.status==="not_selected_for_bounded_fetch")
    return '<p class="source-inspection-source">Original document not selected for bounded content inspection; headline remains provisional.</p>';
  if(s.status!=="document_text_inspected")
    return '<p class="source-inspection-source">Original-document check: '+escapeHtml(s.status)+
      (s.reason?' · '+escapeHtml(s.reason):'')+'. No source-text inference is possible.</p>';
  const g=s.geographic_attribution||{},e=g.evidence_span||{};
  return '<div class="source-inspection-source"><strong>Original document opened — text inspected, event NOT independently verified.</strong>'+
    '<p>Title rule in source body: '+escapeHtml(s.text_rule_relation||"not determined")+'</p>'+
    '<p>Reported locality: '+escapeHtml(g.named_place||"Not established")+
      ' · '+escapeHtml(g.status||"unknown")+
      (g.reported_country_or_area?' · '+escapeHtml(g.reported_country_or_area):'')+'</p>'+
    (e.quote_excerpt?'<p>Source-text evidence excerpt: “'+escapeHtml(e.quote_excerpt)+'”</p>':'')+
    '<p class="muted">A text-mentioned place is not a verified event location. Neither source attribution nor independent occurrence is established.</p></div>';
}
function competingSection(c){
  const d=c.competing_screen||{};
  if(d.status!=="screened"){
    return '<section class="competing-screen"><h3>Competing-explanation screen</h3>'+
      '<p class="muted">Source archive is unavailable. No assessment was made; absence of data is not contradictory evidence.</p></section>';
  }
  const summary=d.summary||{},rules=Array.isArray(d.discriminators)?d.discriminators:[],
    coverage=Array.isArray(d.source_baseline_readiness)?d.source_baseline_readiness:[],
    sourceStatus=d.original_source_inspection||{},gdelt=d.gdelt_context||{};
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
        '<p class="muted">'+escapeHtml(x.reason||"Needs review")+'</p>'+
        sourceInspection(x.original_document_review)+'</li>';
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
    '<p class="source-inspection-summary"><strong>Original source-text inspection prototype:</strong> '+
      escapeHtml(sourceStatus.status==="bounded_receipts_available"?
        ((sourceStatus.archived_original_documents||[]).length+" original document checks (14-day lookback) · "+
         (sourceStatus.archived_original_documents||[]).filter(r=>r.status==="document_text_inspected").length+
         " original narratives retrieved"):
        "Not collected in this publication")+
      '. Opening a document does not independently establish an incident.</p>'+
    (Array.isArray(sourceStatus.archived_original_documents)&&sourceStatus.archived_original_documents.length?
      '<details class="source-inspection-history"><summary>View original article checks and geographic-text attribution</summary>'+
      '<ol class="auto-candidates">'+sourceStatus.archived_original_documents.map(r=>{
        const url=safeUrl(r.source_url);
        const title=escapeHtml(r.title||"Source document");
        return '<li><span class="auto-meta">'+escapeHtml(r.status||"not inspected")+
          (r.source_text_location?' · Reported place: '+escapeHtml(r.source_text_location):' · Site not established')+
          '</span>'+(url?'<a href="'+escapeHtml(url)+'" target="_blank" rel="noopener noreferrer">'+title+'</a>':title)+
          '<small>First collected: '+escapeHtml(r.first_observed_at||"unknown")+
          ' · '+escapeHtml(r.geography_status||r.reason||"no verified source geography")+'</small></li>';
      }).join("")+'</ol></details>':'')+
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
    meta.textContent=caseLabel(c)+' · '+(c.family_count||0)+' evidence families';
    b.append(header,desc,meta);b.addEventListener("click",()=>showCase(c.id));
    const analystIssues=(c.analyst_hypotheses||[]).filter(x=>analystLimit(x).length);
    if(analystIssues.length){
      const wrap=document.createElement("div");wrap.className="case-tile-row";
      wrap.appendChild(b);
      const hint=document.createElement("span");hint.innerHTML=analystCaution(analystIssues[0]);
      wrap.appendChild(hint);host.appendChild(wrap);
    }else host.appendChild(b);
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

function achGroup(f){
  const text=[f.source_mechanism,f.title,...(f.sources||[]).map(s=>s.collection_mode||"")].join(" ").toLowerCase();
  if(/airspace|notam|flight restriction|tfr/.test(text))return "Airspace restrictions";
  if(/aircraft|aviation|flight|ads.b/.test(text))return "Aviation activity";
  if(/maritime|vessel|port|shipping|navwarn|navtex/.test(text))return "Maritime activity";
  if(/cyber|internet|network|dns|bgp|outage|telecom/.test(text))return "Infrastructure & networks";
  if(/market|commercial|finance|supply|trade|procure/.test(text))return "Commercial behavior";
  if(/government|diplom|official|statement|policy/.test(text))return "Government actions";
  return "Other observations";
}
function analystLimit(entry){
  const state=entry?.initial_backfill||{};
  const reason=(Array.isArray(state.limitations)?state.limitations:[]).filter(Boolean);
  if(state.status!=="initial_review_complete" && !reason.length){
    reason.push("Initial evidence evaluation is incomplete or pending");
  }
  return reason.slice(0,4);
}
function analystCaution(entry){
  const reasons=analystLimit(entry);
  if(!reasons.length)return "";
  const message=reasons.join(". ");
  return '<details class="analyst-caution"><summary aria-label="Analyst hypothesis evidence limitation: '+
    escapeHtml(message)+'" title="'+escapeHtml(message)+'"><span aria-hidden="true">⚠</span></summary>'+
    '<div class="caution-popover" role="note"><strong>Evidence review limitation</strong>'+
    '<p>'+escapeHtml(message)+'</p></div></details>';
}
function achTable(c){
  const groups=new Map();
  for(const f of c.families||[]){const name=achGroup(f);if(!groups.has(name))groups.set(name,[]);groups.get(name).push(f);}
  const hypotheses=[c.hypothesis||"Primary hypothesis",...(c.alternatives||[]).slice(0,3)];
  const analystByIndex=new Map((c.analyst_hypotheses||[]).map(x=>[x.index,x]));
  const head=hypotheses.map((h,i)=>{
    const entry=analystByIndex.get(i);
    return '<th scope="col"><strong>H'+(i+1)+'</strong>'+
      (entry?'<small class="analyst-origin">Analyst</small>'+analystCaution(entry):'')+
      '<span title="'+escapeHtml(h)+'">'+escapeHtml(h)+'</span></th>';
  }).join("");
  const body=[...groups].map(([name,families],i)=>{
    const reviewed=families.filter(f=>f.review);
    const support=reviewed.filter(f=>f.direction==="supports").length;
    const oppose=reviewed.filter(f=>f.direction==="contradicts").length;
    const label=!reviewed.length?"Not reviewed":support&&oppose?"Mixed":support?"Consistent":oppose?"Inconsistent":"Context";
    const mark=!reviewed.length?"?":support&&oppose?"±":support?"+":oppose?"−":"—";
    return '<tr><th scope="row"><button class="ach-family" type="button" data-ach-group="'+i+'" aria-expanded="false">'+escapeHtml(name)+' <span>'+families.length+' families · '+families.reduce((n,f)=>n+(f.sources||[]).length,0)+' records</span></button></th>'+
      '<td><button type="button" class="ach-cell '+(support?"has-support":oppose?"has-counter":"")+'" data-ach-group="'+i+'" title="'+escapeHtml(label)+'">'+mark+'<span class="sr-only">'+escapeHtml(label)+'</span></button></td>'+
      hypotheses.slice(1).map((h,j)=>{
        const rv=families.map(f=>f.ach_reviews?.[String(j+1)]).filter(Boolean);
        const sup=rv.filter(x=>x.direction==="supports").length;
        const ctr=rv.filter(x=>x.direction==="contradicts").length;
        const analyst=analystByIndex.get(j+1);
        const initial=(analyst?.initial_backfill?.evaluations||[]);
        const live=(c.semantic_review?.evaluations||[]);
        const provisional=!rv.length ? [...live,...initial].filter(x=>
          (live.includes(x)?x.hypothesis_index===j+1:x.hypothesis_index===0) &&
          families.some(f=>f.evidence_key===x.evidence_key)):[];
        const pos=provisional.filter(x=>x.direction==="possibly_consistent").length;
        const neg=provisional.filter(x=>x.direction==="possibly_inconsistent").length;
        const machine=!rv.length && (pos||neg);
        const mark=!rv.length?(machine?(pos&&neg?"≈±":pos?"≈+":"≈−"):"?"):
          sup&&ctr?"±":sup?"+":ctr?"−":"—";
        const label=rv.length?"Reviewed ACH judgments: "+rv.length:
          machine?"Provisional AI evidence comparison only; no analyst-signed direction":
          "No alternative-specific reviewed evidence";
        return '<td><span class="ach-cell '+(machine?"ach-provisional ": "")+
          (sup?"has-support":ctr?"has-counter":"")+'" title="'+escapeHtml(label)+'">'+
          mark+'</span></td>';
      }).join("")+'</tr>'+
      '<tr class="ach-drill" data-ach-details="'+i+'" hidden><td colspan="'+hypotheses.length+'"><div class="ach-source-list"><h4>'+escapeHtml(name)+' — original evidence</h4>'+
      families.map(familyCard).join("")+'</div></td></tr>';
  }).join("");
  return '<section class="ach-panel"><div class="ach-head"><h3>Analysis of competing hypotheses</h3><span class="pill">Only reviewed directions are scored</span></div>'+
    '<div class="ach-scroll"><table class="ach-table"><thead><tr><th scope="col">Evidence families</th>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>'+
    '<p class="ach-legend">+ consistent · − inconsistent · ± mixed · ? not reviewed. ≈ marks provisional AI observations, never approved evidence. Other marks summarize reviewer judgments; none are probabilities.</p>'+
    '<button type="button" class="new-hypothesis" id="addHypothesis">+ Propose an analyst hypothesis</button></section>';
}
function semanticSection(c){
  const d=c.semantic_review||{};
  if(d.status!=="provisional_complete"){
    return '<details class="semantic-status"><summary>AI semantic assessment · '+escapeHtml(
      d.status==="not_configured"?"Not configured":
      d.status==="not_selected_in_bounded_run"?"Awaiting scheduled batch":
      d.status==="model_or_validation_failed"?"Review unavailable":"No assessment")+
      '</summary><p class="muted">No validated model-generated ACH judgments are published for this case. The existing source and analyst reviews remain available.</p></details>';
  }
  const rows=Array.isArray(d.interpretations)?d.interpretations:[];
  const evaluations=Array.isArray(d.evaluations)?d.evaluations:[];
  const refs=new Map((d.source_references||[]).map(x=>[x.evidence_key,x]));
  const readable={possibly_consistent:"Possibly consistent",possibly_inconsistent:"Possibly inconsistent",
    non_diagnostic:"Not diagnostic",unresolved:"Unresolved"};
  const html=rows.map((x,i)=>{
    const verdicts=evaluations.filter(y=>y.hypothesis_index===i);
    return '<details class="semantic-hypothesis"><summary><strong>H'+(i+1)+'</strong> '+escapeHtml(x.meaning)+
      ' <span class="pill context">'+verdicts.length+' provisional evaluations</span></summary>'+
      '<p><strong>Discriminator:</strong> '+escapeHtml(x.discriminator)+'</p>'+
      '<ul class="semantic-verdicts">'+verdicts.map(v=>{
        const f=refs.get(v.evidence_key)||{};
        const links=(f.sources||[]).map(source=>{
          const url=safeUrl(source.url);
          return url?'<a href="'+escapeHtml(url)+'" target="_blank" rel="noopener noreferrer">'+
            escapeHtml(source.title||"Original source")+'</a>':'';
        }).filter(Boolean).join(" · ");
        return '<li><strong>'+escapeHtml(f.family_title||v.evidence_key)+'</strong> · '+
          escapeHtml(readable[v.direction]||"Unresolved")+
          '<p>'+escapeHtml(v.rationale)+'</p><div class="semantic-source-links">'+links+'</div></li>';
      }).join("")+'</ul></details>';
  }).join("");
  return '<section class="semantic-panel"><div class="ach-head"><h3>AI-assisted hypothesis comparison</h3>'+
    '<span class="pill context">Provisional · analyst review required</span></div>'+
    '<p>Candidate interpretations and evidence comparisons. These do not change reviewed evidence direction.</p>'+
    html+'</section>';
}
function showCase(id){
  selected=id;listCases();const c=rows.find(x=>x.id===id);
  const host=$("caseDetail");if(!c)return;
  const balance=c.balance||{},score=balance.signed_ordinal_balance;
  const assessed=typeof score==="number"&&Number.isFinite(score);
  const at=assessed?Math.max(0,Math.min(100,50+score*45)):50;
  const title=escapeHtml(c.title||c.id);
  const supplementary='<details class="technical-details"><summary>Detailed source diagnostics and collection context</summary>'+
    gdeltSection(c)+competingSection(c)+autoSection(c)+evidenceHistory(c)+
    '<p class="muted">Collection coverage and machine nominations are not approved directional judgments. Missing data are not counterevidence.</p></details>';
  host.innerHTML=
    '<section class="balance ach-first"><div class="balance-title"><h3>Direction of reviewed evidence</h3>'+
      pill(caseLabel(c),assessed?(score>0?"supports":score<0?"contradicts":"context"):"not_assessed")+'</div>'+
      '<div class="balance-track" role="img" aria-label="'+escapeHtml(assessed?"Reviewed ordinal balance "+score:"No approved directional review")+'">'+
      '<span class="balance-mid"></span>'+(assessed?'<span class="balance-marker" style="left:'+at+'%"></span>':'')+'</div>'+
      '<div class="balance-axis"><span>Contradicting</span><span>Undetermined</span><span>Supporting</span></div>'+
      '<p class="balance-summary">'+(assessed?escapeHtml(balance.support_strength||0)+' supporting / '+escapeHtml(balance.contradict_strength||0)+' contradicting ordinal review strength':'Awaiting analyst-reviewed direction')+'</p></section>'+
    '<div class="ach-bluf"><span class="eyebrow">BLUF · '+title+'</span>'+
      '<h2>'+escapeHtml(c.hypothesis||"Hypothesis unspecified")+'</h2>'+
      '<p>'+escapeHtml(c.overview||"Assessment not yet available")+'</p></div>'+
    achTable(c)+semanticSection(c)+
    '<section class="signposts"><h3>What would change this assessment?</h3><p>'+escapeHtml(c.next_discriminators||"No discriminating observations specified.")+'</p></section>'+
    supplementary;
  host.querySelectorAll("[data-ach-group]").forEach(btn=>btn.addEventListener("click",()=>{
    const index=btn.getAttribute("data-ach-group"),panel=host.querySelector('[data-ach-details="'+index+'"]');
    panel.hidden=!panel.hidden;
    host.querySelectorAll('[data-ach-group="'+index+'"]').forEach(b=>b.setAttribute("aria-expanded",String(!panel.hidden)));
  }));
  $("addHypothesis").addEventListener("click",()=>proposeHypothesis(c));
  host.scrollTop=0;
}
function proposeHypothesis(c){
  const existing=$("analystProposal");
  if(existing){existing.remove();return;}
  const wrapper=document.createElement("section");
  wrapper.id="analystProposal";wrapper.className="analyst-proposal";
  wrapper.innerHTML='<h3>Propose an alternative explanation</h3><label for="analystHypText">Analyst hypothesis</label>'+
    '<textarea id="analystHypText" maxlength="1200" rows="4" placeholder="State the proposed explanation, actors and observable implications."></textarea>'+
    '<p>Submitting opens an authenticated GitHub issue. After owner approval, CAIRN performs a one-time retained-evidence backfill and adds the hypothesis to this ACH for normal scheduled reviews. It never auto-signs reviewed evidence.</p>'+
    '<button type="button" id="submitAnalystHyp">Open GitHub proposal</button>';
  $("addHypothesis").after(wrapper);
  $("submitAnalystHyp").addEventListener("click",()=>{
    const statement=$("analystHypText").value.trim();
    if(statement.length<20){$("analystHypText").setCustomValidity("Enter a testable explanation of at least 20 characters.");$("analystHypText").reportValidity();return;}
    $("analystHypText").setCustomValidity("");
    const heading="CAIRN analyst hypothesis: "+(c.title||c.id);
    const body="Case ID: "+c.id+"\n\nProposed hypothesis:\n"+statement+
      "\n\nAnalyst review required: interpret actors, geography, timeframe, expected discriminators, competing explanations and source provenance before accepting. Do not treat automated matching as approved evidence.";
    const url="https://github.com/graupmannj-dev/I-Ws-Dashboard/issues/new?"+
      new URLSearchParams({title:heading,body}).toString();
    window.open(url,"_blank","noopener,noreferrer");
  });
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
      " · evidence updated "+(payload.generated_at||"unknown");
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
