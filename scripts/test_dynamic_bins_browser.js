/* End-to-end browser fixture for global evidence-family discovery. */
const {chromium} = require("playwright");
const assert = require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1400,height:850}});
    const errors=[];
    page.on("pageerror",err=>errors.push(err.message));
    await page.route("**/atlas.json",async route=>{
      const source=await route.fetch();
      const data=await source.json();
      data.dynamic_bins={
        schema:"aiba.dynamic-evidence-bins.v1",registry_status:"available",
        candidate_count_total:2,candidate_count_displayed:2,truncated:false,
        emerging_count:1,monitoring_count:0,quiet_count:1,
        families:[
          {
            id:"family:fixture-new",kind:"source_root_candidate",
            title:"<img src=x onerror=alert(1)> Synthetic unexpected airport operations",
            state:"emerging",last_observed_at:"2026-11-19T19:00:00Z",
            first_observed_at:"2026-11-19T19:00:00Z",
            information_root_count:1,source_record_count:1,
            source_families:["airspace_restriction"],providers:["Synthetic FAA test"],
            case_hints:[],geography_label:null,geography_precision:"not_geocoded",
            map_eligible:false,source_independence_established:false,
            warning_approved:false,
            anomaly_metric:{status:"not_calibrated",z_score:null},
            evidence_facets:{profile:"aviation",values:[
              {key:"source_notice",label:"Official airspace notice",status:"supported",reason:"One provider notice"},
              {key:"telemetry",label:"Aircraft telemetry",status:"not_measured",reason:"Coverage unavailable"},
              {key:"commercial",label:"Commercial reporting",status:"partial",reason:"Unreviewed source mention"},
              {key:"contradiction",label:"Conflicting evidence",status:"contradicted",reason:"Synthetic conflict fixture"},
            ]},
            reason:"Synthetic single source; no verified event.",
            sources:[{id:"fixture-one",title:"Synthetic FAA notice",provider:"Fixture",
              source_family:"airspace_restriction",
              source_url:"https://example.org/source",first_observed_at:"2026-11-19T19:00:00Z"}],
          },
          {
            id:"family:fixture-old",kind:"source_root_candidate",title:"Synthetic archived maritime notice",
            state:"quiet",last_observed_at:"2026-10-10T18:00:00Z",
            first_observed_at:"2026-10-10T18:00:00Z",
            information_root_count:1,source_record_count:1,
            source_families:["maritime_restriction"],providers:["Test"],
            case_hints:[],geography_label:null,geography_precision:"not_geocoded",
            map_eligible:false,source_independence_established:false,warning_approved:false,
            anomaly_metric:{status:"calibrated_metric",z_score:-3.2,
              metric:"Synthetic counted events",unit:"events",observed:5},
            evidence_facets:{profile:"maritime",values:[]},
            reason:"Synthetic history only.",sources:[],
          },
        ]
      };
      await route.fulfill({response:source,json:data});
    });
    await page.route("**/aiba-feed-data/**",route=>route.fulfill({status:503,body:"offline PR browser test"}));
    await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded",timeout:30000});
    await page.waitForFunction(()=>document.querySelectorAll(".family-card").length===2,{timeout:15000});
    assert.equal(await page.locator("#tabFamilies").getAttribute("aria-pressed"),"true");
    assert.equal(await page.locator(".family-quiet").count(),1);
    assert.equal(await page.locator(".family-emerging").count(),1);
    assert.equal(await page.locator(".family-card img").count(),0,"Titles must be escaped, never executed");
    assert.equal(await page.locator(".family-emerging .family-gauge-marker").count(),0,
      "Uncalibrated data must not show a deviation arrow");
    assert.equal(await page.locator(".family-quiet .family-gauge-marker").count(),1);
    assert.equal(await page.locator(".family-emerging .facet-supported").count(),1);
    assert.equal(await page.locator(".family-emerging .facet-partial").count(),1);
    assert.equal(await page.locator(".family-emerging .facet-contradicted").count(),1);
    assert.equal(await page.locator(".family-emerging .facet-not_measured").count(),1);
    assert.match(await page.locator(".family-quiet .family-gauge").getAttribute("aria-label"),/-3.2.*σ/i);

    await page.locator('input[aria-label="Search evidence families"]').fill("maritime");
    assert.equal(await page.locator(".family-card").count(),1);
    await page.locator('input[aria-label="Search evidence families"]').fill("");
    await page.locator(".family-emerging").click();
    assert.equal(await page.locator(".family-detail").count(),1);
    assert.match(await page.locator(".family-detail").innerText(),/Not calibrated/i);
    assert.equal(await page.locator(".family-detail .family-gauge-marker").count(),0);
    assert.match(await page.locator(".family-detail .family-facets").getAttribute("aria-label"),/Evidence facets/i);

    assert.match(await page.locator(".family-detail").innerText(),/Unreviewed/i);
    assert.equal(await page.locator('.family-detail a[href="https://example.org/source"]').count(),1);
    assert.equal(await page.locator(".family-detail img").count(),0);
    await page.locator(".family-detail .detail-close").click();
    assert.equal(await page.locator("#selectedDetail").isHidden(),true);
    await page.locator("#tabAll").click();
    assert.equal(await page.locator(".watch-card").count(),10,"Standing watch history should remain available");
    assert.equal(errors.length,0,"Uncaught errors: "+errors.join("; "));
    console.log("Dynamic evidence-family browser behavior passed");
  }finally{
    await browser.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1});
