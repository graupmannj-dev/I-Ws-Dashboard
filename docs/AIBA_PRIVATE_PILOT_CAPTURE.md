# AIBA prospective shadow trial — private source evidence capture

**Status:** manual local-only tool. NOT automated warnings, assessed predictive
skill, new scheduled collection, or a hosted private ledger.

## Why this step matters

The earlier prospective frame prototype stored hashes of the public
aiba-feed-data registry and fusion records. Those snapshots are mutable:
a future collector update would otherwise remove the exact raw evidence
that the analyst actually saw. This tool archives **the original
source bytes in a restricted private directory** and matches their
SHA256 to the hash-chained coverage frame appended to the private
ledger.

A coverage frame documents which bounded providers returned observations,
their explicit missingness, and currently unreviewed leads. It is
**not a forecast, an event outcome, an all-clear or a verified risk set**.
A 24-hour window does not prove continuous observation for 24 hours.

## One-time setup

Use Python 3.11+ on a POSIX host or Windows Subsystem for Linux.
Download the public repository and a separate checkout of its
public aiba-feed-data evidence branch:

~~~bash
git clone https://github.com/graupmannj-dev/I-Ws-Dashboard.git ~/aiba-code
git clone --branch aiba-feed-data --single-branch \
  https://github.com/graupmannj-dev/I-Ws-Dashboard.git ~/aiba-state
git -C ~/aiba-state pull --ff-only
~~~

Always refresh actual public source data before checking readiness;
never alter its timestamps to make stale data appear current.

First **check only**, without creating any files or issuing forecasts:

~~~bash
python ~/aiba-code/scripts/aiba_private_pilot_capture.py \
  --registry ~/aiba-state/observations/latest/behavioral_registry.json \
  --fusion ~/aiba-state/observations/latest/behavioral_fusion.json
~~~

The strict gate requires a valid registry/fusion pair collected
within 90 minutes of the local run, nonbaseline state, source
health consistency, a finite list of unreviewed observations,
and no automated severity promotion. Failure returns
status=unavailable and a nonzero exit code; an expired
snapshot is NEVER silently reissued.

## Manual freeze only after successful preflight

~~~bash
python ~/aiba-code/scripts/aiba_private_pilot_capture.py \
  --registry ~/aiba-state/observations/latest/behavioral_registry.json \
  --fusion ~/aiba-state/observations/latest/behavioral_fusion.json \
  --mode freeze --accept-unverified-coverage \
  --private-root ~/.aiba-shadow-private
~~~

This opt-in creates or uses an owner-only directory (0700)
**outside the public Git checkout**. Source files, a private
manifest and commit receipt are mode 0600. The raw inputs are
read and SHA256-checked again before archiving, preventing
unexpected changes between preflight and exact-byte storage.

Private layout:

~~~text
~/.aiba-shadow-private/
  tippers.jsonl
  frames/
    shadow-YYYYMMDDTHHMMSS-<digest>/
      registry.json
      fusion.json
      manifest.json
      local-freeze-receipt.json
~~~

The appends use the machine's actual UTC clock; the ledger
and stored source copies are checked after append. A new
capture cannot overwrite an existing frame folder. A
failed append may retain a secure but **uncommitted** source
folder without a successful local-freeze receipt. Never
treat that orphan as a valid risk window.

A successful receipt includes the new private ledger head
SHA256 and entry count. The receipt explicitly says:
independent time witness unverified; no issued tipper;
no confirmed negative event; no predictive skill estimate.

## Independently witness the ledger head

Immediately open the existing GitHub workflow:

https://github.com/graupmannj-dev/I-Ws-Dashboard/actions/workflows/aiba-ledger-head-attest-manual.yml

Use only the hash and entry count from your successful
private capture receipt. Never upload the ledger, raw
source archives, actors, analyst names or forecast texts
to the public repository.

The manual GitHub Sigstore workflow signs a hash-only subject.
Verify its signer identity, attested file hash and witnessed
timestamp before using it in research. It establishes an
independent **upper bound on when the committed content
existed**, not proof that the local clock was accurate.
If the original article predates the actual witness
timestamp, the record does not demonstrate pre-news lead time.

## Issue a genuine analyst-reviewed forecast separately

Only when an independently corroborated preparation signal
justifies a specific hypothesis should an analyst use the
existing private issuer:

~~~bash
python ~/aiba-code/scripts/aiba_tipper_ledger.py issue \
  --ledger ~/.aiba-shadow-private/tippers.jsonl \
  --payload /private/analyst-reviewed-forecast.json
~~~

The issuance must name actual actors, observable action,
place, bounded horizon, probability and time-stamped
available-before-issue evidence, plus alternatives and
counter-indicators. Then **immediately witness the new
ledger head**: the earlier frame witness alone does not
prove the later issued hypothesis existed before the news.

Later use the existing report and adjudicate commands to
append independent first-original-article reviews and
actor/action/place/horizon outcome labels. Missing or
unreviewed outcomes remain censored or unknown. GDELT's
first-observed time is NOT original first publication.

## Engineering and assessment gates still ahead

- Preserve and securely back up actual private files. GitHub
  Actions artifacts and public Pages are not private custody.
- Independent Sigstore timing has been tested with synthetic
  data, not a real geopolitical pre-news forecast.
- Collect repeated prospective frames and bounded coverage
  gaps through healthy post-GitHub-outage operations.
- Register event risk sets and independently discovered misses.
  Do not infer continuously observed calm from one frame.
- Record analyst workload, false warnings, case-specific
  review coverage, event misses and first-article verification
  before estimating calibration and lead-time distribution.

This tool changes no cloud billing, IAM, production alarms,
hotspot ratings or collection schedules.
