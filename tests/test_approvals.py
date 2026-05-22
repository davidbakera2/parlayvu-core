import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.approvals import decide_approval, list_approvals, request_approval, require_approved_approval
from app.database import initialize_database
from app.main import app
from app.models import AgentEvent, Approval, GeneratedOutput
from app.project_memory import ensure_project_context


def build_fake_scope(Session):
    def fake_scope():
        class Scope:
            def __enter__(self):
                self.session = Session()
                return self.session

            def __exit__(self, exc_type, exc, traceback):
                if exc_type:
                    self.session.rollback()
                else:
                    self.session.commit()
                self.session.close()

        return Scope()

    return fake_scope


class ApprovalWorkflowTests(unittest.TestCase):
    def test_request_list_and_decide_approval(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with Session() as session:
            project = ensure_project_context(
                session,
                client_id="ramair",
                project_id="ramair-straight-from-the-hart",
                project_name="Straight from the Hart",
            )
            output = GeneratedOutput(
                project=project,
                agent_name="dylan",
                output_type="astro_site",
                title="Landing page",
                status="generated",
            )
            session.add(output)
            session.commit()
            output_id = output.id

        with patch("app.approvals.session_scope", build_fake_scope(Session)):
            approval = request_approval(
                client_id="ramair",
                project_id="ramair-straight-from-the-hart",
                requested_by_agent="dylan",
                action_type="deploy_site",
                title="Deploy landing page",
                summary="Needs approval before deploy.",
                generated_output_id=output_id,
            )
            approvals = list_approvals(project_id="ramair-straight-from-the-hart", status="pending")
            decided = decide_approval(
                approval_id=approval["id"],
                status="approved",
                approver="dave@parlayvu.ai",
                decision_notes="Approved for demo.",
            )

        self.assertEqual(approval["status"], "pending")
        self.assertEqual(len(approvals), 1)
        self.assertEqual(decided["status"], "approved")
        self.assertEqual(decided["approver"], "dave@parlayvu.ai")

        with Session() as session:
            self.assertEqual(session.query(Approval).count(), 1)
            self.assertEqual(session.query(AgentEvent).count(), 2)
            self.assertEqual(session.get(GeneratedOutput, output_id).status, "approved")

    def test_decision_rejects_invalid_status(self):
        with self.assertRaises(ValueError):
            decide_approval(
                approval_id="approval-id",
                status="pending",
                approver="dave@parlayvu.ai",
            )

    def test_require_approved_approval_validates_status_project_and_action(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with patch("app.approvals.session_scope", build_fake_scope(Session)):
            approval = request_approval(
                client_id="ramair",
                project_id="ramair-straight-from-the-hart",
                requested_by_agent="dylan",
                action_type="deploy_site",
                title="Deploy landing page",
            )
            with self.assertRaises(PermissionError):
                require_approved_approval(
                    approval_id=approval["id"],
                    project_id="ramair-straight-from-the-hart",
                    action_type="deploy_site",
                )
            decide_approval(
                approval_id=approval["id"],
                status="approved",
                approver="dave@parlayvu.ai",
            )
            approved = require_approved_approval(
                approval_id=approval["id"],
                project_id="ramair-straight-from-the-hart",
                action_type="deploy_site",
            )

        self.assertEqual(approved["status"], "approved")


class ApprovalApiTests(unittest.TestCase):
    def test_approval_endpoints(self):
        approval = {
            "id": "approval-1",
            "project_id": "ramair-straight-from-the-hart",
            "status": "pending",
        }
        decided = {**approval, "status": "approved", "approver": "dave@parlayvu.ai"}

        with patch("app.main.request_approval", return_value=approval) as request_fn:
            client = TestClient(app)
            response = client.post(
                "/approvals",
                json={
                    "client_id": "ramair",
                    "project_id": "ramair-straight-from-the-hart",
                    "requested_by_agent": "dylan",
                    "action_type": "deploy_site",
                    "title": "Deploy landing page",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["approval"]["id"], "approval-1")
        request_fn.assert_called_once()

        with patch("app.main.list_approvals", return_value=[approval]) as list_fn:
            client = TestClient(app)
            response = client.get("/approvals?project_id=ramair-straight-from-the-hart&status=pending")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["approvals"][0]["status"], "pending")
        list_fn.assert_called_once_with(project_id="ramair-straight-from-the-hart", status="pending")

        with patch("app.main.decide_approval", return_value=decided):
            client = TestClient(app)
            response = client.post(
                "/approvals/approval-1/decision",
                json={
                    "status": "approved",
                    "approver": "dave@parlayvu.ai",
                    "decision_notes": "Approved.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["approval"]["status"], "approved")

    def test_decision_endpoint_returns_404_for_missing_approval(self):
        with patch("app.main.decide_approval", return_value=None):
            client = TestClient(app)
            response = client.post(
                "/approvals/missing/decision",
                json={"status": "approved", "approver": "dave@parlayvu.ai"},
            )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
