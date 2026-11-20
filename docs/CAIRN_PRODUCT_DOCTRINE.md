# CAIRN — Product doctrine and analytical architecture

**Full name:** Corroborated Alternative Indicators for Risk Navigation

## Purpose

Find and characterize **unusual, source-observed changes in the operating
environment** before they are necessarily prominent in conventional reporting
or receive dedicated collection attention. CAIRN is an *alternative-indicator
early-warning workbench*, not another comprehensive intelligence-fusion portal.

The differentiated value is early recognition of **structural friction**:
the hard-to-hide operational side effects of preparation, disruption,
constraint and reaction. A maritime exclusion notice, abnormal routing,
network reachability change, unusual commercial transport behavior or
institutional announcement might warrant attention **before** an event becomes
a recognizable news story. A signal is not a finding of cause or intent.

This project is meant to **complement** IC/defense analytic workflows, including
situations outside already tasked collection priorities. It does not replace
collection requirements, classified reporting, trained analysts or existing
mission systems. Claims of predictive lead time require prospective validation.

## Priority of evidence

1. **Primary: alternative, behavior-linked indicators.** Maritime and
   airspace restrictions, FAA NAS operational effects, network reachability,
   selected market-implied expectations and other dated institutional or
   commercial traces. Subsequent candidates include AIS vessel rerouting,
   port congestion, war-risk insurance and freight costs, ADS-B corridor
   deviations, public infrastructure telemetry and bounded procurement
   signals. A source's operational collection status is explicit; listing
   a planned stream does **not** imply that it is connected.
2. **Supporting: traditional/contextual information.** GDELT event-coded media
   and news density, conventional reporting, official statements and curated
   historical case briefs. These explain context, identify possible links,
   challenge interpretations and may contribute corroboration **only when
   source independence and claim quality are established**.
3. **Evaluation/retrospective:** Independently time-stamped outcomes and
   conflict-event references where available (e.g., UCDP), used to audit
   whether signals preceded events and whether alternatives outperformed
   obvious news coverage. Outcome data are not raw early-warning indicators.

Conventional reporting must not numerically swamp the alternative-indicator
discovery queue merely because it is abundant. Duplicate syndicated stories
do not constitute distinct evidence roots.

## Analytical pipeline

```text
public providers / operational traces
        |
  source health, time provenance, units, limits, coverage
        |
  immutable observations & comparable dynamic baselines
        |
  unusualness / deviation detection  ---> retain single-source anomalies
        |
  source document identity & automatic analytical topic families
        |
  cross-domain substantive relationship proposals (not event merging)
        |
  contextual reporting and corroboration checks
        |
  analyst investigation with individual original sources
        |
  separately reviewed warnings and prospective evaluation
```

**Unusualness and corroboration are independent dimensions.** Strongly unusual
single-source observations are displayed promptly. Missing corroboration can
be visible without blocking discovery. A normal-looking observation with
multiple headlines is not automatically more important than a rare measurable
operational anomaly.

A third metadata category, **collection coverage/freshness**, is not a
pseudo-risk score: unknown, stale and partial providers are explicitly
indicated and never interpreted as zero activity.

## Event family hierarchy and reasoning

- **Source fragments:** geometries, quote updates, notices, reports and
  versions with individual timestamps and links.
- **Source documents:** a unique official notice or original story; fragment
  count does not equal independent verification count.
- **Analytical families:** time-persistent topics sharing operational
  activity, region or causal subject. These may contain different incidents
  and months or years of records.
- **Candidate incidents:** separate, date/place-sensitive relationships
  proposed from family contents; not asserted to be verified.
- **Corroborated findings:** separately supported and reviewed conclusions.

A family is an organizing lens, not proof of one event, hostile intent,
attribution or source independence. Persist original evidence and maintain
links across time; allow topics to reopen as new material arrives.

## Interface contract

The CAIRN homepage defaults to evidence families when a registry is present.
Families with qualified statistically abnormal measures stay first, even if
single-source. After those, families containing alternative-source records
are prioritized above context-only articles. Conventional reporting is
**retained**, searchable and clearly labeled, not discarded.

The **Sources & status** page shows plain-language descriptions, role,
geographic coverage, last collection check, last valid sample, freshness,
missingness and any provider-specific limits. Passing a collection-health
check does not imply a quiet or safe environment.

Source-linked drilldown must expose underlying observations and explain
why they are grouped. Do not compute a combined z-score by averaging
non-comparable metrics; report named, qualified measures only.

## Evidence of actual performance

Before claiming improved warning skill, evaluate the following on dated,
prospective or truly held-out observations:

- Lead time from first alternative indicator to independently verified
  event onset and separately to first substantial public reporting.
- Sensitivity/recall over clearly defined event populations and risk sets.
- False positive rates and operational analyst review burden, per source
  and alert family, with missing-coverage denominators.
- Calibration, drift and seasonality of source-specific anomaly measures.
- Whether automatic family grouping reduces duplicate work while avoiding
  false thematic joins; false-join and missed-link error rates.
- Robustness to source outages, changing provider sample composition,
  duplicated syndication and strategic adversarial deception.

**No unverified performance claim**: the present workbench does not yet
demonstrate reliable predictive lead time, combatant-command usefulness,
or a production monitoring service-level guarantee.

## Migration and governance

CAIRN is the human-facing product name. Keep historical `aiba.*` JSON
contracts, environment variables, GitHub workflow identifiers, original
repository path and Pages URL until a separately tested compatibility
migration is approved. This prevents breaking collectors, scheduled tasks,
documentation backlinks and existing integrations.

CAIRN should remain unclassified, protect source provenance, avoid
personal surveillance, and distinguish public observations from official
government conclusions.
