/* Browser regression: one analyst topic, many distinct notices and fragments. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    const errs=[];
    page.on("pageerror",err=>errs.push(err.message));
    await page.route("**/atlas.json",async route=>{
      const response=await route.fetch();
      const data=await response.json();
      const notices=Array.from({length:11},(_,i)=>{
        const link="https://niord.dma.dk/#/message/test-"+i;
        const recs=Array.from({length:6},(_,j)=>({
          id:"beh:notice-"+i+"-fragment-"+j,
          information_root:"niord:test-"+i+":"+j,
          first_observed_at:"2026-11-19T19:00:00Z",
          provider:"niord",source_url:link,
          geography_precision:"provider_defined_notice_point_not_incident",
          scheduled_valid_from:"2026-11-22T07:00:00Z",
          scheduled_valid_until:"2026-11-22T15:00:00Z",
        }));
        return {
          id:"notice:"+i,title:"Denmark. Kattegat. EK R "+(i+10)+
            ". Firing exercises. Warning.",
          source_url:link,area_label:i%2?"Kattegat":"The Baltic Sea",
          source_record_count:6,information_root_count:6,
          validity_windows:[{from:"2026-11-22T07:00:00Z",until:"2026-11-22T15:00:00Z"}],
          validity_windows_truncated:false,records:recs,records_truncated:false
        };
      });
      const topic={
        id:"family:topic-fixture",kind:"analytical_topic_family",
        title:"Denmark · maritime firing exercises",country:"Denmark",
        state:"emerging",first_observed_at:"2026-11-10T19:00:00Z",
        last_observed_at:"2026-11-19T19:00:00Z",
        notice_count:11,source_record_count:66,information_root_count:66,
        source_families:["maritime_restriction"],providers:["niord"],
        case_hints:[],geography_label:"Denmark · multiple official notice areas",
        geography_precision:"country_in_official_notice_title_not_incident_location",
        map_eligible:false,source_independence_established:false,
        event_occurrence_verified:false,warning_approved:false,
        anomaly_metric:{status:"not_calibrated",z_score:null},
        evidence_facets:{profile:"maritime",values:[{
          key:"source_notice",label:"Official maritime notice",
          status:"supported",reason:"One notice issuer"
        }]},
        reason:"Same country and firing-exercise topic, not a single event.",
        notice_groups:notices,notice_groups_truncated:false,
        sources:notices.flatMap(x=>x.records.map(r=>({...r,title:x.title,
            source_family:"maritime_restriction"}))),
      };
      const bridge={
        id:"family:bridge",kind:"source_root_candidate",
        title:"Denmark. Liim Fiord. Bridge closed for passage.",
        state:"monitoring",first_observed_at:"2026-11-10T19:00:00Z",
        last_observed_at:"2026-11-18T19:00:00Z",information_root_count:1,
        source_record_count:1,source_families:["maritime_restriction"],
        providers:["niord"],case_hints:[],geography_precision:"unlocated",
        anomaly_metric:{status:"not_calibrated",z_score:null},
        evidence_facets:{profile:"maritime",values:[]},sources:[],
      };
      data.dynamic_bins={
        schema:"aiba.dynamic-evidence-bins.v1",registry_status:"available",
        candidate_count_total:2,candidate_count_displayed:2,truncated:false,
        analytical_topic_family_count:1,source_root_candidates_folded_count:66,
        emerging_count:1,monitoring_count:1,quiet_count:0,
        families:[topic,bridge]
      };
      await route.fulfill({response,json:data});
    });
    await page.route("**/aiba-feed-data/**",route=>route.fulfill({
      status:503,body:"offline browser test"
    }));
    await page.goto("http://127.0.0.1:8765/",{
      waitUntil:"domcontentloaded",timeout:30000
    });
    await page.waitForFunction(()=>document.querySelectorAll(".family-card").length===2,{
      timeout:15000
    });
    assert.equal(await page.locator(".family-card").count(),2);
    assert.match(await page.locator(".family-card").first().innerText(),/11 distinct notices/i);
    assert.match(await page.locator(".family-card").first().innerText(),/66 source fragments/i);
    await page.locator(".family-card").first().click();
    assert.equal(await page.locator("#familyWorkspace").evaluate(x=>x.open),true);
    assert.equal(await page.locator("#familyWorkspaceDetail .topic-notice").count(),11);
    assert.equal(await page.locator("#familyWorkspaceDetail .topic-source-fragments li").count(),66);
    assert.match(await page.locator(".topic-family-summary").innerText(),/not one verified event/i);
    assert.match(await page.locator(".topic-family-summary").innerText(),/11 distinct notices/i);
    await page.locator(".topic-notice").first().locator("summary").click();
    assert.equal(await page.locator(".topic-notice").first().evaluate(x=>x.open),true);
    assert.equal(await page.locator(".topic-notice").first().locator(".topic-source-fragments li").count(),6);
    assert.equal(await page.locator(".topic-notice").first().locator('a[href^="https://niord.dma.dk/"]').count(),1);
    assert.equal(await page.locator("#familyWorkspaceDetail .family-gauge-marker").count(),0);
    assert.match(await page.locator("#familyWorkspaceDetail").innerText(),/independent corroboration/i);
    await page.locator("#familyWorkspaceSearch").fill("bridge");
    assert.equal(await page.locator("#familyWorkspaceList .family-workspace-row").count(),1);
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#familyWorkspace").evaluate(x=>x.open),false);
    assert.deepEqual(errs,[]);
    console.log("Analytical topic grouping and nested 11-notice browser drilldown PASS");
  }finally{
    await browser.close();
  }
})().catch(err=>{console.error(err);process.exitCode=1});
