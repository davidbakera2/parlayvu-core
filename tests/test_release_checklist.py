import unittest

from scripts.release_checklist import build_release_checks, render_release_checklist


class ReleaseChecklistTests(unittest.TestCase):
    def test_release_checks_cover_required_sections(self):
        sections = {section["title"] for section in build_release_checks()}

        self.assertIn("Secret Safety", sections)
        self.assertIn("Local Verification", sections)
        self.assertIn("Demo Memory", sections)
        self.assertIn("Readiness", sections)
        self.assertIn("Demo Rehearsal", sections)
        self.assertIn("AWS/Fargate", sections)
        self.assertIn("Pitch Materials", sections)

    def test_render_release_checklist_mentions_key_commands_and_gates(self):
        checklist = render_release_checklist()

        self.assertIn("python -m unittest discover -s tests", checklist)
        self.assertIn("python scripts/seed_demo.py", checklist)
        self.assertIn("python scripts/demo_runbook.py", checklist)
        self.assertIn("python scripts/aws_deploy_checklist.py", checklist)
        self.assertIn("MICROSOFT_GRAPH_ALLOW_SEND=false", checklist)
        self.assertIn("approval-gated", checklist)
        self.assertIn("Final Gate", checklist)


if __name__ == "__main__":
    unittest.main()
