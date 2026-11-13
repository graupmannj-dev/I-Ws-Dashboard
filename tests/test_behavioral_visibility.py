"""Show actual observed-source inventory without auto-promoting cross-family warnings."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from behavioral_fusion import discovery_visibility, build
from behavioral_registry import SCHEMA as REGISTRY_SCHEMA, iso
from dashboard.behavioral_embed import embed
from ops_pipeline import write_json
from tests.test_behavioral_fusion import NOW,rec

def complete_visibility(records, sample_count):
    return {
        "schema":"aiba.behavioral-discovery-visibility.v1",
        "latest_registry_record_count":len(records),
        "latest_registry_newly_observed_count":0,
        "recent_unique_record_count_72h":len(records),
        "recent_unlocated_count_72h":sum(x["geography"]["key"] is None for x in records),
        "latest_unlocated_record_count":sum(x["geography"]["key"] is None for x in records),
        "shared_exact_geography_keys_across_behavior_families":0,
        "exact_geography_match_required_for_cross_family":True,
        "new_this_collection_required_for_cross_family_nomination":True,
        "latest_initial_baseline":False,
        "recent_observations_sampled":sample_count,
        "new_or_collocated_not_same_as_verified_threat":True,
        "source_coverage_is_globally_complete":False,
    }

class SourceVisibilityTests(unittest.TestCase):
    def test_existing_records_still_visible_from_recent_history(self):
        a=rec("a","ioda","internet_reachability","country:ZZ")
        b=rec("b","amsa","maritime_restriction","navarea:X")
        for x in (a,b):x["registry_novelty"]="existing"
        registry={"records":[a,b]}
        vis,sample=discovery_visibility({x["id"]:x for x in (a,b)},registry)
        self.assertEqual(vis["latest_registry_newly_observed_count"],0)
        self.assertEqual(vis["recent_unique_record_count_72h"],2)
        self.assertEqual(vis["shared_exact_geography_keys_across_behavior_families"],0)
        self.assertEqual(len(sample),2)
        self.assertTrue(all(r["status"]=="recent_source_observation_unreviewed" for r in sample))
        self.assertFalse(vis["source_coverage_is_globally_complete"])

    def test_matching_key_diagnostic_not_a_cross_family_warning(self):
        a=rec("a","ioda","internet_reachability","country:ZZ")
        b=rec("b","official","protective_notice","country:ZZ")
        for x in (a,b):x["registry_novelty"]="existing"
        vis,sample=discovery_visibility({"a":a,"b":b},{"records":[a,b]})
        self.assertEqual(vis["shared_exact_geography_keys_across_behavior_families"],1)
        self.assertEqual(vis["latest_registry_newly_observed_count"],0)
        self.assertEqual(len(sample),2)
        self.assertNotIn("approved_warning",json.dumps(vis))

    def test_unlocated_records_counted_but_not_geocoded(self):
        a=rec("a","official","protective_notice",key=None)
        a["registry_novelty"]="existing"
        vis,sample=discovery_visibility({"a":a},{"records":[a]})
        self.assertEqual(vis["recent_unlocated_count_72h"],1)
        self.assertEqual(vis["latest_unlocated_record_count"],1)
        self.assertIsNone(sample[0]["geography"]["key"])
        self.assertTrue(sample[0]["requires_geolocation"])

    def test_historical_sample_is_bounded_and_balanced(self):
        records=[]
        for i in range(50):
            family="protective_notice" if i<45 else "internet_reachability"
            provider="official" if i<45 else "ioda"
            r=rec(f"record-{i}",provider,family,
                  new_at=NOW-dt.timedelta(minutes=i))
            r["registry_novelty"]="existing"
            records.append(r)
        vis,sample=discovery_visibility({r["id"]:r for r in records},
                                         {"records":records})
        self.assertEqual(vis["recent_unique_record_count_72h"],50)
        self.assertLessEqual(len(sample),24)
        counts={f:sum(x["source_family"]==f for x in sample)
                for f in ("protective_notice","internet_reachability")}
        self.assertEqual(counts,{"protective_notice":8,"internet_reachability":5})
        self.assertEqual(vis["recent_observations_sampled"],13)

    def test_first_baseline_not_used_as_recent_signal_shortlist(self):
        a=rec("a","ioda","internet_reachability")
        vis,sample=discovery_visibility({"a":a},{"records":[a]},initial_baseline=True)
        self.assertTrue(vis["latest_initial_baseline"])
        self.assertEqual(vis["recent_observations_sampled"],0)
        self.assertEqual(sample,[])

    def test_live_fusion_preserves_72hour_old_observations_not_new_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            old=NOW-dt.timedelta(hours=4)
            a=rec("a","ioda","internet_reachability","country:ZZ",new_at=old)
            old_registry={"schema":REGISTRY_SCHEMA,"generated_at":iso(old),
                          "first_registry_baseline":False,"new_records":[a]}
            write_json(path/"history"/"behavioral_registry"/"past.json",old_registry)
            a["registry_novelty"]="existing"
            new_reg={"schema":REGISTRY_SCHEMA,"generated_at":iso(NOW),
                     "records":[a],"record_count":1,
                     "first_registry_baseline":False,"source_health":{
                         "ioda":{"status":"current","source_scope":"bounded country events",
                                 "missingness":"provider_bounded_not_exhaustive"}}}
            write_json(path/"latest"/"behavioral_registry.json",new_reg)
            result=build(path,clock=lambda:NOW,write=False)
            self.assertEqual(result["new_single_source_count_total"],0)
            self.assertEqual(result["review_groups_count_total"],0)
            self.assertEqual(result["discovery_visibility"]["recent_unique_record_count_72h"],1)
            self.assertEqual(result["recent_source_observations"][0]["status"],
                             "recent_source_observation_unreviewed")
            site=path/"site"
            (site/"behavior").mkdir(parents=True)
            write_json(site/"behavior"/"behavioral_fusion.json",result)
            published=embed(site)
            self.assertEqual(published["status"],"read_only_shadow_evidence")
            self.assertEqual(published["discovery_visibility"]["recent_unique_record_count_72h"],1)
            self.assertEqual(len(published["recent_source_observations"]),1)
            self.assertFalse(published["map_coordinates_inferred"])

    def test_embedded_history_rejects_fake_warning_or_bad_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp)
            (site/"behavior").mkdir()
            a=rec("a","ioda","internet_reachability")
            vis,sample=discovery_visibility({"a":a},{"records":[a]})
            base={
                "schema":"aiba.behavioral-convergence-shadow.v1",
                "generated_at":iso(NOW),
                "review_groups":[],"review_groups_count_total":0,
                "new_single_source_leads":[],"new_single_source_count_total":0,
                "collection_coverage":{},
                "forecast_probability":None,"prediction_horizon":None,
                "approved_warning_count":0,"automated_severity_changes":0,
                "discovery_visibility":vis,"recent_source_observations":sample
            }
            base["recent_source_observations"][0]["title"]="<img src=x onerror=alert(1)>"
            write_json(site/"behavior"/"behavioral_fusion.json",base)
            clean=embed(site)
            self.assertEqual(clean["recent_source_observations"][0]["title"],
                             "<img src=x onerror=alert(1)>")
            self.assertFalse(clean["map_coordinates_inferred"])
            base["recent_source_observations"][0]["status"]="approved_warning"
            write_json(site/"behavior"/"behavioral_fusion.json",base)
            self.assertEqual(embed(site)["status"],"unavailable")

if __name__=="__main__":
    unittest.main()
