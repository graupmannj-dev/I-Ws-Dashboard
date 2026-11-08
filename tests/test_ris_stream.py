"""Offline checks for the opt-in, scoped RIS Live network collector."""
import datetime as dt
import unittest
from ris_stream import Window, allowed_prefixes, subscribed_match

UTC = dt.timezone.utc

class RISStreamTests(unittest.TestCase):
    def test_prefix_allowlist_rejects_firehose_and_nonpublic_targets(self):
        for bad in (["0.0.0.0/0"], ["10.0.0.0/8"], ["2001:db8::/32"],
                    ["8.0.0.0/8"], ["8.8.8.0/24"] * 9):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    allowed_prefixes(bad)
        self.assertEqual(str(allowed_prefixes(["8.8.8.0/24"])[0]), "8.8.8.0/24")
        self.assertEqual(subscribed_match("8.8.8.0/25", allowed_prefixes(["8.8.8.0/24"])), ["8.8.8.0/24"])
        self.assertEqual(subscribed_match("1.1.1.0/24", allowed_prefixes(["8.8.8.0/24"])), [])

    def test_messages_are_deduplicated_and_only_scoped_counts_are_reported(self):
        start = dt.datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
        v = Window(["8.8.8.0/24"], started=start)
        msg = {"type": "ris_message", "data": {
            "type": "UPDATE", "timestamp": start.timestamp() + 15,
            "host": "rrc01", "id": "stable-id-001", "path": [1234, 15169],
            "announcements": [{"prefixes": ["8.8.8.0/25", "1.1.1.0/24"]}],
            "withdrawals": ["8.8.8.128/25", "9.9.9.0/24"]}}
        v.accept(msg)
        v.accept(msg)
        output = v.output(ended=start + dt.timedelta(seconds=30))
        p = output["prefixes"][0]
        self.assertEqual(p["announcements"], 1)
        self.assertEqual(p["withdrawals"], 1)
        self.assertEqual(p["unique_ripe_collectors"], 1)
        self.assertEqual(p["origin_asns"], {"15169": 1})
        self.assertIn("not", output["interpretation_ceiling"].lower())
        self.assertEqual(output["messages_processed"], 1)

if __name__ == "__main__":
    unittest.main()
