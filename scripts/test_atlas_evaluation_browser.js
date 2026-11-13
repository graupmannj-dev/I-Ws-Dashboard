/* Browser smoke: public Atlas evaluation cannot fabricate an early-warning score. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1400,height:890}});
    const errors=[];
    page.on("pageerror",err=>errors.push(err.message));
    await page.route("**/aiba-feed-data/observations/latest/friction_briefs.json",
      route=>route.fulfill({status:503,body:"Synthetic outage"}));
    await page.route("**/aiba-feed-data/observations/latest/live_layers.json",
      route=>route.fulfill({status:503,body:"Synthetic outage"}));
    await page.route("**/aiba-feed-data/observations/latest/behavioral_fusion.json",
      route=>route.fulfill({status:503,body:"Synthetic outage"}));
    let mode="normal";
    const snapshot=new Date(Date.now()-5*60000).toISOString();
    await page.route("**/atlas.json",async route=>{
      const response=await route.fetch();
      const payload=await response.json();
      payload.behavioral_discovery={
        schema:"aiba.behavioral-convergence-shadow.v1",
        status:"read_only_shadow_evidence",
        source_generated_at:mode==="old"?
          new Date(Date.now()-4*3600000).toISOString():snapshot,
        approved_warning_count:0,automated_severity_changes:0,
        forecast_probability:null,source_continuity_proven:false,
        map_coordinates_inferred:false,
        review_groups:[],new_single_source_leads:[],
        cross_family_count_total:0,single_source_count_total:0,
        collection_coverage:{
          "ioda":{status:"current",missingness:"provider_bounded_not_exhaustive",
            source_scope:"Selected country observations"},
          "nga":{status:"stale_or_unavailable",missingness:"not_measured_not_zero",
            source_scope:"Not observed; not zero"}
        }
      };
      if(mode==="corrupt"){
        payload.warning_evaluation.metrics["false_alarms_per_analyst_day"]=0;
      }
      await route.fulfill({response,json:payload});
    });
    await page.goto("http://127.0.0.1:8765/",{waitUntil:"networkidle",timeout:30000});
    await page.waitForFunction(()=>document.querySelectorAll(".watch-card").length>0);
    const oldCount=await page.locator("#watchlist .watch-card").count();
    assert(oldCount>0);
    await page.locator("#tabEvaluation").click();
    assert.equal(await page.locator("#tabEvaluation").getAttribute("aria-pressed"),"true");
    assert.match(await page.locator("#watchlist").innerText(),/SKILL NOT YET ESTABLISHED/);
    assert.match(await page.locator("#watchlist").innerText(),/Snapshot recent/);
    assert.match(await page.locator("#watchlist").innerText(),/Source adapters represented:\s*2/);
    assert.match(await page.locator("#watchlist").innerText(),/bounded or degraded:\s*2/);
    assert.equal(await page.locator(".evaluation-metric strong").count(),4);
    for(const label of await page.locator(".evaluation-metric strong").allTextContents())
      assert.equal(label.trim(),"—","Must not imply verified zero or hit rate");
    assert.match(await page.locator("#watchlist").innerText(),/not source completeness/i);
    assert(!((await page.locator("#watchlist").innerText()).includes("100%")));
    assert.equal(await page.locator("#frictionBriefing").isHidden(),true);
    assert.equal(await page.locator("#watchDetailLink").getAttribute("href"),
      "https://github.com/graupmannj-dev/I-Ws-Dashboard/blob/main/docs/AIBA_PROSPECTIVE_SHADOW_PILOT.md");
    await page.locator("#tabBehavior").click();
    assert.match(await page.locator("#watchPanelTitle").innerText(),/Behavioral signals/);
    await page.locator("#tabAll").click();
    assert.equal(await page.locator("#watchlist .watch-card").count(),oldCount);
    await page.locator("#openEvaluation").click();
    assert.equal(await page.locator("#tabEvaluation").getAttribute("aria-pressed"),"true");
    // A stale behavior snapshot is NOT a clean warning evaluation.
    mode="old";
    await page.reload({waitUntil:"networkidle"});
    await page.locator("#tabEvaluation").click();
    assert.match(await page.locator("#watchlist").innerText(),/Snapshot stale or unavailable/);
    assert.match(await page.locator("#watchlist").innerText(),/Unobserved time\/geography remains UNKNOWN/);
    // A bogus aggregate with a purported zero false-alarm rate is ignored.
    mode="corrupt";
    await page.reload({waitUntil:"networkidle"});
    await page.locator("#tabEvaluation").click();
    assert.match(await page.locator("#watchlist").innerText(),/Evaluation data unavailable/);
    assert.equal(await page.locator(".evaluation-metric").count(),0);
    assert.equal(errors.length,0,"Browser JS errors: "+errors.join("; "));
    console.log("AIBA evaluation tab: verified missingness, source age, navigation and no fake 0/0 scores.");
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
