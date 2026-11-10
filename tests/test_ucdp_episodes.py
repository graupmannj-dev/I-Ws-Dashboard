"""UCDP episode construct, uncertainty quarantine and no-actor-match replay tests."""
import csv
from collections import Counter,defaultdict
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ucdp_episode_labels import (
    UCDP_SHA256, RELEASE_END, read_candidate_csv, propose_episodes,
)
from scripts.ucdp_episode_review_queue import build_queue


def source_stub():
    key=("Ukraine","770")
    return {
        "source_sha256":"synthetic_fixture",
        "seen_unique_event_ids":10,
        "dyad_info":{key:("Government of Ukraine - Test Group", "100")},
        "all_dyads":{key},
        "daily_best_deaths":defaultdict(Counter),
        "daily_event_ids":defaultdict(lambda: defaultdict(list)),
        "uncertain_dates":defaultdict(set),
        "country_uncertain_dates":defaultdict(set),
        "source_counts":{},
    }


class EpisodeLabelTests(unittest.TestCase):
    def test_quiet_restart_after_verified_28_day_quiet_only(self):
        src=source_stub()
        key=("Ukraine","770")
        t=dt.date(2026,7,11)
        src["daily_best_deaths"][key][t]=3
        src["daily_event_ids"][key][t]=["U-1"]
        episodes,report=propose_episodes(src,t,t)
        self.assertEqual(len(episodes),1)
        self.assertEqual(episodes[0]["type"],"quiet_restart")
        self.assertEqual(episodes[0]["label_status"],"automated_candidate_unadjudicated")
        self.assertEqual(episodes[0]["source_event_ids"],["U-1"])
        # An uncertain event during the 28-day reference must prohibit
        # pretending the series was quiet.
        src["uncertain_dates"][key].add(t-dt.timedelta(days=3))
        episodes,_=propose_episodes(src,t,t)
        self.assertEqual(episodes,[])

    def test_escalation_surge_is_separate_from_continuing_low_level_violence(self):
        src=source_stub()
        key=("Ukraine","770")
        t=dt.date(2026,7,11)
        for d in range(34,6,-1):
            src["daily_best_deaths"][key][t-dt.timedelta(days=d)]=1
        for d in range(6,0,-1):
            src["daily_best_deaths"][key][t-dt.timedelta(days=d)]=2
        src["daily_best_deaths"][key][t]=20
        src["daily_event_ids"][key][t]=["U-2"]
        episodes,_=propose_episodes(src,t,t)
        self.assertEqual([e["type"] for e in episodes],["intensification"])
        self.assertEqual(episodes[0]["best_fatalities_7d"],32)
        self.assertEqual(episodes[0]["baseline_best_fatalities_28d"],28)
        src["country_uncertain_dates"]["Ukraine"].add(t-dt.timedelta(days=8))
        censored,_=propose_episodes(src,t,t)
        self.assertEqual(censored,[])

    def test_continuing_high_severity_does_not_invent_a_new_escalation(self):
        src=source_stub()
        key=("Ukraine","770")
        t=dt.date(2026,7,11)
        for d in range(34,6,-1):
            src["daily_best_deaths"][key][t-dt.timedelta(days=d)]=1
        for d in range(6,-1,-1):
            src["daily_best_deaths"][key][t-dt.timedelta(days=d)]=7
        src["daily_event_ids"][key][t]=["U-3"]
        episodes,_=propose_episodes(src,t,t)
        self.assertEqual(episodes,[], "Severity already above threshold on t-1 is not a new crossing")

    def test_repeated_escalation_crossings_suppressed_by_cooldown(self):
        src=source_stub()
        key=("Ukraine","770")
        t=dt.date(2026,7,11)
        for n in range(70):
            day=t-dt.timedelta(days=40)+dt.timedelta(days=n)
            src["daily_best_deaths"][key][day]=1 if n<34 else 7
            src["daily_event_ids"][key][day]=[f"U-{n}"]
        episodes,_=propose_episodes(src,t,t+dt.timedelta(days=10))
        surges=[e for e in episodes if e["type"]=="intensification"]
        if surges:
            self.assertLessEqual(len(surges),1)

    def test_pinned_ucdp_source_hash_refuses_mutated_labels(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ucdp.csv"
            p.write_text("id,country\n1,Ukraine\n")
            with self.assertRaisesRegex(ValueError,"SHA256 changed"):
                read_candidate_csv(p,require_sha=True)

    def test_ucdp_dyad_specific_date_source_and_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"ucdp.csv"
            fields=["id","country","type_of_violence","dyad_new_id",
                    "dyad_name","conflict_new_id","date_start","date_end",
                    "date_prec","event_clarity","code_status","best","high"]
            rows=[
                ["1","Ukraine","1","770","Government of Ukraine - Test Group","100",
                 "2026-07-11","2026-07-11","1","1","Clear","2","2"],
                ["2","Ukraine","1","770","Government of Ukraine - Test Group","100",
                 "2026-07-07","2026-07-09","3","1","Check deaths","0","2"],
                ["3","Ukraine","2","770","Government of Ukraine - Test Group","100",
                 "2026-07-06","2026-07-06","1","1","Clear","3","3"],
            ]
            with f.open("w",newline="") as handle:
                w=csv.writer(handle);w.writerow(fields);w.writerows(rows)
            src=read_candidate_csv(f,require_sha=False)
            self.assertEqual(src["source_counts"]["clear_exact_fatal"],1)
            self.assertEqual(src["source_counts"]["ambiguous_quarantined"],1)
            self.assertEqual(src["source_counts"]["other_violence_type"],1)
            episodes,_=propose_episodes(src,dt.date(2026,7,11),dt.date(2026,7,11))
            self.assertEqual(episodes,[])

    def test_inconsistent_fatality_bounds_are_quarantined_not_zeroed(self):
        from scripts.ucdp_episode_labels import produce
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ucdp.csv"
            fields=["id","country","type_of_violence","dyad_new_id",
                    "dyad_name","conflict_new_id","date_start","date_end",
                    "date_prec","event_clarity","code_status","best","high"]
            rows=[
                ["628267","Ukraine","1","770","Government of Ukraine - Test Group","100",
                 "2026-07-09","2026-07-09","1","1","Clear","5","2"],
                ["628268","Ukraine","1","770","Government of Ukraine - Test Group","100",
                 "2026-07-11","2026-07-11","1","1","Clear","3","3"],
            ]
            with p.open("w",newline="") as out:
                w=csv.writer(out);w.writerow(fields);w.writerows(rows)
            src=read_candidate_csv(p,require_sha=False)
            key=("Ukraine","770")
            self.assertEqual(src["source_counts"]["fatality_bounds_inconsistent_quarantined"],1)
            self.assertEqual(src["source_counts"]["clear_exact_fatal"],1)
            self.assertEqual(src["daily_best_deaths"][key][dt.date(2026,7,9)],0)
            self.assertIn(dt.date(2026,7,9),src["uncertain_dates"][key])
            self.assertEqual(src["invalid_fatality_bounds"][0]["event_id"],"628267")
            episodes,_=propose_episodes(src,dt.date(2026,7,11),dt.date(2026,7,11))
            self.assertEqual(episodes,[], "Uncertain earlier fatalities cannot establish a new quiet-restart")
            events,manifest=produce(p,Path(d)/"output",require_sha=False)
            self.assertEqual(events,[])
            self.assertEqual(manifest["quarantined_fatality_bounds_count"],1)
            qc=list(csv.DictReader((Path(d)/"output"/"quarantined_fatality_bounds.csv").open()))
            self.assertEqual(len(qc),1)
            self.assertEqual(qc[0]["event_id"],"628267")

    def test_conflicting_duplicate_event_id_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"ucdp.csv"
            fields=["id","country","type_of_violence","dyad_new_id",
                    "dyad_name","conflict_new_id","date_start","date_end",
                    "date_prec","event_clarity","code_status","best","high"]
            row=["1","Ukraine","1","770","Test dyad","100",
                 "2026-07-09","2026-07-09","1","1","Clear","5","2"]
            with p.open("w",newline="") as out:
                w=csv.writer(out);w.writerow(fields);w.writerow(row);w.writerow(row[:-1]+["6"])
            with self.assertRaisesRegex(ValueError,"Conflicting duplicate"):
                read_candidate_csv(p,require_sha=False)

    def test_nomination_queue_only_pre_event_days_and_no_auto_actor_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            first=dt.date(2026,4,12)
            hist=root/"history.jsonl"
            with hist.open("w") as f:
                for n in range(110):
                    day=first+dt.timedelta(days=n)
                    counts={"DOMESTIC:VEN":1000}
                    if day==dt.date(2026,7,11):
                        counts={"DOMESTIC:VEN":980,"BILAT:RUS:UKR":20}
                    f.write(json.dumps({"day":day.strftime("%Y%m%d"),
                             "rows":1200,"selected":1000,"counts":counts})+"\n")
            x=root/"countries.csv"
            x.write_text("gdelt_code,ucdp_country\nUKR,Ukraine\n")
            ep=[{"episode_id":"EP-1","date":"2026-07-12","type":"quiet_restart",
                 "country":"Ukraine","dyad_new_id":"770","dyad_name":"Test dyad"}]
            queue,info=build_queue(ep,[hist],x)
            self.assertTrue(queue)
            self.assertTrue(all(row["gdelt_asof_date"]<row["episode_date"] for row in queue))
            self.assertTrue(all(row["link_status"]=="UNREVIEWED_NOT_EVIDENCE_OF_ACTOR_MATCH" for row in queue))
            self.assertTrue(all(row["reviewer_1"]=="" and row["decision"]=="" for row in queue))
            self.assertEqual(info["confirmed_actor_matches"],0)


if __name__=="__main__":
    unittest.main()
