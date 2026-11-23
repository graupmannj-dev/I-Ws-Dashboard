const {chromium}=require("playwright");
const assert=require("node:assert/strict");
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:850}});
    const errors=[];page.on("pageerror",e=>errors.push(e.message));
    await page.route("**/hypotheses.json",async route=>{
      const response=await route.fetch(),data=await response.json();
      const item=data.hypotheses[0],hyp="The activity represents scheduled defensive training rather than attack preparations.";
      item.alternatives=[...(item.alternatives||[]).slice(0,1),hyp];
      item.analyst_hypotheses=[{id:"analyst-synthetic",index:2,origin:"analyst",
        statement:hyp,initial_backfill:{status:"interpretation_pending",
          limitations:["Only a bounded historical source sample was available"]}}];
      await route.fulfill({response,json:data});
    });
    await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded"});
    await page.locator("a.hypothesis-link").click();
    await page.waitForURL("**/hypotheses.html");
    await page.waitForFunction(()=>document.querySelectorAll(".case-tile").length>0);
    assert.match(await page.locator("#snapshotStatus").innerText(),/scenarios/);
    const total=await page.locator(".case-tile").count();
    assert.ok(total>=1);
    assert.match(await page.locator(".case-detail").innerText(),/Direction of reviewed evidence/i);
    assert.match(await page.locator(".case-detail").innerText(),/No reviewed directional evidence/i);
    assert.match(await page.locator(".case-detail").innerText(),/Analysis of competing hypotheses/i);
    assert.ok(await page.locator(".ach-table thead .analyst-origin").count()===1);
    const caution=page.locator(".ach-table thead .analyst-caution");
    assert.equal(await caution.count(),1);
    assert.equal(await caution.locator(".caution-popover").isVisible(),false);
    await caution.locator("summary").click();
    assert.equal(await caution.locator(".caution-popover").isVisible(),true);
    assert.match(await caution.locator(".caution-popover").innerText(),/bounded historical source sample/i);
    assert.match(await caution.locator("summary").getAttribute("aria-label"),/Evidence limitation/i);

    assert.match(await page.locator(".case-detail").innerText(),/Evidence families/i);
    assert.ok(await page.locator(".ach-family").count()>=1);
    await page.locator(".ach-family").first().click();
    assert.ok(await page.locator(".evidence-card").count()>=1);
    await page.locator(".evidence-card").first().locator("summary").click();
    assert.ok(await page.locator("#addHypothesis").count()===1);
    await page.locator("#addHypothesis").click();
    await page.locator("#analystHypText").fill("Routine cross-border exercises can explain this activity without preparations for offensive action.");
    assert.ok(await page.locator("#submitAnalystHyp").isVisible());
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
