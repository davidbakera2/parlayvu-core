import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agents.tools import dylan_tools
from app.main import app


class DylanGenerationTests(unittest.TestCase):
    def test_generate_astro_site_creates_project_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(dylan_tools, "GENERATED_SITES_DIR", Path(tmpdir)):
                result = dylan_tools.generate_astro_site.invoke(
                    {
                        "content": "AI content repurposing turns one idea into a full campaign.",
                        "site_name": "ai-content-repurposing",
                        "client_id": "test-client",
                        "brand_voice": "Clear and practical",
                    }
                )

                site_path = Path(result["site_path"])
                self.assertEqual(result["status"], "success")
                self.assertTrue(site_path.exists())
                self.assertTrue((site_path / "package.json").exists())
                self.assertTrue((site_path / "astro.config.mjs").exists())
                self.assertTrue((site_path / "tailwind.config.mjs").exists())
                self.assertTrue((site_path / "src" / "pages" / "index.astro").exists())
                self.assertTrue((site_path / "src" / "layouts" / "Layout.astro").exists())
                self.assertTrue((site_path / "src" / "styles" / "global.css").exists())
                self.assertTrue((site_path / "src" / "styles" / "tailwind.css").exists())

                index_content = (site_path / "src" / "pages" / "index.astro").read_text(
                    encoding="utf-8"
                )
                package_content = (site_path / "package.json").read_text(encoding="utf-8")
                layout_content = (site_path / "src" / "layouts" / "Layout.astro").read_text(
                    encoding="utf-8"
                )
                css_content = (site_path / "src" / "styles" / "global.css").read_text(
                    encoding="utf-8"
                )
                self.assertIn("AI Content Repurposing", index_content)
                self.assertIn("The Parlay Method", index_content)
                self.assertIn("Web & Deployment", index_content)
                self.assertIn("Clear and practical", index_content)
                self.assertIn("tailwindcss", package_content)
                self.assertIn("@tailwindcss/cli", package_content)
                self.assertIn("build:css", package_content)
                self.assertIn("../styles/tailwind.css", layout_content)
                self.assertIn('@import "tailwindcss";', css_content)

    def test_dylan_generate_site_endpoint_returns_tool_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(dylan_tools, "GENERATED_SITES_DIR", Path(tmpdir)):
                client = TestClient(app)
                response = client.post(
                    "/dylan/generate-site",
                    json={
                        "content": "Repurpose a blog post into a landing page.",
                        "site_name": "marketing-landing",
                        "client_id": "endpoint-client",
                        "brand_voice": "Concise and useful",
                    },
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                tool_output = payload["final_output"]["tool_output"]
                self.assertEqual(payload["agent"], "Dylan")
                self.assertEqual(payload["client_id"], "endpoint-client")
                self.assertEqual(tool_output["status"], "success")
                self.assertIn("src/pages/index.astro", tool_output["files_created"])
                self.assertNotIn("deployment_output", payload["final_output"])

    def test_dylan_generate_site_endpoint_can_deploy_after_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(dylan_tools, "GENERATED_SITES_DIR", Path(tmpdir)):
                deploy_result = {
                    "status": "success",
                    "message": "Cloudflare Pages deployment completed.",
                    "project_name": "endpoint-project",
                }
                with patch("app.main.require_approved_approval", return_value={"id": "approval-1"}):
                    with patch("app.main._deploy_site", return_value=deploy_result) as deploy:
                        client = TestClient(app)
                        response = client.post(
                            "/dylan/generate-site",
                            json={
                                "content": "Repurpose a blog post into a landing page.",
                                "site_name": "marketing-landing",
                                "client_id": "endpoint-client",
                                "project_id": "endpoint-project",
                                "brand_voice": "Concise and useful",
                                "deploy": True,
                                "project_name": "endpoint-project",
                                "approval_id": "approval-1",
                            },
                        )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                final_output = payload["final_output"]
                self.assertEqual(final_output["tool_output"]["status"], "success")
                self.assertEqual(final_output["deployment_output"]["status"], "success")
                self.assertEqual(final_output["deployment_output"]["project_name"], "endpoint-project")
                deploy.assert_called_once()

    def test_dylan_generate_site_endpoint_requests_approval_before_deploy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(dylan_tools, "GENERATED_SITES_DIR", Path(tmpdir)):
                approval = {"id": "approval-1", "status": "pending"}
                with patch("app.main.request_approval", return_value=approval) as request_approval:
                    with patch("app.main._deploy_site") as deploy:
                        client = TestClient(app)
                        response = client.post(
                            "/dylan/generate-site",
                            json={
                                "content": "Repurpose a blog post into a landing page.",
                                "site_name": "marketing-landing",
                                "client_id": "endpoint-client",
                                "project_id": "endpoint-project",
                                "brand_voice": "Concise and useful",
                                "deploy": True,
                                "project_name": "endpoint-project",
                            },
                        )

                self.assertEqual(response.status_code, 200)
                final_output = response.json()["final_output"]
                self.assertTrue(final_output["approval_required"])
                self.assertEqual(final_output["approval"]["id"], "approval-1")
                request_approval.assert_called_once()
                deploy.assert_not_called()

    def test_dylan_deploy_site_endpoint_requires_approval(self):
        approval = {"id": "approval-1", "status": "pending"}
        with patch("app.main.request_approval", return_value=approval) as request_approval:
            with patch("app.main._deploy_site") as deploy:
                client = TestClient(app)
                response = client.post(
                    "/dylan/deploy-site",
                    json={
                        "site_path": "does-not-exist",
                        "client_id": "endpoint-client",
                        "project_id": "endpoint-project",
                        "project_name": "endpoint-project",
                    },
                )

        self.assertEqual(response.status_code, 200)
        final_output = response.json()["final_output"]
        self.assertTrue(final_output["approval_required"])
        request_approval.assert_called_once()
        deploy.assert_not_called()

    def test_dylan_deploy_site_endpoint_returns_tool_output_with_approval(self):
        with patch("app.main.require_approved_approval", return_value={"id": "approval-1"}):
            client = TestClient(app)
            response = client.post(
                "/dylan/deploy-site",
                json={
                    "site_path": "does-not-exist",
                    "project_name": "missing-project",
                    "approval_id": "approval-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        tool_output = payload["final_output"]["tool_output"]
        self.assertEqual(payload["agent"], "Dylan")
        self.assertEqual(tool_output["status"], "error")

    def test_dylan_deploy_site_endpoint_rejects_unapproved_approval(self):
        with patch("app.main.require_approved_approval", side_effect=PermissionError("not approved")):
            client = TestClient(app)
            response = client.post(
                "/dylan/deploy-site",
                json={
                    "site_path": "does-not-exist",
                    "project_name": "missing-project",
                    "approval_id": "approval-1",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_deploy_to_cloudflare_returns_error_for_missing_site(self):
        result = dylan_tools.deploy_to_cloudflare.invoke(
            {
                "site_path": "does-not-exist",
                "project_name": "missing-project",
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("does not exist", result["message"])

if __name__ == "__main__":
    unittest.main()
