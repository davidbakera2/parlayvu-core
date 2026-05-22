import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agents.router import RouteDecision
from app.main import app


class FakeGraph:
    async def ainvoke(self, state):
        return {
            "route_decision": RouteDecision(
                target_agent="ava",
                reason="Ava should answer project-specific content questions.",
                payload={
                    "task": "Summarize the current campaign.",
                    "client_id": state.client_id,
                    "project_id": state.project_id,
                    "project_context": state.project_context,
                },
                confidence=0.91,
                needs_human_review=False,
            ),
            "final_output": {"agent": "ava", "content": "Project-specific summary."},
        }


class NathanProjectContextTests(unittest.TestCase):
    def test_nathan_endpoint_includes_project_context_when_project_id_is_provided(self):
        project_context = {
            "id": "ramair-straight-from-the-hart",
            "name": "Straight from the Hart Content Engine",
            "client": {"id": "ramair", "name": "RamAir"},
            "approvals": [{"status": "pending"}],
        }

        with patch("app.main.get_project_context", return_value=project_context):
            with patch("app.main.get_graph", return_value=FakeGraph()):
                with patch("app.main.record_agent_event", return_value=None):
                    client = TestClient(app)
                    response = client.post(
                        "/nathan",
                        json={
                            "message": "Summarize the current campaign.",
                            "client_id": "ramair",
                            "project_id": "ramair-straight-from-the-hart",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["project_id"], "ramair-straight-from-the-hart")
        self.assertEqual(payload["project_context"]["client"]["name"], "RamAir")
        self.assertEqual(payload["route_decision"]["payload"]["project_context"]["approvals"][0]["status"], "pending")

    def test_nathan_endpoint_returns_404_for_missing_project_context(self):
        with patch("app.main.get_project_context", return_value=None):
            client = TestClient(app)
            response = client.post(
                "/nathan",
                json={
                    "message": "Summarize the current campaign.",
                    "client_id": "ramair",
                    "project_id": "missing",
                },
            )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
