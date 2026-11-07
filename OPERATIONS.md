# AIBA Operational Feed Automation (Phase 1)

This branch adds a separate, source-audited collection layer to the existing GDELT/Wikimedia watchboard. It is **not** a calibrated war prediction system. The collectors make no assertion that anomalies indicate an imminent attack.

## Scheduled collection

| Schedule (UTC) | Function | Writes |
| --- | --- | --- |
| 00:17, 06:17, 12:17, 18:17 daily | Public market discovery + US/UK official protective notices | Immutable market/official snapshots, source health, fusion |
| 07:25 daily | Maritime Executive RSS and explicitly labeled Google News syndication **media mentions** | Media leads + source health + fusion |
| 11:50 Mondays | Coverage audit (no unsupported false-alarm scores) | Weekly coverage statement + fusion |
| 14:35 daily (original) | Existing strict GDELT event ingestion + Wikipedia + Pages deployment | Website plus feed status panel |

GitHub cron may be delayed. The GitHub Actions scheduler uses UTC; Eastern wall-clock display shifts with daylight saving. These collections are separate from the ChatGPT monitoring automations.

## Durable state

The repository branch **aiba-feed-data** was created separately from main and is used only for append-only observations. The workflow checks out that branch into \`state/\` and creates:

- \`observations/history/{markets,official,commercial}/{timestamp}.json\`
- \`observations/latest/{markets,official,commercial,fusion,weekly_audit}.json\`
- \`observations/health/{markets,official,commercial}.json\`

A source failure updates health but **does not replace the last successful observation with zeros**. Fusion suppresses stale market changes after 12h and stale commercial media leads after 48h. Website publication reads the latest validated branch state, exposes staleness, and never includes credentials. Every source family has its own freshness clock.

Collection requires the workflow's scoped \`GITHUB_TOKEN\` to have \`contents: write\`. The token pushes observations to the dedicated branch, not to main. It needs no user-generated PAT or API key. Repository admins may need to allow GitHub Actions to push if organizational policy blocks it.

## Source contracts

| Source | Public collection path | Assessment ceiling |
| --- | --- | --- |
| Manifold | Documented unauthenticated \`/v0/search-markets\`, exact title + ID + price | **Market candidate only** (binary questions, no cross-market equivalence) |
| Polymarket | Public Gamma \`/events\` top-volume sample and individual Yes outcome prices | **Market candidate only** (incomplete sample; volume is not calibrated prediction) |
| US State | Public travel/security advisory RSS | **Published official protective notice**, often reactive |
| UK FCDO | Public travel advice Atom feed | **Published official protective notice**, often reactive |
| Maritime Executive RSS / Google News syndication | Publisher RSS and aggregated shipping, air-cargo, war-risk headlines; syndication is NOT independent reporting | **Media mention only**, NOT verified insurer/airline/vessel behavior |
| Existing GDELT event archive | Full previous 35-day strict validation | **Provisional global media-coded anomaly** |
| Existing Wikimedia pageviews | Daily public attention measurements | **Public attention**, NOT local behavior or future conflict |
 
Documentation:
- https://docs.manifold.markets/api
- https://institute.polymarket.com/data
- https://travel.state.gov/_res/rss/TAsTWs.xml
- https://www.gov.uk/foreign-travel-advice.atom
- https://www.maritime-executive.com/articles.rss
- https://www.aircargonews.net/feed/

No Good Judgment, licensed Metaculus history, paid insurance terms, granular aviation operations, or actual corporate-action records are included without authorized access. A news headline about a commercial action is NOT treated as independent verification of that action.

## Fusion logic

- Compare each market's **same immutable ID** over approximately 18–36h. A price move of at least 12 percentage points is an *investigatory repricing event*, not proof of escalation or probability of military attack.
- A matching fresh protective notice yields a "cross-source overlap", **not** independent confirmation of attack plans. Unmatched significant repricing yields "quiet-discrepancy candidate", NOT a declaration that the government has issued no warning.
- Use the underlying publication/observation date, not the scraping date, for historical event chronology.
- No escalation to Critical; no automatic revision of \`data/verified_hotspots.json\`.
- Source freshness and source errors remain visible even if another feed succeeds.
- Weekly audit explicitly refuses to invent hit rates without an event-label series and matched non-event windows.

This is intentionally conservative. Next development should use licensed airline/insurance data or verifiable company/agency statements, robust deduplication by common information root, case-specific contract registry, outcome annotation, and true walk-forward calibration before upgrading automated warning statuses.

## First deployment procedure

1. Review/merge the PR only after test suite passes.
2. Run **Actions → Collect AIBA operational feeds → Run workflow → mode: all**. Verify the GHA run, branch \`aiba-feed-data\` history files, and \`health/\` for any failed providers.
3. Run **Validate and publish AIBA** on main, or allow the next daily schedule.
4. Visit \`https://graupmannj-dev.github.io/I-Ws-Dashboard/ops/\`. Verify no source is incorrectly labeled fresh and check the timestamp and link into the main watchboard.
5. Verify failure: temporarily simulate a network API error in a test and confirm it sets unavailable but does not replace previous latest or generate new repricing.
6. Review repository Actions logs and branch storage growth weekly.

The new schedule **will not run until its PR is merged**. Pull-request validation executes only tests and an offline dashboard render, not network source collection. Do not assume it has already run live.

## PR smoke-test findings

The first network probe returned Manifold 7/7, US/UK notices 2/2, but Polymarket's sort query returned HTTP 422 and GDELT DOC 2.0 returned HTTP 429. The adapters were then changed to Polymarket's documented public-search route and direct publisher RSS. A second smoke test returned 14/14 markets and 2/2 official queries but commercial media feeds remained unavailable (one empty RSS, one HTTP 403). Commercial collection now includes a syndication fallback; a new smoke test must be checked before merging; a passing unit test alone is insufficient to claim those source endpoints operate from GitHub Actions.

Syndicated feed URLs may redirect through Google News. They provide leads only; they must not be counted as independent confirmation or as costly behavior by an airline, insurer, or maritime operator.
