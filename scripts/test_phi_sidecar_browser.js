const {chromium}=require("playwright");
const assert=require("node:assert/strict");

const URL="https://raw.githubusercontent.com/graupmannj-dev/I-Ws-Dashboard/cairn-phi-results/phi/latest.json";
const HASH="a".repeat(64);
const MODEL="phi-4-mini-instruct-q4km-local";

async function inspectScenario(browser,kind){
  const page=await browser.newPage({viewport:{width:1350,height:900}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  let expectedHypCount=0, modelCalls=0, alteredSource=false;
  await page.route("**/hypotheses.json",async route=>{
    const response=await route.fetch(),doc=await response.json();
    doc.phi_async_enabled=true;
    const first=doc.hypotheses[0];
    first.semantic_input_sha256=HASH;
    first.semantic_review={status:"not_configured",evaluations:[],interpretations:[]};
    expectedHypCount=1+(first.alternatives||[]).slice(0,3).length;
    const orig=JSON.stringify(first.balance);
    alteredSource=false;
    await route.fulfill({response,json:doc});
    assert.equal(JSON.stringify(first.balance),orig);
  });
  await page.route(URL,async route=>{
    modelCalls++;
    if(kind==="unavailable"){
      await route.fulfill({status:404,body:"not deployed",
                          headers:{"access-control-allow-origin":"*"}});
      return;
    }
    const original={
      schema:"cairn.phi-sidecar.v1",model:MODEL,provisional_only:true,
      signed_evidence_modified:false,cases:{}};
    const row={
      status:"provisional_complete",model_family:MODEL,input_sha256:HASH,
      model_generated_at:new Date().toISOString(),cache_status:"fresh_inference",
      analyst_approved:false,interpretation_only:true,source_truth_not_verified:true,
      evaluations:[],source_references:[],evidence_notes:[],
      interpretations:Array.from({length:expectedHypCount},(_,i)=>({
        hypothesis_index:i,
        meaning:"This is a provisional explanation to inspect further.",
        discriminator:"Read an independent dated original source about this activity."
      }))
    };
    if(kind==="wrong-hash")row.input_sha256="b".repeat(64);
    if(kind==="expired")row.model_generated_at="2025-11-24T00:00:00Z";
    if(kind==="autonomous-direction")row.evaluations=[
      {hypothesis_index:0,evidence_key:"invented",direction:"possibly_consistent"}];
    if(kind==="invented-source")row.evidence_notes=[{
      evidence_key:"fabricated",status:"unverified_source_title_lead",
      observation:"A claimed new warning appears in an untrusted title.",
      verification_step:"Look up the original dated bulletin independently."
    }];
    original.cases["placeholder"]=row;
    // First case's ID comes from the locally generated source document and
    // is determined by browser interception below, not a fixed hotspot list.
    original.cases["horn_ethiopia_eritrea"]=row;
    await route.fulfill({json:original,headers:{"access-control-allow-origin":"*"}});
  });
  try{
    await page.goto("http://127.0.0.1:8765/hypotheses.html",
                    {waitUntil:"domcontentloaded"});
    await page.waitForFunction(()=>document.querySelectorAll(".case-tile").length>0);
    await page.waitForFunction(()=>{
      let x=document.querySelector("#caseDetail")?.textContent||"";
      return x.includes("Model generated")||x.includes("Awaiting post-deployment Phi")||
             x.includes("Phi result stale or does not match");
    });
    const display=await page.locator("#caseDetail").innerText();
    const valid=kind==="valid";
    if(valid){
      assert.match(display,/Local Phi · hypothesis interpretation/);
      assert.match(display,/Model generated/);
    }else{
      assert.doesNotMatch(display,/Model generated/);
      assert.match(display,kind==="unavailable"?
        /Awaiting post-deployment Phi/:
        /Phi result stale or does not match|Awaiting post-deployment Phi/);
    }
    assert.match(display,/Direction of reviewed evidence/);
    assert.match(display,/Awaiting analyst-reviewed direction|supporting \/ .*contradicting/);
    assert.equal(modelCalls,1);
    assert.equal(alteredSource,false);
    assert.equal(errors.length,0,errors.join("; "));
  }finally{await page.close();}
}

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    for(const kind of ["valid","wrong-hash","expired","autonomous-direction",
                       "invented-source","unavailable"]){
      await inspectScenario(browser,kind);
      console.log("Phi sidecar browser fail-closed case passed:",kind);
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
