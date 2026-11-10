# Fast six-root historical catch-up — bounded and reversible

The initial GCS six-root migration succeeded for **2026-07-11 through
2026-07-24**: 14 stored dates, 14 source-projection parity checks,
zero provider failures. The original immutable four-root reference
already covers July 11–November 9 (122 dates).

Normally the scheduled `six_update` job appends up to 14 source
archives per day. This PR adds a *manual* catch-up option called
`six_sweep` inside the **existing**
`.github/workflows/gdelt-gcs-history.yml`; the same allowlisted
GitHub workflow location is required by your Google Cloud Workload
Identity policy. **No new Cloud Shell commands, secrets, bucket or
service account are needed.**

## One-run catch-up

After merging the PR, open
[Persist GDELT historical baseline to GCS (shadow only)](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/gdelt-gcs-history.yml)
and select *Run workflow* on `main`:

| Input | Value |
|---|---|
| `mode` | **`six_sweep`** |
| `through` | `2026-11-09` for the first fixed audit (or blank for yesterday UTC) |
| `max_batches` | `8` |
| `start`, `end` | Blank |

At most **8 independently audited batches × 14 original GDELT ZIPs**
are processed. Each date is parsed using the production-compatible
13/16/17–20 root definition and **must reproduce the immutable v1
four-root case counts and source row totals**. The current v2
namespace is append-only; previous dates are **never overwritten**.
GCS bucket Object Versioning remains mandatory.

Eight batches can add up to **112 dates** in one run, enough for the
remaining 108 dates in the fixed 122-day reference if GDELT makes all
archives available. It may stop early on provider outages, parity
conflicts, missing v1 references or completed coverage. Re-running it
retries only missing dates; every batch has a unique audit ID and
coverage receipt. There is no zero-filling of unavailable archives.

Outputs in the GitHub Actions artifact
`gdelt-sixroot-audit-RUN_ID-ATTEMPT`:

- `gdelt-sixroot-audit/batch-XX/manifest.json` (one record per bounded
  batch, with created dates, parity checks, source failures and
  outstanding coverage);
- `gdelt-sixroot-audit/sweep_manifest.json`, including the total
  completed dates, remaining dates, provider failures and v1
  dependencies.

**Acceptance:** `status=complete`, expected 122/122 dates through
2026-11-09, zero missing dates, and one 17–20 parity receipt for
every newly created six-root date. Earlier v2 data already passed
parity and remain immutable. This is a source integrity acceptance
gate, not a retrospective warning accuracy test.

### Source coverage caveat

The existing **four-root** GCS source starts July 11, 2026.
This sweep cannot invent the **April 12–July 10** six-root records.
That extra 90-day prehistory must be independently reconstructed with
its own verified four-root source reference before a **full** six-root
90-day baseline can be compared to July–September UCDP outcomes.

### Operating safeguards

- Existing scheduled four-root collection executes first; scheduled
  six-root update remains single-batch, not eight-batch.
- Only manually selected `six_sweep` performs the 8-batch catch-up.
- No changes to the production dashboard, executive status, GDELT
  warning thresholds or source profile.
- No extrapolation of a 14-day success to undownloaded days.
- An accidental interruption does not roll back existing valid
  per-day records. Rerun the sweep for gap recovery.
- Current script caps eight batches and 14 archives per batch;
  the user can choose a smaller number to control network use.
