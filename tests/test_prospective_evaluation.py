"""Prospective evaluation must refuse missing labels, leakage, unregistered scores."""
import datetime as dt
import unittest
from cairn_prospective_evaluation import (RISK_SCHEMA,PRED_SCHEMA,REPORT_SCHEMA,
                                           evaluate,unavailable)

UTC=dt.timezone.utc
ASOF=dt.datetime(2026,11,20,20,0,tzinfo=UTC)

def iso(t):return t.isoformat().replace("+00:00","Z")

def series(n=30):
    windows=[];forecasts=[]
    base=dt.datetime(2026,10,1,0,0,tzinfo=UTC)
    for i in range(n):
        start=base+dt.timedelta(days=i)
        end=start+dt.timedelta(days=1)
        event=i<10
        alert=(i<8) or (10<=i<13)
        w={"id":"risk-"+str(i),"start_at":iso(start),"end_at":iso(end),
           "outcome":"event" if event else "no_event",
           "outcome_coverage_audited":True,
           "adjudicated_at":iso(end+dt.timedelta(hours=1)),
           "adjudication_reference":"https://example.org/outcome/"+str(i)}
        if event:
            w["event_onset_at"]=iso(start+dt.timedelta(hours=2))
            w["first_public_report_at"]=iso(start+dt.timedelta(hours=5))
        windows.append(w)
        forecasts.append({"window_id":w["id"],"issued_at":iso(start),
          "alert":alert,"model_version":"synthetic-frozen-v1",
          "baseline_probability":0.4,
          "augmented_probability":0.8 if event else 0.1})
    return ({"schema":RISK_SCHEMA,"windows":windows},
            {"schema":PRED_SCHEMA,"forecasts":forecasts})

class ProspectiveAuditTests(unittest.TestCase):
    def test_all_requirements_ready_with_frozen_ablation(self):
        risk,forecast=series()
        d=evaluate(risk,forecast,ASOF)
        self.assertEqual(d["schema"],REPORT_SCHEMA)
        self.assertEqual(d["status"],"completed_private_evaluation")
        m=d["metrics"]
        self.assertEqual(m["true_positive_alert_windows"],8)
        self.assertEqual(m["false_positive_alert_windows"],3)
        self.assertEqual(m["false_negative_event_windows"],2)
        self.assertEqual(m["true_negative_quiet_windows"],17)
        self.assertEqual(m["recall"],0.8)
        self.assertEqual(m["median_prepublication_lead_hours"],5)
        self.assertEqual(m["false_alerts_per_100_adjudicated_windows"],10.0)
        self.assertGreater(m["paired_brier_improvement"],0)
        self.assertFalse(d["public_reporting_authorized"])
        self.assertFalse(d["forecast_skill_claim_approved"])

    def test_missing_outcomes_or_coverage_never_become_false_alarms(self):
        risk,forecast=series()
        risk["windows"][10]["outcome"]="pending"
        d=evaluate(risk,forecast,ASOF)
        self.assertEqual(d["status"],"risk_set_outcomes_incomplete")
        self.assertTrue(all(v is None for v in d["metrics"].values()))
        risk,forecast=series()
        risk["windows"][10]["outcome_coverage_audited"]=False
        d=evaluate(risk,forecast,ASOF)
        self.assertEqual(d["status"],"risk_set_outcomes_incomplete")
        self.assertTrue(all(v is None for v in d["metrics"].values()))

    def test_too_small_sample_never_claims_skill(self):
        risk,forecast=series(18)
        d=evaluate(risk,forecast,ASOF)
        self.assertEqual(d["status"],"insufficient_verified_outcomes")
        self.assertTrue(all(v is None for v in d["metrics"].values()))

    def test_missing_frozen_ablation_never_fabricates_brier(self):
        risk,forecast=series()
        for p in forecast["forecasts"]:
            p.pop("baseline_probability")
            p.pop("augmented_probability")
        d=evaluate(risk,forecast,ASOF)
        self.assertIsNone(d["metrics"]["baseline_brier"])
        self.assertIsNone(d["metrics"]["paired_brier_improvement"])

    def test_leakage_in_prediction_or_extra_forecast_rejected(self):
        risk,forecast=series()
        forecast["forecasts"][0]["issued_at"]="2026-10-02T05:00:00Z"
        with self.assertRaisesRegex(ValueError,"sealed before"):
            evaluate(risk,forecast,ASOF)
        risk,forecast=series()
        forecast["forecasts"][0]["augmented_probability"]=1.5
        with self.assertRaisesRegex(ValueError,"finite"):
            evaluate(risk,forecast,ASOF)
        risk,forecast=series()
        forecast["forecasts"].append(forecast["forecasts"][0].copy())
        with self.assertRaises(ValueError):evaluate(risk,forecast,ASOF)

    def test_no_event_unverified_short_window_rejected(self):
        risk,forecast=series()
        risk["windows"][11]["adjudicated_at"]=risk["windows"][11]["start_at"]
        with self.assertRaisesRegex(ValueError,"not adjudicated past"):
            evaluate(risk,forecast,ASOF)

    def test_readiness_status_has_no_private_counts_or_zero_metrics(self):
        o=unavailable("no_connected_signed_prospective_outcomes")
        self.assertFalse(o["forecast_skill_claim_approved"])
        self.assertFalse(o["private_source_material_published"])
        self.assertTrue(all(v is None for v in o["metrics"].values()))
        self.assertEqual(o["evaluated_windows"],0)

if __name__=="__main__":unittest.main()
