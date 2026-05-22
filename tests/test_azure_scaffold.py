import unittest
from pathlib import Path

from scripts.azure_deploy_checklist import build_azure_steps, render_azure_checklist


ROOT_DIR = Path(__file__).resolve().parents[1]


class AzureScaffoldTests(unittest.TestCase):
    def test_azure_secret_inventory_keeps_neon_database_url(self):
        secrets_path = ROOT_DIR / "infra" / "azure" / "secrets.env.example"
        payload = secrets_path.read_text(encoding="utf-8")

        self.assertIn("DATABASE_URL=", payload)
        self.assertIn("PROJECT_MEMORY_ENABLED=true", payload)
        self.assertIn("MICROSOFT_CLIENT_SECRET=", payload)
        self.assertIn("TEAMS_WEBHOOK_SECRET=", payload)
        self.assertIn("HEYGEN_API_KEY=", payload)

    def test_azure_checklist_includes_core_deployment_steps(self):
        titles = [step["title"] for step in build_azure_steps()]

        self.assertIn("Create Azure Container Registry", titles)
        self.assertIn("Build And Push Image In Azure", titles)
        self.assertIn("Create Container Apps Environment", titles)
        self.assertIn("Create Container App", titles)
        self.assertIn("Check Readiness", titles)

    def test_render_azure_checklist_mentions_teams_endpoint_and_neon(self):
        checklist = render_azure_checklist()

        self.assertIn("ParlayVU Azure Container Apps Deployment Checklist", checklist)
        self.assertIn("Neon Postgres", checklist)
        self.assertIn("infra/azure/secrets.env.example", checklist)
        self.assertIn("/teams/messages", checklist)


if __name__ == "__main__":
    unittest.main()
