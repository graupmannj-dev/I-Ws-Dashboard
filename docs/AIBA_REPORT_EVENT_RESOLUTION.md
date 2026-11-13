# AIBA report-to-event resolution — candidate links, not corroboration

AIBA previously required **identical source geography keys** for
cross-family behavioral source nominations. This remains an appropriate
strict investigation gate for *source-defined, spatially compatible*
observations but it is **not** a good general rule for determining
whether two reports describe the same event.

A publication from a New York editorial desk about a missile strike
in Kyiv, and a first-hand Kyiv report about the same strike, can
describe **one underlying event** despite being created in different
places. Conversely, two source reports originating from different
cities about *different* strikes in Kyiv can share a topic and
geography without being the same incident.

This PR adds an entirely separate **unreviewed report relationship**
lane, not a new mechanism for automatic warning escalation.

## Three distinct relationship types

1. **Shared source document:** distinct normalized records or
   sub-geometries point to the same source-specific primary URL
   (including a unique Niord message fragment). Treat as a
   *source-document grouping*, not two independent sources.
   General landing pages are never considered a document ID.
2. **Possibly the same source story:** near-identical article
   titles published through different URLs (including search
   syndication links) may represent **one underlying
   publication**, not independently witnessed events.
3. **Possibly the same event:** two reports have strong
   substantive title overlap and compatible chronology.
   When both sources give explicitly identified event-site
   coordinates, source-declared reported event sites within
   75 km can support a *candidate* with substantive overlap,
   never automatically establish identity. A publisher's
   reporting origin is ignored for event-site comparisons.
4. **Related reporting:** strong thematic/textual similarity
   with explicitly incompatible reported event locations
   (more than 150 km apart) or a long observation-time
   separation. These should be **reviewed**, not collapsed
   into a single incident or counted as extra corroboration.

The similarity implementation uses a deterministic, capped
**English-language title token overlap**, NOT an embedding or
validated article-level semantic equivalence model. Actual
substantive source claims are often unavailable or incomplete.
Similar language can be syndicated or coincidental; short or
paraphrased reports may be missed. This is a **first-stage
candidate generator**, not verified entity resolution.

## Data and provenance contract

- `reporting_origin`: explicitly source-recorded origin of
  the reporting or publisher; informational only.
- `reported_event_location`: optional explicitly identified
  event-site point with `role=reported_event_site`,
  `basis=source_declared` or
  `basis=source_record_geometry`, latitude and longitude.
  It is retained only when source metadata actually supplies
  it; **never guessed** from the publisher, URL, country names,
  article text or an unrelated notice footprint.
- `geography`: existing provider-defined restriction / network
  scope and possible map-layer footprint; **not automatically
  a geocoded security event**. Comparing source notice polygon
  overlap is a future separately reviewed stage.
- `information_root`/source URL: explicit flags for possible
  copying/shared upstream provenance. Two publisher names
  are not sufficient proof of independent observation.
- Timing: event and publication times are used if known,
  otherwise first collection time is only a coarse proxy.
  The 48-hour possible-event window is conservative and
  can miss delayed coverage; an up-to-72-hour relation is
  only thematic, not same-event identity.

Every relationship is `unreviewed`,
`independent_corroboration_established=false`,
`warning_level_change=false`. No automatic incident
geolocation, target identification, issuer, hit rate,
threat probability or watch severity is created.

## Where this appears

The original AIBA Atlas **Behavioral signals** panel
receives a separate **Possible event/report links** section.
Source document groupings, possible same-event reports
and related reporting get distinct labels and source links,
observation times, reporting origins and uncertainty
statements. They do not enter the strict
`review_groups` count, the Recent changes list,
or the public warning scorecard.

The read-only `behavioral_fusion.json` payload includes
a `report_relationships` object. It is bounded to a
72-hour source-history replay, at most 2,000 records,
90,000 comparisons and 20 displayed groups, with
explicit truncation flags. The static Pages embed
and live branch refresh both project a smaller
safe subset and reject attempts to claim already
verified independent corroboration or warning status.

## Actual source-data validation (November 13, 2026)

The read-only PR source probe examined **173 unique normalized
historical observations** (27 history files) and found:

| Relationship kind | Observed |
| --- | ---: |
| Repeated, source-specific primary documents | 9 groups |
| Possible republication of the same article via another URL | 2 pairs |
| Possible event identity across separately worded reports | 0 pairs |
| Related stories about possibly different reported incidents | 0 pairs |

Only **7 of 173** available records were incident-report-like
commercial reporting; **166 were routine notices, market
questions or measurement data**, which are not eligible
for title-only incident matching. The actual current
registry had 270 records in that run; a source snapshot
count is not a worldwide case denominator.

The initial permissive prototype produced **608 apparent
same-event pairs**, overwhelmingly the wrong interpretation
of routine notices and repeated articles. That was rejected
before deployment. The final probe correctly reclassified
syndicated Google News versus direct Maritime Executive
articles as possible *same stories*, not two independently
witnessed geopolitical events.

See [dated source-audit receipt](evidence/aiba-report-resolution-real-probe-2026-11-13.json)
and the read-only
[GitHub source run](https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/runs/43448755858).

No source in that run supplied enough validated event-site
metadata to test a real proximity-based incident match.
A successful synthetic Kyiv/New York test verifies the
*logic*, not actual detection performance.

## Follow-on improvements

An academically/operationally serious report resolution
system must eventually examine *actual source claims*
rather than headlines alone. The next reviewable
iterations should extract source-grounded structured
**actor, action, object, time and event location**
with traceable evidence spans; evaluate precision and
false merges against a blinded human-labeled benchmark;
recognize syndication/derivative articles, contradiction
and location uncertainty; and test spatial overlap
of **actual source-provided event locations** without
conflating publisher office, notice area and attack point.

**Do not loosen executive-warning standards based on
candidate report matches.** Source-specific correlation
and independent corroboration must be validated separately.
