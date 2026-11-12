# FAA published airways: low-cost aircraft route screening

**Experimental offline prototype.** No live collectors, schedules, alert
promotion, cloud changes, or worldwide coverage. FAA NASR airways are
**available paths**, not an aircraft's filed or ATC-cleared route.

## Verified authoritative source

The FAA October 29, 2026 NASR subscription is currently effective
through the next cycle on November 26, 2026. From the official
[FAA NASR Oct 29 archive](https://www.faa.gov/air_traffic/flight_info/aeronav/Aero_Data/NASR_Subscription/2026-10-29/)
obtain the AWY, FIX and NAV CSV ZIP groups. Extract their
AWY_SEG_ALT.csv, FIX_BASE.csv and NAV_BASE.csv records.
The FAA provides navigation routes and fix/navaid geographic
coordinates. Check that all three CSV tables have the same
effective date, and retain a source-checksum and cycle record.

Other possible inputs include
[FAA CIFP navigation data](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/download/)
for SID, STAR and other procedures, subject to additional
format parsing. The [FAA ATC manual](https://www.faa.gov/air_traffic/publications/atpubs/ATC_html/chap4_section_4.html)
specifically allows direct, random RNAV, vector and non-airway
routing. Flying outside a published line is therefore NOT abnormal
by itself. Equally, passing near some published route is not
proof of a normal or cleared path.

Research also found an [FAA ATS Route ArcGIS layer](https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/ArcGIS/rest/services/ATS_Route/FeatureServer/0)
whose metadata still describes a June–August 2021 effective period.
Do NOT treat that data as a current 2026 network.

## Building the dated reference

Manually download FAA source CSVs, then run from the checkout root:

~~~bash
python scripts/aircraft_airway_prefilter.py build \
  --awy /local/faa/AWY_SEG_ALT.csv \
  --fix /local/faa/FIX_BASE.csv \
  --nav /local/faa/NAV_BASE.csv \
  --effective-from 2026-10-29 \
  --effective-until 2026-11-26 \
  --output /tmp/aiba-faa-jq-reference.json
~~~

The importer retains only high-altitude J and Q airway line
segments within a limited CONUS bounding rectangle, matches
fix/navaid coordinates conservatively, and excludes gapped,
unusable, ambiguous, overlong or nonfinite segments. It
rejects mixed cycles. All input files are hashed. The
source_dataset_completeness_verified field remains FALSE
even after a successful local import, because the code
cannot independently verify that all FAA rows were supplied.

The current research runtime could verify the official download
URLs but could not retrieve the ZIP bytes. The importer is
therefore tested only against synthetic FAA-format fixtures,
not yet production-validated against the actual 2026 CSVs.

## Screening an offline track

Input schema: aiba.aircraft-enroute-legs.v1, with a date and a
list of completed, consistently observed flight legs. Each
leg requires a unique flight_id, coverage=complete, and at least
six positions containing UTC Unix timestamp t, lat, lon and
altitude_ft. The minimum valid observation span is 15 minutes,
with no gap over 10 minutes. Only 18,000–45,000 ft MSL CONUS
positions are eligible.

~~~bash
python scripts/aircraft_airway_prefilter.py screen \
  --network /tmp/aiba-faa-jq-reference.json \
  --input /tmp/aiba-enroute-legs.json \
  --width-km 25 \
  --output /tmp/aiba-airway-screen.json

python -m unittest tests.test_aircraft_airway_prefilter -v
~~~

The script uses a 2-degree geographic grid to reduce candidate
segment distances before great-circle calculations. The
25-km distance and 80%-of-points thresholds are tentative
engineering heuristics, not certified airway widths or calibrated
detection thresholds.

| Result | Correct interpretation |
| --- | --- |
| network_proximity_only | Most eligible points are near SOME published airway, not necessarily the assigned route |
| needs_route_context_before_history | Parts of the track fall outside known buffers; look for direct routing, flight plan, ATC, weather and then relevant history |
| uncovered_by_local_reference_index | The local reference offers no nearby segments; UNAVAILABLE geographic coverage, not an anomaly |
| insufficient_observations | Missing altitude, partial reception, time gaps or too little usable path |
| unavailable | Reference out of date or malformed input |

No result emits an alert or changes AIBA hotspot severity.
Even network_proximity_only cannot suppress corroborated
warning evidence from other independent sensor streams.
The review candidate count is not an anomaly count.

## Remaining research and engineering gates

1. Validate the actual October 29 FAA CSV source data and
   all omitted/unresolved route segments. Review redistribution
   and source attribution before publishing route geometry.
2. On CLEAN, real held-out flight legs, compare cheap network
   screening against historical reference behavior. Quantify
   false positive review load, false negatives and how many
   expensive historical comparisons can be avoided without
   suppressing significant activity.
3. Add SID/STAR, filed-route or ATC direct clearance context
   where legitimately available. Do not assume every aircraft
   should remain inside a published airway.
4. Expand to other regions only after identifying and pinning
   current, lawful regional AIP/ATS route data. This CONUS
   test is not global airspace coverage.
5. Keep the broader AIBA mission central: freeze specific
   independent multi-sensor tippers BEFORE public reporting,
   use GDELT for first-report comparison, and adjudicate
   eligible outcomes using independent sources and UCDP.
   Source outages, ambiguous matches and unlabeled
   outcomes must never count as negative cases.

Further details on the mission are in
[AIBA tipper evidence loop](AIBA_TIPPER_EVIDENCE_LOOP.md).
