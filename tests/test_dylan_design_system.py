"""Regression tests for the design-system section composition path.

These guard two things that previously had zero coverage:
  1. `_generate_section_html` builds its prompt with `json.dumps(...)` — a missing
     `import json` made it raise NameError the moment Nathan invoked compose_section_edit.
  2. The `design-system/sections/*.astro` reference designs are actually loaded and
     fed to the LLM as grounding (rather than being orphaned, unread files).
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import dylan_edit_service


def _fake_anthropic_client(html: str) -> MagicMock:
    async def _create(**kwargs):
        block = MagicMock()
        block.text = html
        response = MagicMock()
        response.content = [block]
        # stash the prompt so tests can assert on grounding content
        _create.last_prompt = kwargs["messages"][0]["content"]
        return response

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    client._create = _create
    return client


class LoadSectionReferenceTests(unittest.TestCase):
    def test_returns_markup_for_shipped_reference_sections(self):
        for section in ("CTA", "TeamGrid", "Features3Col"):
            markup = dylan_edit_service._load_section_reference(section)
            self.assertIsNotNone(markup, f"{section}.astro should exist and load")
            self.assertIn("<section", markup)

    def test_returns_none_for_section_without_reference_file(self):
        self.assertIsNone(dylan_edit_service._load_section_reference("LogoCloud"))
        self.assertIsNone(dylan_edit_service._load_section_reference("DoesNotExist"))


class GenerateSectionHtmlTests(unittest.TestCase):
    def test_does_not_raise_nameerror_on_json_dumps(self):
        """The original bug: json used but never imported -> NameError at call time."""
        client = _fake_anthropic_client("<section>cta</section>")
        with patch.object(dylan_edit_service.anthropic, "AsyncAnthropic", return_value=client):
            result = asyncio.run(
                dylan_edit_service._generate_section_html(
                    client_display_name="RamAir",
                    section_name="CTA",
                    section_data={"headline": "Book a call", "buttonText": "Start"},
                )
            )
        self.assertEqual(result, "<section>cta</section>")

    def test_reference_astro_is_injected_into_prompt(self):
        client = _fake_anthropic_client("<section>team</section>")
        with patch.object(dylan_edit_service.anthropic, "AsyncAnthropic", return_value=client):
            asyncio.run(
                dylan_edit_service._generate_section_html(
                    client_display_name="RamAir",
                    section_name="TeamGrid",
                    section_data={"members": []},
                )
            )
        prompt = client._create.last_prompt
        self.assertIn("Canonical reference design", prompt)
        self.assertIn("Astro.props", prompt)  # came from the real .astro file

    def test_missing_reference_falls_back_gracefully(self):
        client = _fake_anthropic_client("<section>faq</section>")
        with patch.object(dylan_edit_service.anthropic, "AsyncAnthropic", return_value=client):
            asyncio.run(
                dylan_edit_service._generate_section_html(
                    client_display_name="RamAir",
                    section_name="FAQ",
                    section_data={"items": []},
                )
            )
        prompt = client._create.last_prompt
        self.assertIn("No reference component exists", prompt)


if __name__ == "__main__":
    unittest.main()
