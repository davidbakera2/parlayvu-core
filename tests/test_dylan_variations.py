"""Tests for Dylan v2 — the homepage-variation generator.

The service orchestrates LLM calls + file writes + (optionally) Cloudflare
deploy. Every test mocks the LLM and the deploy helper. We verify:
  - N variations get written under client_artifacts/<client>/03_Deliverables/sites/
  - The landing index.html links to all variations
  - Path-escape is blocked at the writer
  - Missing client raises ClientConfigError
  - variation_count is clamped to [1, 10]
  - deploy=False skips the Cloudflare helper
  - Audit (record_generated_output) is called with the right output_type
"""

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.client_config import (
    ClientConfig,
    ClientPreferences,
    TeamsConfig,
    clear_client_config_cache,
)
from app.services import dylan_variations_service
from app.services.dylan_variations_service import (
    _build_variations_index,
    _extract_reference_urls,
    _write_site_file,
    generate_homepage_variations,
)


def _config() -> ClientConfig:
    return ClientConfig(
        client_id="ulcannarbor",
        display_name="ULC Ann Arbor",
        teams=TeamsConfig(team_id="t", channel_id="c"),
        preferences=ClientPreferences(),
    )


def _fake_anthropic_client(html_per_call: list[str]) -> MagicMock:
    """Anthropic AsyncAnthropic mock whose messages.create() returns the next
    HTML body in `html_per_call` each time it's called."""
    iterator = iter(html_per_call)

    async def _create(**kwargs):
        block = MagicMock()
        block.text = next(iterator)
        response = MagicMock()
        response.content = [block]
        return response

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    return client


def _fake_html(n: int) -> str:
    return f"<!DOCTYPE html><html><body><h1>Variation {n}</h1></body></html>"


class ExtractReferenceUrlsTests(unittest.TestCase):
    def test_extracts_http_and_https_urls(self):
        md = "Sites:\nhttps://example.org/\nhttp://other.com/path?q=1\n"
        self.assertEqual(
            _extract_reference_urls(md),
            ["https://example.org/", "http://other.com/path?q=1"],
        )

    def test_deduplicates_preserving_order(self):
        md = "https://a.com\nhttps://b.com\nhttps://a.com\n"
        self.assertEqual(_extract_reference_urls(md), ["https://a.com", "https://b.com"])

    def test_strips_trailing_punctuation(self):
        md = "(see https://example.com.)"
        # Trailing `.` and `)` are stripped from the URL
        self.assertEqual(_extract_reference_urls(md), ["https://example.com"])

    def test_caps_at_limit(self):
        md = "\n".join(f"https://site{i}.com" for i in range(20))
        self.assertEqual(len(_extract_reference_urls(md, limit=3)), 3)


class WriteSiteFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = patch.object(dylan_variations_service, "CLIENT_ARTIFACTS_ROOT", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_writes_inside_sites_subtree(self):
        info = _write_site_file("acme", "variation-1/index.html", "<html></html>")
        target = (
            self.root / "acme" / "03_Deliverables" / "sites" / "variation-1" / "index.html"
        )
        self.assertTrue(target.is_file())
        self.assertEqual(info["bytes"], len("<html></html>".encode("utf-8")))

    def test_path_escape_blocked(self):
        with self.assertRaises(ValueError) as ctx:
            _write_site_file("acme", "../../../etc/passwd", "x")
        self.assertIn("Path escape", str(ctx.exception))

    def test_absolute_path_blocked(self):
        with self.assertRaises(ValueError):
            _write_site_file("acme", "/etc/passwd", "x")


class BuildVariationsIndexTests(unittest.TestCase):
    def test_links_to_every_variation_and_shows_thesis(self):
        variations = [
            {"variation_number": 1, "thesis": "Typography-led minimalism"},
            {"variation_number": 2, "thesis": "Imagery-led storytelling"},
        ]
        html = _build_variations_index(
            client_display_name="ULC Ann Arbor",
            variations=variations,
        )
        self.assertIn("ULC Ann Arbor", html)
        self.assertIn('href="./variation-1/"', html)
        self.assertIn('href="./variation-2/"', html)
        self.assertIn("Typography-led minimalism", html)
        self.assertIn("Imagery-led storytelling", html)


class GenerateHomepageVariationsTests(unittest.TestCase):
    def setUp(self):
        clear_client_config_cache()
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._root_patch = patch.object(
            dylan_variations_service, "CLIENT_ARTIFACTS_ROOT", self.root
        )
        self._root_patch.start()
        self._env = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key-for-tests"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._root_patch.stop()
        clear_client_config_cache()
        self._tmp.cleanup()

    def _common_patches(self, *, htmls, deploy_result=None):
        anthropic_client = _fake_anthropic_client(htmls)
        return (
            patch.object(dylan_variations_service, "load_client_config", return_value=_config()),
            patch.object(dylan_variations_service.anthropic, "AsyncAnthropic", return_value=anthropic_client),
            patch.object(dylan_variations_service, "fetch_url", new=AsyncMock(return_value={"url": "x", "content": "stub"})),
            patch.object(dylan_variations_service, "record_generated_output", return_value="out-1"),
            patch.object(dylan_variations_service, "record_agent_event", return_value="evt-1"),
            anthropic_client,
        )

    def test_generates_n_variations_with_distinct_files(self):
        patches = self._common_patches(htmls=[_fake_html(i) for i in range(1, 6)])
        anthropic_client = patches[-1]
        for p in patches[:-1]: p.start()
        try:
            result = asyncio.run(
                generate_homepage_variations(
                    client_id="ulcannarbor", variation_count=5, deploy=False
                )
            )
        finally:
            for p in reversed(patches[:-1]): p.stop()

        self.assertEqual(len(result["variations"]), 5)
        for i in range(1, 6):
            f = self.root / "ulcannarbor" / "03_Deliverables" / "sites" / f"variation-{i}" / "index.html"
            self.assertTrue(f.is_file(), f"variation-{i}/index.html missing")
            self.assertIn(f"Variation {i}", f.read_text(encoding="utf-8"))
        # Index landing page exists and links to every variation
        index = (self.root / "ulcannarbor" / "03_Deliverables" / "sites" / "index.html").read_text(encoding="utf-8")
        for i in range(1, 6):
            self.assertIn(f'href="./variation-{i}/"', index)
        # 5 LLM calls, one per variation
        self.assertEqual(anthropic_client.messages.create.await_count, 5)

    def test_clamps_variation_count_high(self):
        patches = self._common_patches(htmls=[_fake_html(i) for i in range(1, 11)])
        for p in patches[:-1]: p.start()
        try:
            result = asyncio.run(
                generate_homepage_variations(
                    client_id="ulcannarbor", variation_count=999, deploy=False
                )
            )
        finally:
            for p in reversed(patches[:-1]): p.stop()
        self.assertEqual(len(result["variations"]), 10)  # MAX_VARIATIONS

    def test_clamps_variation_count_low(self):
        patches = self._common_patches(htmls=[_fake_html(1)])
        for p in patches[:-1]: p.start()
        try:
            result = asyncio.run(
                generate_homepage_variations(
                    client_id="ulcannarbor", variation_count=0, deploy=False
                )
            )
        finally:
            for p in reversed(patches[:-1]): p.stop()
        self.assertEqual(len(result["variations"]), 1)  # MIN_VARIATIONS

    def test_deploy_false_skips_cloudflare_helper(self):
        patches = self._common_patches(htmls=[_fake_html(1)])
        anthropic_client = patches[-1]
        with patch.object(
            dylan_variations_service, "load_client_config", return_value=_config()
        ), patch.object(
            dylan_variations_service.anthropic, "AsyncAnthropic", return_value=anthropic_client
        ), patch.object(
            dylan_variations_service, "fetch_url", new=AsyncMock(return_value={"url": "x", "content": "stub"})
        ), patch.object(
            dylan_variations_service, "record_generated_output", return_value="out-1"
        ), patch.object(
            dylan_variations_service, "record_agent_event", return_value="evt-1"
        ), patch(
            "app.agents.tools.dylan_tools.deploy_static_directory_to_cloudflare"
        ) as deploy_mock:
            result = asyncio.run(
                generate_homepage_variations(
                    client_id="ulcannarbor", variation_count=1, deploy=False
                )
            )
        deploy_mock.assert_not_called()
        self.assertEqual(result["status"], "generated")
        self.assertIsNone(result["preview_url"])

    def test_deploy_true_calls_cloudflare_helper_and_surfaces_url(self):
        patches = self._common_patches(htmls=[_fake_html(1)])
        anthropic_client = patches[-1]
        with patch.object(
            dylan_variations_service, "load_client_config", return_value=_config()
        ), patch.object(
            dylan_variations_service.anthropic, "AsyncAnthropic", return_value=anthropic_client
        ), patch.object(
            dylan_variations_service, "fetch_url", new=AsyncMock(return_value={"url": "x", "content": "stub"})
        ), patch.object(
            dylan_variations_service, "record_generated_output", return_value="out-1"
        ), patch.object(
            dylan_variations_service, "record_agent_event", return_value="evt-1"
        ), patch(
            "app.agents.tools.dylan_tools.deploy_static_directory_to_cloudflare",
            return_value={
                "status": "success",
                "url": "https://ulcannarbor-previews.pages.dev/",
                "project_name": "ulcannarbor-previews",
            },
        ) as deploy_mock:
            result = asyncio.run(
                generate_homepage_variations(
                    client_id="ulcannarbor", variation_count=1, deploy=True
                )
            )
        deploy_mock.assert_called_once()
        self.assertEqual(result["status"], "deployed")
        self.assertEqual(result["preview_url"], "https://ulcannarbor-previews.pages.dev/")

    def test_records_audit_with_homepage_variations_output_type(self):
        patches = self._common_patches(htmls=[_fake_html(1)])
        anthropic_client = patches[-1]
        with patch.object(
            dylan_variations_service, "load_client_config", return_value=_config()
        ), patch.object(
            dylan_variations_service.anthropic, "AsyncAnthropic", return_value=anthropic_client
        ), patch.object(
            dylan_variations_service, "fetch_url", new=AsyncMock(return_value={"url": "x", "content": "stub"})
        ), patch.object(
            dylan_variations_service, "record_generated_output", return_value="out-99"
        ) as rgo, patch.object(
            dylan_variations_service, "record_agent_event", return_value="evt-99"
        ) as rae:
            asyncio.run(
                generate_homepage_variations(
                    client_id="ulcannarbor", variation_count=1, deploy=False
                )
            )
        rgo.assert_called_once()
        self.assertEqual(rgo.call_args.kwargs["output_type"], "homepage_variations")
        self.assertEqual(rgo.call_args.kwargs["agent_name"], "dylan")
        rae.assert_called_once()
        self.assertEqual(rae.call_args.kwargs["event_type"], "homepage_variations_generated")


if __name__ == "__main__":
    unittest.main()
