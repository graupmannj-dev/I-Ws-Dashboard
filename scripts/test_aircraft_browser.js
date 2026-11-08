/* Offline browser regression for optional ADSB.lol map filters.
 * All aircraft below are synthetic test objects. No external ADS-B requests.
 */
const {chromium}=require("playwright");
const assert=require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1450,height:900}});
  const jsErrors=[];
  page.on("pageerror",e=>jsErrors.push(e.message));
  const now=new Date().toISOString();
  const old=new Date(Date.now()-60*60*1000).toISOString();
  const common={lat:20,lon:52,observed_at:now,
                source:"ADSB.lol",url:"https://www.adsb.lol/docs/open-data/api"};
  const examples=[
    {...common,id:"a00001",title:"TESTF16",affiliation:"military",
      role_category:"combat",classification_basis:"Provider database military flag",
      aircraft_type:"F16"},
    {...common,id:"a00002",title:"TESTC130",affiliation:"military",
      role_category:"transport",classification_basis:"Provider database military flag",
      aircraft_type:"C130"},
    {...common,id:"a00003",title:"TEST738",affiliation:"civilian",
      role_category:"passenger",classification_basis:"Provider operator text suggests civil use",
      aircraft_type:"B738"},
    {...common,id:"a00004",title:"TESTNASA",affiliation:"civilian",
      role_category:"scientific",classification_basis:"Provider operator text suggests civil use",
      aircraft_type:"P3"},
    {...common,id:"a00005",title:"TESTUNKNOWN",affiliation:"unknown",
      role_category:"passenger",classification_basis:"No positive military or civil affiliation evidence",
      aircraft_type:"B738"},
    {...common,id:"a00006",title:"<img src=x onerror=alert(1)>",
      affiliation:"unknown",role_category:"unclassified"},
    {...common,id:"stale0",title:"SHOULD-NOT-BE-PLOTTED",affiliation:"military",
      role_category:"combat",observed_at:old},
  ];
  const makeLayer=records=>({version:1,generated_at:now,layers:{
    aircraft:{status:"snapshot",checked_at:now,records,source:"https://www.adsb.lol/docs/open-data/api",
      attribution:"ADSB.lol contributors · ODbL 1.0"},
    ships:{status:"not_configured",checked_at:null,records:[]},
    airspace:{status:"snapshot",checked_at:now,records:[]},
    maritime:{status:"snapshot",checked_at:now,records:[]},
    advisories:{status:"snapshot",checked_at:now,records:[]},
    embassies:{status:"snapshot",checked_at:now,records:[]}
  }});
  let live=makeLayer(examples);
  await page.route("**/atlas.json",async route=>{
    const response=await route.fetch();
    const data=await response.json();
    data.layer_feed.url="https://mock.aiba.invalid/api/layers";
    await route.fulfill({json:data});
  });
  await page.route("**/api/layers",route=>route.fulfill({json:live}));
  // Keep independent source histories out of this filter-focused regression.
  await page.route("**/aiba-feed-data/observations/latest/friction_briefs.json",
    route=>route.fulfill({status:404,body:"missing in test"}));
  await page.route("**/aiba-feed-data/observations/latest/live_layers.json",
    route=>route.fulfill({status:404,body:"missing in test"}));

  await page.goto("http://127.0.0.1:8765/",{waitUntil:"networkidle"});
  await page.waitForSelector("#layer-aircraft");
  assert.equal(await page.locator("#aircraftFilters").isHidden(),true,
    "Filter panel should stay collapsed until aircraft layer is enabled");
  await page.locator("#layer-aircraft").check();
  await page.waitForFunction(()=>!document.querySelector("#aircraftFilters").hidden);
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/2 plotted \/ 2 matching \/ 6 valid/);
  assert.match(await page.locator("#layerStatus").innerText(),/2 plotted \/ 2 matching \/ 6 valid/);
  assert.match(await page.locator("#layerStatus").innerText(),/ADSB.lol contributors/);
  // Military defaults on, others off. Platform class is a role hypothesis,
  // not the aircraft's present operation.
  assert.equal(await page.locator('[data-aircraft-group="military"]').isChecked(),true);
  assert.equal(await page.locator('[data-aircraft-group="civilian"]').isChecked(),false);
  assert.equal(await page.locator('[data-aircraft-group="unknown"]').isChecked(),false);
  await page.locator('[data-aircraft-category="military:combat"]').uncheck();
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/1 plotted \/ 1 matching/);
  assert(!((await page.locator("#layerStatus").innerText()).includes("TESTF16")));
  await page.locator('[data-aircraft-group="military"]').uncheck();
  await page.locator('[data-aircraft-group="civilian"]').check();
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/2 plotted \/ 2 matching/);
  await page.locator('details.aircraft-subtypes').nth(1).locator("summary").click();
  await page.locator('[data-aircraft-category="civilian:passenger"]').uncheck();
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/1 plotted \/ 1 matching/);
  await page.locator('[data-aircraft-group="unknown"]').check();
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/3 plotted \/ 3 matching/);
  assert.equal(await page.locator("#layerStatus img").count(),0,
    "Untrusted provider text must be escaped");
  await page.locator('details.aircraft-subtypes').nth(2).locator("summary").click();
  await page.locator('[data-aircraft-category="unknown:passenger"]').uncheck();
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/2 plotted \/ 2 matching/);

  // Cap is a visible display limit, NOT a claim that absent markers are
  // missing upstream. Every item in this fixture is still synthetic.
  live=makeLayer(Array.from({length:205},(_,i)=>({
    ...common,id:"b"+String(i).padStart(5,"0"),title:"SYNTHETIC",
    affiliation:"military",role_category:"transport"
  })));
  await page.locator('[data-aircraft-group="military"]').check();
  await page.evaluate(()=>window.AtlasLayers.refresh());
  await page.locator("#aircraftMarkerCap").selectOption("75");
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/75 plotted \/ 205 matching \/ 205 valid/);
  assert.match(await page.locator("#aircraftFilterCount").innerText(),/cap in effect/);
  await page.locator("#layer-aircraft").uncheck();
  assert.equal(await page.locator("#aircraftFilters").isHidden(),true);
  // Live source failure must not leave old aircraft painted as present.
  await page.route("**/api/layers",route=>route.fulfill({status:503,body:"unavailable"}));
  await page.evaluate(()=>window.AtlasLayers.refresh());
  await page.locator("#layer-aircraft").check();
  assert.match(await page.locator("#layerStatus").innerText(),/Feed unavailable|Not connected|unavailable/i);
  assert.equal(jsErrors.length,0,"Browser JS errors: "+jsErrors.join(" | "));
  console.log("ADSB.lol aircraft affiliation, subtype, cap, attribution, XSS and outage controls PASS");
  await browser.close();
})().catch(error=>{console.error(error);process.exit(1);});
