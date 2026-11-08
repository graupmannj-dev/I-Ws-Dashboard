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
  // Zoom must exceed the former 1.9× limit and reset to the default view.
  for(let i=0;i<6;i++)await page.locator("#zoomIn").click();
  const zoom=parseFloat(await page.locator("#zoomLevel").innerText());
  assert(zoom>1.9&&zoom<=5.5,"Extended zoom range did not apply");
  await page.locator("#northView").click();
  assert.match(await page.locator("#zoomLevel").innerText(),/1\.0/);
  await page.locator("#discoveryToggle").click();
  assert.equal(await page.locator("#discoveryDrawer").isVisible(),true);
  assert.equal(await page.locator("#discoveryToggle").getAttribute("aria-expanded"),"true");
  assert.equal(await page.locator("#sidebar #discoveryLeads").count(),0,
    "Provisional leads must not occupy the left controls");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#discoveryDrawer").isHidden(),true);
  await page.locator("#discoveryToggle").click();
  await page.locator("#discoveryClose").click();
  assert.equal(await page.locator("#discoveryDrawer").isHidden(),true);

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
  assert.match(await page.locator("#windowLabel").innerText(),/30|calendar day/i);
  const values=async()=>Promise.all([
    page.locator("#timeStart").inputValue(),page.locator("#timeEnd").inputValue()
  ]).then(v=>v.map(Number));
  const [presetStart,presetEnd]=await values();
  assert(presetEnd>=presetStart);
  // Starting/ending handles independently resize inclusive source-date window.
  await page.locator("#timeStart").evaluate(node=>{
    node.value=String(Math.min(Number(node.max),Number(node.value)+3));
    node.dispatchEvent(new Event("input",{bubbles:true}));
  });
  const [resizedStart,resizedEnd]=await values();
  assert.equal(resizedEnd,presetEnd);
  assert(resizedStart>=presetStart);
  assert.match(await page.locator("#windowLabel").innerText(),/Custom/);
  await page.locator("#timeEnd").evaluate(node=>{
    node.value=String(Math.max(Number(node.min),Number(node.value)-2));
    node.dispatchEvent(new Event("input",{bubbles:true}));
  });
  const [s1,e1]=await values();
  assert(e1>=s1,"Handles may not cross");
  // Slide the selected window without changing its duration.
  await page.locator("#stepBack").click();
  const [s2,e2]=await values();
  assert.equal(e2-s2,e1-s1);
  assert(s2<=s1&&e2<=e1);
  await page.locator("#timeSelection").focus();
  await page.keyboard.press("ArrowRight");
  const [s3,e3]=await values();
  assert.equal(e3-s3,e1-s1);
  assert.equal(s3,s1);
  // Pointer dragging the selected blue bar should shift both dates together.
  await page.locator('#timeWindows [data-days="30"]').click();
  const [dragStart,dragEnd]=await values();
  const selection=await page.locator("#timeSelection").boundingBox();
  assert(selection&&selection.width>20);
  const cx=selection.x+selection.width/2,cy=selection.y+selection.height/2;
  await page.mouse.move(cx,cy);
  await page.mouse.down();
  await page.mouse.move(cx-48,cy,{steps:6});
  await page.mouse.up();
  const [movedStart,movedEnd]=await values();
  assert.equal(movedEnd-movedStart,dragEnd-dragStart);
  assert(movedStart<=dragStart);
  assert(await page.locator("#timelineCaption").innerText());
  // Preset Full History and single-day handles should remain valid.
  await page.locator('#timeWindows [data-days="all"]').click();
  const [allStart,allEnd]=await values();
  assert.equal(allStart,0);
  assert(allEnd>=0);
  await page.locator('#timeWindows [data-days="1"]').click();
  const [oneStart,oneEnd]=await values();
  assert.equal(oneStart,oneEnd);

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
      {id:'closed',title:'Active closure',source:'Synthetic FAA source',url:'https://example.org/closure',
        valid_from:past,valid_until:future,geometry:{type:'Polygon',
          coordinates:[[[50,19],[55,19],[55,23],[50,23],[50,19]]]}},
      {id:'circle',title:'Source-defined circle closure',source:'Synthetic authority',
        url:'https://example.org/circle',valid_from:past,valid_until:future,
        geometry:{type:'Circle',center:[52,20],radius_km:250}},
      {id:'bbox',title:'Source-defined box closure',source:'Synthetic authority',
        url:'https://example.org/box',valid_from:past,valid_until:future,
        geometry:{type:'BBox',coordinates:[[51,18],[54,22]]}},
      {id:'bad-circle',title:'Invalid geometry',valid_from:past,valid_until:future,
        geometry:{type:'Circle',center:[180,90],radius_km:-12}},
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
  assert.match(statuses,/Source-defined circle closure/);
  assert.match(statuses,/Source-defined box closure/);
  assert(!statuses.includes("Invalid geometry"));
  const areaTest=await page.evaluate(()=>{
    const layers=window.AtlasLayers;
    const circle=layers.drawableGeometry({type:"Circle",center:[52,20],radius_km:250});
    const box=layers.drawableGeometry({type:"BBox",coordinates:[[51,18],[54,22]]});
    const antiMeridian=layers.drawableGeometry({type:"Rectangle",coordinates:[[178,10],[-178,15]]});
    return {circle:circle?.coordinates?.[0]?.length,
      box:box?.coordinates?.[0]?.length,
      dateline:antiMeridian?.coordinates?.[0]?.length,
      invalid:layers.validGeometry({type:"Circle",center:[52,20],radius_km:-12})};
  });
  assert(areaTest.circle>=90&&areaTest.box>=5&&areaTest.dateline>=5);
  assert.equal(areaTest.invalid,false);
  // A region without a point anchor must still be selectable on the globe.
  await page.locator("#northView").click();
  await page.waitForTimeout(150);
  const rect=await page.locator("#globe").boundingBox();
  await page.mouse.click(rect.x+rect.width/2,rect.y+rect.height/2);
  assert.match(await page.locator("#selectedDetail").innerText(),/Airspace restrictions|closure/i);
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
