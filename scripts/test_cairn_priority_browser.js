/* CAIRN: alternative indicators drive the discovery queue; context remains available. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:850}});
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    const make=(id,title,family,metric)=>({
      id:"family:"+id,kind:"source_root_candidate",title,
      state:"emerging",first_observed_at:"2026-11-19T18:00:00Z",
      last_observed_at:"2026-11-19T19:00:00Z",
      information_root_count:1,source_record_count:1,
      source_families:[family],providers:["Test"],case_hints:[],
      geography_label:null,geography_precision:"no_event_geolocation",
      map_eligible:false,source_independence_established:false,
      event_occurrence_verified:false,warning_approved:false,
      anomaly_metric:metric||{status:"not_calibrated",z_score:null},
      evidence_facets:{profile:"general",values:[]},
      reason:"Synthetic evidence; no verified occurrence",sources:[],
    });
    await page.route("**/atlas.json",async route=>{
      const response=await route.fetch(),data=await response.json();
      data.dynamic_bins={
        schema:"aiba.dynamic-evidence-bins.v1",registry_status:"available",
        candidate_count_total:3,candidate_count_displayed:3,truncated:false,
        emerging_count:3,monitoring_count:0,quiet_count:0,
        families:[
          make("news","Synthetic conventional reporting: maritime disruption",
            "commercial_media"),
          make("market","Synthetic market expectation: shipping constraints",
            "market_expectation"),
          make("network","Synthetic unusual measured network reachability",
            "internet_reachability",{
              status:"calibrated_metric",z_score:4.1,metric:"Network sample",
              unit:"measurements",source_id:"synthetic",axis_limit:5,
              observed:11,mean:3,sd:1.95
            }),
        ],
      };
      await route.fulfill({response,json:data});
    });
    await page.route("**/aiba-feed-data/**",route=>route.fulfill({
      status:503,body:"offline test",
    }));
    await page.goto("http://127.0.0.1:8765/",{
      waitUntil:"domcontentloaded",timeout:30000,
    });
    await page.waitForFunction(()=>document.querySelectorAll(".family-card").length===3);
    assert.match(await page.title(),/CAIRN/);
    assert.match(await page.locator(".brand").innerText(),/CAIRN/);
    assert.equal(await page.locator("#tabFamilies").getAttribute("aria-pressed"),"true");
    const titles=await page.locator(".family-card .family-card-head strong").allTextContents();
    assert.match(titles[0],/unusual measured network reachability/i);
    assert.match(titles[1],/market expectation/i);
    assert.match(titles[2],/conventional reporting/i);
    assert.match(await page.locator(".family-card").first().innerText(),/Alternative-source evidence/i);
    assert.match(await page.locator(".family-card").last().innerText(),/Reporting and institutional context/i);
    assert.equal(await page.locator(".family-card").count(),3,
      "Conventional news must remain accessible in the candidate list");
    assert.equal(await page.locator(".family-card").first().locator(".family-gauge-marker").count(),1);
    assert.equal(await page.locator(".family-card").nth(1).locator(".family-gauge-marker").count(),0);
    await page.locator(".family-card").first().click();
    assert.equal(await page.locator("#familyWorkspace").evaluate(x=>x.open),true);
    const workspaceTitles=await page.locator("#familyWorkspaceList .family-workspace-row").allTextContents();
    assert.match(workspaceTitles[0],/network reachability/i);
    assert.match(workspaceTitles[2],/conventional reporting/i);
    assert.match(await page.locator("#familyWorkspaceDetail").innerText(),/Unreviewed/i);
    assert.deepEqual(errors,[]);
    console.log("CAIRN alternative-source evidence priority and context-retention PASS");
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
