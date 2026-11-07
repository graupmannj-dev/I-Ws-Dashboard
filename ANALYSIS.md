# AIBA 7: Scenario intelligence synthesis

This release changes the **Operational Feeds** page from a record dump to an evidence-aware
decision briefing. It does **not** make a validated probability forecast or authorize the
system to issue "Critical" military warnings.

## Working analytic logic

For each of the ten source-linked dossiers, show:
1. **Decision question and 7/30/90-day horizon**: what distinct scenario is actually being watched.
2. **Historical severity baseline, separately dated**: current risks are not reset because no new alarm was collected.
3. **What genuinely changed since a prior comparable snapshot**: compare source IDs and publication dates;
   never turn an old standing travel advisory into a new warning simply because it was fetched today.
4. **So what**: distinguish market repricing, public protective notices, syndicated reporting,
   actual independently verified preparation (not collected yet), or a source outage.
5. **Most diagnostic next indicator** and **alternative explanation**: explicit falsification tests
   instead of assuming every anomaly is an attack precursor.
6. **Direct evidence links, original publication date if known, and collection timestamp**.
7. **Source limitations and uncertainty**: no automatically upgraded conflict risk.

Two data products:
- \`observations/latest/decision_briefs.json\`: updated after six-hour / daily operational collections
- \`observations/history/decision_briefs/{timestamp}.json\`: immutable records for later walk-forward audits
- \`_site/ops/decision_briefs.json\`: publication of the most recent brief alongside \`_site/ops/index.html\`

## Exact contract registry

\`data/decision_registry.json\` pins only selected market IDs to **exact event definitions**
and case-specific questions. \`watchlist_collector.py\` fetches public documented
single-ID Manifold or Polymarket endpoints, validates the ID, question text,
binary outcome, expiration and source-specific liquidity; mismatches fail closed.

This matters because a 2030 Taiwan invasion contract, a 2026 Taiwan blockade
contract, an Iranian regime-change contract, and a ceasefire agreement contract
measure **different things**, and their YES prices cannot be averaged into a
single "war probability". Contracts with thin or missing liquidity are excluded
from repricing alerts. An explicitly registered market can still have unusual
resolution rules or incentives that require human assessment.

Move detection compares the **same exact contract and question** against prior
observations 4–10h (8 percentage-point exploratory threshold) or 18–36h
(12 percentage-point exploratory threshold) earlier. These thresholds are
not optimized, do not claim independent prediction skill, and do not automatically
change case threat classification. Directional signs are contract-specific:
more YES for a Hormuz agreement is a potential de-escalation repricing, not
a higher risk of war. Changes in attention or forecast estimates are not evidence
of hidden military preparations.

## Avoiding false intelligence

- First collection is a **baseline**, never a fresh warning.
- Travel notices with missing dates are **undated standing advisories** until an
  observable version change. For revised pages without original publication time,
  report the interval in which the change was **observed**, not invent an event time.
- Syndicated articles and repeated source URLs are not independent economic behavior.
- "No change established" ≠ no risk. Missing/stale feeds create collection gaps.
- For Ethiopia–Sudan and Ethiopia–Kenya, country-only reports cannot be attributed
  to bilateral interstate war; require explicit pair or named border situation.
- Historical curated dossiers remain unchanged unless reviewed separately.
- Source overlap is not independent convergence; look for confirmed primary-source
  cost-bearing action and lead-lag chronology before warning upgrades.
- Snapshot and observation timestamps enable future audits; accuracy/false-positive
  rates still require independent labeled event and non-event periods.

## Production

Operational scheduled workflow runs source collection, then \`fusion_briefs.py\`
and commits source snapshots and decision briefs to \`aiba-feed-data\`.
The daily Pages build renders the decision briefs above the existing feed reports.
The public page **does not update every six hours**; it updates at the daily publish.
Missing briefs show a clearly labeled unavailable state, not a fake "quiet" report.

To test a PR, the original CI runs the full Python suite and offline dashboard rendering.
The PR smoke job probes registered contracts from GitHub's infrastructure read-only.
After merge, dispatch \`Collect AIBA operational feeds\` with mode \`all\`; confirm
the new \`watchlist.json\` and \`decision_briefs.json\` in the data branch. Then dispatch
\`Validate and publish AIBA\` to refresh \`/ops/\`. Do not merge if CI fails.

## Next technical limitations

- Add **primary-source** independent costly behavior and regional peer baselines,
  not merely syndicated reports about shipping or insurance.
- Add source-root event identity, rate/sequence statistics and multi-day change-point
  detection (the current 6/24h thresholds are screening heuristics).
- Link GDELT nomination data and attention spikes as **non-independent context**
  with explicit timestamps, without counting them as verified military signals.
- Track a pre-specified outcome label, date and event threshold to measure precision,
  recall, false-alert burden and actual lead time through walk-forward tests.
- Nothing here certifies that market crowds are calibrated or that reviewed dossiers
  are current beyond their own dated evidence.

References:
- https://docs.manifold.markets/api
- https://institute.polymarket.com/data
- https://github.com/graupmannj-dev/I-Ws-Dashboard/issues/2
