import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.heygen import (
    HeyGenSettings,
    build_live_meeting_session,
    build_live_project_answer,
    get_heygen_settings,
    heygen_status,
    verify_webhook_signature,
)
from app.main import app


class HeyGenTests(unittest.TestCase):
    def _ramair_project_context(self):
        return {
            "id": "ramair-straight-from-the-hart",
            "client_id": "ramair",
            "name": "Straight from the Hart",
            "status": "active",
            "client": {"name": "RamAir"},
            "objective": "Turn one episode into a campaign.",
            "source_assets": [{"id": "source-1", "title": "Podcast episode transcript"}],
            "generated_outputs": [{"id": "output-1", "title": "Weekly campaign kit"}],
            "approvals": [{"id": "approval-1", "status": "pending", "title": "Campaign kit review"}],
        }

    def test_settings_collect_agent_avatars(self):
        with patch.dict(
            os.environ,
            {
                "HEYGEN_API_KEY": "key",
                "HEYGEN_NATHAN_AVATAR_ID": "avatar-nathan",
                "HEYGEN_DYLAN_AVATAR_ID": "avatar-dylan",
            },
            clear=False,
        ):
            settings = get_heygen_settings()

        self.assertTrue(settings.configured)
        self.assertEqual(settings.agent_avatars["nathan"], "avatar-nathan")
        self.assertEqual(settings.agent_avatars["dylan"], "avatar-dylan")

    def test_status_does_not_expose_api_key(self):
        settings = HeyGenSettings(
            api_key="secret",
            base_url="https://api.heygen.com",
            webhook_secret="webhook-secret",
            agent_avatars={"nathan": "avatar-nathan"},
        )

        status = heygen_status(settings)

        self.assertTrue(status["configured"])
        self.assertTrue(status["webhook_secret_configured"])
        self.assertEqual(status["agents"]["nathan"]["avatar_id"], "avatar-nathan")
        self.assertNotIn("api_key", status)

    def test_webhook_signature_verification(self):
        payload = b'{"event":"test"}'
        import hmac
        import hashlib

        signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()

        self.assertTrue(verify_webhook_signature(payload, signature, "secret"))
        self.assertTrue(verify_webhook_signature(payload, f"sha256={signature}", "secret"))
        self.assertFalse(verify_webhook_signature(payload, "bad", "secret"))

    def test_build_live_project_answer_flags_pending_approvals(self):
        project_context = self._ramair_project_context()

        response = build_live_project_answer(
            agent_name="nathan",
            question="What is the campaign status?",
            project_context=project_context,
        )

        self.assertTrue(response["needs_human_review"])
        self.assertEqual(response["grounding"]["pending_approval_count"], 1)
        self.assertIn("RamAir", response["answer"])

    def test_build_live_project_answer_flags_unsupported_metrics(self):
        project_context = self._ramair_project_context()
        project_context["approvals"] = []

        response = build_live_project_answer(
            agent_name="nathan",
            question="What ROI and performance metrics can we share?",
            project_context=project_context,
        )

        self.assertTrue(response["needs_human_review"])
        self.assertTrue(response["grounding"]["unsupported_metric_requested"])
        self.assertIn("do not have approved live performance metrics", response["answer"])

    def test_build_live_meeting_session_returns_provider_agnostic_payload(self):
        project_context = self._ramair_project_context()

        session = build_live_meeting_session(
            agent_name="nathan",
            avatar_id="avatar-nathan",
            project_context=project_context,
            meeting_title="RamAir Teams call",
            heygen_session_id="heygen-1",
            teams_meeting_link="https://teams.example/meeting",
            expected_attendees=["David Hart"],
        )

        self.assertEqual(session["status"], "active")
        self.assertEqual(session["avatar_id"], "avatar-nathan")
        self.assertEqual(session["heygen_session_id"], "heygen-1")
        self.assertEqual(session["project_id"], "ramair-straight-from-the-hart")
        self.assertEqual(session["provider"]["callback_shape"], "POST /heygen/live-meetings/{session_id}/question")

    def test_heygen_status_endpoint(self):
        client = TestClient(app)
        response = client.get("/heygen/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("agents", response.json())

    def test_live_question_endpoint_returns_project_bound_answer(self):
        project_context = self._ramair_project_context()

        with patch("app.main.get_project_context", return_value=project_context):
            with patch("app.main.avatar_for_agent", return_value="avatar-nathan"):
                with patch("app.main.record_agent_event", return_value=None):
                    client = TestClient(app)
                    response = client.post(
                        "/heygen/live-question",
                        json={
                            "agent_name": "nathan",
                            "project_id": "ramair-straight-from-the-hart",
                            "question": "What is the campaign status?",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["avatar_id"], "avatar-nathan")
        self.assertTrue(payload["needs_human_review"])
        self.assertEqual(payload["grounding"]["project_id"], "ramair-straight-from-the-hart")
        self.assertEqual(payload["provider_response"]["spoken_text"], payload["answer"])

    def test_live_meeting_start_endpoint_logs_session_event(self):
        project_context = self._ramair_project_context()

        with patch("app.main.get_project_context", return_value=project_context):
            with patch("app.main.avatar_for_agent", return_value="avatar-nathan"):
                with patch("app.main.record_agent_event", return_value="event-1") as event:
                    client = TestClient(app)
                    response = client.post(
                        "/heygen/live-meetings/start",
                        json={
                            "meeting_title": "RamAir Teams call",
                            "expected_attendees": ["David Hart"],
                            "heygen_session_id": "heygen-1",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "started")
        self.assertEqual(payload["session"]["avatar_id"], "avatar-nathan")
        self.assertEqual(payload["session"]["heygen_session_id"], "heygen-1")
        self.assertEqual(event.call_args.kwargs["event_type"], "live_avatar_meeting_started")

    def test_live_meeting_question_endpoint_uses_path_session(self):
        project_context = self._ramair_project_context()

        with patch("app.main.get_project_context", return_value=project_context):
            with patch("app.main.avatar_for_agent", return_value="avatar-nathan"):
                with patch("app.main.record_agent_event", return_value="event-1") as event:
                    client = TestClient(app)
                    response = client.post(
                        "/heygen/live-meetings/live-123/question",
                        json={
                            "question": "What is the campaign status?",
                            "speaker_name": "David Hart",
                            "provider_event_id": "callback-1",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["session_id"], "live-123")
        self.assertEqual(event.call_args.kwargs["payload"]["session_id"], "live-123")
        self.assertEqual(event.call_args.kwargs["payload"]["provider_event_id"], "callback-1")

    def test_live_meeting_notes_endpoint_publishes_files(self):
        publish = AsyncMock(
            return_value={
                "status": "published",
                "files": {"markdown": {"id": "md-1"}, "docx": {"id": "docx-1"}},
                "memory_output_id": "output-1",
                "event_id": "event-2",
            }
        )

        with patch("app.main._publish_files_meeting_note", publish):
            with patch("app.main.record_agent_event", return_value="event-1") as event:
                client = TestClient(app)
                response = client.post(
                    "/heygen/live-meetings/live-123/notes",
                    json={
                        "title": "RamAir LiveAvatar Meeting Notes",
                        "summary": "Client-approved recap and next actions.",
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "published_files")
        self.assertEqual(payload["notes"]["files"]["docx"]["id"], "docx-1")
        publish.assert_awaited_once()
        publish_request = publish.await_args.args[0]
        self.assertEqual(publish_request.source_conversation_id, "live-123")
        self.assertEqual(publish_request.folder_path, "03_Deliverables/Meeting Notes")
        self.assertEqual(event.call_args.kwargs["event_type"], "live_avatar_meeting_notes_requested")


if __name__ == "__main__":
    unittest.main()
