# Independently verified April–July six-root historical reference

This work is stacked on the bounded sweep PR #26. Merge **#26 before
this PR** to avoid duplicate review of its existing GCS workflow changes.

## Evidence and necessity

The verified AIBA original four-root GCS history begins July 11, 2026.
A full previous-90-calendar-day six-root reference for that date
requires April 12–July 10 six-root data. The UCDP Candidate 2026 source
ends September 30, so an exclusively July–November six-root history
cannot be fairly evaluated against its July–September events using a
*full* 90-day baseline.

The retrospective pilot run
[42912512785](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42912512785)
already retrieved and validated **all 90 original daily GDELT archives**
between April 12 and July 10, under the historical **four-root** parser.
Its retained source SHA256 is pinned:

```text
30c9a5e8e3517acecf877c9f397236016a564e36877035c43a91f340181fef5c
```

This PR uses that verified artifact as the *independent parity reference*
for the earlier period where four-root GCS v1 has no records.

**Do not generate earlier 17–20 reference counts from the same newly
downloaded 13–20 ZIP and call that independent verification.**
Instead, the already archived, source-hashed prior four-root records
must be reproduced exactly (row counts, mapped 17–20 denominator and
every country-case count) from freshly downloaded original daily ZIPs.
If GDELT historical data were revised, validation will fail and the
source discrepancy must be adjudicated, not silently fixed.

## No new cloud setup

This adds `six_prebaseline` to the **same**
`.github/workflows/gdelt-gcs-history.yml` already allowlisted in
the Workload Identity Federation provider for
`aiba-514120`. No extra bucket, service account or new OIDC
provider is necessary.

After **PR #26 and this PR** are merged, use:
[Persist GDELT historical baseline to GCS (shadow only)](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/gdelt-gcs-history.yml)

| Workflow input | Select |
|---|---|
| `mode` | **`six_prebaseline`** |
| `max_batches` | **8** (up to eight audited chunks of 14 files) |
| `start`, `end`, `through` | Leave blank |

The workflow retrieves run 42912512785's immutable research artifact,
checks all 90 original four-root daily aggregates, downloads and
reparses April 12–July 10 GDELT ZIPs into the **production-compatible
13/16/17–20** root profile, and stores them in the **existing** v2 GCS
namespace:

```text
aiba/gdelt/roots-13-16-17-18-19-20/v2/daily/YYYYMMDD.json
```

It additionally preserves the original four-root reference and its
manifest as **immutable, versioned** GCS objects under
`v2/references/verified-20260412-20260710/`. Audit receipts are
written both to GitHub Actions artifacts and GCS run-specific paths.

### Acceptance criteria

- 90/90 April 12–July 10 days stored, with no missing dates.
- All newly created days project exactly onto the independent four-root
  reference for their calendar date.
- Zero source provider failures, mismatched archives or parity failures.
- No duplicate/overwritten objects, no synthetic zero-filled dates.
- The original 122-day July–November four-root GCS history is untouched.
- GCS bucket Object Versioning still enabled.

This is **measurement compatibility**, not proof of forecast skill.
Even when April–November v2 history is fully covered, the UCDP dyad
episode candidate labels remain provisional and actor-specific
GDELT-to-UCDP linkages require independent manual review before
case-level performance can be computed.

## Recommended combined execution sequence

1. Approve and merge PR #26, then this PR.
2. Run `six_sweep` with `through=2026-11-09` and `max_batches=8`
   to finish the July–November 122-day GCS v2 history.
3. Run `six_prebaseline` with `max_batches=8` for the 90-day
   April–July v2 lead-in. Re-run only if the first run is partial.
4. Approve and merge PR #25 (if not yet merged), then run
   `Build UCDP escalation episode adjudication queue (manual)`
   to generate the first auditable event/actor review packet.
5. Return the run links. We can then verify source coverage, examine
   episode labels, and design the independent negative-case universe
   before any model calibration or operational threshold tuning.

The current workflow does **not** introduce automatic warning status
changes and does **not** trigger costly manual sweeps on a daily schedule.
