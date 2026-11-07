import datetime as dt
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from aiba_v4 import ingest, build

class PublicationSafetyTests(unittest.TestCase):
    def archive(self, root, rows):
        with zipfile.ZipFile(root/'20261106.export.CSV.zip','w') as z:
            z.writestr('20261106.export.CSV','\n'.join(rows))
    def row(self):
        r=['']*58
        r[0]='123';r[1]='20261106';r[7]='ETH';r[17]='ERI';r[28]='19';r[29]='4'
        return '\t'.join(r)
    def test_bad_row_discards_whole_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.archive(p,[self.row(),'bad row'])
            counts,totals,roots,days,samples=ingest(p)
            self.assertEqual((dict(counts),dict(totals),dict(roots),days,dict(samples)),({},{},{},[],{}))
    def test_empty_archive_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.archive(p,[])
            self.assertEqual(ingest(p)[3],[])
    def test_strict_missing_data_cannot_emit_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with self.assertRaises(ValueError):build(p/'out',dt.date(2026,11,6),p,strict=True)
            self.assertFalse((p/'out'/'hotspots.json').exists())
    def test_failed_cli_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);out=p/'site';out.mkdir();(out/'index.html').write_text('previous successful site')
            result=subprocess.run([sys.executable,'aiba_v5.py','--as-of','2026-11-06','--strict-gdelt','--cache-dir',str(p/'empty'),'--output-dir',str(out)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((out/'index.html').read_text(),'previous successful site')
    def test_missing_data_distinct_from_zero_leads(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r=build(p/'out',dt.date(2026,11,6),p)
            self.assertEqual(r['discovery_status'],'missing_data')
            self.assertIn('missing or invalid',r['notice'])
            self.assertEqual(r['preconvergence']['live_attention']['completeness']['attempted'],0)
    def test_cached_days_outside_window_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.archive(p,[self.row()])
            self.assertEqual(ingest(p,dt.date(2026,9,1))[3],[])

    def test_documented_gdelt_uncoded_sentinel_is_not_a_corrupt_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r=self.row().split('\t');r[26:29]=['---','---','--']
            self.archive(p,[self.row(),'\t'.join(r)])
            audit={};counts,totals,roots,days,samples=ingest(p,audit=audit)
            self.assertEqual(len(days),1)
            self.assertEqual(audit['2026-11-06']['uncoded_rows'],1)
            self.assertEqual(totals[days[0]],1)
