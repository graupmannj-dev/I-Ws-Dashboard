# CAIRN public border transport friction sample

The direct U.S. Customs and Border Protection (CBP) public JSON
`https://bwt.cbp.gov/api/waittimes` publishes estimated wait times
for U.S. Canadian- and Mexican-border land ports, including commercial lanes.
Unlike the initial FEMA ArcGIS mirror trial, this source returned a directly
retrievable public JSON response during integration research.

## Analytical limits

The measured quantity is a **port's published estimated delay in minutes**,
plus lane status and estimated lanes open. It is not a direct count of trucks,
flow across the border, military traffic, or hostile intent. Waiting times
also change because of staffing, normal seasonal freight, inspections,
weather, and lane closures.

The source reports local wall-clock date/time strings and informal lane
update-time strings, not consistently timestamped UTC event times. We
preserve those strings as metadata and record our own collection time
separately. No UTC event time is synthesized from ambiguous port-local
clocks. Old port dates are rejected (one-day UTC boundary allowance);
missing/invalid wait values remain **null, never zero**. Only publicly
named ports and aggregate lanes are collected; no individuals or routes.

The output is a bounded, source-separated, first-baseline-only supporting
observation and does not automatically authorize any security warning.

Tests:
`python -m unittest tests.test_alternative_sensor_pipeline -v`

Upstream public source and terms:
https://bwt.cbp.gov/
https://bwt.cbp.gov/mfaq.html
https://bwt.cbp.gov/api/waittimes
