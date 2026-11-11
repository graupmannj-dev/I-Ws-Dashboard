#!/usr/bin/env python3
"""Reproducible UCDP Candidate dyad-country violence episode *proposals*.

Episodes are provisional, actor/dyad-resolved coded-violence labels;
NOT automatically interstate war, attacks, or AIBA warning success.
Generated purely from UCDP events before looking at GDELT flags.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path

UCDP_RELEASE = "26.01.26.09"
UCDP_SHA256 = "134da9b3df08b65266802c4b662e572f396c70c92ab62297319be657540bcede"
RELEASE_START = dt.date(2026, 1, 1)
RELEASE_END = dt.date(2026, 9, 30)
FIRST_ELIGIBLE = RELEASE_START + dt.timedelta(days=35)
QUIET_DAYS = 28
ESCALATION_REFERENCE_DAYS = 28
ESCALATION_WINDOW_DAYS = 7
ESCALATION_MIN_BEST_DEATHS = 15
ESCALATION_MIN_PRIOR_BEST_DEATHS = 7
ESCALATION_RATIO = 3.0
COOLDOWN_DAYS = 14
REQUIRED = {
    "id", "country", "type_of_violence", "dyad_new_id",
    "dyad_name", "conflict_new_id", "date_start", "date_end",
    "date_prec", "event_clarity", "code_status", "best", "high",
}


def date(value):
    return dt.date.fromisoformat(str(value).strip()[:10])


def calendar(start, end):
    return [start + dt.timedelta(days=n) for n in range((end-start).days + 1)]


def _integer(value, name):
    try:
        number = float(str(value).strip())
        if not number.is_integer() or number < 0:
            raise ValueError()
        return int(number)
    except (ValueError, OverflowError):
        raise ValueError(f"UCDP candidate has invalid {name}={str(value)[:40]!r}") from None


def read_candidate_csv(path, require_sha=True):
    """Keep exact dyad dates separate from quarantined uncertain intervals."""
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if require_sha and sha != UCDP_SHA256:
        raise ValueError(f"UCDP file SHA256 changed ({sha}); inspect release/version before using outcome labels")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="strict")))
    missing = REQUIRED - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"UCDP Candidate is missing dyad/event fields: {sorted(missing)}")
    country_dyad_deaths = defaultdict(Counter)
    dated_event_ids = defaultdict(lambda: defaultdict(list))
    uncertain = defaultdict(set)
    country_uncertain = defaultdict(set)
    dyad_info, ids, reason = {}, {}, Counter()
    invalid_fatality_bounds = []
    seen_country_dyads = set()
    for row in reader:
        eid = row["id"].strip()
        if not eid:
            raise ValueError("Missing UCDP event id")
        if eid in ids:
            if ids[eid] != row:
                raise ValueError(f"Conflicting duplicate UCDP event id: {eid}")
            continue
        ids[eid] = row
        if row["type_of_violence"].strip() != "1":
            reason["other_violence_type"] += 1
            continue
        country = row["country"].strip()
        dyad = row["dyad_new_id"].strip()
        dyad_name = row["dyad_name"].strip()
        conflict = row["conflict_new_id"].strip()
        if not country:
            raise ValueError("No country in state-based UCDP event")
        start, end = date(row["date_start"]), date(row["date_end"])
        if end < start:
            raise ValueError(f"Reversed UCDP date interval for {eid}")
        if end < RELEASE_START or start > RELEASE_END:
            reason["outside_release"] += 1
            continue
        best = _integer(row["best"], "best")
        high = _integer(row["high"], "high")
        invalid_bounds = high < best
        # A dyad label must be stable within the frozen source release.
        key = (country, dyad)
        if dyad:
            seen_country_dyads.add(key)
            desc = (dyad_name, conflict)
            if key in dyad_info and dyad_info[key] != desc:
                raise ValueError(f"Conflicting dyad metadata {key}")
            dyad_info[key] = desc
        exact = (dyad and row["code_status"].strip().lower() == "clear"
                 and row["date_prec"].strip() == "1"
                 and row["event_clarity"].strip() == "1" and start == end)
        if invalid_bounds or not exact or (best == 0 and high > 0):
            # Source quality exceptions are NOT repaired, silently
            # dropped, or treated as evidence of zero fatalities.
            # Preserve all potentially affected days as uncertain.
            if invalid_bounds:
                reason["fatality_bounds_inconsistent_quarantined"] += 1
                invalid_fatality_bounds.append({
                    "event_id": eid, "country": country,
                    "dyad_new_id": dyad or None,
                    "start": start.isoformat(), "end": end.isoformat(),
                    "best": best, "high": high,
                    "reason": "UCDP high below best; excluded from candidate labels",
                })
            for day in calendar(max(start, RELEASE_START), min(end, RELEASE_END)):
                if dyad:
                    uncertain[key].add(day)
                else:
                    country_uncertain[country].add(day)
            reason["ambiguous_quarantined"] += 1
            continue
        if best > 0:
            country_dyad_deaths[key][start] += best
            dated_event_ids[key][start].append(eid)
            reason["clear_exact_fatal"] += 1
        else:
            reason["clear_exact_zero_best_and_high"] += 1

    return {
        "source_sha256": sha,
        "seen_unique_event_ids": len(ids),
        "dyad_info": dyad_info,
        "all_dyads": seen_country_dyads,
        "daily_best_deaths": country_dyad_deaths,
        "daily_event_ids": dated_event_ids,
        "uncertain_dates": uncertain,
        "country_uncertain_dates": country_uncertain,
        "source_counts": dict(reason),
        "invalid_fatality_bounds": invalid_fatality_bounds,
    }


def any_uncertain(src, key, start, end):
    country = key[0]
    affected = src["uncertain_dates"][key] | src["country_uncertain_dates"][country]
    return any(start <= x <= end for x in affected)


def propose_episodes(src, start=dt.date(2026, 7, 11), end=RELEASE_END):
    """Deterministic, source-only episode labels; no GDELT data in this function.

    Onset: first exact fatal event after >=28 *verified* quiet days for
    that dyad-country. This is a 28-day *renewed-violence episode*, NOT
    a first-ever conflict onset.

    Intensification: >=15 best-estimate deaths in trailing seven days,
    >=7 best-estimate deaths in previous 28-day comparison window, and
    >=3x expected seven-day volume based on those 28 days. At least one
    qualifying fatal event must occur on threshold crossing day.
    The comparison period ends at t-7, never overlapping the seven-day
    evaluation window. Suppress repeated crossings for 14 days.
    """
    start = max(start, FIRST_ELIGIBLE)
    end = min(end, RELEASE_END)
    if end < start:
        return [], {"eligible_days": 0, "source": "UCDP Candidate"}
    episodes, reason = [], Counter()
    for country, dyad in sorted(src["all_dyads"]):
        key = (country, dyad)
        deaths = src["daily_best_deaths"][key]
        names = src["dyad_info"][key]
        last = {"quiet_restart": None, "intensification": None}

        def surge_state(x):
            # The *first* high-intensity crossing is the label, rather
            # than every day an existing conflict stays intense.
            recent_start = x - dt.timedelta(days=6)
            ref_start, ref_end = x-dt.timedelta(days=34), x-dt.timedelta(days=7)
            if any_uncertain(src, key, ref_start, x):
                return None, None, None
            recent = sum(deaths.get(d, 0) for d in calendar(recent_start, x))
            before = sum(deaths.get(d, 0) for d in calendar(ref_start, ref_end))
            qualifies = (before >= ESCALATION_MIN_PRIOR_BEST_DEATHS
                         and recent >= ESCALATION_MIN_BEST_DEATHS
                         and recent >= ESCALATION_RATIO*(before/4))
            return qualifies, recent, before

        for t in calendar(start, end):
            if deaths.get(t, 0) == 0:
                continue
            prev28_start, prev28_end = t-dt.timedelta(days=28), t-dt.timedelta(days=1)
            historic_28 = sum(deaths.get(d, 0) for d in calendar(prev28_start, prev28_end))
            # Source uncertainty can conceal an earlier death, so it
            # must prohibit a confident 'quiet' or surge label.
            if (historic_28 == 0 and not any_uncertain(src, key, prev28_start, t)
                and (last["quiet_restart"] is None or (t-last["quiet_restart"]).days >= COOLDOWN_DAYS)):
                episodes.append({
                    "episode_id": f"UCDP-CAND-{UCDP_RELEASE}-{dyad}-{country}-{t}-QUIET",
                    "date": t.isoformat(), "type": "quiet_restart",
                    "dyad_new_id": dyad, "dyad_name": names[0],
                    "conflict_new_id": names[1], "country": country,
                    "best_fatalities_on_date": deaths[t], "best_fatalities_7d": None,
                    "baseline_best_fatalities_28d": 0,
                    "source_event_ids": sorted(src["daily_event_ids"][key][t]),
                    "label_status": "automated_candidate_unadjudicated",
                })
                last["quiet_restart"] = t
                reason["quiet_restart"] += 1

            qualifies, recent, before = surge_state(t)
            preceding_qualifies, _, _ = surge_state(t-dt.timedelta(days=1))
            if qualifies is None or preceding_qualifies is None:
                reason["intensification_censored_uncertain_event"] += 1
                continue
            if not qualifies or preceding_qualifies:
                # A day remaining above the threshold is NOT a new
                # escalation, even if no earlier label was issued.
                continue
            if last["intensification"] and (t-last["intensification"]).days < COOLDOWN_DAYS:
                continue
            recent_start = t-dt.timedelta(days=6)
            episodes.append({
                "episode_id": f"UCDP-CAND-{UCDP_RELEASE}-{dyad}-{country}-{t}-SURGE",
                "date": t.isoformat(), "type": "intensification",
                "dyad_new_id": dyad, "dyad_name": names[0],
                "conflict_new_id": names[1], "country": country,
                "best_fatalities_on_date": deaths[t], "best_fatalities_7d": recent,
                "baseline_best_fatalities_28d": before,
                "source_event_ids": sorted(
                    {eid for d in calendar(recent_start, t)
                     for eid in src["daily_event_ids"][key][d]}),
                "label_status": "automated_candidate_unadjudicated",
            })
            last["intensification"] = t
            reason["intensification"] += 1
    episodes.sort(key=lambda r:(r["date"], r["country"], r["dyad_new_id"],r["type"]))
    return episodes, {
        "start": start.isoformat(), "end": end.isoformat(),
        "n_dyad_country_series": len(src["all_dyads"]),
        "episodes_by_type": dict(reason), "release": UCDP_RELEASE,
        "source_sha256": src["source_sha256"],
        "definition": {
            "quiet_restart_lookback_days": QUIET_DAYS,
            "intensification_recent_days": ESCALATION_WINDOW_DAYS,
            "intensification_prior_reference_days": ESCALATION_REFERENCE_DAYS,
            "intensification_min_recent_best_fatalities": ESCALATION_MIN_BEST_DEATHS,
            "intensification_min_prior_best_fatalities": ESCALATION_MIN_PRIOR_BEST_DEATHS,
            "intensification_min_relative_rate": ESCALATION_RATIO,
            "episode_cooldown_days": COOLDOWN_DAYS,
        },
    }


def produce(path, output, start=dt.date(2026,7,11), end=RELEASE_END, require_sha=True):
    src=read_candidate_csv(path,require_sha=require_sha)
    events, info=propose_episodes(src,start,end)
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    fields=["episode_id","date","type","dyad_new_id","dyad_name",
            "conflict_new_id","country","best_fatalities_on_date",
            "best_fatalities_7d","baseline_best_fatalities_28d",
            "source_event_ids","label_status"]
    # A separate forensic-quality register makes every excluded
    # contradictory fatality bound independently inspectable. Include
    # even records outside the selected episode period for source QA.
    qc_fields=["event_id","country","dyad_new_id","start","end","best","high","reason"]
    with (out/"quarantined_fatality_bounds.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=qc_fields)
        w.writeheader()
        w.writerows(src["invalid_fatality_bounds"])
    with (out/"episodes_unadjudicated.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for event in events:
            w.writerow({**event,"source_event_ids":";".join(event["source_event_ids"])})
    summary={
        "schema":"aiba.ucdp.episode-labels.v1",
        "ucdp_source_version":UCDP_RELEASE,
        "ucdp_source_sha256":src["source_sha256"],
        "unique_source_events":src["seen_unique_event_ids"],
        "source_counts":src["source_counts"],
        "quarantined_fatality_bounds_count":len(src["invalid_fatality_bounds"]),
        "quarantined_fatality_bounds_artifact":"quarantined_fatality_bounds.csv",
        "coverage":info,
        "episode_count":len(events),
        "approved_episode_count":0,
        "interstate_war_onsets_claimed":0,
        "eligible_for_production":False,
    }
    (out/"manifest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return events,summary
