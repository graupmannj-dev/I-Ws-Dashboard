# GDELT six-root source harmonization and migration (shadow only)

**Source profile:** GDELT daily 1.0 event data, CAMEO EventRootCode 13,16,17,18,19,20.  
**Cloud project:** `aiba-514120`. **Existing private bucket:** configured in `GCS_GDELT_BUCKET`.  
**No additional Cloud Shell configuration required.** This extends the existing
`.github/workflows/gdelt-gcs-history.yml`, whose exact workflow path is
already allowlisted by the repository-restricted workload identity provider.

## Why a second historical archive is required

Existing immutable `v1` historical aggregates are GDELT 17–20 and use
the **mapped** cases as denominator; they cannot be transformed to a
six-root denominator because 13/16 events were never recorded in v1.

Production `aiba_v4.py` counts **all** root 13,16,17–20 events in the
daily selected-root denominator, even when a country-level case is not
mappable. It maps cross-country `BILAT` cases for all six roots,
but allows single-country `DOMESTIC` cases only for roots 17–20.

This migration re-downloads the original GDELT archives and uses the
*same shared* `classify_actors` logic as production. It writes under
a separate prefix:

```text
gs://<GCS_GDELT_BUCKET>/aiba/gdelt/roots-13-16-17-18-19-20/v2/daily/YYYYMMDD.json
```

Existing
`aiba/gdelt/roots-17-18-19-20/v1/daily/*` remains untouched.
GCS Object Versioning, create-if-absent semantics, profile metadata and
raw ZIP SHA256 preserve observation provenance.

**Mandatory parity gate:** the six-root aggregate is projected back
onto 17–20. Its full row count, case keys, counts and mapped denominator
must exactly match the stored historical four-root record for **that day**.
Disagreement (including revised archived source data) raises an error and
prevents writing that v2 date. This is a hard migration check, not a
claim that the two profiles' aggregate denominators are equal.

## How to run historical migration

After merging the PR, use the *existing* Actions workflow:
[Persist GDELT historical baseline to GCS (shadow only)](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/gdelt-gcs-history.yml).

Select branch `main` and `mode = six_backfill`.
For each invocation enter `start` and `end` as UTC calendar dates;
**up to 14 inclusive dates**. Leave `through` blank.

Initial batch example:

```text
mode:   six_backfill
start:  2026-07-11
end:    2026-07-24
```

Subsequent contiguous batches:

| Batch | UTC start | UTC end |
|---|---|---|
| 1 | 2026-07-11 | 2026-07-24 |
| 2 | 2026-07-25 | 2026-08-07 |
| 3 | 2026-08-08 | 2026-08-21 |
| 4 | 2026-08-22 | 2026-09-04 |
| 5 | 2026-09-05 | 2026-09-18 |
| 6 | 2026-09-19 | 2026-10-02 |
| 7 | 2026-10-03 | 2026-10-16 |
| 8 | 2026-10-17 | 2026-10-30 |
| 9 | 2026-10-31 | 2026-11-09 |

GitHub Actions may run batches sequentially due to the existing
workflow's concurrency group; that is intentional. **One batch must
succeed before declaring any dates migrated.** Failed/missing v1 days
remain explicit, and retrying the same batch is idempotent.

Once merged, the **13:27 UTC scheduled workflow** runs the proven
four-root daily update first. The six-root job then downloads the most
recent date plus at most 13 earliest missing dates, so it gradually
fills past gaps without delaying the dashboard's publication. This is
a new external-archive collection effort: expect higher GDELT downloads
and GCS operations during the initial catch-up period. It does not
modify AIBA executive warnings.

A manual `mode = six_update` follows the same queue and accepts
`through=YYYY-MM-DD` or the previous completed UTC day by default.

## Scientific and operational acceptance criteria

- Verify daily 17–20 projections match stored v1 on all migrated days,
  **and** compare matched six-root daily counts against production's
  source parser for representative source days.
- Verify the six-root profile uses **all** six selected event roots in the
  denominator; unmappable cases must not silently disappear from it.
- Verify 28 strictly preceding calendar days and >=90% preceding 90-day
  coverage before generating an eligible six-root screening result.
- Independently adjudicate source duplicates, non-state vs interstate
  actor mapping and temporal reporting artifacts. A coded event is
  *not* independent evidence of escalation.
- No six-root shadow result may alter live alert severity or be described
  as a prediction until separately reviewed.

### Version caveat

Re-downloading an archive on a later date can yield data revisions
relative to the original historic backfill. The parity check will
**deliberately refuse** such a day until source provenance is reviewed.
Never “fix” this by overwriting four-root source history or disabling
the check. A separately versioned reconciliation is required.
