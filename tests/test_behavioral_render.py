"""Source-timed publication must show stale states and escape untrusted content."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from behavioral_render import render
from behavioral_fusion import SCHEMA
from behavioral_registry import iso
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,10,22,0,tzinfo=UTC)


class BehavioralPanelTests(unittest.TestCase):
    def test_unavailable_page_never_claims_current_coverage(self):
        with tempfile.TemporaryDirectory() as p:
            root=Path(p)
            v=render(root/"state",root/"site",clock=lambda:NOW)
            html=(root/"site"/"behavior"/"index.html").read_text()
            self.assertFalse(v["site_snapshot_fresh"])
            self.assertIn("NO RECENT VALID SOURCE SNAPSHOT",html)
            self.assertIn("not collected",html)
            self.assertIn("No automatic",html)

    def test_fresh_exposes_source_link_but_never_html_injection(self):
        with tempfile.TemporaryDirectory() as p:
            root=Path(p)
            source={
                "schema":SCHEMA,"generated_at":iso(NOW),
                "collection_coverage":{"ioda":{
                    "status":"current","snapshot_at":iso(NOW),
                    "source_scope":"IODA country events first-page bounded"}},
                "review_groups":[{
                    "id":"g1","geography":{"key":"country:ZZ","label":"ZZ <script>"},
                    "source_family_count":2,"status":"cross_family_cooccurrence_unreviewed",
                    "assessment":"<img src=x onerror=alert(1)>",
                    "source_links":[{"provider":"ioda","family":"internet_reachability",
                                     "url":"https://ioda.example.org/event",
                                     "first_observed_at":iso(NOW),
                                     "published_at":None}]}],
                "new_single_source_leads":[{
                    "observation_id":"obs1","source_url":"javascript:alert(1)",
                    "title":"<bad>source</bad>",
                    "source_family":"maritime_restriction",
                    "first_observed_at":iso(NOW),
                    "geography":{"key":None,"label":None},
                }],
            }
            write_json(root/"state"/"latest"/"behavioral_fusion.json",source)
            v=render(root/"state",root/"site",clock=lambda:NOW)
            text=(root/"site"/"behavior"/"index.html").read_text()
            self.assertTrue(v["site_snapshot_fresh"])
            self.assertIn("&lt;script&gt;",text)
            self.assertNotIn("<script>",text)
            self.assertNotIn("<img src=x",text)
            self.assertNotIn('href="javascript:',text)
            self.assertIn('href="https://ioda.example.org/event"',text)
            self.assertIn("Location not verified",text)

    def test_aged_source_presented_as_historical_only(self):
        with tempfile.TemporaryDirectory() as p:
            root=Path(p)
            old=NOW-dt.timedelta(hours=8)
            write_json(root/"state"/"latest"/"behavioral_fusion.json",{
                "schema":SCHEMA,"generated_at":iso(old),
                "review_groups":[],"new_single_source_leads":[],
                "collection_coverage":{},
            })
            v=render(root/"state",root/"site",clock=lambda:NOW)
            self.assertFalse(v["site_snapshot_fresh"])
            self.assertEqual(v["site_source_age_hours"],8)


if __name__=="__main__":
    unittest.main()
