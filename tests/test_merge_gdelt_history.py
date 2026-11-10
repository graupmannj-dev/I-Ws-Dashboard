"""Historical artifact continuity tests. Synthetic records only."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from scripts.merge_gdelt_history import build, merge, candidates

START = dt.date(2026, 1, 1)

def rows(n=42, shock_day=34, skip=()):
    data = []
    for i in range(n):
        if i in skip:
            continue
        unusual = i == shock_day
        a = 20 if unusual else 1
        day = START + dt.timedelta(days=i)
        data.append({
            "day": day.strftime("%Y%m%d"), "rows": 150, "selected": 100,
            "counts": {"BILAT:ERI:ETH": a, "DOMESTIC:AAA": 100 - a}
        })
    return data

def write_rows(folder, rows_):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "daily.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in rows_), encoding="utf-8")

class MergeGdeltHistoryTests(unittest.TestCase):
    def test_overlap_is_deduplicated_and_cross_chunk_replay_has_full_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b, output = (Path(tmp)/name for name in ("a","b","out"))
            records=rows()
            write_rows(a, records[:30])
            write_rows(b, records[29:])
            report=build([str(a), str(b)], str(output))
            self.assertEqual(report["complete_days"], 42)
            self.assertEqual(report["missing_days"], [])
            self.assertEqual(report["analyzed_days"], 14)
            candidates_=[json.loads(s) for s in
                (output/"shadow_candidates.jsonl").read_text().splitlines()]
            self.assertTrue(any(r["day"] == (START+dt.timedelta(days=34)).isoformat()
                                and r["case"] == "BILAT:ERI:ETH"
                                for r in candidates_))
            self.assertFalse(report["approved_for_production_thresholds"])

    def test_missing_calendar_day_is_not_a_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a";out=Path(tmp)/"out"
            write_rows(a, rows(skip={16}))
            report=build([str(a)], str(out))
            self.assertIn((START+dt.timedelta(days=16)).isoformat(), report["missing_days"])
            shadow=[json.loads(s) for s in
                    (out/"shadow_candidates.jsonl").read_text().splitlines()]
            self.assertFalse(any(r["day"]==(START+dt.timedelta(days=34)).isoformat()
                                 for r in shadow))

    def test_conflicting_same_date_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a"; b=Path(tmp)/"b"
            initial=rows(1)
            write_rows(a, initial)
            altered=dict(initial[0]); altered["counts"]={"BILAT:ERI:ETH":2,"DOMESTIC:AAA":98}
            write_rows(b,[altered])
            with self.assertRaisesRegex(ValueError,"Conflicting observations"):
                merge([str(a),str(b)])

    def test_selected_denominator_must_match_case_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a"; bad=rows(1)
            bad[0]["selected"]=101
            write_rows(a,bad)
            with self.assertRaisesRegex(ValueError,"denominator"):
                merge([str(a)])

if __name__ == "__main__":
    unittest.main()
