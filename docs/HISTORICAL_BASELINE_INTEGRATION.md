# Historical baseline integration: source-profiled GDELT shadow chronology

## Current state and explicit boundary

PR #17 collects daily GDELT 1.0 **EventRootCode 17–20 only** into
`daily.jsonl`, `shadow_replay.jsonl`, and `manifest.json`, which GitHub
retains as per-run Actions artifacts for **90 days**. It does **not**
change the deployed discovery algorithm or the structural-friction baseline.

The production GDELT discovery code in `aiba_v4.py` uses event roots
**13, 16, 17, 18, 19 and 20**. Its 7-vs-28-day Bayesian-tail heuristic is
not directly comparable to the four-root historical stream. Do **not**
merge its relative frequencies or thresholds with historical four-root
frequencies without a versioned matched-scope refactor.

The structural-friction collector has its own short IODA/NGA/AMSA
matched-hour 14-day baseline; GDELT history cannot calibrate those feeds.

## Reassemble the history

1. In **Actions → Historical GDELT baseline (manual shadow mode)**, run
   bounded dated intervals of up to 120 days, reviewing each artifact's
   `manifest.json`. Partial runs are usable as incomplete data, never
   repaired by zero-filling.
2. After the runs finish, use **Actions → Assemble GDELT historical
   baselines (manual shadow mode)** and enter the desired inclusive
   calendar start/end dates. This downloads up to the most recent 100
   completed backfill workflow runs' retained `gdelt-baseline-*` artifacts,
   deduplicates identical overlap dates, and **rejects conflicting records**.
3. Download the resulting `gdelt-merged-shadow-*` artifact and inspect:
   - `manifest.json`: exact calendar range, missing dates, analyzable
     days, and explicitly unapproved production status;
   - `merged_daily.jsonl.gz`: complete available per-day selected
     counts, without raw publisher content;
   - `shadow_candidates.jsonl`: bounded, provisional departures
     relative to strictly earlier calendar days.
4. The current replay demands **28 immediately preceding complete
   calendar days**, plus >=90% historical coverage across the available
   prior 90-day window. It records the median and 95th-percentile
   historical event-share benchmarks, but screens candidates only.
5. Retain the final merged dataset in an approved persistent object
   store (e.g., a Google Cloud Storage bucket) with checksums and
   versioned manifests. GitHub's 90-day action retention is **not**
   permanent archival storage. Object-storage authentication and
   publication need a separate approved configuration; this PR does
   not guess or deploy credentials.

## Before feeding this into production

- Backfill a suitable historical span and independently validate at
  least several real archives against `aiba_v4.archive_rows` schema.
- Build a **same-root-coverage** comparator for roots 17–20, or
  backfill the production root set 13,16,17–20 using an explicitly
  versioned profile; never mix denominators.
- Compare 7/28, 30/90, and longer conflict-regime-specific reference
  periods on the **same historical cutoffs**.
- Quantify candidate frequency by theater/week and false-surprise
  burden. Deduplicate common media roots where possible; separate
  baseline shifts in media coverage from underlying security activity.
- Keep historical replay in shadow mode until independently adjudicated
  escalation **and non-event** windows permit evaluation.
- Only after review, expose source baseline dates, coverage,
  and measured anomaly magnitude in the dashboard's `so what` panel.
- No automatic change in watch severity or claimed attack probability.

The first 28-day warmup penalty of **each bounded run** is avoided by
recomputing against the assembled calendar series. Gaps still correctly
interrupt nearby baselines. This is a necessary integration stage,
not evidence that the historical archive has been downloaded already.
