#!/usr/bin/env python3
"""Durable source-root family ledger, independent of the 45-day hot sensor index.

Individual accepted source records are added once to a hash-sharded archive on
AIBA's existing evidence branch. Routine re-polls do not update the original
first-seen clock or create fresh anomalies. Indexed relationships are UNREVIEWED
links, not confirmations of one event or independent reporting.

The aggregate JSON is a bounded site cache. The durable source is the
versioned archive shards; older entries are not deleted when the cache caps.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

from ops_pipeline import load_json, write_json
from dashboard.dynamic_bins import when, normalize_registry, normalize_analyst

SCHEMA = "aiba.family-archive.v1"
REGISTRY_SCHEMA = "aiba.behavioral-observations.v1"
UTC = dt.timezone.utc
MAX_TOTAL_RECORDS = 200_000
MAX_TOTAL_ROOTS = 100_000
MAX_SOURCE_PER_ROOT = 2000
MAX_PUBLIC_RECORDS = 5000
MAX_HISTORY_FILES = 10000
MAX_RELATIONSHIPS = 15000
VALID_RELATIONS = {"possible_same_event_unreviewed", "related_reporting_unreviewed"}
SHARD_CHARS = 2


def root_id(root):
    if not isinstance(root, str) or not root:
        raise ValueError("Missing source information root")
    return hashlib.sha256(root.encode("utf-8")).hexdigest()


def read_strict(path, expected_schema, default):
    path = Path(path)
    if not path.exists():
        return default
    if not path.is_file() or path.is_symlink():
        raise ValueError("Archive path must be a regular file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != expected_schema:
        raise ValueError("Corrupt or incompatible family archive")
    return data


def rows_from_history(state):
    path = Path(state) / "history" / "behavioral_registry"
    files = sorted(path.glob("*.json"))
    if len(files) > MAX_HISTORY_FILES:
        raise ValueError("Cannot safely backfill unbounded registry history")
    for file in files:
        if file.stat().st_size > 10_000_000:
            raise ValueError("Oversized historic behavioral delta")
        value = json.loads(file.read_text(encoding="utf-8"))
        if value.get("schema") != REGISTRY_SCHEMA:
            raise ValueError("Unrecognized history schema")
        rows = value.get("new_records", [])
        if not isinstance(rows, list):
            raise ValueError("Historical registry delta is malformed")
        for row in rows:
            yield row


def update(state, clock=None, write=True):
    now = (clock or dt.datetime.now(UTC)).astimezone(UTC)
    state = Path(state)
    base = state / "family_archive"
    latest = state / "latest" / "family_archive.json"
    manifest_path = base / "manifest.json"
    manifest = read_strict(manifest_path, SCHEMA, {"schema": SCHEMA, "bootstrapped": False})
    raw_registry = load_json(state / "latest" / "behavioral_registry.json", {}) or {}
    if raw_registry.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("Latest behavioral registry unavailable; no family archive update")
    # Normalize bounded history deltas independently. The union may be much
    # larger than a single current provider snapshot.
    normal, availability = normalize_registry(raw_registry)
    if availability != "available":
        raise ValueError("Archive source envelope invalid or oversized")
    if not manifest["bootstrapped"]:
        batch = []
        for row in rows_from_history(state):
            batch.append(row)
            if len(batch) == 2000:
                parsed, status = normalize_registry({
                    "schema": REGISTRY_SCHEMA, "records": batch})
                if status != "available":
                    raise ValueError("Invalid historic source delta")
                normal.extend(parsed)
                batch.clear()
        if batch:
            parsed, status = normalize_registry({
                "schema": REGISTRY_SCHEMA, "records": batch})
            if status != "available":
                raise ValueError("Invalid historic source delta")
            normal.extend(parsed)
    # Analyst intake already validates source URLs, time bounds, and roots.
    from dashboard.analyst_intake import load_history
    analyst = load_history(state, clock=now)
    normal.extend(normalize_analyst(analyst))
    # FAA NAS samples are operational source measurements, not restrictions.
    # A qualifying excursion (or a non-routine FAA operational pattern)
    # contributes its OWN single-source family, never inferred onto a TFR.
    faa = load_json(state / "latest" / "faa_nas_calibration.json", {}) or {}
    if faa.get("schema") == "aiba.faa-nas-calibration.v1":
        candidate = faa.get("candidate_source")
        if candidate is not None:
            if (not isinstance(candidate, dict) or
                    not isinstance(candidate.get("id"), str) or
                    not isinstance(candidate.get("information_root"), str) or
                    not isinstance(candidate.get("source_url"), str) or
                    not candidate["source_url"].startswith("https://")):
                raise ValueError("FAA candidate source integrity failed")
            normal.append(candidate)
    shards = {}
    new_records = 0
    for item in normal:
        ident = item["id"]
        stamp = when(item["first_observed_at"])
        if not stamp or stamp > now:
            raise ValueError("Family history source time absent or future")
        key = root_id(item["information_root"])
        prefix = key[:SHARD_CHARS]
        if prefix not in shards:
            path = base / "shards" / (prefix + ".json")
            shards[prefix] = read_strict(path, SCHEMA, {"schema": SCHEMA, "roots": {}})
        family = shards[prefix]["roots"].setdefault(key, {
            "information_root": item["information_root"], "members": {},
        })
        if family.get("information_root") != item["information_root"]:
            raise ValueError("Archive hash collision or mutated source root")
        members = family["members"]
        old = members.get(ident)
        if old:
            if old["information_root"] != item["information_root"]:
                raise ValueError("Source ID changed information root")
            # An existing observation may receive a validated matched-clock
            # baseline later. This is *evidence enrichment*, not newness.
            before = old.get("calibrated_metric")
            after = item.get("calibrated_metric")
            if (not before and isinstance(after, dict)
                    and after.get("baseline_ready") is True):
                old["calibrated_metric"] = after
            # Earliest original collection and publication metadata persist.
            # Re-polling an old notice is NOT a newly observed event.
            continue
        if len(members) >= MAX_SOURCE_PER_ROOT:
            raise ValueError("Source root fragment limit exceeded; audit source identity")
        members[ident] = item
        new_records += 1
    # Include untouched archives; do not forget an old quiet family simply
    # because it was absent from the latest provider snapshot.
    for shard_file in sorted((base / "shards").glob("??.json")):
        prefix = shard_file.stem
        if prefix not in shards:
            shards[prefix] = read_strict(shard_file, SCHEMA, None)
    root_count = sum(len(s["roots"]) for s in shards.values())
    rec_count = sum(len(g["members"]) for s in shards.values() for g in s["roots"].values())
    if root_count > MAX_TOTAL_ROOTS or rec_count > MAX_TOTAL_RECORDS:
        raise ValueError("Archive capacity reached; repartition explicitly, do not drop evidence")
    all_records = [row
                   for shard in shards.values() for group in shard["roots"].values()
                   for row in group["members"].values()]
    all_records.sort(key=lambda v: (v["first_observed_at"], v["id"]), reverse=True)

    # Accumulate report relationships as historical candidate links, but do
    # not claim the reports are independent or resolve to one actual event.
    relations_path = base / "relationships.json"
    relationships = read_strict(relations_path, SCHEMA, {"schema": SCHEMA, "links": {}})
    links = relationships["links"]
    fusion = load_json(state / "latest" / "behavioral_fusion.json", {}) or {}
    refs = (fusion.get("report_relationships") or {}).get("candidate_groups") or []
    if not isinstance(refs, list):
        raise ValueError("Malformed source relationship feed")
    for link in refs:
        if not isinstance(link, dict) or link.get("status") not in VALID_RELATIONS:
            continue
        ident = link.get("id")
        sources = link.get("source_reports")
        if not isinstance(ident, str) or not ident or not isinstance(sources, list):
            continue
        evidence = sorted({x.get("observation_id") for x in sources
                           if isinstance(x, dict) and isinstance(x.get("observation_id"), str)})
        if len(evidence) < 2:
            continue
        old = links.get(ident, {"first_detected_at": now.isoformat(), "source_ids": []})
        old["source_ids"] = sorted(set(old["source_ids"]) | set(evidence))
        old["id"] = ident
        old["status"] = link["status"]
        old["match_basis"] = str(link.get("match_basis") or "")[:200]
        old["independent_corroboration_established"] = False
        old["warning_level_change"] = False
        links[ident] = old
    if len(links) > MAX_RELATIONSHIPS:
        raise ValueError("Relationship ledger needs repartitioning; no silent truncation")
    # The cache is for discoverability and may be bounded; the persistent
    # shards and durable relationships remain intact in the evidence branch.
    snapshot = {
        "schema": SCHEMA, "generated_at": now.isoformat(),
        "source_registry_schema": REGISTRY_SCHEMA,
        "record_count_total": rec_count, "root_count_total": root_count,
        "public_record_count": min(len(all_records), MAX_PUBLIC_RECORDS),
        "public_snapshot_truncated": len(all_records) > MAX_PUBLIC_RECORDS,
        "records": all_records[:MAX_PUBLIC_RECORDS],
        "source_health": raw_registry.get("source_health", {}),
        "historical_relationship_count": len(links),
        "report_relationships": {
            "candidate_groups": list(links.values())[:MAX_RELATIONSHIPS],
        },
        "alerts_promoted": 0, "new_records_added": new_records,
        "archive_integrity": "all shards retained; public discovery cache is bounded",
        "missing_data_is_not_zero": True,
    }
    if write:
        # Only changed shards need an updated git blob; all previous data is
        # left in place. Data-branch workflow commits are serialized.
        for prefix, shard in shards.items():
            path = base / "shards" / (prefix + ".json")
            prior = load_json(path, None)
            if prior != shard:
                write_json(path, shard)
        if read_strict(relations_path, SCHEMA, {"schema": SCHEMA, "links": {}}) != relationships:
            write_json(relations_path, relationships)
        write_json(manifest_path, {
            "schema": SCHEMA, "bootstrapped": True, "generated_at": now.isoformat(),
            "root_count": root_count, "record_count": rec_count,
            "relation_count": len(links),
        })
        write_json(latest, snapshot)
    return snapshot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", required=True)
    args = p.parse_args()
    report = update(args.state)
    print(json.dumps({key: report[key] for key in
                      ("root_count_total", "record_count_total", "new_records_added",
                       "historical_relationship_count", "public_snapshot_truncated")},
                     indent=2))


if __name__ == "__main__":
    main()
