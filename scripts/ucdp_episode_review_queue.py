#!/usr/bin/env python3
"""Create auditable episode-to-GDELT nomination queue (NOT scored matches).

An entity's country exposure is not evidence that a GDELT bilateral
country pair fought in a given UCDP actor dyad. Two named independent
reviews are required before any linkage can be accepted.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.gdelt_shadow_monitor import analyze_day
from scripts.gdelt_retrospective_eval import country_crosswalk,load_history
from scripts.ucdp_episode_labels import RELEASE_END, produce

HORIZON=7


def countries_in_case(case):
    parts=case.split(":")
    if parts[0]=="BILAT" and len(parts)==3:
        return set(parts[1:])
    if parts[0]=="DOMESTIC" and len(parts)==2:
        return {parts[1]}
    raise ValueError(f"Unsupported GDELT aggregate key {case!r}")


def prior_flags(by_day, first, last):
    """Replay a full 90 calendar days before each as-of date, never t+1."""
    cache={}
    for index in range((last-first).days+1):
        day=first+dt.timedelta(days=index)
        if day not in by_day:
            continue
        shadow=analyze_day(by_day,day)
        if shadow["baseline"]["expected_days"]!=90 or shadow["baseline"]["valid_days"]!=90:
            continue
        if not shadow["baseline"]["eligible"]:
            continue
        cache[day]=shadow
    return cache


def build_queue(episodes, history, xwalk, max_per_episode=5):
    if max_per_episode < 1 or max_per_episode>20:
        raise ValueError("1–20 candidates per episode; constrain review burden")
    by_day, fingerprint=load_history(history)
    crosswalk=country_crosswalk(xwalk)
    names_to_code={name:code for code,name in crosswalk.items()}
    first_day=min(by_day);last_day=max(by_day)
    if not episodes:
        raise ValueError("No episode candidates; inspect source labels/filters before making a comparison")
    episode_dates=[dt.date.fromisoformat(e["date"]) for e in episodes]
    valid_episodes=[e for e in episodes if e["country"] in names_to_code
                    and first_day<=dt.date.fromisoformat(e["date"])<=last_day]
    if not valid_episodes:
        raise ValueError("No episode countries match the preselected UCDP-to-GDELT crosswalk")
    first=max(first_day+dt.timedelta(days=90),
              min(dt.date.fromisoformat(e["date"]) for e in valid_episodes)-dt.timedelta(days=HORIZON))
    last=min(last_day,max(dt.date.fromisoformat(e["date"]) for e in valid_episodes)-dt.timedelta(days=1))
    flags=prior_flags(by_day,first,last) if first<=last else {}
    reviewed=[],Counter()
    counts=Counter()
    for e in valid_episodes:
        eday=dt.date.fromisoformat(e["date"])
        country=names_to_code[e["country"]]
        links=[]
        eligible_days=0
        for n in range(1,HORIZON+1):
            lead=eday-dt.timedelta(days=n)
            obs=flags.get(lead)
            if obs is None:
                continue
            eligible_days+=1
            for kind,group in (("established",obs["established_leads"]),("sparse",obs["emerging_leads"])):
                for lead_case in group:
                    if country not in countries_in_case(lead_case["case"]):
                        continue
                    links.append({
                        "episode_id":e["episode_id"],"episode_date":e["date"],
                        "episode_kind":e["type"],"ucdp_country":e["country"],
                        "ucdp_dyad_new_id":e["dyad_new_id"],
                        "ucdp_dyad_name":e["dyad_name"],
                        "gdelt_case":lead_case["case"],
                        "gdelt_asof_date":lead.isoformat(),
                        "lead_days":n,"signal_kind":kind,
                        "gdelt_current_count":lead_case["current_count"],
                        "gdelt_ratio_to_baseline":lead_case["ratio_to_baseline"],
                        "comparison_type":"country_exposure_overlap_only",
                        "link_status":"UNREVIEWED_NOT_EVIDENCE_OF_ACTOR_MATCH",
                        "reviewer_1":"","reviewer_2":"","primary_source_url":"",
                        "independent_source_url":"","decision":"","review_notes":"",
                    })
        counts["eligible_episode_days"]+=eligible_days
        counts["all_exposure_overlap_rows"]+=len(links)
        counts["episodes_with_any_exposure_overlap"]+=bool(links)
        if not links:
            counts["episodes_without_exposure_overlap"]+=1
        links.sort(key=lambda r:(-r["lead_days"],-r["gdelt_current_count"],r["gdelt_case"]))
        reviewed.extend(links[:max_per_episode])
        counts["trimmed_exposure_overlap_rows"]+=max(0,len(links)-max_per_episode)
    counts["episodes_total"]=len(episodes)
    counts["episodes_with_country_xwalk"]=len(valid_episodes)
    counts["episodes_unmapped_country_or_date"]=len(episodes)-len(valid_episodes)
    counts["full_90_reference_days_replayed"]=len(flags)
    return reviewed,{
        "source_profile":"GDELT-v1 EventRootCode 17/18/19/20, selected-event denominator",
        "source_stitched_sha256":fingerprint,
        "ucdp_country_crosswalk_sha256":hashlib.sha256(Path(xwalk).read_bytes()).hexdigest(),
        "coverage_first":first.isoformat() if first<=last else None,
        "coverage_last":last.isoformat() if first<=last else None,
        "queue_counts":dict(counts),
        "causal_prediction_claim":False,
        "confirmed_actor_matches":0,
        "requires_manual_adjudication":True,
        "warnings":[
            "GDELT country-code proximity does not verify an opposing UCDP dyad or actor.",
            "No scores for unreviewed cases; no assumption that no GDELT lead is a true negative.",
            "Replayed source data were downloaded after the observed episodes, not genuinely prospective forecasts.",
            "Prior to full six-root historical migration these are four-root exploratory nominations only.",
        ],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history",nargs="+",required=True)
    p.add_argument("--ucdp",required=True)
    p.add_argument("--crosswalk",default="data/validation/ucdp_country_crosswalk_pilot.csv")
    p.add_argument("--output",default="episode-outcome-audit")
    p.add_argument("--start",default="2026-07-11")
    p.add_argument("--end",default="2026-09-30")
    p.add_argument("--max-per-episode",type=int,default=5)
    p.add_argument("--test-fixture-no-sha",action="store_true",
                   help="Only for offline synthetic unit tests; disallowed in production workflow")
    a=p.parse_args()
    out=Path(a.output)
    episodes,source=produce(a.ucdp,out,dt.date.fromisoformat(a.start),
                            dt.date.fromisoformat(a.end),require_sha=not a.test_fixture_no_sha)
    queue,matching=build_queue(episodes,a.history,a.crosswalk,a.max_per_episode)
    fields=["episode_id","episode_date","episode_kind","ucdp_country","ucdp_dyad_new_id",
            "ucdp_dyad_name","gdelt_case","gdelt_asof_date","lead_days","signal_kind",
            "gdelt_current_count","gdelt_ratio_to_baseline","comparison_type","link_status",
            "reviewer_1","reviewer_2","primary_source_url","independent_source_url",
            "decision","review_notes"]
    with (out/"adjudication_queue_UNREVIEWED.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(queue)
    summary={
        "schema":"aiba.episode-nomination-audit.v1",
        "label_source":source,"nomination_source":matching,
        "approved_for_operational_warning":False,
        "candidate_episode_count":len(episodes),
        "review_queue_rows":len(queue),
        "accepted_verified_links":0,
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"episodes":len(episodes),"review_queue":len(queue),
                      "country_coverage":matching["queue_counts"],
                      "status":"UNREVIEWED_NO_SKILL_CLAIM"},indent=2))


if __name__=="__main__":
    main()
