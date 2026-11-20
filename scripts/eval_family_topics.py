#!/usr/bin/env python3
"""Reproducible, bounded topic-link evaluation; never a field-accuracy claim.

This dated title-only benchmark is a convenience sample, NOT independent truth.
Scores measure pairwise *topic membership* of a fresh empty-ledger clustering
run. They do not assess whether any reported incident actually occurred,
independent corroboration, warning quality, or predictive lead time.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dashboard.automatic_topics import (
    MIN_SHARED_TERMS, MIN_SIMILARITY, GENERIC,
    _seed, _similar, assign, documents,
)

DEFAULT=ROOT/"tests"/"fixtures"/"cairn_topic_pairs_2026_11_20.json"
SCHEMA="cairn.topic-pair-review.v1"


def load_benchmark(path=DEFAULT):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema")!=SCHEMA:
        raise ValueError("Invalid topic-pair benchmark schema")
    docs=data.get("documents") or []
    pairs=data.get("pairs") or []
    ids={d.get("id") for d in docs}
    if len(ids)!=len(docs) or not ids or None in ids:
        raise ValueError("Duplicate or missing document identity")
    if len(pairs)<12:
        raise ValueError("Too few curated pairs for a minimally useful audit")
    observed=set()
    labels=set()
    for p in pairs:
        a,b=p.get("left"),p.get("right")
        if a not in ids or b not in ids or a==b or type(p.get("same_topic")) is not bool:
            raise ValueError("Invalid pair annotation")
        key=tuple(sorted((a,b)))
        if key in observed:
            raise ValueError("Duplicate or contradictory pair annotation")
        observed.add(key)
        labels.add(p["same_topic"])
        if not isinstance(p.get("rationale"),str) or len(p["rationale"])<9:
            raise ValueError("Missing label rationale")
    if labels!={True,False}:
        raise ValueError("Pair labels must include positives and hard negatives")
    return data


def source_rows(docs,stamp="2026-11-20T16:28:46Z"):
    result=[]
    for doc in docs:
        if not isinstance(doc.get("title"),str) or len(doc["title"])<10:
            raise ValueError("Missing source title")
        result.append({
            "id":"heldout:"+doc["id"],
            "information_root":"heldout:original_document:"+doc["id"],
            "first_observed_at":stamp,
            "source_url":"",  # No manufactured link; test identity from source root.
            "title":doc["title"],
            "source_family":doc["source_family"],
            "provider":doc.get("provider",doc["source_family"]),
            "source_kind":"benchmark_source_title",
            "geography_key":doc.get("geography_key"),
            "collection_mode":"benchmark",
        })
    return result


def legacy_assign(rows):
    """Narrow v1 seed/lexical baseline for paired comparison, not production."""
    groups={};ids={}
    for doc in documents(rows):
        if doc["domain"]=="advisory" or len(set(doc["terms"])-GENERIC)<MIN_SHARED_TERMS:
            continue
        match=None
        for gid,g in groups.items():
            score,_=_similar(doc,g)
            if score>=MIN_SIMILARITY and (match is None or score>match[0]):
                match=(score,gid)
        if match is None:
            gid="v1:"+doc["key"]
            groups[gid]=_seed(doc)
        else:gid=match[1]
        ids[doc["key"]]=gid
    return ids


def summarize(labels,predictions):
    c=Counter()
    errors=[]
    for pair in labels:
        actual=pair["same_topic"]
        prediction=predictions.get((pair["left"],pair["right"]))
        if prediction is None:
            raise ValueError("Missing pair prediction")
        if actual and prediction:tag="TP"
        elif actual and not prediction:tag="FN"
        elif not actual and prediction:tag="FP"
        else:tag="TN"
        c[tag]+=1
        if tag in ("FP","FN"):
            errors.append({
                "left":pair["left"],"right":pair["right"],
                "error":tag,"annotator_rationale":pair["rationale"]})
    tp,fp,tn,fn=(c[x] for x in ("TP","FP","TN","FN"))
    safe=lambda n,d:round(n/d,4) if d else None
    return {
        "labeled_pairs":len(labels),
        "tp":tp,"fn":fn,"fp":fp,"tn":tn,
        "pair_recall":safe(tp,tp+fn),
        "pair_precision_on_curated_sample":safe(tp,tp+fp),
        "negative_pair_false_join_rate":safe(fp,fp+tn),
        "negative_pair_specificity":safe(tn,fp+tn),
        "false_links":errors,
    }


def run(path=DEFAULT):
    fixture=load_benchmark(path)
    rows=source_rows(fixture["documents"],
                     fixture["snapshot"]["observed_at"])
    docs=documents(rows)
    key_by_id={r["id"].removeprefix("heldout:"):doc["key"] for r,doc in zip(rows,docs)}
    # The documents() sort is source-key order, NOT necessarily input order.
    key_by_id={}
    for doc in docs:
        for row in doc["rows"]:
            key_by_id[row["id"].removeprefix("heldout:")]=doc["key"]
    ts=time.perf_counter()
    legacy=legacy_assign(rows)
    legacy_seconds=time.perf_counter()-ts
    ts=time.perf_counter()
    hybrid=assign(rows)
    hybrid_seconds=time.perf_counter()-ts
    labels=fixture["pairs"]
    def predictions(assignment):
        return {
            (p["left"],p["right"]):
            bool(assignment.get(key_by_id[p["left"]]) is not None and
                 assignment.get(key_by_id[p["left"]])==
                 assignment.get(key_by_id[p["right"]]))
            for p in labels
        }
    prior=summarize(labels,predictions(legacy))
    current=summarize(labels,predictions(hybrid["assignments"]))
    sample={
        "schema":"cairn.topic-quality-audit.v1",
        "evaluation_type":"dated_convenience_sample_not_independent_test",
        "input_snapshot":fixture["snapshot"],
        "label_scope":fixture["label_scope"],
        "limitations":fixture["limitations"],
        "document_count":len(docs),
        "pair_count":len(labels),
        "positive_labels":sum(p["same_topic"] for p in labels),
        "negative_labels":sum(not p["same_topic"] for p in labels),
        "legacy_sparse_v1":prior,
        "hybrid_v2":current,
        "difference":{
            "false_negative_reduction":prior["fn"]-current["fn"],
            "false_positive_increase":current["fp"]-prior["fp"],
        },
        "runtime_seconds":{
            "legacy":round(legacy_seconds,4),
            "hybrid":round(hybrid_seconds,4),
        },
        "evaluation_caveat":"Pairs share documents, labels are title judgments, cases selected by the same development project. Do not extrapolate a population error rate, attach a CI to these pairs, or claim independently validated semantic accuracy.",
        "operational_note":"Current live ledger may retain older v1 assignments. This fresh-scratch run measures only new-matcher pair behavior, not every previously persisted family.",
    }
    return sample


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path,default=DEFAULT)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    result=run(args.fixture)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "sample":result["evaluation_type"],
        "counts":{"documents":result["document_count"],
                  "pairs":result["pair_count"],
                  "pos":result["positive_labels"],
                  "neg":result["negative_labels"]},
        "legacy":{k:v for k,v in result["legacy_sparse_v1"].items()
                  if k not in ("false_links",)},
        "hybrid":{k:v for k,v in result["hybrid_v2"].items()
                  if k not in ("false_links",)},
        "difference":result["difference"],
        "hybrid_errors":result["hybrid_v2"]["false_links"],
        "caution":result["evaluation_caveat"],
    },indent=2))


if __name__=="__main__":main()
