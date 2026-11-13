"""Source/entity matching must not collapse reporter origin into event location."""
import datetime as dt
import unittest

from behavioral_event_resolution import (
    SCHEMA,build,match_pair,reported_site,report_document,
)
from behavioral_registry import normalize

NOW=dt.datetime(2026,11,13,13,0,tzinfo=dt.timezone.utc)


def row(ident,title,*,provider="agency",family="commercial_media",offset=0,
        event_site=None,reporting_origin=None,url=None,root=None,geo_key=None):
    obs=NOW+dt.timedelta(minutes=offset)
    return {
        "id":ident,"provider":provider,"source_family":family,
        "information_root":root or provider+":"+ident,
        "first_observed_at":obs.isoformat().replace("+00:00","Z"),
        "source_published_at":obs.isoformat().replace("+00:00","Z"),
        "event_at":obs.isoformat().replace("+00:00","Z"),
        "title":title,"source_url":url or f"https://{provider}.example.org/story/{ident}",
        "geography":{"key":geo_key,"label":geo_key,
                     "kind":"source_declared_region"},
        "reported_event_location":event_site,"reporting_origin":reporting_origin,
        "alert_eligible":False,
    }


def location(lat,lon):
    return {"role":"reported_event_site","basis":"source_declared",
            "lat":lat,"lon":lon}


TITLE1="Russian missiles struck Kyiv energy substation overnight"
TITLE2="Kyiv energy substation struck overnight by Russian missiles"


class ReportEventTests(unittest.TestCase):
    def test_new_york_publication_and_kyiv_ground_report_same_event_possible(self):
        a=row("a",TITLE1,provider="newyorkdesk",
              reporting_origin="New York, US",geo_key="country:US")
        b=row("b",TITLE2,provider="kyivreporter",
              reporting_origin="Kyiv, Ukraine",geo_key="country:UA",offset=12)
        match=match_pair(a,b)
        self.assertIsNotNone(match)
        self.assertEqual(match["status"],"possible_same_event_unreviewed")
        self.assertEqual(match["match_basis"],"similar_content_and_time_event_site_unverified")
        self.assertFalse(match["reported_event_site_comparison_available"])
        self.assertFalse(match["reporting_origin_used_as_event_site"])
        self.assertFalse(match["independent_corroboration_established"])
        self.assertTrue(match["warning_level_change"] is False)

    def test_explicit_close_reported_event_sites_strongly_support_candidate(self):
        a=row("a",TITLE1,provider="outlet-a",event_site=location(50.450,30.520))
        b=row("b",TITLE2,provider="outlet-b",event_site=location(50.460,30.560),offset=15)
        result=match_pair(a,b)
        self.assertEqual(result["status"],"possible_same_event_unreviewed")
        self.assertLess(result["reported_event_site_separation_km"],4)
        self.assertEqual(result["match_basis"],"similar_content_and_nearby_reported_event_sites")

    def test_distant_source_declared_event_sites_keep_related_not_duplicate(self):
        a=row("a",TITLE1,event_site=location(50.45,30.52))
        b=row("b",TITLE2,event_site=location(46.48,30.73),offset=10,
              provider="other")
        result=match_pair(a,b)
        self.assertEqual(result["status"],"related_reporting_unreviewed")
        self.assertGreater(result["reported_event_site_separation_km"],150)
        self.assertFalse(result["independent_corroboration_established"])

    def test_publisher_new_york_coordinates_never_used_for_proximity(self):
        a=row("a",TITLE1,reporting_origin="New York lat 40.7 lon -74",
              event_site=location(50.45,30.52))
        b=row("b",TITLE2,provider="other",reporting_origin="Kyiv office")
        self.assertEqual(match_pair(a,b)["status"],"possible_same_event_unreviewed")
        self.assertIsNone(match_pair(a,b)["reported_event_site_separation_km"])

    def test_nearby_points_but_unrelated_content_do_not_match(self):
        a=row("a","Airport baggage conveyor mechanical maintenance",
              event_site=location(50.45,30.52))
        b=row("b","Civilian hospital oxygen supply delivery delayed",
              provider="other",event_site=location(50.46,30.53))
        self.assertIsNone(match_pair(a,b))

    def test_generic_ukraine_war_theme_does_not_merge_incidents(self):
        a=row("a","Ukraine war updates",provider="press-a")
        b=row("b","Ukraine war briefing",provider="press-b")
        self.assertIsNone(match_pair(a,b))

    def test_different_event_times_do_not_merge_unrelated_dates(self):
        a=row("a",TITLE1,provider="press-a")
        b=row("b",TITLE2,provider="press-b",offset=73*60)
        self.assertIsNone(match_pair(a,b))

    def test_shared_notice_document_is_grouped_not_independent_sensors(self):
        url="https://niord.dma.dk/#/message/123456"
        rows=[row(str(i),"Denmark Kattegat Hevring firing exercises",
                  provider="niord",family="maritime_restriction",
                  root=f"niord:notice:{i}",url=url,offset=i) for i in range(3)]
        result=build({x["id"]:x for x in rows})
        self.assertEqual(result["same_document_group_count_total"],1)
        self.assertEqual(result["cross_document_relation_count_total"],0)
        self.assertEqual(result["candidate_groups"][0]["report_count_total"],3)
        self.assertEqual(result["candidate_groups"][0]["status"],"shared_source_document_unreviewed")
        self.assertFalse(result["candidate_groups"][0]["independent_corroboration_established"])
        self.assertFalse(result["candidate_groups"][0]["warning_level_change"])
        self.assertEqual(result["automatic_alerts_created"],0)

    def test_homepage_not_a_document_specific_identity(self):
        x=row("a",TITLE1,url="https://ioda.inetintel.cc.gatech.edu/")
        y=row("b",TITLE2,url="https://ioda.inetintel.cc.gatech.edu/",
              provider="other")
        self.assertIsNone(report_document(x))
        self.assertEqual(build({"a":x,"b":y})["same_document_group_count_total"],0)

    def test_same_information_root_is_not_confirmed_independence(self):
        a=row("a",TITLE1,root="upstream:single-wire",provider="outlet-a")
        b=row("b",TITLE2,root="upstream:single-wire",provider="outlet-b")
        result=match_pair(a,b)
        self.assertTrue(result["shared_information_root"])
        self.assertFalse(result["independent_corroboration_established"])

    def test_record_schema_retains_explicit_site_separately_from_origin(self):
        upstream={
            "id":"src-1","provider":"commercial","source_url":"https://news.example.org/specific/123",
            "collected_at":"2026-11-13T12:00:00Z",
            "source_published_at":"2026-11-13T11:58:00Z",
            "title":TITLE1,
            "reporting_origin":"New York",
            "reported_event_location":location(50.45,30.52),
        }
        item,err=normalize("commercial",upstream,NOW)
        self.assertIsNone(err)
        self.assertEqual(item["reporting_origin"],"New York")
        self.assertEqual(item["reported_event_location"]["role"],"reported_event_site")
        self.assertEqual(item["reported_event_location"]["lat"],50.45)
        self.assertIsNone(item["geography"]["key"])
        self.assertTrue(item["alert_eligible"] is False)

    def test_report_origin_mislabeled_as_event_site_rejected(self):
        upstream={
            "id":"src-1","provider":"commercial","source_url":"https://news.example.org/specific/123",
            "collected_at":"2026-11-13T12:00:00Z","title":TITLE1,
            "reported_event_location":{"role":"publisher_office",
                                        "basis":"source_declared","lat":40.7,"lon":-74.0},
        }
        item,err=normalize("commercial",upstream,NOW)
        self.assertIsNone(item)
        self.assertEqual(err,"unverified_or_invalid_reported_event_site")

    def test_candidate_reports_are_not_geocoded_for_public_map(self):
        a=row("a",TITLE1,provider="press-a",event_site=location(50.45,30.52))
        b=row("b",TITLE2,provider="press-b",event_site=location(50.46,30.55))
        result=build({"a":a,"b":b})
        self.assertEqual(result["schema"],SCHEMA)
        self.assertEqual(result["possible_same_event_count_total"],1)
        group=result["candidate_groups"][0]
        self.assertEqual(group["status"],"possible_same_event_unreviewed")
        for x in group["source_reports"]:
            self.assertNotIn("reported_event_location",x)
        self.assertIsNone(result["forecast_probability"])

if __name__=="__main__":
    unittest.main()
