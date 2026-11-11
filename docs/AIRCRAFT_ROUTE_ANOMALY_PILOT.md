# Daily aircraft route anomaly pilot

Status: **bounded input reader checked; offline experimental historical corridor
comparator implemented separately, not deployed or scheduled**. See
[the offline retrospective prototype](AIRCRAFT_ROUTE_RETROSPECTIVE.md).
No aircraft analysis job is scheduled by this document.

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

The first implementation is `scripts/aircraft_archive_probe.py`. It uses
Python's standard library and `curl` on Linux (including standard Ubuntu
GitHub Actions runners). It is a manual input experiment; no workflow or
dashboard build invokes it.

From the repository root, download a bounded prefix and produce an aggregate
receipt outside the checkout:

```bash
python scripts/aircraft_archive_probe.py \
  --date 2026-11-10 \
  --output /tmp/aiba-aircraft-probe.json
```

The default transfer is 256 KiB with a 30-second deadline, up to 25 complete
aircraft files and 250,000 rows. `--max-bytes` can increase the prefix to at
most 16 MiB; decoded JSON is limited to 2 MiB per aircraft. This is not a
whole-day ingest command. Change `--date` only to an available archived day;
archive publication can lag the observation date. The URL is generated from
the date and cannot be overridden with an arbitrary host.

For an existing local prefix, add `--archive-prefix /path/to/prefix`. Its source
date and provenance are caller supplied, not verified by the local file path.
The same byte and parser limits apply. No archive member is extracted to disk,
and output contains no aircraft identities, callsigns or track coordinates.

Success returns exit code 0 and `status=input_sample_readable`. A network,
format, empty/unusable sample or limit failure returns 1 and writes an
`unavailable` receipt without successful counts, replacing any earlier success
at that output path. An incomplete last member is expected for a prefix and
is excluded with an explicit stop reason. Enough valid rows to read a sample
does not establish accurate flight paths or a usable baseline.

The receipt records a prefix digest, HTTP range metadata for remote reads,
source-quality counts, elapsed wall time and Linux Python-process CPU/peak RSS.
The memory/CPU figures exclude the curl child. Input-byte counts exclude HTTP
headers. Output-file size can be measured separately with `wc -c`; none of
these small-prefix results estimate the workload of a full day.

A [fresh HTTPS-run receipt](evidence/aircraft-archive-probe-2026-11-11.json)
reproduced the original digest and 11-file/8,668-row sample. That run transferred
262,144 payload bytes, took approximately 0.48 seconds of wall time, and
reported 18,120 KiB Python-process peak RSS. The aggregate receipt occupied
1,488 bytes. These are measurements from one small sample on one machine,
not a full-day cost estimate or a claim that worldwide processing is free.

Offline parser, limit, transport-response and failure-receipt tests run with:

```bash
python -m unittest tests.test_aircraft_archive_probe -v
```

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

- [Bounded offline cohort archive scanner](AIRCRAFT_COHORT_ARCHIVE_SCAN.md)
  now extracts preselected source traces for review. Its
  [first full-day production source measurement](AIRCRAFT_ONE_DAY_BENCHMARK.md)
  verified a complete 3.689 GB TAR stream in 23.2 seconds on a
  standard GitHub-hosted runner. That run used a synthetic negative-control
  ICAO. **Real comparative flight-leg coverage and 28-day affordability
  remain unvalidated**, despite successful one-day source ingestion.
- Offline historical reference and held-out evaluation now exist as an
  **unvalidated synthetic-tested prototype**; a real preselected cohort with
  independently verified historical coverage remains necessary.
- Atlas report rendering, then a reviewed daily workflow once measured costs
  and output retention are acceptable.

The offline prototype exists; real-source historical calibration, map
integration and daily scheduling remain planned. The measured archive prefix
remains unsuitable as a route baseline.
