"""Time-series tests use fabricated measurements; NOT real forecasting validation."""
import pathlib,sys,unittest,datetime as dt
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
from preconvergence import trailing_robust_z,examine
from collect_wikipedia import score_attention
class PreconvergenceTests(unittest.TestCase):
 def test_trailing_no_history_no_score(self):
  self.assertIsNone(trailing_robust_z([1]*13,100))
 def test_history_not_overwritten_by_shock(self):
  h=[1+.03*(i%5) for i in range(22)]
  self.assertGreater(trailing_robust_z(h,3),10)
 def test_missing_market_not_called_divergence(self):
  rows=[{'date':(dt.date(2026,10,1)+dt.timedelta(days=i)).isoformat(),
         'iran_to_canada_ratio':str(.75+.02*(i%5) if i<21 else 2.0),
         'iran_daily_change_pp':''} for i in range(22)]
  r=examine(rows)
  self.assertEqual(len(r['flags']),0)
  self.assertEqual(r['daily_diagnostics'][-1]['state'],'attention_without_market_observation')
 def test_market_outcome_specific(self):
  rows=[{'date':(dt.date(2026,10,1)+dt.timedelta(days=i)).isoformat(),
         'iran_to_canada_ratio':str(.75+.02*(i%5) if i<21 else 2.0),
         'iran_daily_change_pp':'0','iran_market_source':'https://example.com'} for i in range(22)]
  self.assertEqual(len(examine(rows)['flags']),1)
 def test_wiki_no_control_not_alert(self):
  s=score_attention({'Iran':{'2026-11-01':200}},dt.date(2026,11,7))
  self.assertEqual(s['all_flags'],[])
if __name__=='__main__':unittest.main()
