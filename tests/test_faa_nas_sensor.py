import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from faa_nas_sensor import analyze, collect, SCHEMA, SOURCE_URL

NOW = dt.datetime(2026,11,13,21,24,0,tzinfo=dt.timezone.utc)

def sample(reason=None, stop_ids=()):
    rows=[]
    for name in ("ATL","JFK","ORD","LAX","SFO","MIA","DFW","SEA","BOS","DEN"):
        rows.append({
            "airportId":name,"groundStop":{"reason":"EQUIPMENT"} if name in stop_ids else None,
            "groundDelay":None,"airportClosure":None,"arrivalDelay":None,
            "departureDelay":{"reason":reason,"averageDelay":"120"} if
                (name in ("ATL","JFK") and reason) else None,
            "airportLongName": "Example "+name, "latitude":"40", "longitude":"-90"
        })
    return rows


class FaaNasSystemicWatchTests(unittest.TestCase):
    def test_national_stop_reason_from_two_airports_without_claim_of_attack(self):
        out=analyze(sample("OTHER: NATIONAL STOP"),collected_at=NOW)
        self.assertEqual(out["schema"],SCHEMA)
        self.assertEqual(out["status"],"multi_airport_national_stop_language")
        self.assertEqual(out["national_stop_airports"],2)
        self.assertTrue(out["provisional_review_required"])
        self.assertFalse(out["national_event_confirmed_by_explicit_ATCSCC_order"])
        self.assertFalse(out["cyberattack_evidence"])
        self.assertFalse(out["hostile_actor_evidence"])
        self.assertFalse(out["military_warning_level_change"])
        self.assertEqual(out["source_family_independence_count"],1)
        self.assertEqual(out["source_url"],SOURCE_URL)

    def test_no_disruption_in_sample_is_not_all_clear(self):
        out=analyze(sample(),collected_at=NOW)
        self.assertEqual(out["status"],"no_systemic_disruption_in_monitored_sample")
        self.assertFalse(out["provisional_review_required"])
        self.assertIn("does not certify nationwide all-clear", " ".join(out["limitations"]))

    def test_multiple_local_stops_differ_from_national_order(self):
        out=analyze(sample(stop_ids=["ATL","JFK","LAX","ORD"]),collected_at=NOW)
        self.assertEqual(out["status"],"multiple_airport_ground_stops")
        self.assertEqual(out["national_stop_airports"],0)
        self.assertEqual(out["active_ground_stop_airports"],4)

    def test_no_non_source_inference_from_airport_count(self):
        out=analyze(sample("COMMS FAILURE"),collected_at=NOW)
        self.assertEqual(out["status"],"no_systemic_disruption_in_monitored_sample")
        self.assertFalse(out["cyberattack_evidence"])

    def test_source_schema_failure_is_not_measured_zero(self):
        for data in (None,{},[],[{"airportId":"JFK"}],
                     sample()+[dict(sample()[0])]):
            with self.assertRaises(ValueError):
                analyze(data,collected_at=NOW)

    def test_persist_history_only_when_pattern_changes(self):
        with tempfile.TemporaryDirectory() as t:
            a=Path(t)
            first,health=collect(a,fetch=lambda:sample("OTHER: NATIONAL STOP"),clock=lambda:NOW)
            self.assertEqual(health["status"],"collected")
            self.assertTrue(first["changed_since_prior_observation"])
            history=list((a/"history"/"faa_nas").glob("*.json"))
            self.assertEqual(len(history),1)
            later=NOW+dt.timedelta(minutes=10)
            second,health=collect(a,fetch=lambda:sample("OTHER: NATIONAL STOP"),clock=lambda:later)
            self.assertFalse(second["changed_since_prior_observation"])
            self.assertEqual(len(list((a/"history"/"faa_nas").glob("*.json"))),1)
            third,health=collect(a,fetch=lambda:sample(),clock=lambda:later+dt.timedelta(minutes=10))
            self.assertTrue(third["changed_since_prior_observation"])
            self.assertEqual(len(list((a/"history"/"faa_nas").glob("*.json"))),2)

    def test_source_failure_keeps_last_valid_data_and_health(self):
        with tempfile.TemporaryDirectory() as t:
            a=Path(t)
            collect(a,fetch=lambda:sample("OTHER: NATIONAL STOP"),clock=lambda:NOW)
            prior=json.loads((a/"latest"/"faa_nas.json").read_text())
            def failing():
                raise OSError("temporary upstream failure")
            out,health=collect(a,fetch=failing,clock=lambda:NOW+dt.timedelta(minutes=10))
            self.assertIsNone(out)
            self.assertEqual(health["status"],"unavailable")
            self.assertTrue(health["missing_not_clear"])
            self.assertEqual(json.loads((a/"latest"/"faa_nas.json").read_text()),prior)

    def test_airport_level_events_are_provider_statements_not_early_warning(self):
        out=analyze(sample("OTHER: NATIONAL STOP"),collected_at=NOW)
        self.assertIsNone(out["forecast_probability"])
        self.assertEqual(out["automatic_event_merges"],0)
        self.assertFalse(out["military_warning_level_change"])


if __name__=="__main__":
    unittest.main()
