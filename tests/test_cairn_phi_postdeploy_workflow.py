"""Workflow-level guarantees that Phi cannot delay source publication."""
from pathlib import Path
import unittest

WORKFLOW=Path(".github/workflows/publish-global-watchboard.yml")


class PostdeployPhiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=WORKFLOW.read_text()
        cls.collect=cls.text.split("\n  collect:\n",1)[1].split("\n  deploy:\n",1)[0]
        cls.phi=cls.text.split("\n  phi-postdeploy:\n",1)[1]

    def test_collection_does_not_start_local_inference(self):
        self.assertIn("python dashboard/semantic_ach.py --site _site",self.collect)
        self.assertNotIn("scripts/run_cairn_phi.sh",self.collect)
        self.assertNotIn("cairn_phi_incremental",self.collect)
        self.assertIn("actions/upload-pages-artifact@v3",self.collect)

    def test_model_job_runs_only_after_pages_and_uses_exact_artifact(self):
        self.assertIn("needs: deploy",self.phi)
        self.assertIn("actions/download-artifact@v4",self.phi)
        self.assertIn("name: github-pages",self.phi)
        self.assertIn("artifact.tar",self.phi)
        self.assertNotIn("https://graupmannj-dev.github.io/",self.phi)
        self.assertIn("scripts.cairn_phi_incremental prepare",self.phi)
        self.assertIn("scripts.cairn_phi_incremental assemble",self.phi)

    def test_model_artifact_is_isolated_from_collector_data(self):
        self.assertIn("ref: cairn-phi-results",self.phi)
        self.assertIn("HEAD:cairn-phi-results",self.phi)
        self.assertNotIn("aiba-feed-data",self.phi)
        self.assertIn("group: cairn-phi-postdeploy-sidecar",self.phi)
        self.assertIn("contents: write",self.phi)
        self.assertIn("OPENAI_API_KEY: ''",self.phi)
        self.assertIn("CAIRN_SEMANTIC_MODEL: ''",self.phi)

    def test_no_inference_on_zero_changes_and_no_log_upload(self):
        self.assertIn('if [ "$count" -eq 0 ]',self.phi)
        self.assertIn("No changed or expired packets",self.phi)
        self.assertIn("timeout --signal=TERM",self.phi)
        self.assertIn("cairn-phi-postdeploy-",self.phi)
        self.assertNotIn("llama-server.log",self.phi)


if __name__=="__main__":
    unittest.main()
