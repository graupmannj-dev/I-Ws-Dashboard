/* Stable four-page CAIRN navigation and mobile Atlas controls. */
const {chromium}=require("playwright");
const assert=require("node:assert/strict");

const pages=[
  {url:"/", key:"atlas"},
  {url:"/hypotheses.html", key:"hypotheses"},
  {url:"/sources.html", key:"sources"},
  {url:"/coverage.html", key:"coverage"}
];
const expected=[
  {key:"atlas",href:"./",text:"Atlas"},
  {key:"hypotheses",href:"hypotheses.html",text:"Hypotheses"},
  {key:"sources",href:"sources.html",text:"Sources & status"},
  {key:"coverage",href:"coverage.html",text:"Coverage & gaps"}
];
const origin="http://127.0.0.1:8765";
(async()=>{
  const browser=await chromium.launch({headless:true});
  try {
    for(const viewport of [{width:1440,height:850},{width:760,height:850},{width:390,height:800}]){
      const page=await browser.newPage({viewport});
      const errors=[];page.on("pageerror",e=>errors.push(e.message));
      const positions=[];
      for(const target of pages){
        await page.goto(origin+target.url,{waitUntil:"domcontentloaded"});
        const links=page.locator(".cairn-topbar nav.cairn-nav a");
        assert.equal(await links.count(),4,"Four stable page destinations");
        assert.equal(await page.locator(".cairn-nav[aria-label='Primary navigation']").count(),1);
        for(let i=0;i<expected.length;i++){
          const link=links.nth(i),want=expected[i];
          assert.equal(await link.getAttribute("data-nav"),want.key);
          assert.equal(await link.getAttribute("href"),want.href);
          assert.equal((await link.innerText()).replace(/\s+/g," ").trim(),want.text);
          assert.equal(await link.getAttribute("aria-current"),
                       target.key===want.key?"page":null);
          assert.equal(await link.isVisible(),true,"Destination hidden at "+viewport.width);
        }
        assert.equal(await page.locator(".cairn-nav [aria-current='page']").count(),1);
        const geom=await page.locator(".cairn-nav").evaluate(e=>{
          const r=e.getBoundingClientRect();
          const h=e.closest(".cairn-topbar").getBoundingClientRect();
          return {x:r.x,y:r.y,width:r.width,height:r.height,
                  relativeX:r.x-h.x,relativeY:r.y-h.y,headerHeight:h.height};
        });
        positions.push(geom);
        assert.ok(geom.width>250,"Navigation too narrow");
        assert.ok(geom.x>=0&&geom.x+geom.width<=viewport.width+2,
                  "Navigation clipped horizontally");
        // Ensure no visual page-specific header metrics shift the primary navigation.
        if(target.key==="atlas"){
          assert.equal(await page.locator("#collectorHealth").count(),0,
                       "Duplicated source health should not exist in Atlas sidebar");
          assert.equal(await page.getByText("Collection health and source times").count(),0);
          assert.equal(await page.locator(".atlas-meta #kpiAsOf").count(),1,
                       "Atlas-specific summary remains available below shared header");
          assert.equal(await page.locator("#discoveryLeads").count(),1,
                       "Unlocated discovery UI must still load");
          if(viewport.width<=480){
            await page.locator("#openControls").click();
            assert.equal(await page.locator("#sidebar").isVisible(),true);
            await page.locator("#openControls").click();
            assert.equal(await page.locator("#sidebar").isVisible(),false);
          }
        }
      }
      for(const geo of positions.slice(1)){
        assert.ok(Math.abs(geo.relativeX-positions[0].relativeX)<=2,
                  "Navigation x shifts relative to header: "+JSON.stringify(positions));
        assert.ok(Math.abs(geo.relativeY-positions[0].relativeY)<=2,
                  "Navigation y shifts relative to header: "+JSON.stringify(positions));
        assert.ok(Math.abs(geo.headerHeight-positions[0].headerHeight)<=2,
                  "Header heights differ: "+JSON.stringify(positions));
        assert.ok(Math.abs(geo.width-positions[0].width)<=2,
                  "Navigation width shifts: "+JSON.stringify(positions));
      }
      // Direct, bidirectional cross-page navigation from Sources to Hypotheses.
      await page.goto(origin+"/sources.html",{waitUntil:"domcontentloaded"});
      await page.locator(".cairn-nav [data-nav='hypotheses']").click();
      await page.waitForURL("**/hypotheses.html");
      assert.equal(await page.locator(".cairn-nav [aria-current='page']").getAttribute("data-nav"),
                   "hypotheses");
      await page.locator(".cairn-nav [data-nav='sources']").click();
      await page.waitForURL("**/sources.html");
      assert.equal(await page.locator(".cairn-nav [aria-current='page']").getAttribute("data-nav"),
                   "sources");
      assert.deepEqual(errors,[],"Browser page errors: "+errors.join("; "));
      await page.close();
    }
    console.log("CAIRN shared navigation: desktop/tablet/phone, position stable, active states, source-hypothesis links, sidebar dedup, mobile Layers PASS");
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
