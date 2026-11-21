"""Non-Western national publishers: bounded evidence, issuer/relay distinction, health."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest

from alternative_sensor_pipeline import collect, entry, urls
from cairn_national_sensors import (
    FEEDS, MODES, RSS_MODES, adapter_for, adapt_quake, adapt_rss, xml_parse,
)
from ops_pipeline import load_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,20,17,0,tzinfo=UTC)
STAMP="2026-11-20T16:30:00Z"
DATE="Fri, 20 Nov 2026 16:30:00 +0000"


def rss(mode,title="Synthetic heavy-rain authority warning",issued=DATE,
        link=None, guid="national-warning-001"):
    link=link or FEEDS[mode]
    raw=(
      '<rss version="2.0"><channel><title>Government warnings</title>'
      '<item><guid>'+guid+'</guid><title>'+title+'</title>'
      '<link>'+link+'</link><pubDate>'+issued+'</pubDate></item>'
      '</channel></rss>'
    )
    return xml_parse(raw.encode("utf-8"))


def quake_event(moment=STAMP):
    return {"Infogempa":{"gempa":[{
        "DateTime":moment,"Magnitude":"5.3","Coordinates":"-5.54,126.32",
        "Kedalaman":"33 km","Wilayah":"Synthetic Banda Sea",
        "Potensi":"Tidak berpotensi tsunami"
    }]}}


class NationalSourcesTests(unittest.TestCase):
    def test_declared_sources_have_nonwestern_issuer_and_bounded_scope(self):
        self.assertEqual(set(MODES),{"bmkg_quake","bmkg_nowcast","inmet_br","imd_in","saws_za"})
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assertTrue(FEEDS[mode].startswith("https://"))
                self.assertEqual(urls(mode,NOW),[FEEDS[mode]])

    def test_bmkg_magnitude_and_time_not_invented_publisher_update(self):
        rows=adapt_quake(quake_event(),NOW,FEEDS["bmkg_quake"],entry)
        self.assertEqual(len(rows),1)
        x=rows[0]
        self.assertEqual(x["event_at"],STAMP)
        self.assertIsNone(x["published_at"])
        self.assertEqual(x["source_measurement"]["value"],5.3)
        self.assertEqual(x["source_measurement"]["depth_km"],33)
        self.assertTrue(x["source_measurement"]["possible_same_physical_event_as_usgs"])
        self.assertEqual(x["geography"]["latitude"],-5.54)
        self.assertEqual(x["geography"]["longitude"],126.32)
        self.assertIsNone(x["geography"]["key"])
        self.assertIn("not_conflict_attribution",x["claim_level"])

    def test_bmkg_invalid_future_coordinates_or_schema_rejected(self):
        with self.assertRaisesRegex(ValueError,"schema"):
            adapt_quake({"Infogempa":{"gempa":{}}},NOW,FEEDS["bmkg_quake"],entry)
        with self.assertRaisesRegex(ValueError,"validated"):
            adapt_quake(quake_event("2026-11-25T16:30:00Z"),NOW,FEEDS["bmkg_quake"],entry)
        bad=quake_event()
        bad["Infogempa"]["gempa"][0]["Coordinates"]="200,300"
        with self.assertRaisesRegex(ValueError,"validated"):
            adapt_quake(bad,NOW,FEEDS["bmkg_quake"],entry)

    def test_national_alert_timestamp_source_identity_and_relay(self):
        for mode in RSS_MODES:
            with self.subTest(mode=mode):
                a=adapt_rss(mode,rss(mode),NOW,FEEDS[mode],entry)
                b=adapt_rss(mode,rss(mode),NOW,FEEDS[mode],entry)
                self.assertEqual(len(a),1)
                self.assertEqual(a,b)
                self.assertTrue(a[0]["id"].startswith(mode+":"))
                self.assertEqual(a[0]["published_at"],STAMP)
                self.assertIsNone(a[0]["event_at"])
                self.assertIn("not_conflict_attribution",a[0]["claim_level"])
                self.assertEqual(a[0]["source_measurement"]["wmo_relay_not_independent_observer"],
                                 mode in ("imd_in","saws_za"))

    def test_rss_malformed_stale_untrusted_links_and_empty_feed(self):
        with self.assertRaisesRegex(ValueError,"prohibited"):
            xml_parse(b'<!DOCTYPE x [<!ENTITY xx "hack">]><rss><channel/></rss>')
        with self.assertRaisesRegex(ValueError,"Expected RSS or Atom"):
            adapt_rss("inmet_br",xml_parse(b"<html></html>"),NOW,FEEDS["inmet_br"],entry)
        mode="inmet_br"
        doc=rss(mode,link="https://malicious.example/phishing")
        row=adapt_rss(mode,doc,NOW,FEEDS[mode],entry)[0]
        self.assertEqual(row["source_url"],FEEDS[mode])
        old=rss(mode,issued="Fri, 06 Nov 2026 16:30:00 GMT")
        self.assertEqual(adapt_rss(mode,old,NOW,FEEDS[mode],entry),[])
        empty=xml_parse(b"<rss><channel><title>Nothing current</title></channel></rss>")
        self.assertEqual(adapt_rss(mode,empty,NOW,FEEDS[mode],entry),[])
        invalid=rss(mode,issued="no timezone")
        with self.assertRaisesRegex(ValueError,"valid timestamped"):
            adapt_rss(mode,invalid,NOW,FEEDS[mode],entry)

    def test_atom_supported_without_claiming_unknown_incident_time(self):
        raw=xml_parse((
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><title>Official storm warning</title><id>urn:test:alert</id>'
            '<updated>2026-11-20T16:30:00Z</updated></entry></feed>').encode())
        rows=adapt_rss("saws_za",raw,NOW,FEEDS["saws_za"],entry)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["published_at"],STAMP)

    def test_provider_failed_health_retains_old_and_never_zero(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            def fake(url):
                if "gempaterkini.json" in url:return quake_event()
                return rss("bmkg_nowcast")
            first=collect(path,clock=lambda:NOW,fetcher=fake,
                          selected=("bmkg_quake","bmkg_nowcast"))
            self.assertEqual(first["bmkg_quake"]["records"],1)
            self.assertEqual(first["bmkg_nowcast"]["status"],"partial")
            earlier=load_json(path/"latest"/"bmkg_nowcast.json")
            def outage(url):
                if "nowcast" in url:raise TimeoutError("National feed temporarily offline")
                return quake_event()
            next=collect(path,clock=lambda:NOW+dt.timedelta(hours=1),
                         fetcher=outage,selected=("bmkg_quake","bmkg_nowcast"))
            self.assertEqual(next["bmkg_quake"]["status"],"partial")
            self.assertEqual(next["bmkg_nowcast"]["status"],"unavailable")
            self.assertIsNone(next["bmkg_nowcast"]["records"])
            self.assertEqual(next["bmkg_nowcast"]["missingness"],"not_measured_not_zero")
            self.assertEqual(load_json(path/"latest"/"bmkg_nowcast.json"),earlier)


if __name__=="__main__":
    unittest.main()
