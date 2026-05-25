"""Verifies that per-client preferences (pronunciation, tone, active client
banner) flow into the system prompt Nathan sees, so the same Nathan brain
behaves differently for RamAir vs Christ's Hope on the same Tavus endpoint.
"""
import unittest
from unittest.mock import patch

from app import nathan_llm
from app.client_config import (
    ClientConfig,
    ClientPreferences,
    TeamsConfig,
    clear_client_config_cache,
)
from app.nathan_llm import _build_client_preferences_context, _openai_messages_to_anthropic


def _config(client_id: str, *, pronunciation=None, tone=None) -> ClientConfig:
    return ClientConfig(
        client_id=client_id,
        display_name={"ramair": "RamAir International", "christshope": "Christ's Hope"}.get(client_id, client_id),
        teams=TeamsConfig(team_id="t", channel_id="c", template_path="x.docx"),
        preferences=ClientPreferences(pronunciation=pronunciation or {}, tone=tone),
    )


class NathanClientPreferenceTests(unittest.TestCase):

    def setUp(self):
        clear_client_config_cache()

    def tearDown(self):
        clear_client_config_cache()

    def test_ramair_pronunciation_appears_in_system_prompt(self):
        config = _config("ramair", pronunciation={"RamAir": "Ram-Air"})
        with patch.object(nathan_llm, "load_client_config", return_value=config):
            system, _ = _openai_messages_to_anthropic(
                [{"role": "user", "content": "hi"}],
                client_id="ramair",
            )
        self.assertIn("RamAir International", system)
        self.assertIn("client_id: ramair", system)
        self.assertIn('"RamAir"', system)
        self.assertIn('"Ram-Air"', system)

    def test_christshope_does_not_leak_ramair_preferences(self):
        ch = _config("christshope", pronunciation={})
        with patch.object(nathan_llm, "load_client_config", return_value=ch):
            system, _ = _openai_messages_to_anthropic(
                [{"role": "user", "content": "hi"}],
                client_id="christshope",
            )
        self.assertIn("Christ's Hope", system)
        self.assertNotIn("Ram-Air", system)
        # The current date block is unrelated; just confirms one base instruction
        # is still present so we know the merge didn't drop anything.
        self.assertIn("Nathan Ellis", system)

    def test_tone_note_included_when_set(self):
        config = _config("ramair", tone="Concise, no filler.")
        with patch.object(nathan_llm, "load_client_config", return_value=config):
            system, _ = _openai_messages_to_anthropic(
                [{"role": "user", "content": "hi"}],
                client_id="ramair",
            )
        self.assertIn("Concise, no filler.", system)

    def test_no_client_id_skips_preferences_block(self):
        # When the Tavus endpoint has no header binding and no env default,
        # the prompt should still assemble cleanly without a preferences block.
        system, _ = _openai_messages_to_anthropic(
            [{"role": "user", "content": "hi"}],
            client_id=None,
        )
        self.assertNotIn("ACTIVE CLIENT", system)
        self.assertIn("Nathan Ellis", system)

    def test_unknown_client_id_warns_and_skips_block(self):
        # If the bound client has no config.yaml (typo, missing onboarding),
        # log and continue rather than crash the Tavus turn.
        block = _build_client_preferences_context("does-not-exist")
        self.assertIsNone(block)


if __name__ == "__main__":
    unittest.main()
