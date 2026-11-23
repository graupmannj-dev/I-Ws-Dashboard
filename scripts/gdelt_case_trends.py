"""GDELT six-root, exact-pair case context for ALL standing CAIRN hypotheses.

This is measurement of media-coded interaction, not military activity, an
event count, probabilistic evidence, or a signed hypothesis judgment.
Unlike global anomaly nomination, case panels do not hide non-anomalous pairs.
"""
from __future__ import annotations

import datetime as dt
from publication_context import GDELT_PAIRS

SCHEMA = "cairn.gdelt-case-trends.v1"
SOURCE_URL = "https://data.gdeltproject.org/events/"


def _days(end, n):
    return [end - dt.timedelta(days=offset) for offset in range(n - 1, -1, -1)]


def build(records, daily_totals, available, asof, baseline_days=28, window_days=7):
    """Compute exact bilateral pair media-coded shares for each standing case.

    Partial windows yield null *all comparative metrics*. Observed zero in a
    complete archive is valid only as zero *coded records* in this scope.
    """
    if not isinstance(asof, dt.date) or isinstance(asof, dt.datetime):
        raise ValueError("asof must be a date")
    if window_days <= 0 or baseline_days <= 0:
        raise ValueError("windows must be positive")
    recent_days = _days(asof, window_days)
    baseline = _days(asof - dt.timedelta(days=window_days), baseline_days)
    seen = set(available)
    coverage = {"recent_days": sum(day in seen for day in recent_days),
                "baseline_days": sum(day in seen for day in baseline),
                "recent_days_required": window_days, "baseline_days_required": baseline_days}
    complete = (coverage["recent_days"] == window_days and
                coverage["baseline_days"] == baseline_days)
    denom_r = sum(daily_totals.get(day, 0) for day in recent_days) if complete else None
    denom_b = sum(daily_totals.get(day, 0) for day in baseline) if complete else None
    if complete and (denom_r <= 0 or denom_b <= 0):
        complete = False
    result = {}
    for case_id, case_pairs in GDELT_PAIRS.items():
        # A bilateral pair belongs to this *one* GDELT case key even when
        # multiple actors appear elsewhere in unrelated media reporting.
        keys = [("BILAT", tuple(sorted(pair))) for pair in case_pairs]
        daily = None
        count_r = count_b = share_r = share_b = ratio = shift = None
        trend = "unavailable_incomplete_coverage"
        if complete:
            daily = [{"date": day.isoformat(),
                      "coded_records": sum(records.get((day, key), 0) for key in keys)}
                     for day in baseline + recent_days]
            count_b = sum(v["coded_records"] for v in daily[:baseline_days])
            count_r = sum(v["coded_records"] for v in daily[baseline_days:])
            share_b = count_b / denom_b
            share_r = count_r / denom_r
            shift = round(100 * (share_r - share_b), 6)
            ratio = round(share_r / share_b, 4) if share_b else None
            trend = ("higher_coded_share" if share_r > share_b
                     else "lower_coded_share" if share_r < share_b
                     else "equal_coded_share")
        result[case_id] = {
            "status": "measured" if complete else "unavailable_incomplete_coverage",
            "matched_actor_pairs": [sorted(pair) for pair in
                                    sorted(case_pairs, key=lambda pair: sorted(pair))],
            "baseline_coded_records": count_b,
            "recent_coded_records": count_r,
            "baseline_denominator": denom_b if complete else None,
            "recent_denominator": denom_r if complete else None,
            "baseline_share": round(share_b, 9) if share_b is not None else None,
            "recent_share": round(share_r, 9) if share_r is not None else None,
            "media_share_change_percentage_points": shift,
            "media_share_ratio": ratio,
            "trend": trend,
            "daily_counts": daily,
            "direction_of_hypothesis": "not_inferred",
            "source_url": SOURCE_URL,
            "independent_corroboration": False,
            "source_clock": asof.isoformat(),
            "interpretation": (
                "GDELT media-coded coercive/conflict EVENT records for exact bilateral actor codes. "
                "Share relative to all six selected GDELT root codes; not a count of distinct real-world "
                "events, source-independent evidence, or an assessment of conflict probability."
            ),
        }
    return {
        "schema": SCHEMA, "status": "measured" if complete else "unavailable_incomplete_coverage",
        "asof": asof.isoformat(), "coverage": coverage,
        "baseline_days": baseline_days, "window_days": window_days,
        "profile": "GDELT 1.0 daily, event roots 13/16/17/18/19/20; exact bilateral actor countries",
        "source_url": SOURCE_URL,
        "measured_case_count": sum(v["status"] == "measured" for v in result.values()),
        "hypothesis_direction_estimated": False,
        "cases": result,
    }
