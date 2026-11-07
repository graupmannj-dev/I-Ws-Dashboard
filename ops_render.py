#!/usr/bin/env python3
"""Publish a dated operations panel from durable snapshots; no browser-side API keys."""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
from pathlib import Path
from ops_pipeline import load_json, parse_time, now_utc, iso

def esc(value):
    return html.escape(str(value or ""), quote=True)

def safe_url(value):
    return value if isinstance(value, str) and value.startswith("https://") else ""

def source_link(url, title):
    if not safe_url(url):
        return esc(title)
    return '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(title) + "</a>"

def feed_status(state, mode, clock):
    health = load_json(Path(state) / "health" / (mode + ".json"), {"status": "not_started"})
    latest = load_json(Path(state) / "latest" / (mode + ".json"), {})
    stamp = parse_time(latest.get("observed_at"))
    age_hours = round((clock - stamp).total_seconds() / 3600, 1) if stamp else None
    age_limit = 48 if mode == "commercial" else 12
    freshness = "not_available" if age_hours is None else ("fresh" if 0 <= age_hours <= age_limit else "stale")
    if health.get("status") == "unavailable":
        freshness = "collection_failed"
    return {"health": health, "snapshot": latest, "age_hours": age_hours, "freshness": freshness}

def render(state, site, clock=now_utc):
    state, site = Path(state), Path(site)
    at = clock()
    sources = {mode: feed_status(state, mode, at) for mode in ("markets", "official", "commercial")}
    fusion = load_json(state / "latest" / "fusion.json", {})
    audit = load_json(state / "latest" / "weekly_audit.json", {})
    status = {"published_at": iso(at), "sources": {
        mode: {"freshness": entry["freshness"], "age_hours": entry["age_hours"],
               "status": entry["health"].get("status"), "last_observed": entry["snapshot"].get("observed_at"),
               "last_checked": entry["health"].get("checked_at"), "records": len(entry["snapshot"].get("records", []))}
        for mode, entry in sources.items()},
        "fusion_asof": fusion.get("generated_at"), "audit_asof": audit.get("generated_at"),
        "assessment": "Lead discovery, NOT a validated forecast, official intelligence assessment or attack probability."}
    target = site / "ops"
    target.mkdir(parents=True, exist_ok=True)
    (target / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    cards = []
    for mode, record in sources.items():
        n = len(record["snapshot"].get("records", []))
        cards.append('<div class="card"><h3>' + esc(mode.capitalize()) + '</h3>'
                     '<div class="big">' + esc(n) + ' <span class="sub">records</span></div>'
                     '<p>Source: <strong>' + esc(record["freshness"].replace("_", " ")) + '</strong></p>'
                     '<p class="sub">Observation: ' + esc(record["snapshot"].get("observed_at") or "Never") +
                     '; collection check: ' + esc(record["health"].get("checked_at") or "Never") + '</p></div>')
    leads = fusion.get("preconvergence_leads", [])
    market_rows = []
    for item in fusion.get("market_moves", [])[:20]:
        market_rows.append("<tr><td>" + source_link(item.get("url"), item.get("title")) +
                           "</td><td>" + esc(item.get("change_24h_approx")) +
                           "</td><td>" + esc(", ".join(item.get("scenario_tags", []))) +
                           "</td></tr>")
    official_rows = []
    for item in fusion.get("new_official_notices", [])[:30]:
        official_rows.append("<li>" + source_link(item.get("source_url"), item.get("title")) +
                             '<span class="sub"> · ' + esc(item.get("publisher")) + " · " +
                             esc(item.get("published_at")) + "</span></li>")
    commercial_rows = []
    for item in fusion.get("commercial_media_leads", [])[:30]:
        commercial_rows.append("<li>" + source_link(item.get("source_url"), item.get("title")) +
                               '<span class="sub"> · news mention, not independently verified</span></li>')
    doc = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AIBA Operational Feeds</title>
<style>
:root{color-scheme:dark}body{margin:0;background:#0f141e;color:#e6ecf7;font:14px/1.55 system-ui,sans-serif}
main{max-width:1160px;padding:26px;margin:auto}a{color:#a8cbff}.sub{color:#9ea9b9;font-size:12px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px}.card,section{background:#1c2532;border:1px solid #364153;padding:16px;border-radius:12px;margin:15px 0}
.big{font-size:26px;font-weight:700}h1{font-size:26px}h2{font-size:18px}h3{font-size:15px;margin:0}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #394456;padding:9px;text-align:left}
li{margin-bottom:9px}.warning{background:#382d1e;border:1px solid #7f6537;border-radius:8px;padding:12px}
</style></head><body><main><p><a href="../">← Global watchboard</a></p>
<h1>AIBA · Operational Feed Monitor</h1><p class="warning">
Unclassified open-source investigative leads only. Market movements are not calibrated attack probabilities;
media reports are not direct observations of commercial decisions. Old data and failed sources are not interpreted as normal.</p>
<p class="sub">Site generated: """ + esc(status["published_at"]) + """ UTC. This panel updates on the daily Pages publish, not on each six-hour collection.</p>
<div class="cards">""" + "".join(cards) + """</div>
<section><h2>Market repricing / pre-convergence</h2>
<p class="sub">""" + esc(len(leads)) + """ investigatory lead(s); strictly same-contract approx. 24h comparisons.</p>
<table><thead><tr><th>Contract and exact question</th><th>Δ probability</th><th>Candidate scenario</th></tr></thead>
<tbody>""" + "".join(market_rows) + """</tbody></table>
<p class="sub">No significant repricing, or insufficient paired historical snapshots, if table is empty. A quiet discrepancy is not confirmation of an imminent event.</p></section>
<section><h2>Recent official protective notices</h2><ul>""" + "".join(official_rows) + """</ul>
<p class="sub">Travel notices usually reflect public risk and are not direct evidence of operational preparations.</p></section>
<section><h2>Commercial and institutional media leads</h2><ul>""" + "".join(commercial_rows) + """</ul>
<p class="sub">News items may describe the same underlying incident or official statement. Confirm company action and effective date independently before treating as a costly signal.</p></section>
<section><h2>Historical validation</h2><p>""" + esc(audit.get("warning_performance") or
            "Pending: no weekly scored backtest. Current system has no validated event prediction accuracy.") +
            """</p><p class="sub"><a href="status.json">Source health JSON</a></p></section>
</main></body></html>"""
    (target / "index.html").write_text(doc, encoding="utf-8")
    link = '<a href="ops/" style="position:fixed;right:14px;bottom:14px;z-index:10000;background:#22334a;color:#fff;border:1px solid #90acd0;border-radius:9px;padding:10px 14px;font:600 13px system-ui;text-decoration:none;box-shadow:0 3px 15px #0008">Operational feeds ↗</a>'
    for file in ("index.html", "Global_AIBA_5_Watchboard.html", "Global_AIBA_4_Watchboard.html"):
        target_html = site / file
        if target_html.exists():
            contents = target_html.read_text(encoding="utf-8")
            if 'href="ops/"' not in contents and "</body>" in contents:
                target_html.write_text(contents.replace("</body>", link + "</body>", 1), encoding="utf-8")
    return status

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, default=Path("observations"))
    p.add_argument("--site", type=Path, default=Path("_site"))
    a = p.parse_args()
    print(json.dumps(render(a.state, a.site), indent=2))
