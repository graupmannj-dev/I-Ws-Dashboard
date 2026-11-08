#!/usr/bin/env python3
"""Publish bounded near-current official restriction snapshots to the public
AIBA evidence branch. This is PERIODIC observation, not continuous streaming.

Each source has independent health. Failures overwrite that source's current
rows with unavailable, rather than treating yesterday's observations as live.
Historical files contain only identity/change summaries; full source geometry
is retained only in the current snapshot.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .collect_layers import TFR, NIORD, collect_tfr, maritime, request, coord
except ImportError:
    from collect_layers import TFR, NIORD, collect_tfr, maritime, request, coord

SOURCES = ("airspace", "maritime")
SOURCE_LINKS = {"airspace": TFR, "maritime": NIORD}
MAX_PER_SOURCE = 1200
MAX_GEOMETRY_POINTS = 15000
MAX_HISTORY_ITEMS = 1500
UTC = dt.timezone.utc


def now():
    return dt.datetime.now(UTC).replace(microsecond=0)


def stamp(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def aware(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def stable_hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()[:20]


def read(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                 allow_nan=False, indent=2)+"\n", encoding="utf-8")


def geometry_is_valid(shape):
    if shape is None:
        return True
    if not isinstance(shape, dict):
        return False
    kind = shape.get("type")
    if kind == "Circle":
        center, rad = shape.get("center"), shape.get("radius_km")
        return (isinstance(center, list) and len(center) == 2 and coord(*center)
                and isinstance(rad, (int, float)) and not isinstance(rad, bool)
                and math.isfinite(rad) and 0 < rad <= 3500)
    if kind in ("BBox", "Rectangle"):
        corners = shape.get("coordinates")
        if not isinstance(corners, list) or len(corners)!=2:
            return False
        if not all(isinstance(p, list) and len(p)==2 and coord(*p) for p in corners):
            return False
        (west,south),(east,north)=corners
        width=east-west if east>=west else east+360-west
        return south<north and 0<width<=180
    if kind not in ("Polygon", "MultiPolygon", "LineString"):
        return False
    points = 0
    def visit(node):
        nonlocal points
        if not isinstance(node, list) or not node or points >= MAX_GEOMETRY_POINTS:
            return False
        if len(node)==2 and isinstance(node[0], (int,float)):
            points += 1
            return coord(*node)
        return all(visit(sub) for sub in node)
    return visit(shape.get("coordinates"))


def clean_row(record):
    if not isinstance(record, dict):
        return None
    title=record.get("title")
    identity=record.get("id")
    source=record.get("source")
    link=record.get("url")
    if not all(isinstance(x,str) and 0<len(x)<=500 for x in (title, identity, source)):
        return None
    if not isinstance(link,str) or len(link)>2048:
        return None
    uri=urlsplit(link)
    if uri.scheme!="https" or not uri.hostname:
        return None
    if not geometry_is_valid(record.get("geometry")):
        return None
    if ("lon" in record or "lat" in record) and not coord(
            record.get("lon"), record.get("lat")):
        return None
    start=record.get("valid_from")
    end=record.get("valid_until")
    if start is not None and aware(start) is None:
        return None
    if end is not None and aware(end) is None:
        return None
    if start and end and aware(end)<=aware(start):
        return None
    # Retain only source fields rendered by the client; no private payloads.
    result={k: record[k] for k in (
        "id","title","source","url","valid_from","valid_until","in_force",
        "date","observed_at","lon","lat","geometry","detail"
    ) if k in record}
    if isinstance(result.get("detail"),str):
        result["detail"]=result["detail"][:2400]
    return result


def source_loaders():
    return {
        "airspace": collect_tfr,
        "maritime": lambda: maritime(json.loads(request(NIORD))),
    }


def collect(state, loaders=None, clock=now):
    state=Path(state)
    when=clock()
    if when.tzinfo is None:
        raise ValueError("Collector clock must be timezone-aware")
    current_stamp=stamp(when)
    loaders=loaders or source_loaders()
    previous=read(state/"latest"/"live_layers.json", {})
    old_layers=previous.get("layers",{}) if isinstance(previous,dict) else {}
    old_health=read(state/"health"/"live_layers.json",{})
    new_layers={}
    health={}
    transitions={}
    successes=0
    for key in SOURCES:
        before=old_layers.get(key,{}) if isinstance(old_layers,dict) else {}
        prev=old_health.get(key,{}) if isinstance(old_health,dict) else {}
        prior_records={r["id"]: stable_hash(r) for r in before.get("records",[])
                       if isinstance(r,dict) and isinstance(r.get("id"),str)}
        try:
            loader=loaders[key]
            result=loader()
            is_partial=isinstance(result,dict)
            rows=result.get("records") if is_partial else result
            skipped=result.get("skipped",0) if is_partial else 0
            if not isinstance(rows,list) or len(rows)>MAX_PER_SOURCE:
                raise ValueError("Unsupported or overlarge official collection response")
            accepted=[]
            omitted=0
            for item in rows:
                clean=clean_row(item)
                if clean is None:
                    omitted+=1
                else:
                    accepted.append(clean)
            if omitted==len(rows) and rows:
                raise ValueError("All official rows failed geometry/source validation")
            if len(accepted)>MAX_PER_SOURCE:
                raise ValueError("Too many normalized notices")
            layer_status="partial" if omitted or skipped else "snapshot"
            mapped=sum(bool(r.get("geometry")) or
                       (coord(r.get("lon"),r.get("lat"))) for r in accepted)
            layer={"status":layer_status,"records":accepted,"checked_at":current_stamp,
                   "source":SOURCE_LINKS[key], "mapped_records":mapped,
                   "message":f"{len(accepted)} supported official notices; {mapped} drawable areas/points"+
                       (f"; {int(skipped)+omitted} skipped/unsupported notices" if omitted or skipped else "")}
            successes+=1
            health[key]={"status":layer_status,"checked_at":current_stamp,
                         "last_success_at":current_stamp,
                         "record_count":len(accepted),"mapped_records":mapped,
                         "skipped":int(skipped)+omitted}
        except (OSError,ValueError,KeyError,TypeError) as error:
            layer={"status":"unavailable","records":[],"checked_at":current_stamp,
                   "source":SOURCE_LINKS[key],
                   "message":f"Source unavailable or schema incompatible ({type(error).__name__}); not a zero-activity finding"}
            health[key]={"status":"unavailable","checked_at":current_stamp,
                         "last_success_at":prev.get("last_success_at"),
                         "record_count":None,"mapped_records":None,"skipped":None,
                         "error_type":type(error).__name__}
        new_layers[key]=layer
        after_records={r["id"]:stable_hash(r) for r in layer["records"]}
        if layer["status"]=="unavailable":
            transitions[key]={"new":[],"modified":[],"withdrawn":[],
                              "withdrawal_claimed":False,
                              "note":"Source failed; no disappearance or cancellation inferred."}
        else:
            transitions[key]={
                "new":sorted(set(after_records)-set(prior_records))[:150],
                "modified":sorted(k for k in after_records.keys()&prior_records.keys()
                                  if after_records[k]!=prior_records[k])[:150],
                "withdrawn":sorted(set(prior_records)-set(after_records))[:150],
                "withdrawal_claimed":False,
                "note":"Items absent from current list are NOT confirmed canceled; check original authority."}
    snapshot={"version":1,"kind":"aiba_restriction_snapshot",
              "generated_at":current_stamp,"collection_mode":"periodic_github_actions",
              "layers":new_layers, "warning":(
                  "Current source notices, not continuous streaming, historical tracks, "
                  "or proof of hostile preparations. Source failures are not zero activity.")}
    write(state/"latest"/"live_layers.json",snapshot)
    write(state/"health"/"live_layers.json",health)
    # No repeated full polygons in Git history; retain compact change ledger.
    historic={
        "generated_at":current_stamp,"source_health":health,
        "change_summary":transitions,
        "note":"Identity changes, not evidence of military escalation. An unavailable source is not an empty list."
    }
    changes=any(t["new"] or t["modified"] or t["withdrawn"] for t in transitions.values())
    if changes or not previous:
        write(state/"history"/"live_layers"/(when.strftime("%Y%m%dT%H%M%SZ")+".json"),historic)
    return {"snapshot":snapshot,"health":health,"changes":transitions,
            "successes":successes}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--state",type=Path,required=True)
    args=p.parse_args()
    result=collect(args.state)
    print(json.dumps({"checked_at":result["snapshot"]["generated_at"],
                      "health":result["health"],"successes":result["successes"]},indent=2))
    # Keep failed coverage in Git, but tell Actions if all sources are unavailable.
    return 1 if result["successes"]==0 else 0


if __name__=="__main__":
    raise SystemExit(main())
