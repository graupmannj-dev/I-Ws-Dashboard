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
