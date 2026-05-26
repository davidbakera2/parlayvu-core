"""Tests for Track 4: Teams chat routed through Nathan's unified tool-loop.

Covers:
  - Surface parameterization in nathan_llm prompt assembly
  - Teams handler routes to run_nathan_conversation with surface=teams_chat
  - 1:1 DM authorized-contacts gate (allow / block / channel-skip)
  - Attachment extraction + download + save + injection into Nathan message
  - is_one_to_one_dm discrimination heuristic
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.client_config import (
    ClientConfig,
    ClientPreferences,
    TeamsConfig,
    clear_client_config_cache,
)
from app.main import _is_authorized_dm_sender, app
from app.nathan_llm import (
    NATHAN_BASE_SYSTEM,
    NATHAN_TAVUS_SURFACE_RULES,
    NATHAN_TEAMS_CHAT_SURFACE_RULES,
    _openai_messages_to_anthropic,
)
from app.teams import (
    extract_teams_attachments,
    is_one_to_one_dm,
)


def _channel_activity(text: str = "Hello Nathan", from_user: str = "matt@ulcannarbor.org") -> dict:
    return {
        "type": "message",
        "id": "activity-1",
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "text": text,
        "from": {"id": "user-1", "name": "Matt", "userPrincipalName": from_user},
        "recipient": {"id": "bot-id", "name": "ParlayVU"},
        "conversation": {"id": "conv-1"},
        "channelData": {
            "team": {"id": "team-1"},
            "channel": {"id": "channel-1", "name": "RamAir"},
        },
    }


def _dm_activity(text: str = "Hello Nathan", from_user: str = "matt@ulcannarbor.org") -> dict:
    return {
        "type": "message",
        "id": "activity-2",
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
        "text": text,
        "from": {"id": "user-1", "name": "Matt", "userPrincipalName": from_user},
        "recipient": {"id": "bot-id", "name": "ParlayVU"},
        "conversation": {"id": "conv-2", "conversationType": "personal"},
        # No channelData.team or channel
    }


class SurfaceParameterizationTests(unittest.TestCase):
    def test_tavus_surface_includes_voice_rules_only(self):
        system, _ = _openai_messages_to_anthropic(
            [{"role": "user", "content": "hi"}], surface="tavus"
        )
        # Base content present
        self.assertIn("Nathan Ellis", system)
        # Tavus rules present
        self.assertIn("spoken-word natural", system)
        self.assertIn("NARRATE WHILE YOU WORK", system)
        # Teams chat rules NOT present
        self.assertNotIn("Markdown is FINE", system)

    def test_teams_chat_surface_includes_chat_rules_only(self):
        system, _ = _openai_messages_to_anthropic(
            [{"role": "user", "content": "hi"}], surface="teams_chat"
        )
        self.assertIn("Nathan Ellis", system)
        self.assertIn("Markdown is FINE", system)
        self.assertIn("asynchronous text", system)
        self.assertNotIn("spoken-word natural", system)
        self.assertNotIn("NARRATE WHILE YOU WORK", system)

    def test_default_surface_is_tavus_for_backcompat(self):
        # Existing callers that don't pass `surface` should get Tavus rules
        # (preserve pre-Track-4 behavior for any unmigrated call site).
        system, _ = _openai_messages_to_anthropic([{"role": "user", "content": "hi"}])
        self.assertIn("spoken-word natural", system)
        self.assertNotIn("Markdown is FINE", system)

    def test_base_system_is_neutral(self):
        # Sanity: the base prompt itself doesn't reference voice OR markdown
        self.assertNotIn("spoken-word natural", NATHAN_BASE_SYSTEM)
        self.assertNotIn("Markdown is FINE", NATHAN_BASE_SYSTEM)
        self.assertIn("Nathan Ellis", NATHAN_BASE_SYSTEM)


class IsOneToOneDmTests(unittest.TestCase):
    def test_channel_post_is_not_dm(self):
        self.assertFalse(is_one_to_one_dm(_channel_activity()))

    def test_dm_with_no_channeldata_is_dm(self):
        self.assertTrue(is_one_to_one_dm(_dm_activity()))

    def test_dm_with_personal_conversationtype_is_dm(self):
        activity = _channel_activity()
        activity["conversation"]["conversationType"] = "personal"
        # Even with channelData, explicit personal type wins
        self.assertTrue(is_one_to_one_dm(activity))


class AuthorizedDmSenderTests(unittest.TestCase):
    def setUp(self):
        clear_client_config_cache()

    def tearDown(self):
        clear_client_config_cache()

    def _config(self, *, allowlist: list[str]) -> ClientConfig:
        return ClientConfig(
            client_id="acme",
            display_name="Acme",
            teams=TeamsConfig(team_id="t", channel_id="c"),
            preferences=ClientPreferences(authorized_contacts=allowlist),
        )

    def test_blocks_when_no_client_id(self):
        self.assertFalse(_is_authorized_dm_sender(None, "matt@acme.com"))

    def test_blocks_when_no_from_user(self):
        with patch("app.client_config.load_client_config", return_value=self._config(allowlist=["matt@acme.com"])):
            self.assertFalse(_is_authorized_dm_sender("acme", None))

    def test_blocks_when_allowlist_empty(self):
        # Fail-closed: empty allowlist = no DM access
        with patch("app.client_config.load_client_config", return_value=self._config(allowlist=[])):
            self.assertFalse(_is_authorized_dm_sender("acme", "matt@acme.com"))

    def test_blocks_when_sender_not_in_allowlist(self):
        with patch("app.client_config.load_client_config", return_value=self._config(allowlist=["matt@acme.com"])):
            self.assertFalse(_is_authorized_dm_sender("acme", "stranger@evil.com"))

    def test_allows_when_sender_in_allowlist(self):
        with patch("app.client_config.load_client_config", return_value=self._config(allowlist=["matt@acme.com"])):
            self.assertTrue(_is_authorized_dm_sender("acme", "matt@acme.com"))

    def test_allow_is_case_insensitive(self):
        with patch("app.client_config.load_client_config", return_value=self._config(allowlist=["Matt@ACME.com"])):
            self.assertTrue(_is_authorized_dm_sender("acme", "matt@acme.com"))


class AttachmentExtractionTests(unittest.TestCase):
    def test_extracts_teams_file_upload(self):
        payload = {
            "attachments": [
                {
                    "name": "report.pdf",
                    "contentType": "application/vnd.microsoft.teams.file.download.info",
                    "content": {
                        "downloadUrl": "https://sharepoint.example/file.pdf",
                        "fileType": "pdf",
                        "fileSize": 12345,
                    },
                }
            ]
        }
        out = extract_teams_attachments(payload)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "report.pdf")
        self.assertEqual(out[0]["content_url"], "https://sharepoint.example/file.pdf")
        self.assertEqual(out[0]["size"], 12345)
        self.assertTrue(out[0]["is_teams_file"])

    def test_skips_attachments_without_url(self):
        payload = {"attachments": [{"name": "x", "contentType": "card", "content": {}}]}
        self.assertEqual(extract_teams_attachments(payload), [])

    def test_empty_attachments_returns_empty(self):
        self.assertEqual(extract_teams_attachments({}), [])
        self.assertEqual(extract_teams_attachments({"attachments": []}), [])


class TeamsHandlerRoutesThroughNathanTests(unittest.TestCase):
    def test_channel_post_routes_to_nathan_tool_loop(self):
        # A Bot Framework channel activity should reach run_nathan_conversation
        # with the right client_id and surface="teams_chat".
        activity = _channel_activity(text="<at>ParlayVU</at> what's RamAir's status?")
        binding = {"client_id": "ramair", "project_id": "ramair-straight-from-the-hart"}

        with patch("app.main.get_teams_channel_binding", return_value=binding), \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)) as send_reply, \
             patch("app.main.record_agent_event", return_value=None), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="Nathan's reply text.")) as nathan_call:
            client = TestClient(app)
            response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "replied")
        nathan_call.assert_awaited_once()
        kwargs = nathan_call.await_args.kwargs
        self.assertEqual(kwargs["client_id"], "ramair")
        self.assertEqual(kwargs["surface"], "teams_chat")
        send_reply.assert_awaited_once()
        # The reply text passed to send_bot_framework_reply is Nathan's
        # tool-loop output, not a routing-decision JSON.
        self.assertEqual(send_reply.await_args.args[1], "Nathan's reply text.")

    def test_unauthorized_dm_is_rejected_without_calling_nathan(self):
        activity = _dm_activity(text="hello", from_user="stranger@evil.com")
        # No binding → client_id stays as the default "ramair" from
        # teams_message_from_activity heuristic, but authorized_contacts
        # for "ramair" is empty in the real config → fail-closed.
        clear_client_config_cache()
        with patch("app.main.get_teams_channel_binding", return_value=None), \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)) as send_reply, \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="should not run")) as nathan_call:
            client = TestClient(app)
            response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unauthorized_dm")
        nathan_call.assert_not_awaited()
        send_reply.assert_awaited_once()
        self.assertIn("authorized contacts", send_reply.await_args.args[1])

    def test_authorized_dm_reaches_nathan(self):
        activity = _dm_activity(text="hi", from_user="matt@acme.com")
        binding = {"client_id": "acme", "project_id": None}
        config = ClientConfig(
            client_id="acme",
            display_name="Acme",
            teams=TeamsConfig(team_id="t", channel_id="c"),
            preferences=ClientPreferences(authorized_contacts=["matt@acme.com"]),
        )
        clear_client_config_cache()
        # _is_authorized_dm_sender imports load_client_config inside its body
        # to avoid a top-level circular import, so patch at the source module.
        with patch("app.main.get_teams_channel_binding", return_value=binding), \
             patch("app.client_config.load_client_config", return_value=config), \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)), \
             patch("app.main.record_agent_event", return_value=None), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="reply")) as nathan_call:
            client = TestClient(app)
            response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "replied")
        nathan_call.assert_awaited_once()

    def test_channel_post_skips_authorized_contacts_check(self):
        # Even when authorized_contacts is empty, a CHANNEL post (not DM)
        # should still reach Nathan — the channel binding implicitly
        # authorizes anyone in the channel.
        activity = _channel_activity(text="hello", from_user="random@anywhere.com")
        binding = {"client_id": "ramair", "project_id": "ramair-straight-from-the-hart"}
        config = ClientConfig(
            client_id="ramair",
            display_name="RamAir",
            teams=TeamsConfig(team_id="t", channel_id="c"),
            preferences=ClientPreferences(authorized_contacts=[]),  # empty
        )
        clear_client_config_cache()
        with patch("app.main.get_teams_channel_binding", return_value=binding), \
             patch("app.client_config.load_client_config", return_value=config), \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)), \
             patch("app.main.record_agent_event", return_value=None), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="reply")) as nathan_call:
            client = TestClient(app)
            response = client.post("/teams/messages", json=activity)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "replied")
        nathan_call.assert_awaited_once()

    def test_attachment_saved_and_path_injected_into_nathan_message(self):
        # Channel post with a file attachment — file lands at the uploads
        # path AND the path appears in the user message Nathan sees.
        activity = _channel_activity(text="see attached")
        activity["attachments"] = [{
            "name": "Q3.pdf",
            "contentType": "application/vnd.microsoft.teams.file.download.info",
            "content": {
                "downloadUrl": "https://sharepoint.example/Q3.pdf",
                "fileType": "pdf",
                "fileSize": 100,
            },
        }]
        binding = {"client_id": "ramair", "project_id": "ramair-straight-from-the-hart"}

        # download_bot_framework_attachment is imported INSIDE
        # _save_teams_attachments, so patch at the source module.
        with patch("app.main.get_teams_channel_binding", return_value=binding), \
             patch("app.main.send_bot_framework_reply", new=AsyncMock(return_value=None)), \
             patch("app.main.record_agent_event", return_value=None), \
             patch("app.teams.download_bot_framework_attachment", new=AsyncMock(return_value=b"fake-pdf-bytes")), \
             patch("app.nathan_llm.run_nathan_conversation", new=AsyncMock(return_value="ok")) as nathan_call:
            client = TestClient(app)
            try:
                response = client.post("/teams/messages", json=activity)
            finally:
                # _save_teams_attachments uses the hardcoded
                # `client_artifacts/<client>/01_Source_Material/uploads/`
                # path, so the test side-effects the real repo. Clean up.
                real_path = Path("client_artifacts/ramair/01_Source_Material/uploads/Q3.pdf")
                if real_path.exists():
                    real_path.unlink()

        self.assertEqual(response.status_code, 200)
        nathan_call.assert_awaited_once()
        messages_arg = nathan_call.await_args.args[0]
        user_text = messages_arg[0]["content"]
        self.assertIn("[Attachments saved", user_text)
        self.assertIn("Q3.pdf", user_text)


if __name__ == "__main__":
    unittest.main()
