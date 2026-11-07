# Validation — 2026-11-07

## Executed successfully in the cloud workspace

- Original package: 10/10 unit tests passed before changes.
- Final implementation: 18/18 tests passed, covering incomplete baselines,
  corrupt/empty/malformed inputs, documented uncoded GDELT markers, exclusion of
  out-of-window cache files, missingness, and preservation of prior build output.
- Python 3.12: clean virtual environment; numpy 2.2.6, scipy 1.15.3;
  `pip check` reports no broken requirements. GitHub CI uses Python 3.11.
- Live command:
  `python aiba_v5.py --as-of 2026-11-06 --download-days 35 --wiki-days 90 --strict-gdelt --output-dir _site`
- All 35 daily ZIPs, 2026-10-03 through 2026-11-06, downloaded from
  `https://data.gdeltproject.org/events/`: 224,364,628 compressed bytes.
  All matched the MD5 values advertised in GDELT's HTTPS directory index.
  MD5 is an upstream integrity comparison, not a cryptographic authenticity proof.
- Entire archives decoded with CRC/schema validation: 3,609,597 rows; four explicit
  uncoded rows excluded. Full 7/7 recent and 28/28 baseline coverage.
- Generated 11 provisional GDELT leads plus 10 supplied curated dossiers.
  No lead was promoted to verified intelligence by the build.
- Wikimedia: 15/15 complete page series; two recent attention-only anomalies.
- Actual generated HTML payload parsed; embedded executable JavaScript passed
  `node --check`.
- System Chromium via Playwright over local HTTP: 21 candidates rendered;
  algorithmic filter showed 11; search and dossier selection worked; mobile
  viewport (390px) had no horizontal overflow; no JavaScript page errors.
- Common credential/private-key pattern scan found no matches in project files.

Per-archive hashes and daily parsing counts are saved in `validation/`.
The initial strict run rejected uncoded markers. Inspecting the live records
identified GDELT's `--- / --- / --` sentinel; a targeted regression test now
preserves the day while explicitly excluding and counting those observations.
The initial failure emitted no deployable output.

## Remaining limitations and approval boundary

- No PR merge or dashboard deployment is authorized yet. The initial empty
  repository required a placeholder base commit so GitHub can present a PR.
- GitHub integration lacks Pages administration permission: creation of a
  workflow-based Pages configuration returned HTTP 403, `Resource not accessible
  by integration`. Owner must select **Settings → Pages → Source → GitHub Actions**.
  No site was enabled or published by that failed request.
- `AIBA_PUBLISH_APPROVED=true` must be set only after explicit publication approval.
  A successful build alone cannot deploy while this variable is unset.
- The live test ran locally in this cloud environment, not on a deployed Pages
  site. GitHub-hosted test results are tracked separately on the PR.
- Source-linked curated narratives, historical CSV observations, market contract
  prices, and assertions of verification supplied in the ZIP were not independently
  fact-checked. Their original dates, qualifications, and URLs are preserved;
  automated builds explicitly disclose this limitation.
- Models are exploratory, do not establish conflict prediction skill, and do not
  correct for multiple hypothesis screening. Wikipedia attention is a worldwide
  English-language audience proxy. Market series are historical, not live.
- Complete files do not guarantee full news coverage, unique events, correct
  country coding, or real-world truth. Malformed or empty required days block
  deployment; explicit uncoded rows are reported, not interpreted as normality.
- Wikimedia is optional. Partial/failing pages are visibly reported; their failure
  cannot be used as evidence of absent attention anomalies. Strict GDELT failure
  blocks artifact upload and deployment; last successful site remains and shows
  its age. Scheduling and remote availability cannot be guaranteed.
- Archive cache currently grows over time; long-lived runners may need cache
  retention tuning. GitHub's cache eviction policy bounds retained remote caches.
- MIT covers project code. Third-party source text/data retain their own terms.
