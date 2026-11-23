#!/usr/bin/env python3
"""Second-stage CAIRN shadow benchmark: controlled ACH gold + real archival abstention.

No production writes, no event truth inferred from archival titles. Strict JSON
schema mode separately measures whether output-format failures can be remedied.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import resource
import statistics
import time
from urllib import request, error
from scripts.benchmark_local_ach_models import select_cases, digest

DIRECTIONS=("possibly_consistent","possibly_inconsistent","non_diagnostic","unresolved")
SCHEMA={"type":"object","properties":{
  "evaluations":{"type":"array","minItems":2,"maxItems":2,
    "items":{"type":"object","properties":{
      "hypothesis_index":{"type":"integer"},
      "evidence_key":{"type":"string"},
      "direction":{"type":"string","enum":list(DIRECTIONS)},
      "rationale":{"type":"string"}},"required":["hypothesis_index","evidence_key","direction","rationale"],
      "additionalProperties":False}},
  "discriminator":{"type":"string"},
  "coverage_limitations":{"type":"string"},
  "source_independence_established":{"type":"boolean"},
  "event_verified":{"type":"boolean"}},
  "required":["evaluations","discriminator","coverage_limitations",
              "source_independence_established","event_verified"],
  "additionalProperties":False}
SYSTEM=("Analyze two competing hypotheses against the supplied evidence ONLY. "
  "The archive title is an unverified source claim, not a verified incident. "
  "Controlled scenario facts are explicitly fictional and supplied for this test; "
  "do not claim those events occurred. Evidence can fit multiple hypotheses. "
  "Directions: possibly_consistent = evidence favors or is consistent with claim; "
  "possibly_inconsistent = evidence is incompatible with claim; "
  "non_diagnostic = evidence does not meaningfully distinguish claim; "
  "unresolved = too little reliable data for sign. "
  "Do not manufacture primary corroboration, independent sources, actors or intent. "
  "An absent observation is not a contradiction unless detection capability is established. "
  "Return two evaluations (indexes 0 and 1), source key exactly as supplied, "
  "specific rationale, concrete next discriminator, coverage limits, "
  "and source_independence_established=false and event_verified=false "
  "unless the evidence EXPLICITLY demonstrates either.")
HYPOTHESES=[
  "The observed activity represents preparations for imminent offensive military action.",
  "The observed activity reflects routine training or non-hostile operations."
]
def example(record,i,kind,case_label):
    return {"id":f"{kind}-{i}-{case_label}","kind":kind,
      "evidence_key":"cairn:"+str(record["id"]),
      "source_title":record["title"],"source_url":record["url"],
      "source_root_hash":record["root_hash"],
      "hypotheses":list(HYPOTHESES),"case_label":case_label,
      "verified_event":False,"independent_corroboration":False}

def dataset(records):
    if len(records)<6: raise ValueError("Need >=6 actual retained source records")
    out=[]
    for i,r in enumerate(records[:6]):
        x=example(r,i,"real","title_only")
        x["evidence"]={"archive_title":r["title"],
           "description":"Single retained source title. No original-document verification, primary-source attribution, or reliable completeness information."}
        x["allowed"]=[["unresolved","non_diagnostic"],["unresolved","non_diagnostic"]]
        out.append(x)
    # Counterfactual *explicit* stipulations allow gold scoring, while retaining
    # traceable actual CAIRN source titles as the background stimulus.
    tests=[
      ("scheduled_notice",
       "CONTROLLED, FICTIONAL STIPULATION: An authenticated official exercise schedule issued 30 days before the activity explicitly lists the same unit, time, geographic polygon, and exercise designation. No hostile intent is alleged.",
       ["non_diagnostic","possibly_consistent"],False,False),
      ("stated_attack_order",
       "CONTROLLED, FICTIONAL STIPULATION: The supplied primary-source document is an authenticated order explicitly directing an offensive cross-border attack at the stated location and time; it rules out a scheduled exercise. This is ONE authenticated source, not independent corroboration.",
       ["possibly_consistent","possibly_inconsistent"],True,False),
      ("syndicated_relay",
       "CONTROLLED, FICTIONAL STIPULATION: Five headlines repeat the same original anonymous account with identical claims. No additional sources or documents exist in the packet.",
       ["non_diagnostic","non_diagnostic"],False,False),
      ("no_reports",
       "CONTROLLED, FICTIONAL STIPULATION: This packet has no relevant observations. Collection completeness and sensor detection probability are unknown.",
       ["unresolved","unresolved"],False,False),
      ("confirmed_activity_ambiguous_cause",
       "CONTROLLED, FICTIONAL STIPULATION: A single official notice verifies that a maritime exclusion zone was posted, but provides no exercise schedule, intent, or force deployment facts.",
       ["non_diagnostic","non_diagnostic"],False,True),
      ("false_claim_correction",
       "CONTROLLED, FICTIONAL STIPULATION: A published photograph in a viral claim is conclusively documented as a photo from a different country five years earlier. No other evidence concerning current military activity is present.",
       ["non_diagnostic","non_diagnostic"],False,False),
      ("preannounced_cancelled",
       "CONTROLLED, FICTIONAL STIPULATION: An authenticated prior exercise schedule explicitly states that the advertised exercise was cancelled before the observation. The source title claims a restriction, but gives no offensive preparations or intent.",
       ["non_diagnostic","possibly_inconsistent"],False,False),
      ("unrelated_environmental_event",
       "CONTROLLED, FICTIONAL STIPULATION: The observation is explicitly an earthquake-driven civilian evacuation and weather-related airspace closure with verified geophysical cause. No military presence is described.",
       ["non_diagnostic","non_diagnostic"],False,False),
    ]
    for i,(label,stip,gold,verified,independent) in enumerate(tests):
        x=example(records[i%len(records)],i,"controlled",label)
        x["evidence"]={"archive_title":x["source_title"],
           "controlled_fictional_context":stip,
           "context_is_not_historical_event_evidence":True}
        x["allowed"]=[[gold[0]],[gold[1]]]
        x["verified_event"]=verified
        x["independent_corroboration"]=independent
        out.append(x)
    return out

def ask(server,item,mode,timeout,max_tokens):
    system=SYSTEM
    body={"id":item["id"],"evidence_key":item["evidence_key"],
      "evidence":item["evidence"],"hypotheses":item["hypotheses"],
      "source_scope":"No additional sources; do not consult external knowledge"}
    fields={"model":"local","temperature":0,"max_tokens":max_tokens,
            "messages":[{"role":"system","content":system},
                        {"role":"user","content":json.dumps(body,ensure_ascii=False)}]}
    if mode=="constrained":
        fields["response_format"]={"type":"json_schema","json_schema":{"name":"cairn_ach_result","strict":True,"schema":SCHEMA}}
    else:
        fields["response_format"]={"type":"json_object"}
    req=request.Request(server.rstrip("/")+"/v1/chat/completions",
        data=json.dumps(fields).encode(),method="POST",
        headers={"Content-Type":"application/json"})
    with request.urlopen(req,timeout=timeout) as resp:
        response=json.load(resp)
    return response["choices"][0]["message"]["content"],response.get("usage",{})

def grade(content,item):
    try: v=json.loads(content)
    except (TypeError,ValueError):
        return {"json_valid":False,"schema_valid":False,"gold_correct":False,
                "source_fidelity":False,"epistemic_flags":False,"error":"invalid_json"}
    if not isinstance(v,dict):
        return {"json_valid":True,"schema_valid":False,"gold_correct":False,
                "source_fidelity":False,"epistemic_flags":False,"error":"non_object"}
    rows=v.get("evaluations")
    valid=(isinstance(rows,list) and len(rows)==2 and
           all(isinstance(r,dict) and type(r.get("hypothesis_index")) is int
             and r.get("hypothesis_index")==i
             and r.get("direction") in DIRECTIONS
             and isinstance(r.get("rationale"),str) and len(r["rationale"])>=15
             and isinstance(r.get("evidence_key"),str) for i,r in enumerate(rows))
           and isinstance(v.get("coverage_limitations"),str)
           and isinstance(v.get("discriminator"),str) and len(v["discriminator"])>=12
           and type(v.get("event_verified")) is bool
           and type(v.get("source_independence_established")) is bool)
    fidelity=bool(valid and all(r["evidence_key"]==item["evidence_key"] for r in rows))
    accurate=bool(fidelity and all(r["direction"] in item["allowed"][i] for i,r in enumerate(rows)))
    flags=bool(valid and v["event_verified"]==item["verified_event"] and
        v["source_independence_established"]==item["independent_corroboration"])
    return {"json_valid":True,"schema_valid":bool(valid),
      "source_fidelity":fidelity,"gold_correct":accurate,"epistemic_flags":flags,
      "predicted_directions":[r.get("direction") for r in rows] if isinstance(rows,list) else [],
      "expected_allowed":item["allowed"],
      "model_rationales":[r.get("rationale","")[:260] for r in rows] if isinstance(rows,list) else [],
      "discriminator":str(v.get("discriminator",""))[:360],
      "coverage_limitations":str(v.get("coverage_limitations",""))[:320],
      "event_verified":v.get("event_verified"),
      "source_independence_established":v.get("source_independence_established")}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",required=True)
    p.add_argument("--model-name",required=True)
    p.add_argument("--mode",choices=["constrained","json_object"],default="constrained")
    p.add_argument("--server",default="http://127.0.0.1:8080")
    p.add_argument("--output",required=True)
    p.add_argument("--max-tokens",type=int,default=700)
    p.add_argument("--timeout",type=int,default=170)
    a=p.parse_args()
    archive=json.loads(Path(a.archive).read_text())
    records,inventory=select_cases(archive)
    items=dataset(records)
    results=[]
    for item in items:
        started=time.monotonic()
        try:
            content,usage=ask(a.server,item,a.mode,a.timeout,a.max_tokens)
            assessed=grade(content,item)
            status="completed"
        except (ValueError,TimeoutError,OSError,error.URLError,KeyError,IndexError) as exc:
            assessed={"json_valid":False,"schema_valid":False,"source_fidelity":False,
                      "gold_correct":False,"epistemic_flags":False,"error":type(exc).__name__}
            status="failed";usage={}
        elapsed=round(time.monotonic()-started,2)
        results.append({"id":item["id"],"kind":item["kind"],
          "source_id":item["evidence_key"],"source_title":item["source_title"],
          "duration_sec":elapsed,"completion_tokens":usage.get("completion_tokens"),
          "status":status,**assessed})
        print("QUALITY_CASE "+json.dumps({"id":item["id"],"status":status,
          "gold":assessed.get("gold_correct"),"schema":assessed.get("schema_valid"),
          "seconds":elapsed}),flush=True)
    metrics={name:{"success":sum(bool(x.get(name)) for x in results),"total":len(results)}
       for name in ("json_valid","schema_valid","source_fidelity","gold_correct","epistemic_flags")}
    output={"schema":"cairn.local-llm-ach-quality.v2",
      "model":a.model_name,"mode":a.mode,"model_prompt_version":"cairn-ach-quality-v2",
      "created_at":dt.datetime.now(dt.timezone.utc).isoformat(),
      "archive_sha256":hashlib.sha256(Path(a.archive).read_bytes()).hexdigest(),
      "probe_sha256":digest(items),"inventory":inventory,
      "controlled_probe_count":sum(i["kind"]=="controlled" for i in items),
      "real_archive_probe_count":sum(i["kind"]=="real" for i in items),
      "not_real_world_event_ground_truth":True,
      "quality_rule":"Exact controlled stipulation gold; real source-title abstention",
      "metrics":metrics,
      "mean_duration_sec":round(statistics.mean(x["duration_sec"] for x in results),2),
      "total_duration_sec":round(sum(x["duration_sec"] for x in results),2),
      "python_peak_rss_kb":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      "cases":results}
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n")
    print("QUALITY_SUMMARY "+json.dumps({k:v for k,v in output.items() if k!="cases"}),flush=True)
if __name__=="__main__":main()
