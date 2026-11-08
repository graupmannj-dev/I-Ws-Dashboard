"""Offline regression tests for a bounded, licensed ADSB.lol aircraft adapter.

All positions/hex values are synthetic fixture data. Never write synthetic
flight records to a public AIBA evidence branch.
"""
import datetime as dt
import json
import unittest
from unittest.mock import patch

from dashboard.adsb_lol import (
    BASE, MAX_RESPONSE_AIRCRAFT, bounded_query, classify, collect_region,
    parse_response,
)
from dashboard.collect_layers import Collector

NOW = dt.datetime(2026,11,8,20,0,tzinfo=dt.timezone.utc)
CENTER=(30.4,-84.3,100)


def entry(hex_id,typ="",op="",flags=None,age=12,lat=30.45,lon=-84.25,flight="TEST01"):
    row={"hex":hex_id,"t":typ,"ownOp":op,"seen_pos":age,
         "lat":lat,"lon":lon,"flight":flight,"track":92.5}
    if flags is not None:
        row["dbFlags"]=flags
    return row


def envelope(*items,when=NOW):
    return {"now":when.timestamp(),"total":len(items),"ac":list(items)}


class ADSBLolTests(unittest.TestCase):
    def test_geographic_query_must_be_bounded_and_explicit(self):
        uri,region=bounded_query({"AIBA_ADSB_LAT":"30.4",
                                  "AIBA_ADSB_LON":"-84.3",
                                  "AIBA_ADSB_RADIUS_NM":"100"})
        self.assertEqual(uri,BASE+"/v2/point/30.40000/-84.30000/100")
        self.assertEqual(region,CENTER)
        for env in (
            {},
            {"AIBA_ADSB_LAT":"30","AIBA_ADSB_LON":"-84","AIBA_ADSB_RADIUS_NM":"251"},
            {"AIBA_ADSB_LAT":"NaN","AIBA_ADSB_LON":"-84"},
            {"AIBA_ADSB_LAT":"91","AIBA_ADSB_LON":"-84"},
            {"AIBA_ADSB_LAT":"30","AIBA_ADSB_LON":"-84","AIBA_ADSB_RADIUS_NM":"0"},
            {"AIBA_ADSB_LAT":"30","AIBA_ADSB_LON":"-84","AIBA_ADSB_RADIUS_NM":"1.5"},
        ):
            with self.subTest(env=env), self.assertRaises(ValueError):
                bounded_query(env)

    def test_positive_affiliation_evidence_not_negative_inference(self):
        self.assertEqual(classify(entry("abc123",typ="F16",flags=1))[:2],
                         ("military","combat"))
        self.assertEqual(classify(entry("abc124",typ="KC46",flags=1))[:2],
                         ("military","tanker"))
        self.assertEqual(classify(entry("abc125",typ="R135",flags=1))[:2],
                         ("military","surveillance"))
        self.assertEqual(classify(entry("abc126",typ="C130",flags=1))[:2],
                         ("military","transport"))
        self.assertEqual(classify(entry("abc127",typ="B738",flags=1))[:2],
                         ("military","unclassified"))
        # Passenger-type airframe alone is NOT proof of civilian affiliation.
        self.assertEqual(classify(entry("abc128",typ="B738",flags=0))[:2],
                         ("unknown","passenger"))
        self.assertEqual(classify(entry("abc129",typ="B738",op="Example Airlines"))[:2],
                         ("civilian","passenger"))
        self.assertEqual(classify(entry("abc130",typ="B77F",op="Cargo Express"))[:2],
                         ("civilian","cargo"))
        self.assertEqual(classify(entry("abc131",typ="P3",op="NASA Research"))[:2],
                         ("civilian","scientific"))
        self.assertEqual(classify(entry("abc132",typ="R44"))[:2],
                         ("unknown","helicopter"))
        self.assertEqual(classify(entry("abc133",typ="??"))[:2],
                         ("unknown","unclassified"))
        # ADS-B 'category' is wake/emitter category, NEVER passenger/combat.
        self.assertEqual(classify({**entry("abc134",typ=""),"category":"A5"})[:2],
                         ("unknown","unclassified"))

    def test_parse_retains_clocks_and_source_license(self):
        rows=parse_response(envelope(
            entry("a12345",typ="F16",flags=1,age=14),
            entry("a12346",typ="B738",op="Example Airlines",age=25),
            entry("a12347",typ="B77F",op="Example Cargo",age=0),
            entry("a12348",typ="SR22",age=19),
        ),CENTER,NOW)
        self.assertEqual(len(rows["records"]),4)
        m,c,cargo,unknown=rows["records"]
        self.assertEqual(m["affiliation"],"military")
        self.assertEqual(m["role_category"],"combat")
        self.assertEqual(c["affiliation"],"civilian")
        self.assertEqual(cargo["role_category"],"cargo")
        self.assertEqual(unknown["affiliation"],"unknown")
        self.assertEqual(m["observed_at"],(NOW-dt.timedelta(seconds=14)).isoformat())
        self.assertEqual(rows["coverage"],"regional_position_sample_not_global")
        self.assertTrue(all(x["license"]=="ODbL-1.0" for x in rows["records"]))
        self.assertNotIn("registration",m)
        self.assertNotIn("ownOp",m)
        self.assertIn("not evidence",m["detail"])

    def test_age_distance_and_bad_identity_rejection(self):
        payload=envelope(
            entry("def001",age=121),
            entry("def002",lat=45,lon=-84),
            entry("not-a-hex"),
            entry("def003",lat=None),
            entry("def004",age=8),
            entry("def004",age=6),
            entry("def005",age=float("nan")),
            entry("def006",flight="<script>alert(1)</script>")
        )
        result=parse_response(payload,CENTER,NOW)
        self.assertEqual(len(result["records"]),2)
        self.assertEqual(result["skipped"],6)
        self.assertEqual(result["records"][1]["title"],"Aircraft position")
        self.assertEqual(result["records"][0]["id"],"def004")

    def test_unrecognized_schema_or_bad_provider_clock_fails_not_zero(self):
        for payload in (
            {}, {"ac":None,"now":NOW.timestamp()},
            {"ac":[]},
            envelope(when=NOW-dt.timedelta(hours=1)),
            {"ac":[],"now":True},
            {"ac":[{}]*(MAX_RESPONSE_AIRCRAFT+1),"now":NOW.timestamp()},
        ):
            with self.subTest(payload=str(payload)[:70]),self.assertRaises(ValueError):
                parse_response(payload,CENTER,NOW)
        self.assertEqual(parse_response(envelope(),CENTER,NOW)["records"],[])

    def test_collector_integration_is_explicit_and_non_retrying(self):
        calls=[]
        env={"AIBA_AIRCRAFT_PROVIDER":"adsb_lol",
             "AIBA_ADSB_LAT":"30.4","AIBA_ADSB_LON":"-84.3",
             "AIBA_ADSB_RADIUS_NM":"100"}
        def fetch(uri,headers=None):
            calls.append((uri,headers))
            return json.dumps(envelope(entry("f00001",flags=1,typ="C130",age=15))).encode()
        value=collect_region(fetch,env,NOW)
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0][0].startswith("https://api.adsb.lol/v2/point/"))
        self.assertIn("User-Agent",calls[0][1])
        self.assertNotIn("Authorization",calls[0][1])
        self.assertEqual(value["records"][0]["role_category"],"transport")
        with patch.dict("os.environ",env,clear=True):
            with patch("dashboard.collect_layers.request",side_effect=fetch):
                c=Collector()
                c.update("aircraft",lambda:collect_region(fetch,env,NOW),
                         "https://www.adsb.lol/docs/open-data/api")
                data=c.payload["layers"]["aircraft"]
                self.assertEqual(data["status"],"snapshot")
                self.assertEqual(data["attribution"],"ADSB.lol contributors · ODbL 1.0")
                self.assertEqual(data["records"][0]["affiliation"],"military")

    def test_failure_never_retains_stale_positions_or_prints_internal_error(self):
        c=Collector()
        c.update("aircraft",lambda:[{"id":"not-real-old"}],"source")
        def fail():
            raise ValueError("Sensitive example token")
        c.update("aircraft",fail,"https://www.adsb.lol/docs/open-data/api")
        layer=c.payload["layers"]["aircraft"]
        self.assertEqual(layer["status"],"unavailable")
        self.assertEqual(layer["records"],[])
        self.assertNotIn("token",layer["message"])
        self.assertEqual(layer["source"],"https://www.adsb.lol/docs/open-data/api")

    def test_provider_exclusion_is_visible_as_partial(self):
        result=parse_response(envelope(entry("111111",age=10),
                                       entry("222222",age=500)),CENTER,NOW)
        c=Collector()
        c.update("aircraft",lambda:result,"https://www.adsb.lol/docs/open-data/api")
        layer=c.payload["layers"]["aircraft"]
        self.assertEqual(layer["status"],"partial")
        self.assertIn("excluded",layer["message"])
        self.assertEqual(len(layer["records"]),1)


if __name__=="__main__":
    unittest.main()
