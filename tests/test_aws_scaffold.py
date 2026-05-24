import json
import unittest
from pathlib import Path

from scripts.aws_deploy_checklist import build_aws_steps, render_aws_checklist


ROOT_DIR = Path(__file__).resolve().parents[1]


class AwsScaffoldTests(unittest.TestCase):
    def test_ecs_task_definition_template_is_valid_json(self):
        template_path = ROOT_DIR / "infra" / "aws" / "ecs-task-definition.template.json"
        payload = json.loads(template_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["family"], "parlayvu-core")
        self.assertIn("FARGATE", payload["requiresCompatibilities"])
        self.assertEqual(payload["containerDefinitions"][0]["portMappings"][0]["containerPort"], 8000)
        secret_names = {item["name"] for item in payload["containerDefinitions"][0]["secrets"]}
        self.assertIn("DATABASE_URL", secret_names)
        self.assertIn("XAI_API_KEY", secret_names)
        self.assertIn("MICROSOFT_CLIENT_SECRET", secret_names)
        self.assertIn("TAVUS_API_KEY", secret_names)

    def test_aws_checklist_includes_core_deployment_steps(self):
        titles = [step["title"] for step in build_aws_steps()]

        self.assertIn("Authenticate Docker To ECR", titles)
        self.assertIn("Build Docker Image", titles)
        self.assertIn("Push Docker Image", titles)
        self.assertIn("Register ECS Task Definition", titles)
        self.assertIn("Update ECS Service", titles)
        self.assertIn("Check Readiness", titles)

    def test_render_aws_checklist_mentions_secret_inventory(self):
        checklist = render_aws_checklist()

        self.assertIn("ParlayVU AWS Fargate Deployment Checklist", checklist)
        self.assertIn("infra/aws/ecs-task-definition.template.json", checklist)
        self.assertIn("infra/aws/secrets.env.example", checklist)
        self.assertIn("/parlayvu/prod/<NAME>", checklist)


if __name__ == "__main__":
    unittest.main()
