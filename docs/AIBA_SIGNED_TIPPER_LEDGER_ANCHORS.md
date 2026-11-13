# AIBA private tipper ledger: GitHub Sigstore witnessed hash only

**Status:** candidate independent timing anchor. This does not issue a
warning, grant event success, identify any actors, or change the dashboard.
No GCP services, IAM resources or collectors are configured.

## Security objective

A local JSONL SHA-256 chain from PR44 detects accidental mutation but
is not time-trusted: a privileged party can rewrite it and its local
machine clock. We need an independent third party to witness **the
hash of the exact chain** before an eventual event's first
credible public reporting.

The manual workflow uses GitHub's **actions/attest@v4** to create a
public-repository Sigstore-signed build attestation for a small JSON
subject containing only:

- the 64-character SHA-256 head hash of the verified private ledger;
- the number of ledger records;
- the GitHub Actions run ID and source commit hash;
- explicit no-original-content and no-issuance-clock-proof flags.

No source identifiers, geo-coordinates, aircraft telemetry, analyst
identities or forecast hypotheses are uploaded. Actual source ledger
remains locally held by the user, **outside the public repo**. The
public subject hash should be treated as unclassified publication.

The GitHub Actions workflow requires three permissions to create
a real Sigstore witness: contents:read, id-token:write and
attestations:write. It does NOT receive external cloud credentials.
GitHub documentation describes public-repository artifact attestations
as available for public repos on current plans. The signature binds
the attested subject digest to the GitHub Actions workflow identity.

## Proving date vs claiming date

A cryptographically verified Sigstore transparency-log or TSA
timestamp means the **hash-committed ledger existed no later than
the witnessed timestamp**. It does **not** prove:

- the local issuance timestamp written inside that ledger;
- that its predictions were factually reasonable or true;
- that the event happened after the prediction, unless an independent
  event timeline verifies this against the witnessed time;
- that original news publication occurred at a GDELT ingestion time;
- that the ledger cannot subsequently be deleted, altered or lost.

A meaningful AIBA *pre-news* claim needs independent verification
of the **earliest credible publication** and must compare it to the
**witnessed timestamp**, not the user-supplied local clock.
If a first article predates the signing witness, a positive
pre-news claim is not established even if the local ledger
has an earlier recorded_at timestamp.

The signer workflow identity and signed witnessed time must be
cryptographically validated with the GitHub CLI, and the exact
attested subject digest compared to the private ledger's verified
chain head. **Do not trust unsigned JSON fields presented as proof**.
Store a long-lived copy of the GitHub attestation bundle for
reproducibility; Actions artifacts have limited retention.

## Prepare a private ledger digest

~~~bash
python scripts/aiba_tipper_anchor.py export \
  --ledger /private/aiba-tipper-ledger.jsonl \
  --output /private/aiba-head-to-submit.json
~~~

The local export is not a signed attestation. Its status is
external_signed_timestamp_verified=false and
trusted_issuance_time_proven=false. Check the head and entry count
before submitting. Local CLI refuses source/subject overwrite,
corrupt chain, symlinks or ledgers inside the public checkout.

## Create a signed time witness

After workflow is merged, use **Actions → Manual AIBA signed
private-ledger hash witness → Run workflow**. Enter the head SHA-256
and number of records (no other content). The workflow:

1. Generates a hash-only JSON subject on an ephemeral GitHub runner.
2. Signs that subject with actions/attest@v4 and Sigstore.
3. Calls gh attestation verify with repository and signer-workflow
   identity constraints and checks for independently witnessed
   timestamps. If verification fails, the job fails closed.
4. Uploads only the public hash subject and a compact
   verification-success summary as an Actions artifact.
   The original ledger stays on your local private storage.

To independently verify after downloading the exact subject:

~~~bash
gh attestation verify /private/anchor-subject.json \
  --repo graupmannj-dev/I-Ws-Dashboard \
  --signer-workflow graupmannj-dev/I-Ws-Dashboard/.github/workflows/aiba-ledger-head-attest-manual.yml \
  --format json
~~~

Verify that verifiedTimestamps is nonempty and that the original
private JSONL chain validates to the SHA-256 head digest in the
subject. Also audit first publication independently.

The workflow can be dispatched manually as needed. It is
**not scheduled**, and it does not create forecasts. Historical
ledgers submitted *after* a public event may receive a genuine
timestamp but have **no prospective evidentiary value for that
event**. Privacy and classified information restrictions remain
the operator's responsibility.

## Empirical verification of the signing service (November 12)

A one-time synthetic-only GitHub Actions test confirmed the attestation
workflow can sign a known fake hash and recover a independently
cryptographically verifiable Sigstore/Rekor timestamp. The GitHub
test run was
https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/43332630210
and the transparency timestamp was
**2026-11-12T23:53:50Z**. The attested hash was 64 hexadecimal
characters all set to F (an unmistakably synthetic subject),
NOT a genuine AIBA forecast or real private ledger.
The workflow's ephemeral one-time pull-request trigger was
removed after the aggregate proof was recorded.

See [permanent verification evidence](evidence/aiba-sigstore-synthetic-witness-2026-11-12.json).
The manual workflow reuses the same successfully tested
actions/attest@v4 signing and GH CLI verification pattern
with narrowly scoped GitHub Actions write permissions. There
is still **no real-world pre-news tipper** or verified leadtime
result. A real anchor is only meaningful when a private
ledger is committed *before* the independently established
earliest public article and the exact private ledger hash
is later independently validated.

## Next gates to real warning skill

- Stabilize source cadence, measure provider-specific gaps,
  and preserve missingness. An unattested local hash is not a
  prospective proof.
- Freeze a contemporaneous 24-hour monitoring frame with
  actual recent source data; anchor its hash immediately.
- On a substantive new independent sensor signal, record a
  specific, human-reviewed actor/action/location/horizon event
  hypothesis in the private tipper ledger and immediately
  anchor the new chain head. Record counterevidence and
  alternative explanations.
- Collect later original publication timestamps and independent
  outcome labels, including UCDP where relevant, preserving
  legitimate censored/unknown cases. Estimate false-alarm and
  missed-case burden from ex ante monitored risk sets.
- Validate any automated scoring procedure before live warning
  promotion or major analytic claims.

GitHub source documentation:
https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
https://cli.github.com/manual/gh_attestation_verify
