"""Offline synthetic route comparisons: no real aircraft, downloads or uploads."""
import contextlib
import copy
import datetime as dt
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts import aircraft_route_history as route


DAY = "2026-11-10"
AIRCRAFT = ["abc123", "abc124", "abc125", "abc126"]
DATES = ["2026-11-02", "2026-11-04", "2026-11-06", "2026-11-08"]
GROUP = "east-corridor"


def epoch(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def manifest():
    return {"schema": route.COHORT_SCHEMA, "frozen_before": "2026-11-09",
            "cohorts": [{"id": GROUP, "label": "Synthetic eastbound corridor",
                         "direction": "east", "aircraft_ids": AIRCRAFT}]}


def flight(day, name, aircraft="abc123", *, deviation=False, coverage="complete"):
    coords = []
    for i in range(11):
        lat = 0.60 if deviation and 3 <= i <= 7 else 0.0
        coords.append({"t": epoch(day) + 12 * 3600 + i * 180,
                       "lat": lat, "lon": i * 0.20})
    return {"flight_id": name, "cohort_id": GROUP, "aircraft_id": aircraft,
            "direction": "east", "day": day, "coverage": coverage, "points": coords}


def dataset(*, deviation=False):
    flights = [flight(day, f"history-{i}", AIRCRAFT[i])
               for i, day in enumerate(DATES)]
    flights.append(flight(DAY, "heldout", deviation=deviation))
    return {"schema": route.INPUT_SCHEMA, "source": "ADSB.lol",
            "collection_scope": "preselected_cohort_offline",
            "days": [{"date": d, "status": "complete"} for d in DATES + [DAY]],
            "flights": flights}


def report(*, deviation=False):
    return route.analyze(manifest(), dataset(deviation=deviation), DAY)


class RouteRetrospectiveTests(unittest.TestCase):
    def single(self, data, cohort=None, day=DAY):
        return route.analyze(cohort or manifest(), data, day)["results"][0]

    def test_normal_heldout_path_and_historical_corridor(self):
        result = report()
        item = result["results"][0]
        self.assertEqual(item["status"], "within_reference")
        self.assertEqual(result["counts"]["deviation_candidate"], 0)
        self.assertEqual(item["reference_flights"], 4)
        self.assertEqual(item["reference_days"], 4)
        self.assertEqual(len(item["geometry"]["historical_center_latlon"]), 21)
        self.assertEqual(len(item["geometry"]["actual_path_latlon"]), 11)
        self.assertGreaterEqual(item["geometry"]["corridor_half_width_km"], 10)
        self.assertEqual(result["comparison"], "prior_28_days_only")
        self.assertFalse(result["changes_aiba_warning_status"])
        self.assertFalse(result["publishing_enabled"])
        self.assertIsNone(result["calibrated_accuracy"])

    def test_sustained_deviation_is_candidate_not_threat_assessment(self):
        item = report(deviation=True)["results"][0]
        self.assertEqual(item["status"], "deviation_candidate")
        self.assertEqual(item["reason"], "sustained_outside_reference")
        self.assertGreater(item["max_excess_km"], 25)
        self.assertTrue(item["experimental"])
        self.assertIn("historical_p90_spread_km", item["geometry"])

    def test_single_fleeting_far_point_is_not_sustained(self):
        data = dataset()
        data["flights"][-1]["points"][5]["lat"] = 1.0
        item = self.single(data)
        self.assertEqual(item["status"], "within_reference")
        self.assertGreater(item["max_excess_km"], 25)

    def test_few_reference_flights_and_days_are_insufficient_history(self):
        data = dataset(deviation=True)
        data["flights"] = data["flights"][:2] + data["flights"][-1:]
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_history")
        self.assertIsNone(item["geometry"])
        self.assertIsNone(item["max_excess_km"])
        self.assertEqual(item["reference_flights"], 2)

    def test_window_and_heldout_day_cannot_leak_into_history(self):
        data = dataset()
        data["flights"][0]["day"] = "2026-10-01"
        data["days"].append({"date": "2026-10-01", "status": "complete"})
        # Other historical days plus an evaluation-day clone are still insufficient.
        data["flights"].append(flight(DAY, "another-target"))
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_history")
        self.assertEqual(item["reference_flights"], 3)
        self.assertEqual(len(route.analyze(manifest(), data, DAY)["results"]), 2)

    def test_incomplete_history_excluded_and_reported(self):
        data = dataset()
        data["days"][0]["status"] = "partial"
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_history")
        self.assertEqual(item["excluded_history_flights"], 1)
        self.assertEqual(item["reference_flights"], 3)

    def test_missing_or_partial_eval_day_is_insufficient_coverage(self):
        for status in ("partial", "unknown"):
            with self.subTest(status=status):
                data = dataset(deviation=True)
                data["days"][-1]["status"] = status
                item = self.single(data)
                self.assertEqual(item["status"], "insufficient_coverage")
                self.assertEqual(item["reason"], "source_day_not_complete")
                self.assertIsNone(item["geometry"])
        data = dataset()
        data["days"] = data["days"][:-1]
        self.assertEqual(self.single(data)["status"], "insufficient_coverage")

    def test_unknown_or_partial_leg_is_insufficient_coverage(self):
        for value in ("unknown", "partial"):
            with self.subTest(value=value):
                data = dataset(deviation=True)
                data["flights"][-1]["coverage"] = value
                item = self.single(data)
                self.assertEqual(item["status"], "insufficient_coverage")
                self.assertEqual(item["reason"], "flight_coverage_not_complete")

    def test_gap_leg_start_and_unsorted_positions_do_not_invent_maneuver(self):
        for change, reason in [
            (lambda pts: pts[5].update(t=pts[4]["t"] + 1500), "observation_gap"),
            (lambda pts: pts[5].update(flags=2), "multiple_legs"),
            (lambda pts: pts[5].update(t=pts[4]["t"]), "unordered_or_duplicate_timestamps"),
            (lambda pts: pts[5].update(lat=90.0), "implausible_step_or_gap"),
        ]:
            with self.subTest(reason=reason):
                data = dataset(deviation=True)
                change(data["flights"][-1]["points"])
                item = self.single(data)
                self.assertEqual(item["status"], "insufficient_coverage")
                self.assertEqual(item["reason"], reason)
                self.assertIsNone(item["max_excess_km"])

    def test_source_stale_rows_drop_and_can_expose_coverage_gap(self):
        data = dataset()
        data["flights"][-1]["points"][4]["flags"] = 1
        item = self.single(data)
        self.assertEqual(item["status"], "within_reference")
        self.assertEqual(item["dropped_stale_or_ground_positions"], 1)
        for i in (4, 5, 6):
            data["flights"][-1]["points"][i]["flags"] = 1
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_coverage")
        self.assertEqual(item["reason"], "observation_gap")

    def test_mixed_historical_routes_cannot_form_misleading_wide_corridor(self):
        data = dataset()
        data["flights"][0]["points"] = flight(DATES[0], "other", deviation=True)["points"]
        # Make one complete but radically different route: its p90 dispersion grows.
        data["flights"][0]["points"] = [
            {**pt, "lat": pt["lat"] + 2.0} for pt in data["flights"][0]["points"]]
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_history")
        self.assertEqual(item["reason"], "incoherent_reference_routes")

    def test_readsb_trace_offline_input_and_multiple_callsign_detection(self):
        data = dataset()
        held = data["flights"][-1]
        base = epoch(DAY) + 12 * 3600
        held.pop("points")
        held["readsb"] = {
            "icao": "abc123", "timestamp": base,
            "trace": [[i * 180, 0.0, i * 0.20, 30000, 420, 90,
                       2 if i == 0 else 0, 0, {"flight": "TEST1"}]
                      for i in range(11)],
        }
        self.assertEqual(self.single(data)["status"], "within_reference")
        held["readsb"]["trace"][5][8] = {"flight": "TEST2"}
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_coverage")
        self.assertEqual(item["reason"], "callsign_change")
        held["readsb"]["trace"][5][8] = {"flight": "TEST1"}
        held["readsb"]["trace"][5][6] = 3
        self.assertEqual(self.single(data)["status"], "within_reference")

    def test_antimeridian_corridor_is_short_not_long_way_around(self):
        data = dataset()
        for entry in data["flights"]:
            for pt in entry["points"]:
                pt["lon"] = (179 + pt["lon"] + 180) % 360 - 180
        result = self.single(data)
        self.assertEqual(result["status"], "within_reference")
        center = result["geometry"]["historical_center_latlon"]
        self.assertGreater(center[0][1], 178)
        self.assertLess(center[-1][1], -178)

    def test_missing_eval_flight_is_not_successful_zero_anomalies(self):
        data = dataset()
        data["flights"].pop()
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_coverage")
        self.assertEqual(item["reason"], "no_evaluation_flight_in_cohort")

    def test_cohort_freeze_identity_direction_and_format_validation(self):
        data = dataset()
        bad = manifest()
        bad["frozen_before"] = DAY
        with self.assertRaisesRegex(route.InputError, "frozen"):
            route.analyze(bad, data, DAY)
        data["flights"][-1]["direction"] = "west"
        with self.assertRaisesRegex(route.InputError, "direction"):
            self.single(data)
        data = dataset()
        data["flights"][-1]["aircraft_id"] = "ffffff"
        with self.assertRaisesRegex(route.InputError, "predeclared"):
            self.single(data)
        data = dataset()
        data["flights"][-1]["flight_id"] = "history-0"
        with self.assertRaisesRegex(route.InputError, "Duplicate"):
            self.single(data)
        data = dataset()
        data["collection_scope"] = "global"
        with self.assertRaisesRegex(route.InputError, "preselected"):
            self.single(data)

    def test_nan_coordinates_and_untrusted_status_not_scored(self):
        data = dataset()
        data["flights"][-1]["points"][4]["lon"] = math.nan
        item = self.single(data)
        self.assertEqual(item["status"], "insufficient_coverage")
        self.assertEqual(item["reason"], "invalid_position")
        data = dataset()
        data["flights"][-1]["coverage"] = "claimed_100_percent"
        with self.assertRaises(route.InputError):
            self.single(data)

    def test_output_geometry_is_bounded(self):
        data = dataset()
        item = data["flights"][-1]
        first = epoch(DAY) + 3600
        item["points"] = [{"t": first + i * 40, "lat": 0, "lon": i * .001}
                          for i in range(1000)]
        output = self.single(data)
        self.assertEqual(output["status"], "within_reference")
        self.assertLessEqual(len(output["geometry"]["actual_path_latlon"]), 128)

    def test_cli_local_output_and_failed_run_replaces_previous_success(self):
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(root)
            manifest_file, input_file, output_file = [folder / name for name in
                                                      ("cohort.json", "flights.json", "result.json")]
            manifest_file.write_text(json.dumps(manifest()))
            input_file.write_text(json.dumps(dataset(deviation=True)))
            args = ["--cohort", str(manifest_file), "--input", str(input_file),
                    "--date", DAY, "--output", str(output_file)]
            self.assertEqual(route.main(args), 0)
            saved = json.loads(output_file.read_text())
            self.assertEqual(saved["counts"]["deviation_candidate"], 1)
            input_file.write_text('{"flights":')
            self.assertEqual(route.main(args), 1)
            saved = json.loads(output_file.read_text())
            self.assertEqual(saved["status"], "unavailable")
            self.assertEqual(saved["results"], [])
            self.assertNotIn("counts", saved)

    def test_input_file_limit_prevents_large_local_ingestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "too-big.json"
            path.write_bytes(b"x" * (route.MAX_INPUT_BYTES + 1))
            with self.assertRaisesRegex(route.InputError, "8 MiB"):
                route.read_json(path)


if __name__ == "__main__":
    unittest.main()
