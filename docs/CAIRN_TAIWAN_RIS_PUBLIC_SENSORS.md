# CAIRN: public Taiwan grid load and sampled non-Western network routing

## Taiwan: official Taipower national grid load

**Original publisher:** Taiwan Power Company.

- Government dataset: https://data.gov.tw/en/datasets/162595
- Direct JSON: https://service.taipower.com.tw/data/opendata/apply/file/d006020/001.json
- Licence: Taiwan Open Government Data Licence, version 1.0.

The feed reports `curr_load` in **ten-thousand kilowatts**
(`萬瓩`; multiply by 10 to convert to megawatts). CAIRN retains source
numerical and normalized MW fields. The `publish_time` field uses a
Republic-of-China year, Taiwanese day name, and **Asia/Taipei UTC+8**.
It is a **release time**, not a separately verified live physical sampling
clock; no artificial event timestamp is created. Stale/future release clocks
and invalid numeric fields fail the provider check.

This is a **national aggregate**. It is neither a local blackout nor a
frequency measurement, an actor-attributed attack, or an indication of
military preparations.

## Routing: RIPE RIS public BGP announcements on six selected ASNs

RIPEstat documentation:
https://stat.ripe.net/docs/data-api/api-endpoints/bgp-update-activity

Six examples associated with network operators in China (AS4134),
India (AS9829), South Korea (AS4766), Vietnam (AS7552),
South Africa (AS5713), and Argentina (AS7303). Confirm current
ASN assignment before making country statements. These targets
sample different **operator networks**, not representative country
connectivity coverage. Measurements come from RIPE RIS routing
collectors; the observation publisher remains RIPE, not the target
operator.

Each query requests six hours of sampled BGP announcements with at
most 24 buckets. Returned observation clocks are aggregate
query-window boundaries, not timestamps of an outage. In the
RIPEstat ASNs API, **withdrawals are null**; we never treat null as
measured zero. Every target remains independently healthy/unavailable
and an ASN silence is not an all-clear. No individual IPs, users, or
facility positions are collected.

Both sources enter the alternative-source pipeline as **context**,
not automatic warning or signed hypothesis evidence. Their health
is source separated. A national Taipower reading and aggregate
BGP updates can be considered together only with an explicit,
validated spatiotemporal hypothesis and a false-alarm comparison.

## Acceptance
`python -m unittest tests.test_grid_and_bgp tests.test_alternative_sensor_pipeline -v`

`python -m unittest discover -s tests -v`

The CI's read-only source probe checks whether the official endpoints
actually answer, reports unavailable modes and incomplete network
cohorts, and does not convert failed fetches to zero.
