import os
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agents.router import RouteDecision
from app.main import app
from app.teams import (
    TeamsSettings,
    approval_to_teams_card,
    get_teams_settings,
    get_bot_framework_token,
    graph_files_target_from_teams_activity,
    grounded_project_reply,
    is_meeting_note_publish_request,
    nathan_response_to_text,
    normalize_teams_message,
    parse_meeting_note_publish_command,
    strip_bot_mentions,
    teams_message_from_activity,
    teams_status,
)


class FakeGraph:
    async def ainvoke(self, state):
        return {
            "route_decision": RouteDecision(
                target_agent="ava",
                reason="Ava should summarize the project for Teams.",
                payload={
                    "task": state.messages[-1].content,
                    "client_id": state.client_id,
                    "project_id": state.project_id,
                },
                confidence=0.9,
                needs_human_review=False,
            ),
            "final_output": {"agent": "ava", "content": "Teams-ready project summary."},
        }


class TeamsTests(unittest.TestCase):
    def test_settings_use_microsoft_tenant_fallback(self):
        with patch.dict(
            os.environ,
            {
                "TEAMS_APP_ID": "teams-app",
                "TEAMS_APP_PASSWORD": "teams-password",
                "MICROSOFT_TENANT_ID": "tenant",
            },
            clear=True,
        ):
            settings = get_teams_settings()

        self.assertTrue(settings.configured)
        self.assertEqual(settings.tenant_id, "tenant")

    def test_status_does_not_expose_password(self):
        status = teams_status(
            TeamsSettings(
                app_id="app",
                app_password="password",
                tenant_id="tenant",
                webhook_secret="secret",
            )
        )

        self.assertTrue(status["configured"])
        self.assertTrue(status["webhook_secret_configured"])
        self.assertNotIn("app_password", status)

    def test_normalize_teams_message(self):
        self.assertEqual(normalize_teams_message("  Nathan,\n\nsummarize   this  "), "Nathan, summarize this")

    def test_strip_bot_mentions(self):
        text = '<at>ParlayVU</at> Nathan, summarize RamAir.'
        entities = [
            {
                "type": "mention",
                "text": "<at>ParlayVU</at>",
                "mentioned": {"id": "bot-id", "name": "ParlayVU"},
            }
        ]

        self.assertEqual(strip_bot_mentions(text, entities), "Nathan, summarize RamAir.")

    def test_meeting_note_publish_command_parser(self):
        text = "Nathan, publish meeting note to OneNote\nTitle: RamAir Weekly\nSummary: Decisions and next steps."

        self.assertTrue(is_meeting_note_publish_request(text))
        command = parse_meeting_note_publish_command(text)

        self.assertEqual(command["title"], "RamAir Weekly")
        self.assertEqual(command["summary"], "Decisions and next steps.")

    def test_meeting_note_publish_command_parser_accepts_user_phrase(self):
        text = (
            "publish meeting note to OneNote: Test meeting note for RamAir. Client confirmed weekly campaign "
            "summaries and a follow-up interview plan."
        )

        self.assertTrue(is_meeting_note_publish_request(text))
        command = parse_meeting_note_publish_command(text)

        self.assertEqual(command["title"], "RamAir Meeting Notes")
        self.assertEqual(
            command["summary"],
            "Test meeting note for RamAir. Client confirmed weekly campaign summaries and a follow-up interview plan.",
        )

    def test_meeting_note_publish_command_parser_accepts_files_target(self):
        text = "Nathan, publish meeting note to Files Title: RamAir Weekly Summary: Decisions and next steps."

        self.assertTrue(is_meeting_note_publish_request(text))
        command = parse_meeting_note_publish_command(text)

        self.assertEqual(command["target"], "files")
        self.assertEqual(command["title"], "RamAir Weekly")
        self.assertEqual(command["summary"], "Decisions and next steps.")

    def test_meeting_note_publish_command_parser_accepts_single_line_live_files_shape(self):
        text = (
            "Nathan, publish meeting note to Files Title: RamAir Weekly Meeting "
            "Summary: Client-approved recap and next steps."
        )

        self.assertTrue(is_meeting_note_publish_request(text))
        command = parse_meeting_note_publish_command(text)

        self.assertEqual(command["target"], "files")
        self.assertEqual(command["title"], "RamAir Weekly Meeting")
        self.assertEqual(command["summary"], "Client-approved recap and next steps.")

    def test_graph_files_target_ignores_thread_id_team_values(self):
        target = graph_files_target_from_teams_activity(
            "19:69-deGgFVN6FlIU8A06A6S-g6pROzT8TgHy-U_A3sNs1@thread.tacv2",
            "19:69-deGgFVN6FlIU8A06A6S-g6pROzT8TgHy-U_A3sNs1@thread.tacv2",
        )

        self.assertEqual(target, {"team_id": None, "channel_id": None})

    def test_teams_message_from_bot_framework_activity_infers_ramair(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, summarize the RamAir campaign.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1"},
            },
        }

        request = teams_message_from_activity(activity)

        self.assertEqual(request["text"], "Nathan, summarize the RamAir campaign.")
        self.assertEqual(request["client_id"], "ramair")
        self.assertEqual(request["project_id"], "ramair-straight-from-the-hart")
        self.assertEqual(request["conversation_id"], "conversation-1")

    def test_nathan_response_to_text_prefers_final_output_content(self):
        response = {
            "final_output": {"content": "Here is the Teams-ready answer."},
            "route_decision": {"reason": "Route reason."},
        }

        self.assertEqual(nathan_response_to_text(response), "Here is the Teams-ready answer.")

    def test_grounded_project_reply_uses_memory_and_disclaims_missing_metrics(self):
        project_context = {
            "id": "ramair-straight-from-the-hart",
            "client_id": "ramair",
            "name": "Straight from the Hart Content Engine",
            "objective": "Turn each weekly podcast episode into a coordinated campaign.",
            "client": {"name": "RamAir"},
            "source_assets": [{"id": "source-1"}],
            "generated_outputs": [{"id": "output-1"}],
        }
        approvals = [
            {
                "id": "approval-1",
                "status": "pending",
                "decision_notes": "Demo approval gate for publishing/deployment actions.",
                "metadata": {"title": "Weekly episode campaign kit", "action_type": "approval"},
            }
        ]

        reply = grounded_project_reply(project_context, approvals)

        self.assertIn("Straight from the Hart Content Engine", reply)
        self.assertIn("Weekly episode campaign kit", reply)
        self.assertIn("Memory: 1 source asset(s), 1 generated output(s)", reply)
        self.assertIn("Pending approvals (1)", reply)
        self.assertIn("Approval ID: approval-1", reply)
        self.assertIn("Next safe step", reply)
        self.assertIn("I do not have stored support for budgets", reply)
        self.assertNotIn("$1.85", reply)
        self.assertNotIn("99.7", reply)
        self.assertNotIn("$4.2", reply)

    def test_teams_status_endpoint(self):
        client = TestClient(app)
        response = client.get("/teams/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("configured", response.json())

    def test_teams_message_endpoint_routes_to_nathan(self):
        # Post-Track-4: direct-API Teams messages go through Nathan's tool-loop
        # (run_nathan_conversation) with surface="teams_chat". The response
        # shape no longer carries the LangGraph `nathan` dict — it has
        # `nathan_text` (the final tool-loop output text).
        from unittest.mock import AsyncMock

        with patch("app.main.get_teams_channel_binding", return_value=None), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="Nathan's text reply.")) as nathan_call, \
             patch("app.main.record_agent_event", return_value=None) as record_event:
            client = TestClient(app)
            response = client.post(
                "/teams/messages",
                json={
                    "text": " Nathan, summarize the current campaign. ",
                    "from_user": "dave@parlayvu.ai",
                    "conversation_id": "conversation-1",
                    "team_id": "team-1",
                    "channel_id": "channel-1",
                    "client_id": "ramair",
                    "project_id": "ramair-straight-from-the-hart",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "routed")
        self.assertEqual(payload["channel"], "teams")
        self.assertEqual(payload["nathan_text"], "Nathan's text reply.")
        nathan_call.assert_awaited_once()
        self.assertEqual(nathan_call.await_args.kwargs["client_id"], "ramair")
        self.assertEqual(nathan_call.await_args.kwargs["surface"], "teams_chat")
        record_event.assert_called_once()
        self.assertEqual(record_event.call_args.kwargs["channel"], "teams")
        self.assertEqual(record_event.call_args.kwargs["payload"]["conversation_id"], "conversation-1")

    def test_teams_message_endpoint_replies_to_bot_framework_activity(self):
        # Post-Track-4: Bot Framework activities go through Nathan's tool-loop;
        # the reply text IS Nathan's response (no more grounded_project_reply
        # formatter / list_approvals call).
        from unittest.mock import AsyncMock

        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, summarize the RamAir campaign.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1"},
            },
        }

        with patch("app.main.get_teams_channel_binding", return_value=None), \
             patch("app.main.record_agent_event", return_value=None), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="Here's the RamAir summary in chat form.")), \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)) as send_reply:
            client = TestClient(app)
            response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "replied")
        send_reply.assert_awaited_once()
        self.assertEqual(send_reply.await_args.args[0]["id"], "activity-1")
        self.assertEqual(send_reply.await_args.args[1], "Here's the RamAir summary in chat form.")

    def test_teams_message_endpoint_uses_channel_binding(self):
        # Post-Track-4: channel binding still resolves client_id, and Nathan's
        # tool-loop is called with that client_id. The old list_approvals
        # call is gone (Nathan calls get_project_context himself if relevant).
        from unittest.mock import AsyncMock

        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, summarize this channel.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }
        binding = {"client_id": "ramair", "project_id": "ramair-straight-from-the-hart"}

        with patch("app.main.get_teams_channel_binding", return_value=binding), \
             patch("app.main.record_agent_event", return_value=None), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="bound reply")) as nathan_call, \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)):
            client = TestClient(app)
            response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "replied")
        nathan_call.assert_awaited_once()
        # Binding overrode client_id from the activity-derived default
        self.assertEqual(nathan_call.await_args.kwargs["client_id"], "ramair")

    def test_teams_message_endpoint_binds_channel_from_command(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, bind this channel to RamAir.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }

        with patch(
            "app.main.bind_teams_channel",
            return_value={"project_id": "ramair-straight-from-the-hart"},
        ) as bind_channel:
            with patch("app.main.send_bot_framework_reply", return_value=None) as send_reply:
                client = TestClient(app)
                response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "bound")
        bind_channel.assert_called_once()
        self.assertEqual(bind_channel.call_args.kwargs["channel_name"], "RamAir")
        self.assertEqual(bind_channel.call_args.kwargs["project_id"], "ramair-straight-from-the-hart")
        self.assertIn("now bound", send_reply.call_args.args[1])

    def test_teams_message_endpoint_publishes_onenote_from_command(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, publish meeting note to OneNote\nTitle: RamAir Weekly\nSummary: Decisions and next steps.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }

        publish_result = {
            "status": "published",
            "page": {"id": "page-1", "title": "RamAir Weekly", "webUrl": "https://onenote.example/page-1"},
            "memory_output_id": "output-1",
            "event_id": "event-1",
        }
        with patch("app.main._publish_onenote_meeting_note", return_value=publish_result) as publish:
            with patch("app.main.send_bot_framework_reply", return_value=None) as send_reply:
                client = TestClient(app)
                response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "published_onenote")
        publish.assert_called_once()
        publish_request = publish.call_args.args[0]
        self.assertEqual(publish_request.title, "RamAir Weekly")
        self.assertEqual(publish_request.summary, "Decisions and next steps.")
        self.assertEqual(publish_request.source_conversation_id, "conversation-1")
        self.assertIn("https://onenote.example/page-1", send_reply.call_args.args[1])

    def test_teams_message_endpoint_publishes_files_from_command(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, publish meeting note to Files\nTitle: RamAir Weekly\nSummary: Decisions and next steps.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }

        publish_result = {
            "status": "published",
            "files": {
                "markdown": {"id": "md-1", "webUrl": "https://sharepoint.example/ramair-weekly.md"},
                "docx": {"id": "docx-1", "webUrl": "https://sharepoint.example/ramair-weekly.docx"},
            },
            "docx_template": {
                "status": "fallback",
                "path": "template.docx",
                "fallback_reason": "Template file was not found at the configured SharePoint path",
            },
            "memory_output_id": "output-1",
            "event_id": "event-1",
        }
        with patch("app.main._publish_files_meeting_note", return_value=publish_result) as publish:
            with patch("app.main.send_bot_framework_reply", return_value=None) as send_reply:
                client = TestClient(app)
                response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "published_files")
        publish.assert_called_once()
        publish_request = publish.call_args.args[0]
        self.assertEqual(publish_request.title, "RamAir Weekly")
        self.assertEqual(publish_request.summary, "Decisions and next steps.")
        self.assertEqual(publish_request.client_name, "RamAir")
        self.assertEqual(publish_request.source_conversation_id, "conversation-1")
        self.assertIn("https://sharepoint.example/ramair-weekly.docx", send_reply.call_args.args[1])
        self.assertIn("generated DOCX fallback", send_reply.call_args.args[1])
        self.assertIn("Template file was not found at the configured SharePoint path", send_reply.call_args.args[1])
        self.assertIn("Expected template path: template.docx", send_reply.call_args.args[1])

    def test_teams_files_publish_uses_bound_project_and_channel_label(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": "<at>ParlayVU</at> Nathan, publish meeting note to Files Title: RamAir Weekly Summary: Decisions.",
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }
        binding = {
            "client_id": "ramair",
            "project_id": "ramair-straight-from-the-hart",
        }
        publish_result = {
            "status": "published",
            "files": {
                "markdown": {"id": "md-1", "webUrl": "https://sharepoint.example/ramair-weekly.md"},
                "docx": {"id": "docx-1", "webUrl": "https://sharepoint.example/ramair-weekly.docx"},
            },
            "memory_output_id": "output-1",
            "event_id": "event-1",
        }

        with patch("app.main.get_teams_channel_binding", return_value=binding):
            with patch("app.main._publish_files_meeting_note", return_value=publish_result) as publish:
                with patch("app.main.send_bot_framework_reply", return_value=None):
                    client = TestClient(app)
                    response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "published_files")
        publish_request = publish.call_args.args[0]
        self.assertEqual(publish_request.client_id, "ramair")
        self.assertEqual(publish_request.client_name, "RamAir")
        self.assertEqual(publish_request.project_id, "ramair-straight-from-the-hart")

    def test_teams_message_endpoint_omits_thread_id_team_for_files_publish(self):
        thread_id = "19:69-deGgFVN6FlIU8A06A6S-g6pROzT8TgHy-U_A3sNs1@thread.tacv2"
        activity = {
            "type": "message",
            "id": "1779119777415",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": (
                "<at>ParlayVU</at> Nathan, publish meeting note to Files Title: RamAir Weekly Meeting "
                "Summary: Client-approved recap and next steps."
            ),
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": f"{thread_id};messageid=1779119777415"},
            "channelData": {
                "team": {"id": thread_id},
                "channel": {"id": thread_id, "name": "RamAir"},
            },
        }
        publish_result = {
            "status": "published",
            "files": {
                "markdown": {"id": "md-1", "webUrl": "https://sharepoint.example/ramair-weekly.md"},
                "docx": {"id": "docx-1", "webUrl": "https://sharepoint.example/ramair-weekly.docx"},
            },
            "memory_output_id": "output-1",
            "event_id": "event-1",
        }

        with patch("app.main._publish_files_meeting_note", return_value=publish_result) as publish:
            with patch("app.main.send_bot_framework_reply", return_value=None):
                client = TestClient(app)
                response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "published_files")
        publish_request = publish.call_args.args[0]
        self.assertEqual(publish_request.title, "RamAir Weekly Meeting")
        self.assertEqual(publish_request.summary, "Client-approved recap and next steps.")
        self.assertIsNone(publish_request.team_id)
        self.assertIsNone(publish_request.channel_id)

    def test_teams_message_endpoint_publishes_onenote_from_user_phrase(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": (
                "<at>ParlayVU</at> publish meeting note to OneNote: Test meeting note for RamAir. Client confirmed "
                "weekly campaign summaries and a follow-up interview plan."
            ),
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }
        publish_result = {
            "status": "published",
            "page": {"id": "page-1", "title": "RamAir Meeting Notes", "webUrl": "https://onenote.example/page-1"},
            "memory_output_id": "output-1",
            "event_id": "event-1",
        }

        with patch("app.main._publish_onenote_meeting_note", return_value=publish_result) as publish:
            with patch("app.main.send_bot_framework_reply", return_value=None) as send_reply:
                client = TestClient(app)
                response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "published_onenote")
        publish_request = publish.call_args.args[0]
        self.assertEqual(publish_request.title, "RamAir Meeting Notes")
        self.assertEqual(
            publish_request.summary,
            "Test meeting note for RamAir. Client confirmed weekly campaign summaries and a follow-up interview plan.",
        )
        self.assertEqual(publish_request.client_id, "ramair")
        self.assertIn("https://onenote.example/page-1", send_reply.call_args.args[1])

    def test_teams_message_endpoint_replies_when_onenote_publish_fails(self):
        activity = {
            "type": "message",
            "id": "activity-1",
            "serviceUrl": "https://smba.trafficmanager.net/amer/",
            "text": (
                "<at>ParlayVU</at> publish meeting note to OneNote: Test meeting note for RamAir. Client confirmed "
                "weekly campaign summaries and a follow-up interview plan."
            ),
            "entities": [
                {
                    "type": "mention",
                    "text": "<at>ParlayVU</at>",
                    "mentioned": {"id": "bot-id", "name": "ParlayVU"},
                }
            ],
            "from": {"id": "user-1", "name": "David Baker"},
            "recipient": {"id": "bot-id", "name": "ParlayVU"},
            "conversation": {"id": "conversation-1"},
            "channelData": {
                "team": {"id": "team-1"},
                "channel": {"id": "channel-1", "name": "RamAir"},
            },
        }

        with patch("app.main._publish_onenote_meeting_note", side_effect=RuntimeError("Graph unavailable")):
            with patch("app.main.send_bot_framework_reply", return_value=None) as send_reply:
                client = TestClient(app)
                response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "publish_failed")
        send_reply.assert_called_once()
        self.assertIn("recognized the OneNote meeting note command", send_reply.call_args.args[1])

    def test_teams_message_endpoint_requires_text(self):
        client = TestClient(app)
        response = client.post("/teams/messages", json={"text": "   "})

        self.assertEqual(response.status_code, 400)

    def test_approval_to_teams_card(self):
        card = approval_to_teams_card(
            {
                "id": "approval-1",
                "project_id": "project-1",
                "status": "pending",
                "requested_by_agent": "dylan",
                "decision_notes": "Deploy needs approval.",
                "metadata": {"title": "Deploy landing page", "action_type": "deploy_site"},
                "generated_output": {"id": "output-1", "title": "Landing page"},
                "created_at": "2026-05-17T16:00:00Z",
            }
        )

        self.assertEqual(card["approval_id"], "approval-1")
        self.assertEqual(card["title"], "Deploy landing page")
        self.assertEqual(card["facts"]["action_type"], "deploy_site")
        self.assertEqual(card["actions"][0]["id"], "approved")

    def test_teams_approval_cards_endpoint(self):
        approval = {
            "id": "approval-1",
            "project_id": "ramair-straight-from-the-hart",
            "status": "pending",
            "requested_by_agent": "dylan",
            "metadata": {"title": "Deploy landing page", "action_type": "deploy_site"},
            "generated_output": None,
            "created_at": "2026-05-17T16:00:00Z",
        }

        with patch("app.main.list_approvals", return_value=[approval]) as list_approvals:
            client = TestClient(app)
            response = client.get("/teams/approval-cards?project_id=ramair-straight-from-the-hart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cards"][0]["approval_id"], "approval-1")
        list_approvals.assert_called_once_with(project_id="ramair-straight-from-the-hart", status="pending")

    def test_teams_approval_decision_endpoint(self):
        approval = {
            "id": "approval-1",
            "project_id": "ramair-straight-from-the-hart",
            "status": "approved",
            "requested_by_agent": "dylan",
            "approver": "dave@parlayvu.ai",
            "metadata": {"title": "Deploy landing page", "action_type": "deploy_site"},
            "generated_output": None,
            "created_at": "2026-05-17T16:00:00Z",
        }

        with patch("app.main.decide_approval", return_value=approval) as decide:
            with patch("app.main.record_agent_event", return_value=None) as record_event:
                client = TestClient(app)
                response = client.post(
                    "/teams/approvals/approval-1/decision",
                    json={
                        "status": "approved",
                        "approver": "dave@parlayvu.ai",
                        "decision_notes": "Approved.",
                        "conversation_id": "conversation-1",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "decision_recorded")
        self.assertEqual(response.json()["card"]["approval_id"], "approval-1")
        decide.assert_called_once()
        record_event.assert_called_once()

    def test_teams_approval_decision_endpoint_returns_404(self):
        with patch("app.main.decide_approval", return_value=None):
            client = TestClient(app)
            response = client.post(
                "/teams/approvals/missing/decision",
                json={"status": "approved", "approver": "dave@parlayvu.ai"},
            )

        self.assertEqual(response.status_code, 404)


class TeamsAsyncTests(IsolatedAsyncioTestCase):
    async def test_bot_framework_token_uses_configured_tenant(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"access_token": "token"}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.post_calls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, data):
                self.post_calls.append((url, data))
                FakeClient.last_url = url
                return FakeResponse()

        with patch("app.teams.httpx.AsyncClient", FakeClient):
            token = await get_bot_framework_token(
                TeamsSettings(
                    app_id="app-id",
                    app_password="secret",
                    tenant_id="tenant-id",
                    webhook_secret="webhook",
                )
            )

        self.assertEqual(token, "token")
        self.assertIn("/tenant-id/oauth2/v2.0/token", FakeClient.last_url)


if __name__ == "__main__":
    unittest.main()
