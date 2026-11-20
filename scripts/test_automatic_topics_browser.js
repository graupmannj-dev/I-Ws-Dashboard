const {chromium}=require("playwright");
const assert=require("node:assert/strict");
(async()=>{
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1400,height:870}});
    const jsErrors=[];page.on("pageerror",e=>jsErrors.push(e.message));
    await page.route("**/atlas.json",async route=>{
      const response=await route.fetch(),data=await response.json();
      const docs=[0,1].map(n=>({
        id:"notice:auto-"+n,title:n===0?"Iran Hormuz agreement by November":
          "Iran Hormuz agreement by December",
        source_url:"https://example.org/article/"+n,
        source_record_count:1,information_root_count:1,
        publisher_names:n===0?["Source A"]:["Source B"],
        validity_windows:[],records:[{
          id:"beh:auto-"+n,first_observed_at:"2026-11-19T19:00:00Z",
          source_url:"https://example.org/article/"+n,provider:n===0?"Source A":"Source B",
          information_root:"root:"+n,geography_precision:"not_verified",
        }]
      }));
      const topic={
        id:"family:auto-1",kind:"analytical_topic_family",
        title:"iran · hormuz / agreement",activity:"automatically_discovered_shared_subject",
        country:"iran",state:"emerging",
        first_observed_at:"2026-11-19T19:00:00Z",
        last_observed_at:"2026-11-19T19:00:00Z",
        notice_count:2,source_record_count:2,information_root_count:2,
        source_families:["market_expectation"],providers:["Source A","Source B"],
        case_hints:[],geography_precision:"textual_subject_not_event_location",
        anomaly_metric:{status:"not_calibrated",z_score:null},
        evidence_facets:{profile:"general",values:[]},
        notice_groups:docs,notice_groups_truncated:false,sources:[],
        sources_truncated:false,reason:"Automatic lexical topic, not a verified event.",
        automatic_grouping:{method:"stable_seed_weighted_lexical_similarity_v1",
                            membership_review_status:"unreviewed_automatic_theme"},
      };
      data.dynamic_bins={
        schema:"aiba.dynamic-evidence-bins.v1",registry_status:"available",
        candidate_count_total:1,candidate_count_displayed:1,truncated:false,
        emerging_count:1,monitoring_count:0,quiet_count:0,
        analytical_topic_family_count:1,automatic_topic_family_count:1,
        families:[topic]
      };
      await route.fulfill({response,json:data});
    });
    await page.route("**/aiba-feed-data/**",route=>route.fulfill({
      status:503,body:"offline test"
    }));
    await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded",timeout:30000});
    await page.waitForFunction(()=>document.querySelectorAll(".family-card").length===1,{
      timeout:15000
    });
    assert.match(await page.locator(".family-card").innerText(),/2 distinct source documents/i);
    await page.locator(".family-card").click();
    assert.equal(await page.locator("#familyWorkspace").evaluate(node=>node.open),true);
    assert.match(await page.locator("#familyWorkspaceDetail").innerText(),/Similar source documents \(2\)/);
    assert.equal(await page.locator(".topic-notice").count(),2);
    await page.locator(".topic-notice").first().locator("summary").click();
    assert.equal(await page.locator(".topic-notice").first().locator("a").count(),1);
    assert.match(await page.locator(".topic-family-summary").innerText(),
      /not established independent corroboration/i);
    assert.equal(await page.locator(".family-detail .family-gauge-marker").count(),0);
    assert.deepEqual(jsErrors,[]);
    console.log("Automatic analytical theme browser drilldown PASS");
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
