"""Dated operational feed chronology for Atlas.

Reads bounded archives from the durable observation branch. These are
source observations and media mentions, not independent proof of events.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None or d.utcoffset() is None:
            return None
        return d.astimezone(dt.timezone.utc)
    except ValueError:
        return None


SOURCE_MODES = ("official", "commercial")
SNAPSHOT_LIMIT = 70
MAX_DAYS = 90
MAX_ARCHIVE_BYTES = 2_000_000


def source_reports(state, registry, clock):
    """Map source-dated records to *existing* reviewed theater anchors only.

    Unknown/nonmatching reports remain unplotted. Identical links repeated in
    subsequent pulls produce one chronological record.
    """
    state = Path(state)
    patterns = {}
    for case in registry.get("cases", []):
        key = case.get("id")
        if isinstance(key, str):
            patterns[key] = [re.compile(p, re.IGNORECASE) for p in case.get("patterns", [])]
    history = []
    stats = {}
    for mode in SOURCE_MODES:
        directory = state / "history" / mode
        files = sorted(directory.glob("*.json"))[-SNAPSHOT_LIMIT:] if directory.exists() else []
        latest = state / "latest" / (mode + ".json")
        if latest.is_file():
            files.append(latest)
        count = 0
        for path in files:
            if path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError(f"Oversized {mode} source archive")
            snap = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(snap, dict) or not isinstance(snap.get("records"), list):
                raise ValueError(f"Invalid {mode} source archive")
            count += 1
            for rec in snap["records"]:
                if not isinstance(rec, dict):
                    continue
                date = parse_time(rec.get("published_at"))
                if date is None or not dt.timedelta(0) <= clock - date <= dt.timedelta(days=MAX_DAYS):
                    continue
                title = rec.get("title")
                url = rec.get("source_url")
                if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                    continue
                parts = urlsplit(url)
                if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                    continue
                for case_id, checks in patterns.items():
                    if not any(p.search(title) for p in checks):
                        continue
                    material = "|".join((mode, case_id, url, date.date().isoformat()))
                    uid = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
                    history.append({
                        "id": "ops:" + uid, "hotspot_id": case_id,
                        "date": date.date().isoformat(),
                        "category": "Official protective notice" if mode == "official"
                                    else "Commercial media mention",
                        "title": title[:300],
                        "assessment": "Public advisory; may be reactive" if mode == "official"
                                      else "Syndicated media lead; behavior unverified",
                        "detail": ("A dated public notice, not independent evidence of military preparation."
                                   if mode == "official" else
                                   "A trade press or syndicated mention, not verified insurance, airline or vessel behavior."),
                        "source": str(rec.get("publisher") or rec.get("publisher_domain") or mode)[:150],
                        "url": url, "root": str(rec.get("root") or url)[:300],
                        "location_precision": "Theater-associated source; no incident-point geolocation.",
                    })
        stats[mode] = {"archives_read": count}
    unique = {r["id"]: r for r in history}
    return sorted(unique.values(), key=lambda r: (r["date"], r["id"])), stats
