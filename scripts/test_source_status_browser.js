const {chromium}=require("playwright");
const assert=require("node:assert/strict");
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:860}});
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    await page.route("**/atlas.json",async route=>{
      const res=await route.fetch(), data=await res.json();
      data.visibility_funnel={
        ...(data.visibility_funnel||{}),
        provider_health:[
          {name:"ioda",status:"current",asof:new Date().toISOString(),
            scope:"IODA limited country sample"},
          {name:"live_maritime",status:"stale_or_unavailable",
            asof:"2020-01-01T00:00:00Z",scope:"NIORD"},
          {name:"nga",status:"stale_or_unavailable",asof:null,scope:"NGA"},
        ],
      };
      await route.fulfill({response:res,json:data});
    });
    await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded"});
    await page.waitForSelector("#watchlist");
    assert.equal(await page.locator("#faaNasPanel").count(),0,
      "FAA panel must not consume the evidence rail");
    assert.equal(await page.locator("a.source-health-link").count(),1);
    assert.ok(await page.locator(".watch-heading").evaluate(x=>x.getBoundingClientRect().height)<140,
      "Evidence family navigation should be compact");
    assert.ok(await page.locator("#watchlist").evaluate(x=>x.getBoundingClientRect().height)>=215,
      "The scrollable evidence region must remain readable");
    await page.locator("a.source-health-link").click();
    await page.waitForURL("**/sources.html");
    await page.waitForFunction(()=>document.querySelectorAll("#sourceRows tr").length>=3);
    const text=await page.locator("#sourceRows").innerText();
    assert.match(text,/IODA connectivity/i);
    assert.match(text,/FAA temporary flight restrictions/i);
    assert.match(text,/GDELT news\/event index/i);
    assert.match(text,/collects|measurements|connectivity/i);
    assert.match(text,/Alternative indicator/i);
    assert.match(text,/Context and corroboration/i);
    assert.match(text,/neither objective conflict probabilities|objective conflict probabilities/i);
    assert.match(text,/News\/event-index background|indexes worldwide news coverage/i);
    assert.match(text,/Selected airport sample|monitored sample/i);
    assert.match(await page.locator(".brand").innerText(),/CAIRN/i);
    assert.ok(await page.locator(".source-description").count()>=10);
    assert.match(text,/Stale \/ unavailable/i);
    assert.match(await page.locator("#sourceAsOf").innerText(),/published Atlas snapshot/i);
    await page.locator("#sourceRefresh").click();
    await page.waitForFunction(()=>!document.querySelector("#sourceRefresh").disabled);
    assert.equal(errors.length,0,"Browser JS errors: "+errors.join("; "));
    console.log("Source health page and compact evidence rail PASS");
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});