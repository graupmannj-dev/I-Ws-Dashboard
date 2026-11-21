# CAIRN: national primary-source pilot beyond U.S./European issuers

**Date:** 2026-11-20. This pilot is **officially issued environmental/hazard context**,
not verified military preparations, independent incident corroboration or
worldwide coverage.

## Data contracts and scope

| Source mode | Original national authority | Public endpoint | Real footprint / observation |
|---|---|---|---|
| `bmkg_quake` | **BMKG, Indonesia** | https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json | Indonesia-area 15 most recent magnitude-5+ catalog earthquakes; UTC origin, epicenter and magnitude |
| `bmkg_nowcast` | **BMKG, Indonesia** | https://www.bmkg.go.id/alerts/nowcast/en | Indonesia provincial official severe-weather RSS bulletins; not observed storms |
| `inmet_br` | **INMET, Brazil** | https://apiprevmet3.inmet.gov.br/avisos/rss | Brazil national severe-weather issued warning documents |
| `imd_in` | **IMD, India** | https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml | IMD weather alerts distributed by the World Meteorological Organization (WMO) CAP Alert Hub |
| `saws_za` | **SAWS, South Africa** | https://cap-sources.s3.amazonaws.com/za-saws-en/rss.xml | South African weather-alert announcements relayed by the WMO CAP Alert Hub; not Africa-wide |

BMKG official specifications: https://data.bmkg.go.id/gempabumi/ and
https://data.bmkg.go.id/peringatan-dini-cuaca/ . Both require explicit BMKG
attribution and impose a 60-request-per-minute rate limit per IP; CAIRN
polls on its existing *three-hour* collector workflow, at most one endpoint
per mode per run.

India IMD feed:
https://alertingauthority.wmo.int/authorities.php?recId=182 and
https://www.nrsc.gov.in/nrscnew/assets/pdf/announcements/DRM_Meet_2023/S-III_MeteorologicalDisaster.pdf .

South Africa authority:
https://alertingauthority.wmo.int/authorities.php?recId=152 .

INMET national severe weather service:
https://portal.inmet.gov.br/servicos/avisos-especiais .

## Controls

- Only provider-declared HTTPS hosts; bounded 4MB RSS/XML response, no
  DTD/entities, no HTML scraping, no authenticated or paid endpoints.
- Timestamped, stable source root; no inferred event time from the **issue**
  date of a weather bulletin. Source-reported earthquake origin is
  NOT publication time.
- Active/stale feed dates bounded to seven days. An old notice in an
  RSS catalog is not new activity; a feed schema failure is **unavailable**,
  never zero or calm.
- No two national authority **publication feeds** become independent physical
  events. BMKG earthquakes can overlap USGS records; WMO redistribution
  is the same authoritative notice, not an independent observation.
- Country footprint of each feed is explicit. More publishers do not imply
  worldwide country coverage or validated hypothesis support.
- First provider read initializes a baseline, never automatically
  nominates new conflict warnings. No calibrated numerical baselines exist.
- Links, first capture, and freshness feed the existing registry and
  source health. New records are eligible for descriptive review only.

## Testing

```bash
python -m unittest tests.test_national_sensors tests.test_alternative_sensor_pipeline -v
python -m unittest discover -s tests -v
```

CI also performs a read-only **live source probe** for all national sources;
network/schema failures must be visible in health receipts, not quietly
suppressed. Passing offline tests alone does not establish public availability
or completeness.

Next: independent non-Western **transport, communications, energy** and
commerce series with recorded sampling denominators and meaningful baselines.
