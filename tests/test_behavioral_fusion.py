"""As-of, causal-dependence, geolocation, source novelty and no-warning gates."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from behavioral_fusion import build, candidate_observation, converge, recently_observed
from behavioral_registry import SCHEMA as RSCHEMA, iso
from ops_pipeline import write_json

UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,10,22,0,tzinfo=UTC)


def rec(ident,provider,family,key="country:ZZ",new_at=NOW,published=None,root=None):
    return {
        "id":ident,"provider":provider,"source_family":family,
        "information_root":root or f"{provider}:{ident}",
        "geography":{"key":key,"kind":"country_code" if key else "unlocated",
                     "label":key,"precision":"provider_reported_country" if key else
                     "no_source_verified_geography"},
        "first_observed_at":iso(new_at),
        "source_published_at":iso(published) if published else iso(new_at),
        "source_url":f"https://{provider}.example.org/source/{ident}",
        "title":f"{provider} reported observation",
        "evidence_class":"network_measurement" if family=="internet_reachability" else
                         "official_notice" if family in ("maritime_restriction","protective_notice")
                         else "media_mention",
        "alert_eligible":False,
        "registry_novelty":"newly_observed",
    }


def fixture(state,rows,now=NOW,baseline=False):
    write_json(state/"latest"/"behavioral_registry.json",{
        "schema":RSCHEMA,"generated_at":iso(now),"records":rows,
        "record_count":len(rows),"first_registry_baseline":baseline,
        "source_health":{x["provider"]:{"status":"current"} for x in rows}})
    write_json(state/"history"/"behavioral_registry"/(now.strftime("%Y%m%dT%H%M%SZ")+".json"),{
        "schema":RSCHEMA,"generated_at":iso(now),
        "first_registry_baseline":baseline,
        "new_records":[] if baseline else rows})


class FusionTests(unittest.TestCase):
    def test_strict_geo_and_independent_family_create_unreviewed_only(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            rows=[rec("a","ioda","internet_reachability"),
                  rec("b","official","protective_notice")]
            fixture(state,rows)
            r=build(state,clock=lambda:NOW,run_id="a")
            self.assertEqual(r["review_groups_count_total"],1)
            self.assertEqual(r["new_single_source_count_total"],2)
            group=r["review_groups"][0]
            self.assertEqual(group["source_family_count"],2)
            self.assertEqual(group["status"],"cross_family_cooccurrence_unreviewed")
            self.assertFalse(group["warning_level_change"])
            self.assertEqual(r["automated_severity_changes"],0)
            self.assertEqual(r["approved_warning_count"],0)
            self.assertIsNone(r["forecast_probability"])

    def test_media_and_market_do_not_confirm_behaviors(self):
        good=rec("a","ioda","internet_reachability")
        press=rec("b","news","commercial_media")
        market=rec("c","market","market_expectation")
        a,total=converge({x["id"]:x for x in (good,press,market)},
                         {"a","b","c"},NOW)
        self.assertEqual(total,0)
        self.assertEqual(a,[])

    def test_maritime_same_source_family_not_independent_confirmation(self):
        a=rec("a","nga","maritime_restriction","navarea:X")
        b=rec("b","amsa","maritime_restriction","navarea:X")
        groups,total=converge({"a":a,"b":b},{"a","b"},NOW)
        self.assertEqual(total,0)
        self.assertEqual(groups,[])

    def test_cross_family_different_geography_not_miscombined(self):
        a=rec("a","ioda","internet_reachability","country:ZZ")
        b=rec("b","official","protective_notice","country:AA")
        groups,total=converge({"a":a,"b":b},{"a","b"},NOW)
        self.assertEqual(total,0)

    def test_unlocated_source_remains_single_source_not_geo_match(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            a=rec("a","ioda","internet_reachability",key=None)
            b=rec("b","official","protective_notice",key=None)
            fixture(state,[a,b])
            r=build(state,clock=lambda:NOW,run_id="x")
            self.assertEqual(r["review_groups_count_total"],0)
            self.assertEqual(len(r["new_single_source_leads"]),2)
            self.assertTrue(all(x["requires_geolocation"] for x in r["new_single_source_leads"]))

    def test_earlier_observations_support_later_new_but_not_replayed_warning(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            prior=NOW-dt.timedelta(hours=4)
            a=rec("a","ioda","internet_reachability",new_at=prior)
            fixture(state,[a],now=prior)
            b=rec("b","official","protective_notice",new_at=NOW)
            fixture(state,[b],now=NOW)
            recent,_=recently_observed(state,NOW)
            self.assertEqual(len(recent),2)
            groups,total=converge(recent,{"b"},NOW)
            self.assertEqual(total,1)
            groups,total=converge(recent,set(),NOW)
            self.assertEqual(total,0,"Old evidence must not trigger recurring fusion")

    def test_unobserved_publication_time_is_not_backdated(self):
        a=rec("a","ioda","internet_reachability")
        a["source_published_at"]=None
        ok,reason=candidate_observation(a,NOW)
        self.assertTrue(ok)
        self.assertIsNone(reason)
        a["source_published_at"]=iso(NOW-dt.timedelta(days=12))
        ok,reason=candidate_observation(a,NOW)
        self.assertFalse(ok)
        self.assertEqual(reason,"old_source_publication")

    def test_first_baseline_never_promotes_observations(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            fixture(state,[rec("a","ioda","internet_reachability"),
                           rec("b","official","protective_notice")],baseline=True)
            r=build(state,clock=lambda:NOW,run_id="base")
            self.assertEqual(r["review_groups_count_total"],0)
            self.assertEqual(r["approved_warning_count"],0)

    def test_stale_registry_must_not_fuse(self):
        with tempfile.TemporaryDirectory() as p:
            state=Path(p)
            fixture(state,[rec("a","ioda","internet_reachability")],
                    now=NOW-dt.timedelta(hours=2))
            with self.assertRaisesRegex(ValueError,"fresh bounded collection"):
                build(state,clock=lambda:NOW,run_id="stale")

    def test_future_provenance_cannot_create_advance_warning(self):
        row=rec("a","ioda","internet_reachability",
                new_at=NOW+dt.timedelta(minutes=1))
        allowed,reason=candidate_observation(row,NOW)
        self.assertFalse(allowed)
        self.assertEqual(reason,"outside_asof_window")


if __name__=="__main__":
    unittest.main()
