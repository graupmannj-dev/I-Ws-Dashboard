/* Browser smoke for the public Atlas. Requires npm package playwright and Chromium.
 * Runs against a local copy of the generated GitHub Pages output.
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1450,height:900},deviceScaleFactor:1});
  const errors=[];
  // Block external GitHub raw fetches in deterministic PR browser tests.
  // The live Atlas polls that public branch; the fixture protects CI from
  // internet latency and tests that untrusted briefing strings are escaped.
  const mockFriction={
    schema_version:1,shadow_mode:true,generated_at:new Date().toISOString(),
    fresh_snapshot:true,coverage_gaps:["nga"],
    executive_summary:"Synthetic source observations: review before escalation.",
    cases:[{id:"taiwan",title:"<img src=x onerror=alert(1)>",
      triage:"source_review",what_changed:"A test-only source observation changed.",
      so_what:"This is not a real conflict indicator.",
      next_signpost:"Seek verified independent confirmation.",
      alternative:"Normal operations",coverage_gaps:["nga"],
      source_evidence:[{title:"Synthetic evidence",url:"https://example.org/test",
        family:"internet_reachability",event_at:"2026-11-08T11:00:00Z",
        first_seen_at:"2026-11-08T11:15:00Z"}]}]
  };
  await page.route('**/aiba-feed-data/observations/latest/friction_briefs.json',
    route=>route.fulfill({json:mockFriction}));
  page.on("pageerror",err=>errors.push(err.message));
  page.on("console",msg=>{if(msg.type()==="error")errors.push(msg.text());});
  await page.goto("http://127.0.0.1:8765/",{waitUntil:"networkidle",timeout:30000});
  await page.waitForFunction(()=>document.querySelectorAll(".watch-card").length>0,{timeout:15000});
  assert.match(await page.title(),/AIBA/);
  assert.equal(await page.locator(".watch-card").count(),10);
  await page.waitForFunction(()=>document.querySelector("#frictionSummary").textContent.includes("Synthetic source observations"));
  assert.match(await page.locator("#frictionTime").innerText(),/Gaps: nga/i);
  assert.equal(await page.locator("#frictionHighlights img").count(),0,"Untrusted source strings must be escaped");
  await page.locator("#frictionExpand").click();
  assert.match(await page.locator("#frictionHighlights").innerText(),/test-only source/i);
  await page.locator("#frictionExpand").click();
  const pixels=await page.locator("#globe").evaluate(canvas=>{
    const context=canvas.getContext("2d"),w=canvas.width,h=canvas.height;
    const samples=[[w/2,h/2],[w/2+40,h/2],[w/2-60,h/2],[w/2,h/2-45]];
    return samples.map(([x,y])=>Array.from(context.getImageData(x|0,y|0,1,1).data));
  });
  assert(pixels.some(p=>p[3]>0),"Globe canvas is blank");

  await page.locator('[data-severity="critical"]').click();
  assert.equal(await page.locator(".watch-card").count(),0,"Unverified Critical classification should not appear");
  await page.locator('[data-severity="all"]').click();
  assert.equal(await page.locator(".watch-card").count(),10);
  await page.locator("#layerCommands").check();
  await page.locator("#layerReports").uncheck();
  await page.locator("#layerReports").check();
  await page.locator("#tabNew").click();
  assert(await page.locator(".watch-card").count()>=0);
  await page.locator("#tabAll").click();
  await page.locator(".watch-card").first().click();
  await page.locator("#selectedDetail").waitFor({state:"visible"});
  assert.match(await page.locator("#selectedDetail").innerText(),/So what|Next signpost/i);
  // Confirm the selected theater has a source-linked shadow mode comparison.
  await page.locator("#selectedDetail .detail-close").click();
  await page.locator(".watch-card").filter({hasText:"Taiwan"}).click();
  assert.match(await page.locator("#selectedDetail").innerText(),/Cross-source comparison|Structural friction|What changed/i);
  assert.equal(await page.locator("#selectedDetail img").count(),0);

  await page.locator("#selectedDetail .detail-close").click();
  await page.locator("#collapseControls").click();
  assert(await page.locator("#sidebar").evaluate(node=>node.classList.contains("sidebar-minimized")));
  await page.locator("#collapseControls").click();
  assert(!(await page.locator("#sidebar").evaluate(node=>node.classList.contains("sidebar-minimized"))));

  await page.locator('#timeWindows [data-days="30"]').click();
  assert.match(await page.locator("#windowLabel").innerText(),/30/);
  await page.locator("#timeCursor").evaluate(node=>{
    node.value="0";node.dispatchEvent(new Event("input",{bubbles:true}));
  });
  assert(await page.locator("#timelineCaption").innerText());
  await page.locator("#stepForward").click();

  await page.setViewportSize({width:390,height:820});
  await page.locator("#openControls").click();
  assert(await page.locator("#sidebar").evaluate(node=>node.classList.contains("mobile-open")));
  await page.locator("#openControls").click();
  assert(!(await page.locator("#sidebar").evaluate(node=>node.classList.contains("mobile-open"))));

  await page.setViewportSize({width:1450,height:900});
  await page.reload({waitUntil:"networkidle"});
  await page.waitForFunction(()=>document.querySelectorAll(".watch-card").length>0);
  await page.waitForTimeout(350);
  await page.screenshot({path:"atlas-preview.jpg",type:"jpeg",quality:72});
  console.log("Atlas screenshot saved as atlas-preview.jpg for PR review.");
  // Deterministic feed QA: traffic stays hidden even when the feed contains tracks.
  const now=new Date().toISOString(), future=new Date(Date.now()+3600000).toISOString();
  const past=new Date(Date.now()-3600000).toISOString();
  const fixture={version:1,layers:{
    aircraft:{status:'snapshot',checked_at:now,records:[
      {id:'fresh',title:'Fresh aircraft',lon:52,lat:20,observed_at:now,heading:90},
      {id:'old',title:'Stale aircraft',lon:52,lat:20,observed_at:past}]},
    ships:{status:'streaming',checked_at:now,records:[
      {id:'ship',title:'<img src=x onerror=alert(1)>',lon:53,lat:20,observed_at:now}]},
    advisories:{status:'snapshot',checked_at:now,records:[{id:'a',country:'Iran',level:4,title:'Iran advisory',url:'https://travel.state.gov/',detail:'Example advisory'}]},
    airspace:{status:'partial',checked_at:now,message:'Incomplete US coverage',records:[
      {id:'closed',title:'Active closure',valid_from:past,valid_until:future,geometry:{type:'Polygon',coordinates:[[[50,20],[51,20],[51,21],[50,20]]]}},
      {id:'unsafe',title:'<img src=x onerror=alert(1)>',valid_from:past,valid_until:future},
      {id:'expired',title:'Expired closure',valid_from:past,valid_until:past},
      {id:'scheduled',title:'Scheduled closure',valid_from:future,valid_until:future}]},
    maritime:{status:'unavailable',checked_at:now,records:[]},
    embassies:{status:'snapshot',checked_at:now,records:[{id:'e',country:'Iran',title:'Departure notice',notice_only:true}]}
  }};
  await page.route('**/layers.json',route=>route.fulfill({json:fixture}));
  await page.reload({waitUntil:'networkidle'});
  assert.equal(await page.locator('#layer-aircraft, #layer-ships').count(),0);
  assert.equal(await page.locator('#measuredLayerControls input').count(),4);
  for(const key of ['advisories','airspace','maritime','embassies'])await page.locator('#layer-'+key).check();
  const statuses=await page.locator('#layerStatus').innerText();
  assert(!statuses.includes('Fresh aircraft')&&!statuses.includes('AIS vessels'));
  assert(!statuses.includes('Stale aircraft'));
  assert.match(statuses,/Active closure/);
  assert(!statuses.includes('Expired closure')&&!statuses.includes('Scheduled closure'));
  assert.match(statuses,/partial/);
  assert.equal(await page.locator('#layerStatus img').count(),0,'Feed titles must remain escaped');
  assert.equal(await page.evaluate(()=>window.AtlasLayers.countryFill('Iran')),'#ef879b99');
  await page.locator('#layer-embassies').uncheck();
  assert.equal(await page.evaluate(()=>window.AtlasLayers.countryFill('Iran')),'#f0657099');
  await page.getByRole('button',{name:'Iran advisory',exact:true}).click();
  assert.match(await page.locator('#selectedDetail').innerText(),/State Department Level 4/);
  await page.route('**/layers.json',route=>route.fulfill({status:503,body:'Unavailable'}));
  await page.reload({waitUntil:'networkidle'});
  await page.locator('#layer-airspace').check();
  assert.match(await page.locator('#layerStatus').innerText(),/Feed unavailable/);
  // The deliberate network failure is expected; JS runtime errors still fail.
  const unexpected=errors.filter(e=>!e.includes('503'));
  assert.equal(unexpected.length,0,"Console or page errors: "+unexpected.join(" | "));
  console.log("AIBA browser globe, controls, time filter, mobile controls and sourced watchlist PASS");
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
