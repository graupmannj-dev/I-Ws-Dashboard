# Aircraft retention shadow-loss audit — held-out Nov 10 source day

**Status:** experimental validation only. No raw trace deletion or storage
policy change. The experiment compares PR #42's 10-minute, 2-km/500-ft
loss-bounded copy against original source tracks in memory, using a
**precommitted 2026-11-10** held-out production archive and the identical
path-independent hash sampling rule frozen in PR #40 on 2026-11-07.

This is NOT a prospective dated geopolitical warning or a demonstrated
route-anomaly detector. There are no historical cohort-matched assigned
flight paths in this test. The only objects compared here are **geometric
and short-time diagnostic signatures**. Do not infer precision/recall
about real threats or real aircraft mission changes from these outputs.

## Observed production-source findings (November 11/12, 2026)

The complete November 10 production TAR was downloaded and verified on a
standard public GitHub runner. There were two runs; **the first found a
real defect** in the source PR42 time-anchor selection: the code picked
the first observation at or after the 600-second interval, which can
produce a stored gap over 600 seconds when raw ADS-B rows are irregular.
This invalidated 73 out of 130 otherwise plausible shadow legs.
The follow-up fix anchors at the last observation BEFORE a crossed
time deadline and uses additional selected rows to keep every
stored interval <=600 seconds. A synthetic irregular-interval
regression test now covers the failure.

The initial run is recorded for audit, not blended with the corrected
results. Evidence: [Initial run](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/43139506141);
[Corrected run](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/43140037805);
[permanent comparative aggregate receipt](evidence/aircraft-retention-heldout-2026-11-10.json).

**Corrected-run results:**

| Metric | Observed |
| --- | ---: |
| Source archive size; both SHA-256 checks passed | 3,689,415,168 B |
| Total source trace members | 75,360 |
| Path-independent sampled traces | 70 |
| Provisional segments | 1,107 |
| Too short / sparse / otherwise subthreshold segments | 977 |
| Uninterrupted segments evaluated for compression | 130 |
| Original positions in those segments | 54,343 |
| Thinned positions in those segments | 2,055 (96.22% reduction) |
| Gzip original geometry-arrays (not source archive) | 752,551 B |
| Gzip thinned geometry-arrays | 38,297 B (94.91% reduction) |
| Max verified horizontal reconstruction error | 1.99185 km |
| Max verified altitude reconstruction error | 499.537 ft |
| Segment-level full lateral/altitude diagnostic positives | 0 / 1 |
| Full-positive events absent from reduced version | 0 / 0 |
| New positives when applying the SAME triplet code to reduced positions | 99 lateral / 60 altitude |

The new triplet positives do **not** indicate 159 physical
maneuvers. This is an explicit *sampling-cadence mismatch*: with
different adjacent timestamps, local triplets cover different
distances and durations. Re-running a high-frequency event
detector on a sparse geometry archive without adapting its
sampling logic can generate spurious signatures. The absence
of any original lateral-positive segment also means this
sample **cannot estimate real short-turn sensitivity**.
A separate synthetic test demonstrates that a **1.5 km,
short-lived lateral excursion can disappear** under the 2 km
per-point reconstruction allowance, despite satisfying the
claimed geometry bound.

**Conclusions:** the time-anchor bug is fixed; the implementation
can reduce the *eligible shadow legs'* geometry arrays by roughly
95% even relative to gzip-compressed originals. That is **NOT**
an estimate of savings from the 3.69 GB daily source acquisition,
or from a real deployed backend. The sampled data are
historical observations, not independently verified
completed/landed/normal flights. No actual event-labeled
production warning detector was run, and none of this supports
a raw-retention purge. The normal-review gate in PR42 remains
mandatory, unvalidated and inactive in production.

The one-time GitHub Actions event trigger was removed from
the PR branch after the corrected empirical run. The complete
raw source files and ephemeral selected geometry were discarded
by the isolated runner; only the aggregate receipt is retained.

## Pre-registered tests and safeguards

The source is the same SHA-256-pinned Nov 10, 2026 ADSB.lol production
archive previously benchmarked in PR #39. The runner uses one standard
public-repo GitHub Actions machine, with a fixed 4.0 GB scan cap,
600-second time cap, selected sample maximum 150 aircraft traces,
48 MiB expanded source cap, and source-size plus 2 GiB minimum ephemeral storage
before downloads. Downloading each source part requires SHA-256
verification and exact publication metadata match.

The sampled identities are selected by the PR #40 frozen SHA-256
modulo-1024 rule **without looking at the Nov 10 paths**.
This avoids tuning to an apparently unusual held-out flight, but
it does not make the tiny sample representative of global aviation,
receiver coverage, geography, or operational military behavior.

Only single, continuous-seeming airborne segments are considered:
stale, ground, source-leg boundary, callsign change, invalid altitude,
duplicate timestamps, reception gaps and jumps separate/stop segments.
No attempt is made to classify landing or normality; none of the
segments qualifies for PR #42's actual reviewed-retention authorization.

For each eligible segment compare:

1. Original versus PR #42 post-flight simplification geometry
   using a max 600-second gap, 2 km horizontal/500 ft vertical
   reconstruction error. Record number of positions kept.
2. Actual **gzip to gzip** byte burden for full and reduced
   source arrays. Compression savings relative to uncompressed
   raw JSON **overstate** real storage savings, so use the
   compressed baseline here.
3. Two deliberately basic probes to test *short events potentially
   missed* by thinning. For consecutive position triplets whose
   total span is at most 300 seconds, compare (a) a middle-point
   lateral excursion greater than 1 km from a time-interpolated
   straight chord and (b) a >750-ft middle-point altitude pulse.
   Score at the **segment** level whether an event was present
   in full data but absent in the compacted version.

These diagnostic probes are **not calibrated AIBA maneuver/intent
detectors**. In particular, comparing triplets with fewer retained
points can suppress a positive event even when the original
critical point is retained; that is a reason not to run
high-cadence detectors on the post-flight compact copy. It
does not mean the compressed copy is physically inaccurate.

Every aggregate receipt explicitly includes raw-data deletion
authorization = FALSE, historical tipper accuracy = untested,
landed state = unverified and receiver coverage = unverified.
All selected aircraft identities, callsigns and geometry remain
ephemeral and are not uploaded to GitHub artifacts.

## Reproducible offline commands

Without network access, from checkout root:

~~~bash
python -m unittest \
  tests.test_aircraft_retention_shadow_audit \
  tests.test_aircraft_retention_shadow_run -v
~~~

The source runner defaults to **metadata-only** unless the
source-day download is explicitly acknowledged:

~~~bash
python scripts/aircraft_retention_shadow_run.py \
  --pin data/validation/aircraft_one_day_source_pin.json \
  --output /tmp/heldout-retention-audit.json
~~~

The full optional runner includes --execute plus
--acknowledge YES_ONE_HELDOUT_3_69_GB and an ephemeral
--work-dir outside the Git checkout. No recurring job
is defined. Any one-off PR-triggered experiment workflow
must be removed after successful measurement.

## What success would and would not mean

The pilot can determine how aggressively the original
**geometry** can be thinned and what fraction of two basic
short-duration signatures disappear. It cannot establish
acceptable missed-event rates or safety of purge decisions
without original event labels and real-world analyst review.

**Deletion is prohibited in this PR, irrespective of observed
compression or false-negative counts.**

Required further work before altering actual raw-data policy:

- Freeze and validate historical route cohorts with real
  route endpoints/direction, rather than mere closeness to
  an arbitrary FAA J/Q airway.
- Replay actual AIBA production-like detectors before and after
  compression on an independent labeled sample, including
  rare positive events and uncertain, incomplete flights.
- Confirm legal and source-license obligations, pending
  tippers, source outages, adjudication requirements, and
  rehydration procedures.
- Confirm that both data reduction and flight screening
  actually reduce compute/storage versus already compressed
  source telemetry; measure with expected production formats.

## Larger AIBA roadmap

This aviation experiment is **supporting infrastructure**, not
the primary global warnings product. After validating the
feasibility and error sensitivity of thin storage, the next
priority should shift to the **source-independent immutable
pre-news tipper ledger and evaluation loop**:

Independent friction observations → time-stamped specific
pre-news hypothesis → GDELT first-public-report timing →
independent event outcome adjudication (including UCDP
for eligible organized violence) → rolling held-out calibration
on missed cases, false alarms, warning lead time, and
analyst review burden.

See [AIBA tipper evidence contract](AIBA_TIPPER_EVIDENCE_LOOP.md).
