"""Brazil ONS actual (verified) regional electricity load, half-hourly.

ONS (Operador Nacional do Sistema Elétrico), Brazil national electricity
operator. Public API described at dados.ons.org.br (CC BY). The ONS source
field din_referenciautc is explicitly UTC+0 by official data dictionary.
Values may be negative (reconciliation), never recode negative as missing.
This is measured electricity system *load*, NOT an outage or hostile activity.
"""
from __future__ import annotations

import datetime as dt
import math
from urllib.parse import parse_qs,urlsplit
from urllib.parse import urlencode

AREAS={"SECO":"Southeast/Central West","N":"North","NE":"Northeast","S":"South"}
BASE="https://apicarga.ons.org.br/prd/cargaverificada?"
DOC="https://dados.ons.org.br/dataset/carga-energia-verificada"
SCOPE=("Brazilian national system operator ONS verified half-hour load, "
       "four macroregions, previous two-day sample; no local facilities/outage attribution")
MAX_SAMPLES=700
UTC=dt.timezone.utc

def urls(checked):
    # Delay one calendar day to allow verified half-hour data to publish.
    # One bounded two-day period per load zone.
    target=(checked-dt.timedelta(days=2)).date()
    date=target.isoformat()
    return [BASE+urlencode({"dat_inicio":date,"dat_fim":date,"cod_areacarga":area})
            for area in AREAS]

def _utc(value):
    if not isinstance(value,str) or not value.strip():return None
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:return None
    # Official ONS dictionary states din_referenciautc is UTC+0.
    # Don't generalize this source-specific exception to other providers.
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)

def adapt(data,checked,url,entry):
    query=parse_qs(urlsplit(url).query)
    area=(query.get("cod_areacarga") or [None])[0]
    if area not in AREAS:raise ValueError("Unexpected ONS load area")
    records=data if isinstance(data,list) else (
        data.get("data") if isinstance(data,dict) else None)
    if not isinstance(records,list) or len(records)>MAX_SAMPLES:
        raise ValueError("ONS verified load JSON schema mismatch or bounded sample limit")
    if not records:raise ValueError("ONS verified load historical daily sample empty")
    valid=[]
    for source in records:
        if not isinstance(source,dict) or source.get("cod_areacarga")!=area:continue
        stamp=_utc(source.get("din_referenciautc"))
        if not stamp or stamp>checked+dt.timedelta(minutes=5):continue
        if checked-stamp>dt.timedelta(days=7):continue
        val=source.get("val_cargaglobal")
        if isinstance(val,bool) or not isinstance(val,(int,float,str)):continue
        try:metric=float(val)
        except ValueError:continue
        if not math.isfinite(metric) or abs(metric)>1000000:continue
        valid.append((stamp,metric))
    if not valid:raise ValueError("ONS load sample lacks valid recent area/UTC/measurement")
    # One latest strictly dated reading per macroregion per collection; the
    # historical half-hour raw sample is not rebranded as high-frequency live.
    stamp,value=max(valid,key=lambda x:x[0])
    at=stamp.isoformat().replace("+00:00","Z")
    row=entry("ons_br",area+":"+stamp.strftime("%Y%m%dT%H%M%SZ"),
        "Brazil ONS "+AREAS[area]+" verified half-hourly system load",
        DOC,checked,event_at=at,
        kind="verified_regional_electricity_load_context_not_outage",
        source_scope=SCOPE,
        geo={"key":"br-ons-loadarea:"+area,"kind":"official_electric_load_macroregion",
             "label":AREAS[area],"precision":"regional_grid_not_incident_site",
             "latitude":None,"longitude":None,"verified_iso":False},
        measurement={"name":"verified_half_hour_global_load",
                     "value":value,"unit":"MWmed",
                     "load_area_code":area,"load_area_name":AREAS[area],
                     "sample_interval_minutes":30,
                     "source_field":"val_cargaglobal",
                     "source_utc_field":"din_referenciautc",
                     "collected_history_day":query.get("dat_inicio",[None])[0],
                     "sampled_rows":len(valid),
                     "historical_verified_not_live":True,
                     "baseline_status":"not_calibrated",
                     "not_outage_or_attribution":True})
    return [row] if row else []
