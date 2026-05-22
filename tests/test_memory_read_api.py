import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class MemoryReadApiTests(unittest.TestCase):
    def test_memory_clients_endpoint_returns_clients(self):
        with patch("app.main.list_clients", return_value=[{"id": "ramair", "name": "RamAir"}]):
            client = TestClient(app)
            response = client.get("/memory/clients")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["clients"][0]["id"], "ramair")

    def test_memory_projects_endpoint_filters_by_client(self):
        with patch("app.main.list_projects", return_value=[{"id": "ramair-straight-from-the-hart"}]) as list_projects:
            client = TestClient(app)
            response = client.get("/memory/projects?client_id=ramair")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["projects"][0]["id"], "ramair-straight-from-the-hart")
        list_projects.assert_called_once_with(client_id="ramair")

    def test_memory_project_context_endpoint_returns_404_for_missing_project(self):
        with patch("app.main.get_project_context", return_value=None):
            client = TestClient(app)
            response = client.get("/memory/projects/missing")

        self.assertEqual(response.status_code, 404)

    def test_memory_project_context_endpoint_returns_project(self):
        project = {
            "id": "ramair-straight-from-the-hart",
            "client": {"id": "ramair", "name": "RamAir"},
            "source_assets": [{"title": "Straight from the Hart weekly episode"}],
            "generated_outputs": [{"title": "Weekly episode campaign kit"}],
            "approvals": [{"status": "pending"}],
            "agent_events": [{"event_type": "demo_seeded"}],
        }
        with patch("app.main.get_project_context", return_value=project):
            client = TestClient(app)
            response = client.get("/memory/projects/ramair-straight-from-the-hart")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["project"]
        self.assertEqual(payload["client"]["name"], "RamAir")
        self.assertEqual(payload["approvals"][0]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
