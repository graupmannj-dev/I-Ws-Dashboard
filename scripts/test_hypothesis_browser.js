const {chromium}=require("playwright");
const assert=require("node:assert/strict");
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:850}});
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded"});
    await page.locator("a.hypothesis-link").click();
    await page.waitForURL("**/hypotheses.html");
    await page.waitForFunction(()=>document.querySelectorAll(".case-tile").length>0);
    assert.match(await page.locator("#snapshotStatus").innerText(),/scenarios/);
    const total=await page.locator(".case-tile").count();
    assert.ok(total>=1);
    assert.match(await page.locator(".case-detail").innerText(),/Direction of reviewed evidence/i);
    assert.match(await page.locator(".case-detail").innerText(),/No reviewed directional evidence/i);
    assert.match(await page.locator(".case-detail").innerText(),/Alternative explanatory hypotheses/i);
    assert.match(await page.locator(".case-detail").innerText(),/Families of evidence/i);
    assert.ok(await page.locator(".evidence-card").count()>=1);
    await page.locator(".evidence-card").first().locator("summary").click();
    assert.match(await page.locator(".evidence-card").first().innerText(),/Source check/i);
    assert.match(await page.locator(".evidence-card").first().innerText(),/historical_reference_not_live|Historical/i);
    const searchable=await page.locator(".case-tile").first().locator("strong").innerText();
    await page.locator("#caseSearch").fill(searchable);
    assert.ok(await page.locator(".case-tile").count()>=1);
    await page.locator("#caseFilter").selectOption("reviewed");
    assert.equal(await page.locator(".case-tile").count(),0);
    await page.locator("#caseFilter").selectOption("all");
    await page.locator("#caseSearch").fill("");
    assert.equal(await page.locator(".case-tile").count(),total);
    await page.locator(".case-tile").last().click();
    assert.match(await page.locator(".case-detail h2").innerText(),/./);
    assert.equal(errors.length,0,"Hypothesis browser errors: "+errors.join("; "));
    console.log("CAIRN hypothesis workspace browser: cases, evidence drilldown, source health, alternatives, unreviewed balance and controls PASS");
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
