#!/usr/bin/env python3
"""Historical GDELT baseline builder: shadow-mode only, no production threshold changes."""
import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import statistics
import urllib.request
import zipfile
from collections import Counter

URL = "https://data.gdeltproject.org/events/{day}.export.CSV.zip"
ROOTS = {"17", "18", "19", "20"}
def daily_counts(data, day):
    counts = Counter()
    rows = selected = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = [n for n in z.namelist() if n.endswith(".CSV")]
        if len(members) != 1:
            raise ValueError("Unexpected GDELT archive members")
        if z.testzip() is not None:
            raise ValueError("ZIP CRC failure")
        with z.open(members[0]) as f:
            for raw in f:
                rows += 1
                fields = raw.decode("utf-8", "replace").rstrip("\r\n").split("\t")
                if len(fields) < 29 or fields[28].strip() not in ROOTS:
                    continue
                a, b = fields[7].strip(), fields[17].strip()
                valid = lambda c: len(c) == 3 and c.isalpha()
                if valid(a) and valid(b) and a != b:
                    key = "BILAT:" + ":".join(sorted((a,b)))
                elif valid(a) or valid(b):
                    key = "DOMESTIC:" + (a if valid(a) else b)
                else:
                    continue
                counts[key] += 1
                selected += 1
    if not rows or not selected:
        raise ValueError("Empty or unusable daily archive")
    return {"day": day, "rows": rows, "selected": selected, "counts": dict(counts)}

def build_panel(records, min_history=28):
    # All estimates are based strictly on prior dates; no look-ahead.
    records = sorted(records, key=lambda r: r["day"])
    output = []
    for idx, current in enumerate(records):
        prior = records[max(0, idx-90):idx]
        for key, value in current["counts"].items():
            eligible = [r for r in prior if key in r["counts"]]
            # Absence of a case key in a VALID full archive means zero case events.
            # Missing/failed archives are never included in records.
            if len(prior) < min_history:
                continue
            shares = [r["counts"].get(key,0)/r["selected"] for r in prior]
            med = statistics.median(shares)
            mad = statistics.median(abs(x-med) for x in shares)
            current_share = value/current["selected"]
            output.append({"day":current["day"],"case":key,"count":value,
                           "share":round(current_share,9),"baseline_days":len(prior),
                           "median_share":round(med,9),"mad_share":round(mad,9),
                           "ratio_to_median":round(current_share/med,3) if med else None,
                           "robust_z":round((current_share-med)/(1.4826*mad),3) if mad else None,
                           "status":"shadow_only_not_predictive"})
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--cache",default=".cache/gdelt-history")
    p.add_argument("--output",default="historical-baseline")
    p.add_argument("--max-days",type=int,default=120)
    a=p.parse_args()
    start,end=dt.date.fromisoformat(a.start),dt.date.fromisoformat(a.end)
    if end<start or (end-start).days+1>a.max_days:
        p.error("Invalid range or exceeds --max-days; run in bounded chunks")
    cache,out=pathlib.Path(a.cache),pathlib.Path(a.output)
    cache.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    records=[];failures=[]
    for i in range((end-start).days+1):
        day=(start+dt.timedelta(days=i)).strftime("%Y%m%d")
        path=cache/(day+".export.CSV.zip")
        try:
            if not path.exists():
                request=urllib.request.Request(URL.format(day=day),headers={"User-Agent":"AIBA-Historical-Baseline/1.0"})
                with urllib.request.urlopen(request,timeout=90) as resp:
                    payload=resp.read()
                daily_counts(payload,day)
                path.write_bytes(payload)
            records.append(daily_counts(path.read_bytes(),day))
        except Exception as exc:
            failures.append({"day":day,"error":type(exc).__name__,"message":str(exc)[:160]})
    with (out/"daily.jsonl").open("w") as f:
        for r in records:f.write(json.dumps(r,sort_keys=True)+"\n")
    panel=build_panel(records)
    with (out/"shadow_replay.jsonl").open("w") as f:
        for r in panel:f.write(json.dumps(r,sort_keys=True)+"\n")
    manifest={"start":a.start,"end":a.end,"requested_days":(end-start).days+1,
              "complete_days":len(records),"failed_days":len(failures),
              "failures":failures,"shadow_rows":len(panel),
              "method":"prior-90-valid-day median/MAD of selected-event shares; no outcome labels",
              "warning":"This is a descriptive anomaly panel, not a validated forecast."}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({k:v for k,v in manifest.items() if k!="failures"},indent=2))
    if failures:raise SystemExit("Incomplete coverage; outputs preserved with missingness manifest")
if __name__=="__main__":main()
