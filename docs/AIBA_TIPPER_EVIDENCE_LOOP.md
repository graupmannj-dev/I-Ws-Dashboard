# AIBA global pre-news tipper and outcome-learning contract

**North star:** a small number of well-supported global indications-and-warnings
tippers from independent public and nontraditional evidence, issued while an
event is in preparation or development. GDELT provides news/event structure
and timestamps; UCDP provides a later and **narrower** set of coded-violence
outcomes. Neither retroactively establishes that AIBA warned early.

This is an architecture and validation contract, **not** a production
fusion implementation.

## Evidence chain

| Stage | Role | Non-negotiable limit |
| --- | --- | --- |
| Independent sensors | Worldwide nontraditional friction, aviation/maritime deviations, restrictions, cyber/infrastructure/commercial/civic behaviors | One aircraft anomaly or missing receiver data is not evidence of hostile intent |
| AIBA fusion | Assess source quality, independent signal families, correlated changes, baseline departures, alternatives and counter-indicators | Do not count relayed copies of the same underlying sensor as independent confirmations |
| Frozen tipper | Preserve actual issuance timestamp, event hypothesis, actors, area, expected horizon, evidence and response implication | Never reconstruct a tipper after the event and describe it as a previously issued warning |
| GDELT news timeline | Determine public-reporting timing, structured case geography, narrative propagation and corroborating coverage | News volume is not independent proof; GDELT ingestion can lag article publication |
| UCDP and independent outcome reviews | Code eligible episode-level state-based violence; require genuine actor/dyad/time matching and complete release horizon | UCDP does not cover all alertable geopolitical developments; missing releases are not negative cases |
| Evaluation | Rolling-origin precision, recall where outcomes are actually observed, lead time, false alarms per analyst-day, source outages and ablation versus GDELT-only | Avoid in-sample threshold optimization and cherry-picked successes |

## Minimum immutable tipper record (future implementation)

- An explicit falsifiable event hypothesis, actors, geography, material
  consequence and a bounded prospective horizon.
- As-of source availability: source publication, original observation,
  collection, ingestion and final tipper issuance timestamps.
- Family of indicators, underlying original providers, shared dependencies,
  quality/completeness state, lagged baseline and counter-indicators.
- Supporting and competing explanations, limitations and a requested
  analyst action. Define in advance what observation would downgrade it.
- Immutable forecast ID, version and issuance state, separate from any
  subsequent GDELT context or UCDP adjudication.
- Evaluation window status: labeled, unadjudicated, not applicable or
  censored; do not score an uncovered period as a no-event outcome.

AIDA-style anomalous detection alone is insufficient. No single
airport flight-path deviation changes AIBA threat severity.

## Definition of actual early warning

The central question is not whether an anomaly occurred before a
headline discovered retrospectively. It is whether an immutable,
auditable tipper was actually *issued* before the first independently
accessible relevant primary or mainstream report, and whether its
specified actors, action, geography and horizon subsequently matched.
Record both the first credible article/publication date and GDELT
first-observed time. Never backdate new knowledge into the warning.

Separate three metrics:
(1) early warning ahead of news, (2) eventual specific event match,
and (3) analyst burden/noise. A high hit rate in ongoing conflict
zones without genuinely new and actionable early cues is not success.

## Learning discipline

- Construct monitored case/region risk sets **before** viewing labels,
  including complete, verified negative cases and quiet periods.
- UCDP Candidate/episode labels lag live conditions and cover only
  some lethal-conflict outcomes. Match opposing actors/dyads and
  episodes rather than geographic country overlap.
- Compare the same frozen time range and comparable sources:
  GDELT-only vs GDELT plus independently collected nontraditional
  friction indicators. Ablate each sensor and account for shared
  sources and varying coverage.
- Track lead-time distribution, precision, false alarms per
  analyst-week, review time, missed events, source outages and
  threshold stability. Cluster evaluation by event/dyad when
  repeated country-days overlap.
- Feed *later* adjudications into future out-of-sample
  calibration; never silently rewrite historical tippers.
- Decay persistent hotspot scores and use threshold hysteresis
  without smoothing away genuine abrupt changes.

See [GDELT retrospective limits](GDELT_RETROSPECTIVE_VALIDATION.md)
and [UCDP actor/episode adjudication](UCDP_EPISODE_ADJUDICATION.md).
The existing country-day GDELT-to-UCDP evaluation cannot establish
specific early warning about the opposing actors of a conflict.

## Air traffic pilot is one candidate sensor, not the mission

The [offline flight corridor detector](AIRCRAFT_ROUTE_RETROSPECTIVE.md)
and [one-day archive benchmark](AIRCRAFT_ONE_DAY_BENCHMARK.md)
measure the feasibility of **one** indicator class. Prove source-day
cost, receipt completeness, representative history, flight segmentation
and out-of-sample false-alarm burden first. Receiver gaps, weather,
ordinary ATC reroutes and changing aircraft assignments are
alternative explanations.

If the full-day collection or 28-day history is uneconomical,
inadequate or overly noisy, retain AIBA's broader global discovery
architecture and deprioritize this source until a cheaper
queryable historical feed exists.

**Not implemented in this PR:** a production tipper registry,
cross-source automatic warning changes, GDELT article first-seen joins,
UCDP outcome promotion, or a scheduled worldwide aircraft job.
