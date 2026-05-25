"""Tests for app/client_config.py — the per-client YAML loader that
replaced the singleton M365 env vars.
"""
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import client_config
from app.client_config import (
    ClientConfigError,
    clear_client_config_cache,
    list_clients,
    load_client_config,
)


class ClientConfigTests(unittest.TestCase):

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = patch.object(client_config, "CLIENT_ARTIFACTS_ROOT", self.root)
        self._patch.start()
        clear_client_config_cache()

    def tearDown(self):
        self._patch.stop()
        clear_client_config_cache()
        self._tmp.cleanup()

    def _write(self, client_id: str, body: str) -> None:
        client_dir = self.root / client_id
        client_dir.mkdir(parents=True, exist_ok=True)
        (client_dir / "config.yaml").write_text(textwrap.dedent(body), encoding="utf-8")

    def test_load_happy_path_returns_all_fields(self):
        self._write(
            "acme",
            """
            client_id: acme
            display_name: "Acme Corp"
            teams:
              team_id: "team-xyz"
              channel_id: "19:channel@thread.tacv2"
              meeting_notes_folder: "03_Deliverables/Notes"
              template_path: "Templates/AcmeNotes.docx"
            preferences:
              pronunciation:
                Acme: "AK-mee"
              tone: "Friendly but direct."
              authorized_contacts:
                - matt@acme.com
                - sara@acme.com
            """,
        )

        cfg = load_client_config("acme")

        self.assertEqual(cfg.client_id, "acme")
        self.assertEqual(cfg.display_name, "Acme Corp")
        self.assertEqual(cfg.teams.team_id, "team-xyz")
        self.assertEqual(cfg.teams.channel_id, "19:channel@thread.tacv2")
        self.assertEqual(cfg.teams.meeting_notes_folder, "03_Deliverables/Notes")
        self.assertEqual(cfg.teams.template_path, "Templates/AcmeNotes.docx")
        self.assertEqual(cfg.preferences.pronunciation, {"Acme": "AK-mee"})
        self.assertEqual(cfg.preferences.tone, "Friendly but direct.")
        self.assertEqual(cfg.preferences.authorized_contacts, ["matt@acme.com", "sara@acme.com"])

    def test_missing_file_raises_clear_error(self):
        with self.assertRaises(ClientConfigError) as ctx:
            load_client_config("ghost")
        self.assertIn("ghost", str(ctx.exception))
        self.assertIn("config.yaml", str(ctx.exception))

    def test_missing_team_id_or_channel_id_raises(self):
        self._write(
            "halfwired",
            """
            client_id: halfwired
            display_name: "Half Wired"
            teams:
              team_id: ""
              channel_id: "19:channel@thread.tacv2"
            preferences: {}
            """,
        )
        with self.assertRaises(ClientConfigError) as ctx:
            load_client_config("halfwired")
        self.assertIn("team_id", str(ctx.exception))

    def test_mismatched_client_id_in_file_raises(self):
        self._write(
            "alpha",
            """
            client_id: beta
            display_name: "Beta"
            teams:
              team_id: "t"
              channel_id: "c"
            """,
        )
        with self.assertRaises(ClientConfigError) as ctx:
            load_client_config("alpha")
        self.assertIn("beta", str(ctx.exception))

    def test_malformed_yaml_raises(self):
        self._write("broken", "client_id: [unterminated\n")
        with self.assertRaises(ClientConfigError) as ctx:
            load_client_config("broken")
        self.assertIn("Malformed YAML", str(ctx.exception))

    def test_list_clients_returns_sorted_ids_with_config(self):
        self._write("zeta", "client_id: zeta\nteams:\n  team_id: t\n  channel_id: c\n")
        self._write("alpha", "client_id: alpha\nteams:\n  team_id: t\n  channel_id: c\n")
        # A folder without config.yaml should not be listed
        (self.root / "no_config_yet").mkdir()

        self.assertEqual(list_clients(), ["alpha", "zeta"])

    def test_empty_client_id_raises(self):
        with self.assertRaises(ClientConfigError):
            load_client_config("")
        with self.assertRaises(ClientConfigError):
            load_client_config("   ")

    def test_defaults_applied_when_optional_fields_missing(self):
        self._write(
            "minimal",
            """
            client_id: minimal
            display_name: "Minimal Client"
            teams:
              team_id: t
              channel_id: c
            """,
        )
        cfg = load_client_config("minimal")
        self.assertEqual(cfg.teams.meeting_notes_folder, "03_Deliverables/Meeting Notes")
        self.assertEqual(cfg.teams.template_path, "")
        self.assertEqual(cfg.preferences.pronunciation, {})
        self.assertIsNone(cfg.preferences.tone)
        self.assertEqual(cfg.preferences.authorized_contacts, [])


if __name__ == "__main__":
    unittest.main()
