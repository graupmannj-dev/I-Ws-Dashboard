# One representative complete aircraft archive day — bounded benchmark

**State:** source release metadata verified; **full source not yet
downloaded or scanned**. This is one manually triggered benchmark,
not historical cohort validation, an automatic collector, a live
sensor, a warning, or a dashboard publication.

## Representative source selection

ADSB.lol release metadata for production source day 2026-11-10:

| Asset | Source bytes | SHA-256 |
| --- | ---: | --- |
| v2026.11.10-planes-readsb-prod-0.tar.aa | 2,000,000,000 | 2b44326f24bc6c0eb7cd6dcfa39923ac25e6fe4746fc7d9a32860cee630ed293 |
| v2026.11.10-planes-readsb-prod-0.tar.ab | 1,689,415,168 | 831f9b6b751ca597ed24afc5ac0f75ac3c12fe0740a0428529848505203c4449 |

Total: **3,689,415,168 bytes (3.689 GB / 3.436 GiB)**;
source published 2026-11-11 03:27 UTC. This pins the source instance
and guards against silently replacing changed release assets.

To assess representativeness by size, other source-day production
metadata recorded at the same time:

| Day | Production source bytes |
| --- | ---: |
| 2026-11-07 | 3,404,765,184 |
| 2026-11-08 | 3,459,915,264 |
| 2026-11-09 | 3,723,313,664 |
| 2026-11-10 | 3,689,415,168 |

These are publisher-reported **asset sizes**, **not** measured
transfer, completeness of ADS-B reception, runtime, coverage, number
of aircraft or detection performance. Source:
https://api.github.com/repos/adsblol/globe_history_2026/releases/tags/v2026.11.10-planes-readsb-prod-0 .

## How the one-day verification works

The standard-library runner in
scripts/aircraft_one_day_benchmark.py has two modes.

1. Default: query the public GitHub release metadata and require
   exact agreement of asset filenames, published status, sizes
   and SHA-256 pins. **No archive download**.
2. Explicit opt-in: require the manual phrase
   YES_ONE_DAY_3_69_GB, an ephemeral work directory, and a
   source-day-only test cohort. Before any download, validate
   metadata and require enough free space for the files plus
   a 2-GiB buffer. Then download the two named HTTPS assets
   using bounded curl transfers (600 seconds each),
   validate exact byte count and SHA-256, and invoke the
   already tested offline bounded split-TAR scanner (600
   seconds maximum; 4,000,000,000-byte cap).
   Raw archives are stored only in an auto-deleting temporary
   directory. No selected aircraft traces are written to
   files or uploaded.

The resource receipt can establish **bytes downloaded, elapsed
transfer/scan wall time, bytes scanned, TAR member/trace counts,
Python peak RSS and whether the supplied two-part TAR was fully
scanned**. It does not prove full global receiver coverage,
flight-leg validity or early-warning accuracy.

The synthetic ICAO 000000 in
data/validation/aircraft_one_day_benchmark_control.json is a
**negative-control selection**, not a real route cohort. The
scanner will likely select zero matching aircraft, and that is
**not** evidence that a legitimate aircraft cohort is empty.
The first run is an infrastructure feasibility test only.

## Safe manual execution (after review/merge)

Use the GitHub Actions page for the workflow:

https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/aircraft-one-day-benchmark.yml

Select **Run workflow** on main. The default choice is
METADATA_ONLY, which checks source metadata without downloading.
To intentionally perform the complete one-day scan, choose
YES_ONE_DAY_3_69_GB. This starts a single 3.69-GB public download.
No cron, push trigger, pull-request download or other auto-run
path exists in this benchmark workflow.

The workflow runs on a **standard** ubuntu-latest hosted runner.
Its job has a 40-minute timeout and contents:read-only
permission. Only the small JSON measurement receipt is uploaded
as a seven-day GitHub Actions artifact. The source data and any
raw selected tracks are never uploaded and are discarded at exit.

GitHub currently documents standard GitHub-hosted runners for
public repositories as free and lists 14 GB SSD storage for
ubuntu-latest. This does **not** guarantee source availability,
network throughput, daily future run success or absence of
future pricing changes. Verify resource use before proposing
even one daily scheduled download. Do not run this benchmark
on a billable larger runner or in Google Cloud.

Source runner reference:
https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job

## Acceptance gate to consider a 28-day pilot

A one-day result is acceptable only if:

- The release metadata exactly matches the pinned asset sizes
  and SHA-256 values; downloads re-hash successfully.
- Both parts can be read on a standard free runner without
  cloud resources or accidentally publishing geometry.
- The full TAR stream reaches a verified terminator, remains
  inside time/memory/byte limits and has no parser errors.
- Receipt explicitly differentiates successfully read TAR from
  source receiver coverage and from valid flight history.
- Benchmark timing and source size support a sustainable plan
  for a **bounded, preselected** historical cohort; do not
  equate a one-day pass with 28-day affordability.
- The team identifies real recurring route/direction cohorts,
  verified source-day availability and leg segmentation
  *before* evaluating held-out flight paths.

On any failure, output must be unavailable or incomplete, never
a successful zero-anomaly day.

## Strategic placement

The aviation module is one source class in the larger
[global pre-news tipper and learning architecture](AIBA_TIPPER_EVIDENCE_LOOP.md).
AIBA should discover developing situations through convergent
independent indicators. It should then record actual lead time
relative to GDELT/news first reporting, and validate *eligible*
later outcomes against UCDP and reviewed primary evidence. This
one-day benchmark has **zero** authority to change that process,
dashboard severity, or historical warning records.

Run offline synthetic tests:

~~~bash
python -m unittest tests.test_aircraft_one_day_benchmark -v
~~~
