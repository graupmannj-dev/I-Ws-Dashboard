import datetime as dt
from pathlib import Path
import csv,io,sys,tempfile,unittest,zipfile
sys.path.insert(0,str(Path(__file__).parents[1]))
from aiba_v4 import ingest
class ParseTests(unittest.TestCase):
 def test_58_column_event(self):
  with tempfile.TemporaryDirectory() as zdir:
   zdir=Path(zdir)
   r=['']*58
   r[0]='1002003';r[1]='20261106';r[7]='ETH';r[17]='ERI';r[28]='19';r[29]='4';r[-1]='https://example.com/one'
   with zipfile.ZipFile(zdir/'20261106.export.CSV.zip','w') as z:
    z.writestr('20261106.export.CSV','\t'.join(r)+'\n')
   records,totals,roots,days,samples=ingest(zdir)
   key=('BILAT',('ERI','ETH'))
   self.assertEqual(records[dt.date(2026,11,6),key],1)
   self.assertEqual(totals[dt.date(2026,11,6)],1)
   self.assertEqual(samples[key],['https://example.com/one'])
if __name__=='__main__':unittest.main()
