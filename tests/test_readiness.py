import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.readiness import llm_readiness, overall_status, readiness_report
from app.settings import Settings


def test_settings(**overrides):
    values = {
        "llm_provider": "grok",
        "llm_temperature": 0.2,
        "xai_api_key": "xai-key",
        "grok_model": "grok-4.3",
        "grok_api_base": "https://api.x.ai/v1",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "groq_api_key": "",
        "groq_model": "llama-3.3-70b-versatile",
        "anthropic_api_key": "",
        "allowed_origins": ["http://localhost:4321"],
    }
    values.update(overrides)
    return Settings(**values)


class ReadinessTests(unittest.TestCase):
    def test_llm_readiness_uses_active_provider_key(self):
        self.assertTrue(llm_readiness(test_settings())["configured"])
        self.assertFalse(llm_readiness(test_settings(xai_api_key=""))["configured"])
        self.assertTrue(
            llm_readiness(
                test_settings(llm_provider="openai", openai_api_key="openai-key")
            )["configured"]
        )

    def test_overall_status_requires_foundation_checks(self):
        checks = {
            "llm": {"configured": True},
            "database": {"configured": True},
            "approvals": {"configured": True},
        }
        self.assertEqual(overall_status(checks), "ready")

        checks["database"]["configured"] = False
        self.assertEqual(overall_status(checks), "needs_configuration")

    def test_readiness_report_does_not_expose_secrets(self):
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:", "PROJECT_MEMORY_ENABLED": "true"}):
            report = readiness_report(test_settings())

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["checks"]["llm"]["provider"], "grok")
        self.assertNotIn("xai_api_key", str(report))
        self.assertNotIn("sqlite:///:memory:", str(report))

    def test_readiness_endpoint(self):
        with patch("app.main.readiness_report", return_value={"status": "ready", "checks": {}}):
            client = TestClient(app)
            response = client.get("/readiness")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_health_includes_readiness_status(self):
        with patch("app.main.readiness_report", return_value={"status": "ready", "checks": {}}):
            client = TestClient(app)
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["readiness_status"], "ready")


if __name__ == "__main__":
    unittest.main()
