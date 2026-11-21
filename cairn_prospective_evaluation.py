#!/usr/bin/env python3
"""CAIRN offline ex-ante forecast/evaluation audit, never inferred from alerts.

Only explicitly supplied, frozen risk windows, timestamped predictions, and
independently adjudicated outcomes are valid. No current CAIRN source history
alone supplies an event/quiet label, forecast probability, or false alarm.
Production publishes ONLY a zero-disclosure readiness contract.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import statistics

UTC=dt.timezone.utc
RISK_SCHEMA="cairn.prospective-risk-set.v1"
PRED_SCHEMA="cairn.prospective-forecasts.v1"
REPORT_SCHEMA="cairn.prospective-warning-evaluation.v1"
MIN_WINDOWS=20
MIN_EVENT=5
MIN_NON_EVENT=5
MAX_WINDOWS=10000

METRIC_NAMES=("true_positive_alert_windows","false_positive_alert_windows",
  "false_negative_event_windows","true_negative_quiet_windows",
  "precision","recall","false_alerts_per_100_adjudicated_windows",
  "median_verified_lead_hours","median_prepublication_lead_hours",
  "baseline_brier","augmented_brier","paired_brier_improvement")

def utc(value):
    if not isinstance(value,str):return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(UTC) if t.tzinfo is not None else None
    except ValueError:return None

def probability(value):
    return type(value) in (float,int) and math.isfinite(value) and 0<=value<=1

def unavailable(status,reason=None,checked_at=None):
    return {"schema":REPORT_SCHEMA,"status":status,"generated_at":checked_at,
            "evaluated_windows":0,"eligible_registered_windows":0,
            "metrics":{key:None for key in METRIC_NAMES},
            "private_source_material_published":False,
            "forecast_skill_claim_approved":False,
            "reason":reason or "No registered eligible risk set and prospective forecast/outcome ledger"}

def evaluate(risk,forecast,asof):
    """Evaluate complete, frozen windows. Refuse retrospective score leakage."""
    now=utc(asof) if isinstance(asof,str) else asof
    if not isinstance(now,dt.datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware as-of is mandatory")
    now=now.astimezone(UTC)
    if not isinstance(risk,dict) or risk.get("schema")!=RISK_SCHEMA or not isinstance(risk.get("windows"),list):
        raise ValueError("Risk-set schema mismatch")
    if not isinstance(forecast,dict) or forecast.get("schema")!=PRED_SCHEMA or not isinstance(forecast.get("forecasts"),list):
        raise ValueError("Forecast-log schema mismatch")
    rows=risk["windows"]; preds=forecast["forecasts"]
    if not rows or len(rows)>MAX_WINDOWS or len(preds)!=len(rows):
        raise ValueError("Explicit one-to-one risk-set and predictions required")
    raw_by={}
    for p in preds:
        if not isinstance(p,dict) or not isinstance(p.get("window_id"),str):
            raise ValueError("Invalid forecast ID")
        ident=p["window_id"]
        if ident in raw_by:raise ValueError("Duplicate forecast window")
        raw_by[ident]=p
    seen=set(); outcomes=[]; missing=0; events=non_events=0
    for row in rows:
        if not isinstance(row,dict):raise ValueError("Invalid risk-set entry")
        ident=row.get("id")
        if not isinstance(ident,str) or not ident or len(ident)>140 or ident in seen:
            raise ValueError("Missing or duplicate risk window")
        seen.add(ident)
        p=raw_by.get(ident)
        if not isinstance(p,dict):raise ValueError("Unmatched registered forecast")
        begin,end=utc(row.get("start_at")),utc(row.get("end_at"))
        issued=utc(p.get("issued_at"))
        if not begin or not end or not issued or begin>=end or issued>begin or end>now:
            raise ValueError("Forecast not sealed before risk window, or clock invalid")
        if type(p.get("alert")) is not bool:
            raise ValueError("Forecast alert flag must be explicitly Boolean")
        if not isinstance(p.get("model_version"),str) or not p["model_version"]:
            raise ValueError("Frozen pre-event model identity mandatory")
        probs=(p.get("baseline_probability"),p.get("augmented_probability"))
        if (probs[0] is None)!=(probs[1] is None):
            raise ValueError("Ablation requires BOTH frozen probability forecasts")
        if any(x is not None and not probability(x) for x in probs):
            raise ValueError("Probability forecasts must be finite [0,1]")
        outcome=row.get("outcome")
        coverage=row.get("outcome_coverage_audited")
        adj=utc(row.get("adjudicated_at"))
        doc=row.get("adjudication_reference")
        if outcome not in ("event","no_event","pending"):
            raise ValueError("Explicit outcome enum mandatory")
        if outcome=="pending" or coverage is not True or adj is None or adj>now or not (
            isinstance(doc,str) and doc.startswith("https://") and len(doc)<1600):
            missing+=1
            continue
        if outcome=="no_event":
            if adj<end or row.get("event_onset_at") is not None:
                raise ValueError("No-event outcome not adjudicated past risk window")
            non_events+=1
            onset=published=None
            actual=0
        else:
            onset=utc(row.get("event_onset_at"))
            published=utc(row.get("first_public_report_at"))
            if not onset or not begin<=onset<end or adj<onset:
                raise ValueError("Event onset/adjudication chronology invalid")
            if published and published>now:raise ValueError("Future public report")
            events+=1;actual=1
        outcomes.append((ident,p,actual,issued,onset,published))
    if set(raw_by)!=seen:raise ValueError("Unregistered forecast outside risk set")
    if missing:
        v=unavailable("risk_set_outcomes_incomplete",
            "Some windows have missing, unreviewed, or non-exhaustive outcomes; cannot infer quiet periods",
            now.isoformat())
        v["registered_windows"]=len(rows)
        v["unadjudicated_or_inadequately_covered_windows"]=missing
        return v
    if len(outcomes)<MIN_WINDOWS or events<MIN_EVENT or non_events<MIN_NON_EVENT:
        v=unavailable("insufficient_verified_outcomes",
            "Require >=20 independently adjudicated windows with >=5 event and >=5 no-event outcomes",
            now.isoformat())
        v["registered_windows"]=len(rows)
        v["verified_event_windows"]=events
        v["verified_no_event_windows"]=non_events
        return v
    tp=fp=fn=tn=0
    lead=[];prepublic=[]
    baseline_losses=[];augmented_losses=[]
    for ident,p,actual,issued,onset,published in outcomes:
        alert=p["alert"]
        if actual and alert:
            tp+=1
            lead.append((onset-issued).total_seconds()/3600)
            if published and issued<published:
                prepublic.append((published-issued).total_seconds()/3600)
        elif actual:fn+=1
        elif alert:fp+=1
        else:tn+=1
        if p.get("baseline_probability") is not None:
            baseline_losses.append((p["baseline_probability"]-actual)**2)
            augmented_losses.append((p["augmented_probability"]-actual)**2)
    brier_base=statistics.mean(baseline_losses) if len(baseline_losses)==len(outcomes) else None
    brier_new=statistics.mean(augmented_losses) if len(augmented_losses)==len(outcomes) else None
    return {
      "schema":REPORT_SCHEMA,"status":"completed_private_evaluation",
      "generated_at":now.isoformat(),"evaluated_windows":len(outcomes),
      "eligible_registered_windows":len(rows),
      "verified_event_windows":events,"verified_no_event_windows":non_events,
      "metrics":{
        "true_positive_alert_windows":tp,"false_positive_alert_windows":fp,
        "false_negative_event_windows":fn,"true_negative_quiet_windows":tn,
        "precision":round(tp/(tp+fp),4) if tp+fp else None,
        "recall":round(tp/(tp+fn),4) if tp+fn else None,
        "false_alerts_per_100_adjudicated_windows":round(100*fp/len(outcomes),3),
        "median_verified_lead_hours":round(statistics.median(lead),2) if lead else None,
        "median_prepublication_lead_hours":round(statistics.median(prepublic),2) if prepublic else None,
        "baseline_brier":round(brier_base,5) if brier_base is not None else None,
        "augmented_brier":round(brier_new,5) if brier_new is not None else None,
        "paired_brier_improvement":round(brier_base-brier_new,5)
             if brier_base is not None and brier_new is not None else None,
      },
      "public_reporting_authorized":False,
      "private_source_material_published":False,
      "forecast_skill_claim_approved":False,
      "ablation_requires_same_predeclared_cases":True,
      "no_inference_from_unobserved_quiet_time":True,
      "explanation":"Paired retrospective performance evaluation of pre-issued frozen forecasts only; no public forecast claims until independent audit."
    }

def cli():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--risk-set",type=Path)
    p.add_argument("--forecasts",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--readiness-only",action="store_true")
    args=p.parse_args()
    if args.readiness_only:
        report=unavailable("no_connected_signed_prospective_outcomes",
            "No private forecasts or verified risk-set outcomes are connected; all skill metrics unavailable",
            dt.datetime.now(UTC).isoformat())
    else:
        if not args.risk_set or not args.forecasts or not args.output:
            p.error("Risk set, forecasts, and explicit private output path required")
        if args.output.resolve().is_relative_to(Path.cwd().resolve()):
            p.error("Refuse to write potentially sensitive evaluation output in public source tree")
        with args.risk_set.open() as fh:risk=json.load(fh)
        with args.forecasts.open() as fh:forecasts=json.load(fh)
        report=evaluate(risk,forecasts,dt.datetime.now(UTC))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+"\n")
    else:
        print(json.dumps(report,indent=2))

if __name__=="__main__":cli()
