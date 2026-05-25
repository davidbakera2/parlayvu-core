"""Verifies that publish_meeting_notes_to_teams routes per-client config
(team_id, channel_id, folder, template) correctly when the caller does
not pass those explicitly. This is the core multi-client invariant: two
different client_ids must publish to two different Teams channels with
two different templates, with no env-var fallback.
"""
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.client_config import (
    ClientConfig,
    ClientPreferences,
    TeamsConfig,
    clear_client_config_cache,
)
from app.microsoft365 import Microsoft365Settings
from app.services import meeting_notes_service
from app.services.meeting_notes_service import publish_meeting_notes_to_teams


_NO_LOCAL_ARTIFACTS = Path("__no_local_artifacts_for_per_client_tests__")


def _fake_graph_client():
    graph_client = AsyncMock()
    graph_client.settings = Microsoft365Settings(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        graph_scope="scope",
        webhook_client_state="state",
        allow_send=False,
        agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
    )
    graph_client.download_teams_channel_file.side_effect = RuntimeError(
        "template missing — falls back to generated DOCX, which is fine for this test"
    )
    graph_client.upload_teams_channel_file.side_effect = [
        {"id": "md", "name": "x.md", "webUrl": "https://sharepoint.example/x.md"},
        {"id": "docx", "name": "x.docx", "webUrl": "https://sharepoint.example/x.docx"},
    ]
    return graph_client


def _fake_config(client_id: str, *, team_id: str, channel_id: str, template_path: str, folder: str) -> ClientConfig:
    return ClientConfig(
        client_id=client_id,
        display_name=client_id.title(),
        teams=TeamsConfig(
            team_id=team_id,
            channel_id=channel_id,
            meeting_notes_folder=folder,
            template_path=template_path,
        ),
        preferences=ClientPreferences(),
    )


class PerClientPublishingTests(unittest.TestCase):

    def setUp(self):
        clear_client_config_cache()

    def tearDown(self):
        clear_client_config_cache()

    def _publish(self, client_id: str, config: ClientConfig):
        graph_client = _fake_graph_client()
        with patch.object(
            meeting_notes_service, "load_client_config", return_value=config
        ), patch.object(
            meeting_notes_service, "MicrosoftGraphClient", return_value=graph_client
        ), patch.object(
            meeting_notes_service, "_ARTIFACTS_ROOT", _NO_LOCAL_ARTIFACTS
        ), patch.object(
            meeting_notes_service, "record_generated_output", return_value="out-1"
        ), patch.object(
            meeting_notes_service, "record_agent_event", return_value="evt-1"
        ):
            asyncio.run(
                publish_meeting_notes_to_teams(
                    title="Sync",
                    summary="Discussed the work.",
                    client_id=client_id,
                )
            )
        return graph_client

    def test_ramair_routes_to_ramair_team_and_channel(self):
        config = _fake_config(
            "ramair",
            team_id="ramair-team",
            channel_id="ramair-channel",
            template_path="00_Client_Brief/Templates/RamAir Meeting Notes Template.docx",
            folder="03_Deliverables/Meeting Notes",
        )
        graph = self._publish("ramair", config)

        # Both upload calls should land in RamAir's team + channel + folder
        for call in graph.upload_teams_channel_file.await_args_list:
            self.assertEqual(call.kwargs["team_id"], "ramair-team")
            self.assertEqual(call.kwargs["channel_id"], "ramair-channel")
            self.assertEqual(call.kwargs["folder_path"], "03_Deliverables/Meeting Notes")

    def test_christshope_routes_to_its_own_team_and_channel(self):
        config = _fake_config(
            "christshope",
            team_id="ch-team",
            channel_id="ch-channel",
            template_path="00_Client_Brief/Templates/Christs Hope Meeting Notes Template.docx",
            folder="03_Deliverables/CH Notes",
        )
        graph = self._publish("christshope", config)

        for call in graph.upload_teams_channel_file.await_args_list:
            self.assertEqual(call.kwargs["team_id"], "ch-team")
            self.assertEqual(call.kwargs["channel_id"], "ch-channel")
            self.assertEqual(call.kwargs["folder_path"], "03_Deliverables/CH Notes")

    def test_explicit_team_id_override_wins_over_config(self):
        """Passing team_id/channel_id explicitly should bypass the per-client
        config — useful for ad-hoc one-off publishes and existing HTTP endpoint
        callers that already know the target channel."""
        config = _fake_config(
            "ramair",
            team_id="config-team",
            channel_id="config-channel",
            template_path="t.docx",
            folder="default-folder",
        )
        graph_client = _fake_graph_client()
        with patch.object(
            meeting_notes_service, "load_client_config", return_value=config
        ), patch.object(
            meeting_notes_service, "MicrosoftGraphClient", return_value=graph_client
        ), patch.object(
            meeting_notes_service, "_ARTIFACTS_ROOT", _NO_LOCAL_ARTIFACTS
        ), patch.object(
            meeting_notes_service, "record_generated_output", return_value="out-1"
        ), patch.object(
            meeting_notes_service, "record_agent_event", return_value="evt-1"
        ):
            asyncio.run(
                publish_meeting_notes_to_teams(
                    title="Sync",
                    summary="Body.",
                    client_id="ramair",
                    team_id="override-team",
                    channel_id="override-channel",
                    folder_path="override-folder",
                )
            )

        for call in graph_client.upload_teams_channel_file.await_args_list:
            self.assertEqual(call.kwargs["team_id"], "override-team")
            self.assertEqual(call.kwargs["channel_id"], "override-channel")
            self.assertEqual(call.kwargs["folder_path"], "override-folder")

    def test_missing_template_path_in_config_raises(self):
        config = _fake_config(
            "ramair",
            team_id="t",
            channel_id="c",
            template_path="",  # not configured
            folder="f",
        )
        with patch.object(meeting_notes_service, "load_client_config", return_value=config):
            with self.assertRaises(ValueError) as ctx:
                asyncio.run(
                    publish_meeting_notes_to_teams(
                        title="Sync", summary="Body.", client_id="ramair"
                    )
                )
        self.assertIn("template_path", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
