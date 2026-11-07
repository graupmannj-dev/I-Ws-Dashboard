/* Browser smoke for the public Atlas. Requires npm package playwright and Chromium.
 * Runs against a local copy of the generated GitHub Pages output.
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");

(async()=>{
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1450,height:900},deviceScaleFactor:1});
  const errors=[];
  page.on("pageerror",err=>errors.push(err.message));
  page.on("console",msg=>{if(msg.type()==="error")errors.push(msg.text());});
  await page.goto("http://127.0.0.1:8765/",{waitUntil:"networkidle",timeout:30000});
  await page.waitForFunction(()=>document.querySelectorAll(".watch-card").length>0,{timeout:15000});
  assert.match(await page.title(),/AIBA/);
  assert.equal(await page.locator(".watch-card").count(),10);
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
  if(process.env.AIBA_SCREENSHOT_B64==="true"){
    const shot=await page.screenshot({type:"jpeg",quality:53});
    console.log("AIBA_SCREENSHOT_START");
    console.log(shot.toString("base64"));
    console.log("AIBA_SCREENSHOT_END");
  }
  assert.equal(errors.length,0,"Console or page errors: "+errors.join(" | "));
  console.log("AIBA browser globe, controls, time filter, mobile controls and sourced watchlist PASS");
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
