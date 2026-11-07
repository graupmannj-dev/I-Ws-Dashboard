#!/usr/bin/env python3
"""Attach decision-first case synthesis to AIBA's deployed operations page.

No external text generation or undocumented real-time inference. The main
watchboard and original feed monitor remain available and unchanged in source.
"""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
from pathlib import Path
from ops_pipeline import parse_time, load_json, now_utc, iso

def e(value):
    return html.escape(str(value if value is not None else ""), quote=True)

def link(url, title):
    if not isinstance(url, str) or not url.startswith("https://"):
        return e(title)
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(title)}</a>'

def render_case(case, first=False):
    priority = case["collection_priority"]
    status = "changed" if case.get("source_evidence") else "routine"
    attr = " open" if first else ""
    evidence = []
    for item in case.get("source_evidence", [])[:10]:
        timing = item.get("published_at") or "Publication date unavailable"
        observation = item.get("observed_at") or "Unknown collection timestamp"
        extra = ""
        if item.get("change_pp") is not None:
            extra = f" · {e(item['change_pp'])} pp / {e(item.get('window'))}"
        evidence.append(
            "<li>" + link(item.get("source_url"), item.get("title")) +
            f'<span class="sub"> · {e(item.get("source_family"))}{extra}'
            f' · Published: {e(timing)}; captured: {e(observation)}</span></li>'
        )
    evidence_html = "<ul>" + "".join(evidence) + "</ul>" if evidence else '<p class="sub">No new dated case-specific change established. Historical signals remain in the original watchboard.</p>'
    hist_counter = "".join(
        f'<li>{e(x.get("date"))}: {e(x.get("title"))} — {e(x.get("assessment"))}</li>'
        for x in case.get("historical_counter_signals", [])
    )
    return (
        f'<details class="aiba-case {status}"{attr}><summary>'
        f'<span class="aiba-case-title">{e(case["title"])}</span>'
        f'<span class="aiba-priority">{e(priority)}</span></summary>'
        '<div class="aiba-detail">'
        f'<p class="aiba-prompt"><strong>Decision question:</strong> {e(case["question"])}</p>'
        f'<p><strong>What changed:</strong> {e(case["what_changed"])}</p>'
        f'<p><strong>So what:</strong> {e(case["so_what"])}</p>'
        f'<p><strong>What would change the assessment:</strong> {e(case["what_would_change_assessment"])}</p>'
        f'<p><strong>Alternative explanation:</strong> {e(case["alternative_explanation"])}</p>'
        f'<p class="sub"><strong>Background severity:</strong> {e(case["standing_state"])} '
        f'(curated as of {e(case["standing_asof"])}; historical, not automatically reverified). '
        f'Warning horizon: {e(case["warning_horizon"])}</p>'
        '<h4>New source observations and provenance</h4>' + evidence_html +
        ('<h4>Dated historical counter-signals</h4><ul>' + hist_counter + "</ul>" if hist_counter else "") +
        '<p class="sub">' + e(case.get("verification")) + '</p>'
        "</div></details>"
    )

CSS = """
#aiba-decision{border:1px solid #789bc1;padding:17px;border-radius:12px;background:#172433;margin:16px 0}
#aiba-decision h2{color:#f3f6ff;margin:0 0 10px}#aiba-decision p{margin:8px 0 12px}
#aiba-decision .aiba-case{border:1px solid #445468;border-radius:9px;margin:8px 0;background:#1e2d3e}
#aiba-decision .aiba-case summary{cursor:pointer;list-style:none;padding:11px 14px;display:flex;gap:9px;align-items:center;justify-content:space-between}
#aiba-decision .aiba-case summary::-webkit-details-marker{display:none}
#aiba-decision .aiba-case-title{font-weight:700}
#aiba-decision .aiba-priority{border:1px solid #7d92a8;border-radius:12px;padding:3px 9px;font-size:11px;color:#dce7f1;white-space:nowrap}
#aiba-decision .aiba-case.changed{border-color:#ccad72}
#aiba-decision .aiba-case.changed .aiba-priority{color:#f8da97;border-color:#c49b5f}
#aiba-decision .aiba-detail{padding:0 14px 14px}
#aiba-decision .aiba-prompt{font-size:14px;background:#263a50;padding:10px;border-radius:7px}
#aiba-decision .aiba-stats{display:flex;flex-wrap:wrap;gap:9px;font-size:12px;color:#bfcfdf;margin:10px 0 16px}
#aiba-decision .aiba-stats span{border:1px solid #3e536b;border-radius:8px;padding:6px 8px}
#aiba-decision h4{font-size:13px;margin:14px 0 6px}
#aiba-decision li{margin-bottom:8px}
@media(max-width:550px){#aiba-decision .aiba-case summary{display:block}.aiba-priority{display:inline-block;margin-top:5px}}
"""

def attach(state, site, clock=now_utc):
    site = Path(site)
    home = site / "ops" / "index.html"
    if not home.exists():
        raise FileNotFoundError("Run ops_render.py before decision_render.py")
    output = load_json(Path(state) / "latest" / "decision_briefs.json", None)
    if output is None:
        # The daily Pages build must not fail just because the new independent
        # six-hour collector has not executed. Label unavailability explicitly.
        output = {
            "generated_at": None, "cases": [], "new_change_count": 0,
            "executive_summary": "Scenario synthesis is unavailable: no verified collection snapshot has been received.",
            "operational_action": "Run the operational collector and check its source-health records; do not infer a quiet environment.",
            "source_health": {}, "limits": ["No synthesis observations were available at publication time."]
        }
    stamp = parse_time(output.get("generated_at"))
    age = (clock() - stamp).total_seconds() / 3600 if stamp else None
    age_state = ("current" if age is not None and 0 <= age <= 24 else "STALE / timestamp unavailable")
    cases = output.get("cases", [])
    source_status = output.get("source_health", {})
    counts = f'{e(output.get("new_change_count"))} cases with new monitored change leads'
    states = "".join(
        '<span>' + e(k.capitalize()) + ': ' + e(v.get("status")) +
        ' (as of ' + e(v.get("latest_observation") or "unknown") + ')</span>'
        for k,v in source_status.items()
    )
    cases_html = "".join(render_case(c, i < 2) for i,c in enumerate(cases))
    section = (
        '<section id="aiba-decision"><h2>Intelligence synthesis · What changed and why it matters</h2>'
        '<p><strong>' + e(output.get("executive_summary")) + '</strong></p>'
        '<p>' + e(output.get("operational_action")) + '</p>'
        '<p class="sub">Assessment evidence captured ' + e(output.get("generated_at")) +
        '; freshness: ' + e(age_state) + '. The page itself updates on daily publication, not every source check. '
        'Case priority is a collection task, not a probability or threat level.</p>'
        '<div class="aiba-stats"><span>' + counts + '</span>' + states + '</div>'
        + cases_html +
        '<p class="sub">Strict safeguard: first snapshots establish baselines; archived advisories are not new events; '
        'markets reflect their exact outcomes; headlines are not independent commercial decisions. '
        '<a href="decision_briefs.json">Inspect source-linked machine-readable briefs</a>.</p>'
        '</section>'
    )
    existing = home.read_text(encoding="utf-8")
    anchor = '<div class="cards">'
    if anchor not in existing:
        raise ValueError("Cannot find feed-monitor insertion point")
    if 'id="aiba-decision"' in existing:
        raise ValueError("Repeated injection would duplicate synthesis")
    existing = existing.replace("</style>", CSS + "\n</style>", 1)
    existing = existing.replace(anchor, section + "\n" + anchor, 1)
    home.write_text(existing, encoding="utf-8")
    (site/"ops"/"decision_briefs.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"case_count": len(cases), "changed": output.get("new_change_count"),
            "asof": output.get("generated_at"), "freshness": age_state}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--site", type=Path, required=True)
    a=p.parse_args()
    print(json.dumps(attach(a.state, a.site), indent=2))
