"""Evidence-family observation facets and qualified metric deviation contracts.

An anomaly magnitude is independent of corroboration. Current public feeds do
not provide per-family matched baseline metrics, so gauges remain uncalibrated
unless an explicit, comparable, validated numerical source metric is present.
"""
from __future__ import annotations
import math

FACET_PROFILES = {
    "aviation": [
        ("source_notice","Official airspace notice"),
        ("traffic_effect","Independent flight/airport effects"),
        ("telemetry","Aircraft telemetry"),
        ("commercial","Commercial disruption reporting"),
        ("corroboration","Independent corroboration"),
        ("contradiction","Conflicting evidence"),
    ],
    "maritime": [
        ("source_notice","Official maritime notice"),
        ("telemetry","AIS or vessel telemetry"),
        ("traffic_effect","Port/shipping disruption"),
        ("commercial","Shipping/war-risk reporting"),
        ("corroboration","Independent corroboration"),
        ("contradiction","Conflicting evidence"),
    ],
    "network": [
        ("telemetry","Direct network measurement"),
        ("source_notice","Official outage announcement"),
        ("traffic_effect","Independent routing effects"),
        ("commercial","Secondary reporting"),
        ("corroboration","Independent corroboration"),
        ("contradiction","Conflicting evidence"),
    ],
    "general": [
        ("source_notice","Official notice"),
        ("telemetry","Direct measurement"),
        ("commercial","Commercial reporting"),
        ("market","Market expectation"),
        ("corroboration","Independent corroboration"),
        ("contradiction","Conflicting evidence"),
    ],
}


def profile(rows):
    families={row.get("source_family") for row in rows}
    if "airspace_restriction" in families:
        return "aviation"
    if "maritime_restriction" in families:
        return "maritime"
    if "internet_reachability" in families:
        return "network"
    return "general"


def facet_type(row):
    fam=row.get("source_family")
    if fam in {"airspace_restriction","maritime_restriction","protective_notice"}:
        return "source_notice"
    if fam == "internet_reachability":
        return "telemetry"
    if fam == "commercial_media":
        return "commercial"
    if fam == "market_expectation":
        return "market"
    return None


def facets(rows, source_health=None):
    """Facet states describe collection status, NOT the truth of an event."""
    source_health=source_health if isinstance(source_health,dict) else {}
    typ=profile(rows)
    output=[]
    for key,label in FACET_PROFILES[typ]:
        observed=[x for x in rows if facet_type(x)==key]
        if key=="corroboration":
            # Multiple unique roots do not prove independent observation.
            state="not_measured"
            reason="Independent originating observations have not been adjudicated."
        elif key=="contradiction":
            contradicted=[x for x in rows if x.get("claim_level")=="explicit_source_contradiction"]
            state="contradicted" if contradicted else "not_measured"
            observed=contradicted
            reason=("Explicit contradictory source evidence needs review." if contradicted else
                    "Contradiction assessment unavailable; not the same as no contradictions.")
        elif not observed:
            state="not_measured"
            reason="No validated measurement of this facet; source coverage is not globally complete."
        else:
            partial=any(source_health.get(x.get("collection_mode"),{}).get("status")=="current_partial"
                        for x in observed)
            media=key in {"commercial","market"}
            state="partial" if partial or media else "supported"
            reason=("Observed with incomplete sampling or as a media/market claim." if state=="partial"
                    else "A primary-source observation exists for this facet; event identity unverified.")
        output.append({
            "key":key,"label":label,"status":state,
            "reason":reason,"source_ids":[x["id"] for x in observed[:8]],
            "source_count":len(observed),
            "coverage_note":"unmeasured_not_zero" if state=="not_measured" else
                            "source_observed_not_event_confirmed",
        })
    return {"profile":typ,"values":output,
            "independent_event_corroboration_established":False}


def qualified_metric(rows):
    """Return one explicitly qualified deviation; no mixed-unit averaging.

    A source adapter must supply a standardized numeric metric and a comparable
    reference sample. No current production adapters supply this contract.
    """
    qualified=[]
    for row in rows:
        m=row.get("calibrated_metric")
        if not isinstance(m,dict):
            continue
        if m.get("baseline_ready") is not True or m.get("coverage_current") is not True:
            continue
        if m.get("source_id") != row.get("id") or m.get("metric_family") != row.get("source_family"):
            continue
        if not all(isinstance(m.get(k),str) and 0<len(m[k])<=120
                   for k in ("metric","unit","observed_window","reference_window","source_id")):
            continue
        if (type(m.get("comparable_days")) is not int or
                m["comparable_days"]<14 or
                type(m.get("reference_sample_count")) is not int or
                m["reference_sample_count"]<14):
            continue
        values=[m.get(v) for v in ("observed","mean","sd")]
        if not all(type(v) in (float,int) and math.isfinite(v) for v in values):
            continue
        obs,mean,sd=values
        if sd<=0:
            continue
        z=(obs-mean)/sd
        if not math.isfinite(z):
            continue
        qualified.append({
            "status":"calibrated_metric","z_score":round(z,2),
            "observed":obs,"mean":mean,"sd":sd,"unit":m["unit"],
            "metric":m["metric"],"source_id":m["source_id"],
            "observed_window":m["observed_window"],
            "reference_window":m["reference_window"],
            "comparable_days":m["comparable_days"],
            "reference_sample_count":m["reference_sample_count"],
            "axis_limit":5,"clipped_on_axis":abs(z)>5,
        })
    return max(qualified,key=lambda x:abs(x["z_score"])) if qualified else {
        "status":"not_calibrated","z_score":None,
        "reason":"No validated comparable per-metric baseline in the current source data.",
    }
