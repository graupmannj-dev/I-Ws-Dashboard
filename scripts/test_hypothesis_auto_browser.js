const {chromium}=require("playwright");
const assert=require("node:assert/strict");
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1400,height:900}});
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    await page.route("**/hypotheses.json",async route=>{
      const response=await route.fetch(),body=await response.json();
      body.gdelt_case_status={status:"measured",asof:"2026-11-22",measured_case_count:10};
      body.hypotheses[0].gdelt_media_trend={
        status:"measured",source_clock:"2026-11-22",
        source_url:"https://data.gdeltproject.org/events/",
        matched_actor_pairs:[["ERI","ETH"]],recent_coded_records:35,
        baseline_coded_records:70,baseline_share:0.01,recent_share:0.02,
        media_share_change_percentage_points:1.0,trend:"higher_coded_share",
        daily_counts:Array.from({length:7},(_,i)=>({date:"2026-11-"+(16+i),coded_records:5}))
      };
      body.automated_screen={status:"screened",screened_at:"2026-11-21T15:00:00Z",
        source_snapshot_at:"2026-11-21T14:30:00Z",window_hours:9};
      body.discriminator_screen={status:"screened",hypothesis_count:10,source_lookback_days:7};
      body.hypotheses[0].competing_screen={
        status:"screened",evaluated_at:"2026-11-23T12:00:00Z",
        alternative_explanation:"Scheduled exercises can explain restrictions",
        summary:{competing_pattern:"competing_candidates_present",
          escalation_signpost_nominations:1,alternative_signpost_nominations:1,
          ambiguous_signpost_nominations:0,source_documents_case_associated:2,
          direction_of_armed_conflict_hypothesis:"not_estimated"},
        source_baseline_readiness:[{mode:"official",current_source_status:"current",
          comparable_days:2,status:"baseline_inadequate_or_source_unavailable"}],
        gdelt_context:{status:"measured",media_coded_share_trend:"higher_coded_share"},
        discriminators:[
          {id:"direct_state_engagement",label:"Cross-border strike indicator",
            role:"escalation_candidate",candidate_count:1,ambiguous_count:0,
            status:"candidate_observed",discriminator:"Verify original state attribution",
            sources:[{title:"Illustrative strike report",source_url:"https://example.org/escalation",
              screening_bucket:"candidate",event_verification:"not_verified",
              source_mode:"official",first_observed_at:"2026-11-23T12:00:00Z",
              reason:"Requires primary-source verification"}]},
          {id:"scheduled_training",label:"Training as competing explanation",
            role:"alternative_candidate",candidate_count:1,ambiguous_count:0,
            status:"candidate_observed",discriminator:"Check scheduled training baseline",
            sources:[{title:"Exercise notice",source_url:"https://example.org/training",
              source_mode:"live_maritime",screening_bucket:"candidate"}]}
        ]
      };
      body.hypotheses[0].automated_screen={
        status:"screened",screened_at:"2026-11-21T15:00:00Z",
        new_matching_records:1,possible_support:1,possible_counter:0,
        unavailable_source_matches:0,candidates_truncated:false,
        historical_case_roots:1,history_window_hours:168,
        historical_sources:[{record_id:"old-1",title:"Dated historical source report",
          source_url:"https://example.org/historical",source_mode:"analyst",
          first_observed_at:"2026-11-18T00:00:00Z",
          provenance:"public_analyst_intake_not_independently_verified",
          preliminary_direction:"requires_interpretation",
          rationale:"Source-linked public intake"}],
        candidates:[{record_id:"fixture-1",title:"Synthetic source notice",
          source_url:"https://example.org/source",provider:"Test source",
          source_health:"current",match_basis:"distinctive_case_cue",
          first_observed_at:"2026-11-21T14:30:00Z",preliminary_direction:"possible_support",
          rationale:"Candidate observable signpost: maritime exclusion"}]};
      await route.fulfill({response,json:body});
    });
    await page.goto("http://127.0.0.1:8765/hypotheses.html",{waitUntil:"domcontentloaded"});
    await page.waitForFunction(()=>document.querySelectorAll(".case-tile").length>0);
    assert.match(await page.locator("#snapshotStatus").innerText(),/Automated: screened/);
    assert.match(await page.locator("#caseDetail").innerText(),/Automated incoming-evidence screen/);
    assert.match(await page.locator("#caseDetail").innerText(),/Machine preliminary/);
    assert.match(await page.locator("#caseDetail").innerText(),/Candidate observable signpost/);
    assert.match(await page.locator("#caseDetail").innerText(),/Hypothesis-specific discriminator workbench/);
    assert.match(await page.locator("#caseDetail").innerText(),/What might distinguish escalation/);
    assert.match(await page.locator("#caseDetail").innerText(),/What might favor alternative explanations/);
    await page.locator(".discriminator-rule summary").first().click();
    assert.match(await page.locator("#caseDetail").innerText(),/Verify original state attribution/);
    assert.match(await page.locator("#caseDetail").innerText(),/Scheduled exercises can explain restrictions/);
    await page.locator(".coverage-details summary").first().click();
    assert.match(await page.locator("#caseDetail").innerText(),/Insufficient for baseline/);
    const link=page.locator('a[href="https://example.org/escalation"]');
    assert.equal(await link.count(),1);
    assert.match(await page.locator("#caseDetail").innerText(),/not_verified/);
        assert.match(await page.locator("#caseDetail").innerText(),/GDELT exact actor-pair trend/);
    assert.match(await page.locator("#caseDetail").innerText(),/Higher media-coded share/);
    assert.match(await page.locator("#caseDetail").innerText(),/Rolling case-linked evidence history/);
    assert.match(await page.locator("#caseDetail").innerText(),/Dated historical source report/);
    assert.match(await page.locator("#caseDetail").innerText(),/NOT an analyst-approved direction/);
    assert.match(await page.locator("#caseDetail").innerText(),/No reviewer-approved signed evidence/);
    assert.equal(await page.locator(".auto-candidates a").first().getAttribute("href"),
      "https://example.org/source");
    await page.locator("#caseFilter").selectOption("discriminators");
    assert.equal(await page.locator(".case-tile").count(),1);
    await page.locator("#caseFilter").selectOption("machine");
    assert.equal(await page.locator(".case-tile").count(),1);
    assert.equal(errors.length,0,errors.join("; "));
    console.log("CAIRN automated hypothesis screen: visible unapproved leads, source links, timestamps, filter PASS");
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
