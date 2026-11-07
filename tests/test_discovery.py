"""Synthetic tests only: not actual observed geopolitical counts."""
import datetime as dt
import pathlib,sys,unittest
from collections import Counter,defaultdict
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
from aiba_v4 import analyze,beta_binomial_sf
class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.asof=dt.date(2026,11,7)
  self.days=[self.asof-dt.timedelta(days=i) for i in range(34,-1,-1)]
  self.base_key=('BILAT',('ETH','ERI'))
  self.other=('BILAT',('USA','CHN'))
  self.samples={}
 def make(self,spike=False):
  rec=Counter();total=Counter()
  for d in self.days:
   recent=(self.asof-d).days<7
   total[d]=1000
   rec[(d,self.base_key)]=80 if spike and recent else 10
   rec[(d,self.other)]=10
  return rec,total,defaultdict(Counter),self.days,self.samples
 def test_anomaly_detected(self):
  leads,_=analyze(*self.make(True),self.asof)
  self.assertTrue(any(x['id']=='gdelt_BILAT_ETH_ERI' for x in leads),leads)
 def test_stable_baseline_not_flagged(self):
  leads,_=analyze(*self.make(False),self.asof)
  self.assertEqual(leads,[])
 def test_incomplete_data_no_scoring(self):
  rec,total,roots,days,samples=self.make(True)
  leads,complete=analyze(rec,total,roots,days[:10],samples,self.asof)
  self.assertEqual(leads,[])
  self.assertLess(complete['recent_days'],7)
 def test_one_missing_baseline_day_blocks_scoring(self):
  rec,total,roots,days,samples=self.make(True)
  leads,coverage=analyze(rec,total,roots,days[1:],samples,self.asof)
  self.assertEqual(leads,[])
  self.assertEqual(coverage['baseline_days'],27)
 def test_tail_range(self):
  a=beta_binomial_sf(5,10,1,1)
  self.assertGreaterEqual(a,0);self.assertLessEqual(a,1)
if __name__=='__main__':unittest.main()
