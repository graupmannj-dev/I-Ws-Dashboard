#!/usr/bin/env python3
"""One ONS day and Singapore MPA history: read-only schema/clock probe."""
import datetime as dt
import json
from alternative_sensor_pipeline import json_get
from cairn_metric_history_backfill import ons_urls,adapt_ons_day,adapt_sg,SG_URL

UTC=dt.timezone.utc
now=dt.datetime.now(UTC)
area,day,url=next(ons_urls(now))
status={}
for name,fn in (
    ("ons_br_history",lambda:adapt_ons_day(json_get(url),area,day,url,now)),
    ("sg_mpa_history",lambda:adapt_sg(json_get(SG_URL),SG_URL,now)),
):
    try:
        rows=fn()
        status[name]={"ok":True,"records":len(rows),
                      "source_clocked":True,"first_id":rows[0]["id"]}
    except Exception as e:
        status[name]={"ok":False,"error":type(e).__name__+": "+str(e)[:180]}
print(json.dumps(status,indent=2))
if not all(x["ok"] for x in status.values()):
    raise SystemExit("Official historical source probe invalid or inaccessible")
