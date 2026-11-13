/* Atlas behavioral tab end-to-end browser checks (synthetic, no live sources). */
const {chromium}=require("playwright");
const assert=require("node:assert/strict");

const HOST="http://127.0.0.1:8765/";
function mockBehavior(stamp){
  return {
    schema:"aiba.behavioral-convergence-shadow.v1",
    status:"read_only_shadow_evidence",
    source_generated_at:stamp,site_snapshot_fresh:true,
    cross_family_count_total:1,single_source_count_total:1,
    approved_warning_count:0,automated_severity_changes:0,
    source_continuity_proven:false,forecast_probability:null,
    map_coordinates_inferred:false,
    review_groups:[{
      id:"behavioral:synthetic-a",status:"cross_family_cooccurrence_unreviewed",
      warning_level_change:false,
      geography:{label:"Synthetic source-declared region",precision:"source_notice_footprint",
        scope_key:"source-footprint:synthetic"},
      assessment:"Unverified co-occurrence; not proof of military intent.",
      distinct_source_families:["internet_reachability","maritime_restriction"],
      source_root_count:2,source_family_count:2,distinct_provider_count:2,
      first_observed_at:stamp,last_observed_at:stamp,
      source_links:[
        {url:"https://example.org/primary",provider:"Synthetic source A",family:"internet_reachability",
         first_observed_at:stamp,published_at:null},
        {url:null,provider:"Synthetic source B",family:"maritime_restriction",
         first_observed_at:stamp,published_at:null}
      ]
    }],
    new_single_source_leads:[{
      observation_id:"beh:synthetic-1",status:"single_source_unreviewed",
      title:'<img src=x onerror=alert(1)> Synthetic lead',
      source_family:"protective_notice",
      source_url:"https://example.org/advisory",first_observed_at:stamp,
      source_published_at:stamp,
      geography:{label:"Location not verified",scope_key:null,precision:"not_geocoded"},
      requires_geolocation:true
    }],
    collection_coverage:{
      ioda:{status:"current",missingness:"provider_bounded_not_exhaustive",
        source_scope:"Bounded country sampling",snapshot_at:stamp},
      nga:{status:"stale_or_unavailable",missingness:"not_measured_not_zero",
        source_scope:"NGA source not responding",snapshot_at:stamp},
    },
    provider_baselines:{ioda:{status:"insufficient_history",comparable_days:6,median_records:null}}
  };
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1380,height:900}});
    const errors=[];
    page.on("pageerror",err=>errors.push(err.message));
    await page.route("**/aiba-feed-data/observations/latest/friction_briefs.json",
      route=>route.fulfill({json:{schema_version:1,shadow_mode:true,
        generated_at:new Date().toISOString(),fresh_snapshot:false,cases:[],
        coverage_gaps:["nga"],executive_summary:"No verified warning."}}));
    await page.route("**/aiba-feed-data/observations/latest/live_layers.json",
      route=>route.fulfill({json:{version:1,kind:"aiba_restriction_snapshot",
        generated_at:"2000-01-01T00:00:00Z",layers:{
          airspace:{status:"unavailable",checked_at:"2000-01-01T00:00:00Z",records:[]},
          maritime:{status:"unavailable",checked_at:"2000-01-01T00:00:00Z",records:[]}}}}));
    let stamp=new Date(Date.now()-10*60000).toISOString();
    let fixtureMode="normal";
    await page.route("**/aiba-feed-data/observations/latest/behavioral_fusion.json",
      route=>route.fulfill({status:503,body:"Simulated branch outage"}));
    await page.route("**/atlas.json",async route=>{
      const response=await route.fetch();
      const payload=await response.json();
      payload.behavioral_discovery=mockBehavior(stamp);
      if(fixtureMode==="funnel"){
        const b=payload.behavioral_discovery;
        b.review_groups=[];b.cross_family_count_total=0;
        b.new_single_source_leads=[];b.single_source_count_total=0;
        b.discovery_visibility={
          schema:"aiba.behavioral-discovery-visibility.v1",
          latest_registry_record_count:377,
          latest_registry_newly_observed_count:0,
          recent_unique_record_count_72h:171,
          recent_unlocated_count_72h:140,
          latest_unlocated_record_count:335,
          shared_exact_geography_keys_across_behavior_families:0,
          recent_observations_sampled:1,
          exact_geography_match_required_for_cross_family:true,
          new_this_collection_required_for_cross_family_nomination:true,
          source_coverage_is_globally_complete:false
        };
        b.recent_source_observations=[{
          observation_id:"realistic-history-record",title:"<img src=x onerror=alert(1)> A historical observation",
          status:"recent_source_observation_unreviewed",
          source_family:"maritime_restriction",provider:"amsa",
          source_url:"https://example.org/notice",
          first_observed_at:new Date(Date.now()-2*3600000).toISOString(),
          source_published_at:null,
          geography:{label:"Region not verified",precision:"source_defined_only"},
          requires_geolocation:true
        }];
      }
      await route.fulfill({response,json:payload});
    });
    await page.goto(HOST,{waitUntil:"networkidle",timeout:30000});
    await page.waitForFunction(()=>document.querySelectorAll(".watch-card").length>0);
    const originalWatchCount=await page.locator("#watchlist .watch-card").count();
    assert(originalWatchCount>0);
    assert.equal(await page.locator("#tabBehavior").count(),1);
    assert.match(await page.locator("#behaviorTabCount").innerText(),/2/);
    await page.locator("#tabBehavior").click();
    assert.equal(await page.locator("#tabBehavior").getAttribute("aria-pressed"),"true");
    assert.equal(await page.locator("#frictionBriefing").isHidden(),true);
    assert.match(await page.locator("#watchPanelTitle").innerText(),/Behavioral signals/);
    assert.match(await page.locator("#watchlist").innerText(),/SOURCE SNAPSHOT WITHIN 90 MIN/);
    assert.equal(await page.locator("#watchlist .behavior-card").count(),2);
    assert.equal(await page.locator("#watchlist img").count(),0,"XSS input may not render images");
    await page.locator("#watchlist .behavior-card").first().click();
    assert.match(await page.locator("#selectedDetail").innerText(),/not proof of military intent/i);
    assert.match(await page.locator("#selectedDetail").innerText(),/No automatic change to standing severity/i);
    assert.equal(await page.locator("#selectedDetail a[href='https://example.org/primary']").count(),1);
    await page.locator("#selectedDetail .detail-close").click();
    await page.locator("#watchlist .behavior-card").last().click();
    assert.match(await page.locator("#selectedDetail").innerText(),/GEOGRAPHY|geocoded|not verified/i);
    assert.equal(await page.locator("#selectedDetail img").count(),0);
    await page.locator("#selectedDetail .detail-close").click();
    await page.locator(".behavior-health summary").click();
    const cover=await page.locator(".behavior-health").innerText();
    assert.match(cover,/stale_or_unavailable/);
    assert.match(cover,/not responding/);
    assert.match(cover,/insufficient|unavailable|6 days/i);
    assert.match(await page.locator("#watchDetailLink").getAttribute("href"),/^behavior\/$/);
    await page.locator("#tabAll").click();
    assert.equal(await page.locator("#frictionBriefing").isVisible(),true);
    assert.equal(await page.locator("#watchlist .watch-card").count(),originalWatchCount);
    assert.equal(await page.locator("#watchDetailLink").getAttribute("href"),"ops/");
    await page.locator("#openBehavior").click();
    assert.equal(await page.locator("#tabBehavior").getAttribute("aria-pressed"),"true");
    // The tab also fetches newer public evidence-branch source records,
    // but NEVER escalates their status or infers exact incident geometry.
    const newer=new Date(Date.now()-60000).toISOString().replace(/\.\d{3}Z$/,"Z");
    const rawLive={...mockBehavior(newer),generated_at:newer,
      registry_asof:newer,review_groups_count_total:1,
      new_single_source_count_total:1,prediction_horizon:null};
    await page.route("**/aiba-feed-data/observations/latest/behavioral_fusion.json",
      route=>route.fulfill({json:rawLive}));
    await page.reload({waitUntil:"networkidle"});
    await page.locator("#tabBehavior").click();
    await page.waitForFunction(()=>document.querySelector("#watchlist").textContent.includes("public evidence branch snapshot"));
    assert.match(await page.locator("#watchlist").innerText(),/SOURCE SNAPSHOT WITHIN 90 MIN/);
    assert.equal(await page.locator("#watchlist .behavior-card").count(),2);
    // A newer Pages publication must NOT make a 4-hour-old behavioral
    // observation look like a fresh prospective frame. Simulate network
    // failure to verify the dated static fallback stays clearly stale.
    await page.route("**/aiba-feed-data/observations/latest/behavioral_fusion.json",
      route=>route.fulfill({status:503,body:"Simulated second outage"}));
    stamp=new Date(Date.now()-4*3600*1000).toISOString();
    await page.reload({waitUntil:"networkidle"});
    await page.locator("#tabBehavior").click();
    assert.match(await page.locator("#watchlist").innerText(),/STALE OR UNVERIFIED SNAPSHOT/);
    assert.match(await page.locator("#watchlist").innerText(),/Historical context only/i);
    assert.equal(await page.locator("#watchlist .behavior-card").count(),2);
    // The new public observation-context view must not disappear simply
    // because the last collection contains zero new-only nominations.
    fixtureMode="funnel";
    stamp=new Date(Date.now()-10*60000).toISOString();
    await page.reload({waitUntil:"networkidle"});
    await page.locator("#tabBehavior").click();
    const text=await page.locator("#watchlist").innerText();
    assert.match(text,/377/);
    assert.match(text,/171/);
    assert.match(text,/335|140/);
    assert.match(text,/Recent source observations/);
    assert.match(text,/NOT warnings/i);
    assert.equal(await page.locator("#watchlist .behavior-card").count(),0);
    assert.equal(await page.locator("#watchlist .behavior-history-card").count(),1);
    assert.equal(await page.locator("#watchlist img").count(),0,"Source title must not become HTML");
    await page.locator("#watchlist .behavior-history-card").click();
    assert.match(await page.locator("#selectedDetail").innerText(),/A historical observation/);
    await page.locator("#selectedDetail .detail-close").click();
    assert.equal(errors.length,0,"No browser JS exceptions: "+errors.join("; "));
    console.log("Unified Atlas behavioral panel: interactive source, missingness, XSS and stale-data browser checks passed.");
  }finally{
    await browser.close();
  }
})().catch(err=>{console.error(err);process.exitCode=1;});
