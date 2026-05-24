import unittest

from scripts.demo_runbook import DEFAULT_BASE_URL, build_demo_steps, render_demo_runbook


class DemoRunbookTests(unittest.TestCase):
    def test_build_demo_steps_includes_core_flow(self):
        steps = build_demo_steps()
        titles = [step["title"] for step in steps]

        self.assertIn("Start the API", titles)
        self.assertIn("Seed RamAir Project Memory", titles)
        self.assertIn("Check Readiness", titles)
        self.assertIn("Show Teams Front Door", titles)
        self.assertIn("Request Deployment Approval", titles)
        self.assertIn("Show Teams Approval Cards", titles)
        self.assertIn("Ask Nathan a Project Question (custom LLM endpoint)", titles)

    def test_render_demo_runbook_contains_safe_commands(self):
        runbook = render_demo_runbook()

        self.assertIn(DEFAULT_BASE_URL, runbook)
        self.assertIn("ramair-straight-from-the-hart", runbook)
        self.assertIn("/readiness", runbook)
        self.assertIn("/teams/messages", runbook)
        self.assertIn("/dylan/deploy-site", runbook)
        self.assertIn("/teams/approval-cards", runbook)
        self.assertIn("/m365/email-drafts", runbook)
        self.assertIn("/v1/chat/completions", runbook)
        self.assertIn('"request_approval": true', runbook)


if __name__ == "__main__":
    unittest.main()
