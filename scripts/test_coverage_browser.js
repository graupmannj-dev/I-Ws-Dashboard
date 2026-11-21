const {chromium}=require("playwright");
const assert=require("node:assert/strict");
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1380,height:850}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded"});
  await page.locator("a.coverage-link").click();
  await page.waitForURL("**/coverage.html");
  await page.waitForFunction(()=>document.querySelectorAll(".source-card").length>=20);
  assert.match(await page.locator("#coverageSummary").innerText(),/Documented source modes/i);
  assert.match(await page.locator(".disclaimer").innerText(),/specific falsifiable prediction/i);
  const total=await page.locator(".source-card").count();
  await page.locator("#coverageClass").selectOption("global_unlocated");
  assert.ok((await page.locator(".source-card").count()) < total);
  assert.match(await page.locator("#sourceList").innerText(),/wiki edits/i);
  await page.locator("#coverageClass").selectOption("national_sample");
  await page.locator("#coverageSearch").fill("sg_mpa");
  assert.equal(await page.locator(".source-card").count(),1);
  await page.locator(".source-card summary").first().click();
  assert.match(await page.locator(".source-card").first().innerText(),/Not established/i);
  await page.locator("#coverageSearch").fill("");
  await page.locator("#coverageClass").selectOption("all");
  assert.equal(await page.locator(".source-card").count(),total);
  assert.equal(errors.length,0,errors.join("; "));
  console.log("CAIRN source geography and missingness browser checks PASS");
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});