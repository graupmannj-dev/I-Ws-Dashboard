# Public AIBA Atlas: prospective warning evaluation readiness

This capability is inside the existing Atlas site:
https://graupmannj-dev.github.io/I-Ws-Dashboard/
It does not create a new website or backend.

## Why performance numbers are unavailable

AIBA now has an experimental private append-only tipper ledger,
a prospective 24-hour frame protocol, and a synthetic-only
GitHub/Sigstore witnessed timestamp test. These demonstrate
engineering functionality; they do NOT demonstrate geopolitical
warning skill.

A dashboard that interprets unconnected private ledgers or
unobserved intervals as zero false alarms would be invalid.
The new Atlas Evaluation tab displays:
- Real observed source freshness and declared provider missingness
  from the existing behavioral engine, updated by the same
  read-only five-minute evidence branch refresh as that tab
- No invented worldwide coverage or source completeness
- Unavailable (not zero) verified pre-news lead time,
  false alarms per analyst-day, missed-event recall and calibration
- The independently reviewed evidence gates required before
  public performance metrics become defensible
- Documentation and existing manual source readiness links

There are no new collectors, schedules, cloud costs, IAM roles,
alerts, or separate services in this change.

## Public machine-readable contract

The new dashboard/evaluation_readiness.py emits a strictly
bounded evaluation_summary.json and embeds an identical
warning_evaluation object into atlas.json. All nine
forecast metric fields MUST be null. All six private
verification gates MUST read not_connected, meaning the
public site has no independent audit of private tippers;
it does not assert that nobody privately issued warnings.

Source health is derived only from a recognized public
behavioral snapshot. Missing snapshot means unknown provider
count, not zero. Fresh timestamps are labeled source
snapshot recency, NOT global collection completeness.

No private ledger row, subject hypothesis, actor/location
identity, analyst data, or aircraft coordinates are imported
by the web build. The browser fails closed on an invalid
public score schema or injected non-null "skill" metric.

## Source continuity vs operational accuracy

AIBA's November 9–12 collection records overlapped major
GitHub service incidents. A browser can successfully render
a static page while its behavioral evidence is stale.
The Evaluation tab inherits the actual source age and
degraded feed coverage, preserving the unknown intervals.
It never counts a missing interval as a verified true
negative or as an absence of world events.

## Future release protocol for actual aggregate performance

A future separately approved private-to-public pipeline must:
1. Verify original ledger chain, actual third-party Sigstore
   signer and timestamp, and matching subject digest.
2. Independently establish original earliest credible
   first-news publication (not GDELT ingest time).
3. Pre-register specific forecast hypothesis, geography,
   action, actor, probability, horizon and risk sets.
4. Independently adjudicate matched events and confirmed
   negative horizons; keep censored cases unscored.
5. Reconstruct verified source coverage and independent
   missed-event denominators before estimating recall.
6. Publish only human-reviewed, privacy-screened aggregate
   outcomes with explicit forecast/event denominators,
   lead-time definitions, periods and limitations.

A real warning lead-time or false-alarm rate is NOT
implemented or claimed by this PR.

## Tests and operator review

The existing Pages CI builds the single Atlas site.
Unit tests reject source promotion, missing timestamps,
simulated classified fields and false zero rates.
The browser E2E tests verify the Evaluation tab in the
existing watch panel, navigation, stale-source behavior,
no 0/0 performance claims, and rejection of forged metrics.

The evaluation_summary.json can be read by downstream
public clients but does not authorize forecast issuance
or source status changes.
