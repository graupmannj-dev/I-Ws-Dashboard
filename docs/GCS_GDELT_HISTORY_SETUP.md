# GCS persistence for the AIBA GDELT shadow baseline

**Cloud project:** `aiba-514120`  
**GitHub repository:** `graupmannj-dev/I-Ws-Dashboard`  
**Status:** opt-in infrastructure; **no live GCP resources are created by this PR**.

This proposal keeps validated UTC-day GDELT source-code aggregates permanently in
a versioned Google Cloud Storage bucket, rather than depending on 90-day
GitHub Actions artifact retention. It has no connection to AIBA's publishing
deployment and does **not** change executive warning severity.

## Current seed and evidence

Verified source: successful [forward shadow run 42893068477](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/42893068477).
Artifact `gdelt-shadow-baseline-42893068477`, complete period **2026-07-11
through 2026-11-09**, **122 valid daily aggregates**, zero failed days. It
contains the **four-root** GDELT 17/18/19/20 denominator, *not* the six-root
GDELT operational discovery denominator.

The one-time `seed` operation copies and verifies the 122 records. Each
daily object is stored under:

```text
gs://BUCKET/aiba/gdelt/roots-17-18-19-20/v1/daily/YYYYMMDD.json
```

Run-specific immutable health receipts and comparisons are stored under
`.../runs/<github-run>-<attempt>/`. Only validated aggregate counts are
stored; bulk downloaded GDELT ZIPs are not retained.

Daily `update` checks recent missing UTC dates, fetches at most 14 source
archives per invocation, checks ZIP content, validates actor/event denominators,
and only creates new GCS objects if no object exists. Exact duplicate uploads
are verified; different data on the same date **fail closed** rather than
silently overwriting the historical observation. GitHub Actions concurrency
prevents two scheduled updates operating simultaneously. Versioning provides a
second recovery control.

Provider 404/503/timeouts do not become zero observations; incomplete coverage
is identified in a durable manifest. A successfully executed workflow can be
**partial** as an analytical source-health status, which operators must review.
Malformed/contradictory stored source data fails the workflow. Calendar gaps
are repaired in later runs when the upstream archive becomes accessible.

## A. Configure Google Cloud once (Cloud Shell)

Use the [Google Cloud console](https://console.cloud.google.com/?project=aiba-514120)
and select **Activate Cloud Shell**. Ensure you have permission to manage
IAM, enabled APIs, service accounts and Cloud Storage buckets, and confirm
billing is enabled. Execute the commands below in the *Cloud Shell*, not
the GitHub Actions editor.

Bucket names are **globally unique**. The example is
`aiba-514120-gdelt-history`; if already taken, select a unique private
name and use the same name in all subsequent steps and the GitHub variable.

```bash
export PROJECT_ID="aiba-514120"
export BUCKET="aiba-514120-gdelt-history"
export POOL="aiba-gh-history"
export PROVIDER="gdelt-main"
export SA_NAME="aiba-gdelt-history"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export REPO="graupmannj-dev/I-Ws-Dashboard"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com storage.googleapis.com \
  --project="$PROJECT_ID"

gcloud storage buckets create "gs://$BUCKET" \
  --project="$PROJECT_ID" --location="us-east1" \
  --uniform-bucket-level-access \
  --public-access-prevention
gcloud storage buckets update "gs://$BUCKET" --versioning

gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="AIBA GDELT history writer"

# Limit data access to this *bucket*, not the entire project.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectUser"
# Required for the application's explicit check that Object Versioning is on.
# storage.objectUser alone does not grant storage.buckets.get.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.bucketViewer"

gcloud iam workload-identity-pools create "$POOL" \
  --project="$PROJECT_ID" --location="global" \
  --display-name="AIBA GitHub history jobs"

# Federation is accepted ONLY from this repo's main-branch GCS workflow.
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --project="$PROJECT_ID" --location="global" \
  --workload-identity-pool="$POOL" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == '$REPO' && assertion.repository_id == '1449535816' && assertion.ref == 'refs/heads/main' && assertion.workflow_ref == '$REPO/.github/workflows/gdelt-gcs-history.yml@refs/heads/main' && (assertion.event_name == 'schedule' || assertion.event_name == 'workflow_dispatch')"

export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO}"

export WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
echo "GCP_WIF_PROVIDER=$WIF_PROVIDER"
echo "GCP_SERVICE_ACCOUNT=$SA_EMAIL"
echo "GCS_GDELT_BUCKET=$BUCKET"

gcloud storage buckets describe "gs://$BUCKET" \
  --format="default(name,versioning_enabled,iam_config.uniform_bucket_level_access)"
```

Cloud control plane IAM updates may take a few minutes to propagate. **Do not
create or upload service-account key files.** The GitHub workflow uses
`google-github-actions/auth@v3` with GitHub OIDC and short-lived credentials.
If a GCS bucket or pool of the given names already exists, inspect its
configuration before deciding whether to reuse it; do not blindly overwrite
an unrelated identity provider or bucket policy.

### IAM notes

The bucket-level `roles/storage.objectUser` role allows reading,
listing and creating daily objects (and includes other object operations).
The application *itself* uses create-only generation preconditions on
observations and refuses different content for a stored day. If you need
strict no-delete IAM, a custom role with the exact storage-object permissions
can replace this broad predefined role after testing.

The provider condition restricts tokens by repository, repository ID,
branch, workflow identity, and trigger. The service account must not receive
roles such as project Editor or Owner.

## B. Configure GitHub repository variables

In `graupmannj-dev/I-Ws-Dashboard`, open **Settings → Secrets and
variables → Actions → Variables**, then add three **repository variables**:

| Name | Value |
|---|---|
| `GCP_WIF_PROVIDER` | The full `projects/NUMBER/locations/global/workloadIdentityPools/aiba-gh-history/providers/gdelt-main` value printed above |
| `GCP_SERVICE_ACCOUNT` | `aiba-gdelt-history@aiba-514120.iam.gserviceaccount.com` |
| `GCS_GDELT_BUCKET` | `aiba-514120-gdelt-history` (or the unique name you created; no `gs://`) |

Do **not** put credential JSON into GitHub Actions secrets. These three
values are resource identifiers, not private credentials.

Before those variables exist, the scheduled workflow reports that persistence
is disabled and does not attempt cloud access. A manual dispatch without
configuration fails explicitly.

## C. Activate the new workflow, in this order

1. Merge the separate PR adding `.github/workflows/gdelt-gcs-history.yml`.
2. Complete sections A and B; inspect Google Cloud IAM and bucket versioning.
3. GitHub → **Actions → Persist GDELT historical baseline to GCS
   (shadow only) → Run workflow**. Select branch `main`, then choose
   **`seed`**. Leave `through` empty. The workflow retrieves the
   independently verified 122-day seed artifact, checks all calendar
   dates and selected-event counts, creates one immutable GCS object per
   date, and writes a run receipt.
4. Inspect the run's `gdelt-gcs-audit-...` artifact and the private
   bucket. The seed should report **122 new dates**, **0 failures**,
   `status=complete`, and no production publishing.
5. Dispatch **`update`**, leaving `through` blank to use *yesterday
   in UTC*. Or supply a completed UTC date in `YYYY-MM-DD` form.
   Repeating an already archived date is idempotent.
6. Leave the daily schedule enabled. At **13:27 UTC**, the pipeline checks
   dates that should have fully closed, repairs historical gaps when
   upstream archives appear, and stores a permanent source-health manifest.
   GitHub scheduling may start later than the nominal minute.

### What to check after every run

| Field | Required interpretation |
|---|---|
| `status` | `complete` or explicitly `partial`; `invalid_source` fails |
| `created_days` | Exactly which UTC dates were newly written |
| `failed_downloads` | Upstream unavailable or invalid GDELT days, never zero-filled |
| `missing_last_120_days` | Calendar completeness, separate from job success |
| `unattempted_backlog` | Gaps deferred beyond the 14-day/request budget |
| `evaluated_days` | Dates scored against *earlier* 90-day references |
| `executive_alerts_approved` | Always `false` until a separately reviewed integration |

The workflow **does not** update the front-facing site and should not be
included in its deploy dependency chain. Protect the bucket against public
access and do not put bulk historical data inside the website directory.

## D. Operational acceptance gates (not yet met)

- Verify one successful seed, one idempotent retry, and at least two
  independent next-UTC-day additions.
- Simulate a missing upstream day; confirm it appears as missing and is
  subsequently repaired (no interpolated zero).
- Test that an altered count for an existing date is refused.
- Compare retrospective source-extraction profiles (17–20 versus
  production 13/16/17–20). Production threshold integration remains blocked.
- Log source ingestion latency, date/metadata provenance and weekly
  collection failure rate. Independently assess lead false-alarm burden
  before alert promotion.

**Storage cost:** Aggregate JSON objects are small, but object operations
and versioning still incur charges. Create project billing alerts and review
GCS lifecycle policy before data volume grows.

References:
- [Google Cloud GitHub OIDC auth action](https://github.com/google-github-actions/auth)
- [Google Cloud workload identity federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Cloud Storage versioning](https://docs.cloud.google.com/storage/docs/using-object-versioning)
