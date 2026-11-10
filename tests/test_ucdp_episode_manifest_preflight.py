"""Regression tests: two historical GDELT tools use distinct failure schemas."""
import copy
import unittest

from scripts.validate_ucdp_episode_inputs import validate_manifests, SOURCE_PROFILE


def fixtures():
    early = {
        "start": "2026-04-12", "end": "2026-07-10",
        "requested_days": 90, "complete_days": 90,
        "failed_days": 0, "failures": [],
    }
    later = {
        "historical_start": "2026-07-11",
        "available_end": "2026-11-09",
        "total_valid_days": 122, "failed_days": [],
        "profile": SOURCE_PROFILE,
    }
    return early, later


class UCDPEpisodeManifestTests(unittest.TestCase):
    def test_two_actual_manifest_shapes_both_pass(self):
        early, later = fixtures()
        result = validate_manifests(early, later)
        self.assertEqual(result["joined_valid_days"], 212)
        self.assertEqual(result["failed_days"], 0)

    def test_valid_empty_list_is_not_integer_zero(self):
        early, later = fixtures()
        later["failed_days"] = 0
        with self.assertRaisesRegex(ValueError, "shadow manifest 'failed_days'"):
            validate_manifests(early, later)

    def test_missing_and_nonempty_failures_fail_closed(self):
        early, later = fixtures()
        later["failed_days"] = [{"day": "2026-11-09", "error": "unavailable"}]
        with self.assertRaisesRegex(ValueError, "failed_days"):
            validate_manifests(early, later)
        early, later = fixtures()
        early["failed_days"] = 1
        with self.assertRaisesRegex(ValueError, "failed_days"):
            validate_manifests(early, later)

    def test_date_or_coverage_mismatch_fails_closed(self):
        early, later = fixtures()
        later["available_end"] = "2026-11-08"
        with self.assertRaisesRegex(ValueError, "available_end"):
            validate_manifests(early, later)
        early, later = fixtures()
        early["complete_days"] = 89
        with self.assertRaisesRegex(ValueError, "complete_days"):
            validate_manifests(early, later)


if __name__ == "__main__":
    unittest.main()
