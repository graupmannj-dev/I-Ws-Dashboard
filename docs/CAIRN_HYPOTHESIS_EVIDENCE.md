# CAIRN hypothesis-centered evidence workspace (first operational slice)

The Atlas now links to `hypotheses.html`, a full-width public **analyst review**
workspace generated from the existing curated case dossier and explicitly linked
durable evidence families. The workflow publishes `hypotheses.json` as part of
the same approved Pages build. No separate backend, keys or new cost required.

## Data model

- One displayed scenario per existing, dated case dossier. It is a **hypothesis**,
  not a CAIRN-authenticated prediction, warning or probability.
- Every original dossier source information root produces a distinct evidence
  family (multiple reporting fragments sharing a root do not multiply counts).
- Unreviewed dynamic evidence families are linked **only by explicit case hints**.
  A family can belong to several hypotheses. Neither source-title similarity
  nor country proximity is a causal match or an independently observed event.
- Each family retains its original links, source timestamp, mechanism and
  collector status. Dossier evidence is labeled *historical reference*, not
  current sensor coverage. Missing collectors remain stale/unknown.
- Sourced dossier explanatory alternatives appear alongside the primary
  hypothesis. Analyst-defined additional alternatives are limited to three total.
  The view separately displays potential next observations that could
  discriminate between alternatives.

## Review-gated weight of evidence

By default there is **no signed weight**. The system deliberately refuses to
derive direction from phrases such as `Confirmed`, a source count, a new
collection, an extreme z-score, or simple topical association. Those terms can
validate an observation without proving the hypothesis.

A reviewer can add explicit, dated decisions to
`data/hypothesis_reviews.json`:

```json
{
  "schema": "cairn.hypothesis-reviews.v1",
  "reviews": [
    {
      "hypothesis_id": "CASE_ID",
      "evidence_key": "dossier:HASH_OR_family:ID",
      "direction": "supports",
      "strength": 2,
      "rationale": "Explain the observed difference from competing explanations",
      "reviewed_at": "2026-11-20T17:00:00Z",
      "dependency_group": "independently_audited_source_root"
    }
  ],
  "alternative_hypotheses": {}
}
```

Directions: `supports`, `contradicts`, `context`. Strength is ordinal
1–3; it is never a calibrated likelihood or attack risk. For each dependency
group the largest signed weight in that direction is counted once.
Groups with internally opposing signed roles are excluded pending review.
The resulting -1 to +1 display is labeled **reviewed ordinal balance** and
is not a probability. It always names the supporting and contradicting
totals. Dependency-group independence is a reviewer judgment and should be
revisited during source validation.

Future work: UI review actions need a secured, auditable write API. This
read-only GitHub Pages MVP does not silently write annotations or permit
unauthenticated changes. It also does not automatically promote hypotheses
from source coincidences into warnings.

## Offline acceptance

`python -m unittest tests.test_hypothesis_evidence -v`

`python -m unittest discover -s tests -v`

`node --check dashboard/hypotheses.js`

The tests include unreviewed default, duplicated source root, shared family
on two hypotheses, signed directions, dependency caps, contradictory dependent
sources, stale health, bad annotations and built-site output.


## Automatic preliminary screening after collection

The existing `Collect CAIRN public alternative sensors` (~every 3 hours) and
`Collect AIBA operational feeds` (six-hour cycles plus other intervals)
workflows update `aiba-feed-data`. On **successful** completion, the existing
`Validate and publish AIBA` `workflow_run` rebuild screens the available
current durable registry/archive and embeds results in `hypotheses.json`.
The same screen runs during any other approved publication rebuild. There is no
separate polling collector, competing write to the evidence branch, API key or
infrastructure expense. GitHub scheduling, collection success and Pages
publication are best effort, not a real-time SLA. A public update still depends
on `AIBA_PUBLISH_APPROVED=true`.

`dashboard/hypothesis_auto_review.py` examines **first ingested** source
records within a trailing nine-hour window (not their claimed event time).
It uses only HTTPS-linked records and source-specific current/partial health.
It groups repeated reports sharing a collector mode and information root, and
requires either an explicit case ID or a distinctive case-specific title or
reported-geography cue. Broad generic topics cannot create case associations.
Candidate source titles are checked for concrete signpost patterns, possible
reversals, and contextual/ambiguous language. They are labeled *possible support*,
*possible counter-indicator*, *context* or *requires interpretation* — never
reviewed evidence. Unavailable feeds, aged snapshots, unknown source links,
missing records, provider-initial baselines and unobserved indicators do not
count against a hypothesis. Overly long evidence archives are capped after
selecting recent records rather than preferentially retaining old items.

The Hypotheses page shows the machine screen time, input snapshot time,
nine-hour review window, source links, nominal cues, and a filter for new
machine-screened leads. The analyst-reviewed ordinal balance remains untouched.
The screen does **not** assign confidence or probability, validate source claims,
establish independence, deduce military intent, issue threat alerts or promote
a hypothesis. Pattern matching can miss novel phrasing and can generate false
positives; an actual human review of original material is needed before any
directional assessment.

Screen state is explicit: `screened`, `source_snapshot_stale`, or
`source_snapshot_unavailable`. A refresh with no eligible candidates means
only that the bounded available data yielded none; it is not an all-clear.

Tests:
`python -m unittest tests.test_hypothesis_auto_review -v`
and `node scripts/test_hypothesis_auto_browser.js` (after building and serving
a local preview; the PR browser workflow runs this automatically).


## November 23 correction: complete GDELT coverage and rolling case history

Previously the nine-hour machine screen consumed only the behavioral registry and
durable archive, **not GDELT**. GDELT only surfaced case context when a pair
passed the *global anomaly nomination* threshold, and then only on a separate
ops page. All human-signed balances remained empty because
`data/hypothesis_reviews.json` starts with zero human judgments. Repeated
automatic screening never wrote analyst approvals.

Every normal GDELT archive build now emits `gdelt_case_trends.json`. It computes
seven-day versus preceding 28-day data for **all ten exact bilateral actor-pair
hypotheses**, not merely the globally nominated anomaly set. It publishes
source completeness, coded-event counts, total six-root sample denominators,
per-pair media-event shares, ratio when defined, percentage-point share
change, and all 35 daily counts. Actor-pair matching uses the existing
`publication_context.GDELT_PAIRS` crosswalk; a conflict involving a single
country and an unrelated third party does not become evidence of a specified
bilateral confrontation.

A missing day or invalid denominator leaves all comparison metrics null;
complete days may yield zero *coded records* but cannot establish that no
real-world incidents happened. A higher/lower **GDELT-coded share** is a
measurement direction, not an endorsement of military escalation, attribution,
or likelihood. GDELT event coding and reporting are non-independent and
subject to news coverage and country-code error. No human-reviewed directional
strength is fabricated.

The nine-hour new-ingest screen remains separate. A seven-day, deduplicated,
case-associated historical source view also prevents recently collected
records from vanishing from the Hypotheses page simply because they are
older than nine hours. Public analyst-intake reports are labeled unverified:
they may be inspected and sourced but are not silently accepted as live
source-healthy observations. Such history is context, not corroboration.

Acceptance tests: `python -m unittest tests.test_gdelt_case_trends
tests.test_hypothesis_auto_review -v` and the existing Playwright hypothesis
browser tests. A successful publication produces the dated GDELT comparison
file and attaches it to each hypothesis in `hypotheses.json`.
