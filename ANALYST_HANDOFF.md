# AIBA analyst-report handoff — implementation and limits

**Status:** GitHub operational collectors already write to the dedicated
aiba-feed-data/observations/ branch. This PR provides a validated intake for
separate ChatGPT analyst automations. **It does NOT itself connect the ChatGPT
task runner to GitHub.** Those tasks require explicit, authorized GitHub
writes or an authenticated dispatch service. Until that is enabled and tested,
the Atlas says **not connected**, not "operational".

## Existing operational path

- The GitHub-hosted operational workflow writes markets, official notices,
  commercial media observations, audit and fusion records to aiba-feed-data.
- Publishing follows a successful operational or authenticated analyst-intake
  workflow, and still runs on the pre-existing daily schedule. Required GDELT
  completeness failures retain the last live site.
- The Atlas now uses archived source-publication dates for chronological
  official/commercial records and the real feed health timestamps.
- Unlocated GDELT algorithmic nominations appear as unverified sidebar
  discoveries. Neither source media anomalies nor new ChatGPT reports can
  automatically change severity or create invented map coordinates.

## Authenticated import

After merging, use GitHub Actions > Ingest AIBA analyst OSINT report > Run
workflow on main. Put a single JSON batch in the report_json field. This
workflow validates it and appends a dated immutable file to the evidence
branch; a successful run schedules a separate Pages update.

For a local-only import (does not push or deploy):

    python scripts/import_analyst_report.py --state /path/to/observations --input report.json

Example JSON below is FICTIONAL test content, not actual reporting:

    {
      "schema_version": 1,
      "run_id": "six-hour-20261108T1100Z",
      "collector": "six_hour_signal",
      "status": "completed",
      "collected_at": "2026-11-08T11:00:00Z",
      "observations": [
        {
          "observation_id": "example-source-001",
          "case_id": "taiwan",
          "published_at": "2026-11-08T09:30:00Z",
          "title": "SYNTHETIC: fictional source event",
          "summary": "Training fixture, not a real-world observation.",
          "publisher": "Fictional provider",
          "source_url": "https://example.org/test-source",
          "information_root": "fictional-root",
          "evidence_class": "source_observation",
          "confidence": "low",
          "independently_confirmed": false
        }
      ]
    }

Collector options: six_hour_signal, commercial_behavior,
global_discovery, weekly_audit.
Status: completed, partial, failed (failed has zero observations).
Evidence class: source_observation, media_mention, analyst_hypothesis.
Confidence: low, moderate, high, unknown.

Every observation needs a stable identifier, primary or syndication HTTPS
source URL, publication date WITH timezone (null if unknown), source-root
identity and explicit confidence/confirmation classifications. Do not use
the ChatGPT collection time as the source publication date. Repeated
observations and common information roots are deduplicated; conflicting
stable IDs cause deployment to fail.

Known case IDs are anchored to explicitly approximate theater locations.
Unrecognized or null case IDs become unlocated discovery candidates in
the sidebar. The independently_confirmed field is an external analyst
assertion and not AIBA verification. Newly ingested source-linked reports
may pulse for 36 hours from FIRST collection only when the original source
publication date is within seven days; they remain labeled unreviewed.
Standing severity never changes automatically.

Everything submitted here becomes publicly visible through GitHub branch
history and/or the Pages site. No classified, sensitive, private or
restricted material may be sent to this intake.

## Acceptance and still-missing connection

1. Review the PR CI and confirm a synthetic event appears in a temporary
   generated Atlas, then disappears from the *recent lead* filter once aged.
2. After merging, inspect the operational collector to durable branch to
   Pages deployment chain. Health timestamps must be source-specific.
3. Configure each ChatGPT scheduled task (with authorized GitHub access)
   to emit the schema and write it to this public data branch, or dispatch
   the workflow through an authorized service. ChatGPT reports otherwise
   remain inside ChatGPT, even if every scheduled task says completed.
4. Perform one reviewed real-source handoff and verify its original date,
   source link, confidence qualifier and intake timestamp in the Atlas.
5. Check collection freshness separately from GDELT completed-day as-of
   and Pages generation. Failed sources must not be counted as zero risk.

Neither operational OSINT leads nor ChatGPT assessments are official
intelligence or calibrated conflict probabilities.
