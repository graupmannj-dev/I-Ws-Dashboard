# CAIRN public border transport friction sample

The FEMA ArcGIS public mirror of CBP border wait estimates provides a useful
**transport-friction proxy** separate from published navigation restrictions.
This collector reads the FEMA `BorderPorts_CBP/FeatureServer/0` public
GeoServices JSON, restricted to its published southern-border extent.

## Interpretation

The underlying data record **estimated wait minutes** and selected commercial
lane states at published U.S. land ports. They are *not vehicle counts, actual
crossing throughput, evidence of troop movements or a measure of hostile
intent*. Staffing, holiday flows, inspection policy, seasonal freight, and
source delays all provide alternative explanations for a sudden wait change.

The public FEMA layer states that it mirrors CBP data about hourly. The
collector records the source measurement time from `date_` (ArcGIS epoch ms);
records older than 12 hours are rejected instead of relabeled as current.
Published port IDs, names and crossing names are retained; a port is not
interpreted as the location of an incident. No individual tracking or personal
data is collected.

Collection is bounded, source-specific and fail-closed: unparseable or stale
responses write unavailable health and cannot replace a current success with
fictitious normal traffic. Port-level delay baseline calibration is **not yet
implemented**, and the new stream does not approve any automatic warning.

Sources:
- https://gis.fema.gov/arcgis/rest/services/Partner/BorderPorts_CBP/FeatureServer/0
- https://bwt.cbp.gov/mfaq.html

Run: `python -m unittest tests.test_alternative_sensor_pipeline -v`

Existing pipeline: `alternative_sensor_pipeline.py`, `behavioral_registry.py`,
`dashboard/source_status.js`, and the 3-hour workflow
`.github/workflows/collect-cairn-alternative-sensors.yml`.
