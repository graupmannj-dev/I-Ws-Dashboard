# Daily aircraft route anomaly pilot

Status: **planned; input readability checked locally; detector not implemented
or deployed**. No aircraft analysis job is scheduled by this document.

## Intended dashboard behavior

AIBA should surface a small number of unusual observed flight paths, explain
why they differ from comparable earlier flights, and show actual tracks beside
a historical reference corridor. Worldwide discovery is the eventual scope;
displaying every aircraft is not required. The first processing experiment
uses a small, predefined cohort from any region and must not be described as
worldwide monitoring.

Start with one retrospective report per day. Six-hour observation updates are
a later goal. A corridor describes earlier observations, not an assigned flight
plan, a known destination, a prediction or evidence of intent. Unusual behavior
alone does not establish its cause or change AIBA's threat classifications.

## Current implementation and evidence

The [existing ADSB.lol adapter](../dashboard/adsb_lol.py) collects one explicitly
configured region with a maximum radius of 250 nautical miles. It does not
retain aircraft history, construct normal routes or detect deviations.
[Deployment instructions](../ADSB_LOL_DEPLOYMENT.md) for that adapter do not
implement this pilot.

ADSB.lol publishes daily archives with per-aircraft trace JSON. The upstream
[2026 release index](https://github.com/adsblol/globe_history_2026/blob/main/RELEASES.md)
listed the 2026-11-10 production archive as **3,518 MiB**, split across two
assets. This is a source-day size, not a measured processing requirement.
Do not ingest production, staging and MLAT-only archives as independent
aircraft populations without checking their overlap.

A local check on 2026-11-11 read only the first **262,144 bytes** of the first
production asset. Eleven complete aircraft JSON files contained 8,668 trace
rows. All rows had numeric coordinates; the source marked 148 rows stale and
10 rows as leg starts. Callsigns were present in supplementary metadata on
2,025 rows, so a callsign cannot be assumed on every position.

This archive-order prefix is not a representative geographic sample. The
check demonstrates readable structure only. It does **not** establish complete
coverage, valid flight segmentation, a historical baseline, detector accuracy,
runtime for a full archive, or zero-cost hosting. Counts and the prefix digest
are recorded in [the input-check receipt](evidence/aircraft-input-check-2026-11-11.json).
No raw aircraft traces are included in this PR.

The [readsb trace format](https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons)
documents per-position time offsets, coordinates, altitude, speed, supplementary
metadata and flags for stale positions and possible leg starts. These fields
are useful inputs; their presence does not validate an anomaly method.

## Implementation sequence and acceptance checks

1. **Measure ingestion.** Build a bounded reader with explicit byte, time and
   output limits. Record transfer bytes, runtime, peak memory and retained
   geometry size. Test failure and incomplete-archive handling. Stream where
   practical rather than storing whole raw archives. Determine whether the
   archive packaging still requires reading substantial unrelated data to
   select a small cohort.
2. **Fix the comparison cohort.** Select recurring flights before looking at
   the evaluation day's deviations. Initially test comparable route/direction
   groups, rather than treating every flight of the same aircraft as having
   the same expected destination. Keep an explicit cohort and coverage record.
   Changes in aircraft identity, route assignment or callsign need handling;
   insufficient metadata must remain an explicit limitation.
3. **Construct historical references.** Use only observations preceding the
   evaluated flight. A provisional starting window is 28 days; require enough
   comparable flights rather than treating a full window as proof of adequacy.
   Retain compact per-flight geometry and supporting metrics: counts alone
   cannot draw a reference corridor. Keep baseline and evaluation days
   separate to avoid using the evaluated flight to define its own normality.
4. **Handle gaps and flight legs.** Exclude stale/unreliable positions and
   distinguish multiple flights in a daily aircraft file. Source leg markers
   are hints requiring validation. Do not draw a continuous path across long
   observation gaps or treat receiver loss as an aircraft maneuver. Missing
   coverage and missing history are separate output states.
5. **Evaluate explainable deviations.** Begin with sustained distance from a
   historical route corridor. Choose and document minimum comparison counts,
   usable coverage and deviation thresholds before evaluating held-out days.
   Review ordinary and unusual examples; do not tune only to striking cases.
   With insufficient comparable history or coverage, emit
   `insufficient_history` or `insufficient_coverage`, not an anomaly score or
   an invented expected line. Scores remain experimental until reviewed.
6. **Connect a bounded report to Atlas.** After local detector validation,
   define a report contract and offline rendering checks. Show candidate
   reasons, actual paths, reference corridors, source dates, observation gaps
   and comparison counts. A failed job must show unavailable/stale status,
   not a successful zero-anomaly report. Review source attribution and the
   applicable database license before public redistribution.
7. **Schedule only after measurement and review.** Candidate hosting is
   standard GitHub Actions runners for a public repository, with compact
   results displayed by GitHub Pages. Verify actual workload and service
   limits before claiming it is free. Bound output retention and avoid an
   indefinitely growing Git branch of raw flight tracks. Review initial
   results before enabling scheduled collection or publishing the UI.

## Cadence, cost and deployment boundaries

- Daily source archives support daily retrospective reports. Re-running their
  analysis every six hours does not provide newer observations. Six-hour
  updates need a supported fresher source and a new access/workload assessment.
- A small local processing test needs no Google Cloud VM. The zero-cost goal
  is a design constraint, not an established result or permission to incur
  charges. Google Cloud free-tier allowances are not spending caps.
- Cloud resource creation, IAM changes, VM modification, deployment and
  production workflow dispatch remain outside the currently authorized
  read-only cloud work. This plan adds none of those operations.
- Codex can assist through reviewed repository changes and analysis outputs.
  A permanently signed-in shared cloud browser is not required by this batch
  design. Windows CLI authentication does not authenticate a GitHub runner or
  Codex's separate cloud environment.

## Reproduce the bounded input check

The receipt points to the source asset, exact inclusive byte range and SHA-256
of the downloaded prefix. Keep TLS verification and inherited proxy settings.
For a local recheck, request `Range: bytes=0-262143`, require HTTP 206 and a
matching content range, and reject a full-archive response. Read complete tar
members only; the prefix ends before the entire archive is available. Parse
JSON, decompress gzip members if present, and count source flags using the
documented bit meanings. Do not extract archive paths onto the filesystem.

The check used an explicit transfer limit and a 30-second timeout; it did not
download a complete archive. A later mismatch in this prefix digest must be
investigated as a source-content change, not silently accepted as the same run.

## Follow-up PRs

- Bounded archive reader and measured processing experiment, with a
  reproducible command and meaningful malformed/missing-input tests.
- Historical route reference and held-out evaluation, including insufficient
  history and coverage cases.
- Atlas report rendering, then a reviewed daily workflow once measured costs
  and output retention are acceptable.

These are planned deliverables. None is completed by this documentation PR.
