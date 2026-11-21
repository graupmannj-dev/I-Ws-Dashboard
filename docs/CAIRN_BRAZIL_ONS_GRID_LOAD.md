# CAIRN Brazil ONS: measured regional grid load (pilot)

**Publisher:** Operador Nacional do Sistema Elétrico (ONS), Brazil's
national electricity-system operator. Source and CC-BY notice:
https://dados.ons.org.br/dataset/carga-energia-verificada

**Documentation:** https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/carga_verificada_tm/DicionarioDados_Carga_Verificada.pdf

## Actual sensor mechanism

The ONS API publishes **verified electricity demand, half-hourly**, by
official Brazilian electrical load area. CAIRN samples four
macroregions `SECO` (Southeast/Central West), `N` (North),
`NE` (Northeast), and `S` (South), each as a separate bounded
public call:

```
https://apicarga.ons.org.br/prd/cargaverificada?dat_inicio=YYYY-MM-DD&dat_fim=YYYY-MM-DD&cod_areacarga=SECO
```

The collector requests a one-day interval **two days before collection**
to allow publication and verification delay. It uses official source field
`din_referenciautc` (source explicitly defines UTC+0) and value
`val_cargaglobal` in `MWmed` — an averaged megawatt measure,
*not* a frequency deviation, unexpected blackout, damaged component
or adverse actor's action. Negative load adjustments are not
arbitrarily erased because the source dictionary permits them.

Each macroregion yields at most one latest validated half-hourly
historical reading, with original source time, grid area ID, source
count and full source URL. Collection and source timestamps are separate;
the read is **not continuously live**. Each area failure is isolated
within the overall provider health and prior samples are retained
as historical records, not reinterpreted as current availability.

No seasonal, day-of-week, weather- and comparable-hour baseline is
calibrated yet. The evidence class is `grid_load`, but no
automatic hostile intent, attributed outage, or negative evidence.

The authoritative documentation permits CC BY reuse with ONS
attribution. Interface availability is not guaranteed; a blocked,
empty or changed API is recorded as `unavailable` rather than
a fabricated zero.

## Acceptance

`python -m unittest tests.test_brazil_power tests.test_alternative_sensor_pipeline -v`

`python -m unittest discover -s tests -v`

Live source probe in PR validates public endpoint availability and
per-source failure isolation; offline tests alone do not establish
the live dataset's continuity.

## Next steps

Build at least 14–30 comparable day/hour intervals for each
macroregion, with seasonal/weather/holiday adjustments and
source missingness. Regional demand alone can rise/fall due to
ordinary market behavior; test incremental discrimination against
competing explanations before using as a directional hypothesis signpost.
