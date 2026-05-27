"""Tests for `_resolve_active_html` — the live-fetch + disk-fallback strategy
that makes Dylan's edit workflow survive ephemeral container restarts.

Why this exists: every container revision roll wipes
client_artifacts/<client>/03_Deliverables/sites/active/. Before this
resolver, that meant "Nathan, edit the live site" fired off an immediate
FileNotFoundError. Now the resolver fetches from the production domain
first (Cloudflare is always authoritative), caches to disk for future
calls, and falls back to the disk cache only when the network can't help.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.dylan_edit_service import _resolve_active_html


def _make_config(production_domain: str | None = "ulcannarbor.info"):
    """Build a minimal ClientConfig stand-in with just the fields the resolver reads."""
    cf = MagicMock()
    cf.production_domain = production_domain
    config = MagicMock()
    config.cloudflare_config = cf
    return config


def _run(coro):
    return asyncio.run(coro)


class LiveFetchSucceedsTests(unittest.TestCase):
    def test_returns_live_html_and_writes_cache(self):
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = "<!DOCTYPE html><html><body>live</body></html>"
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                html = _run(_resolve_active_html(
                    client_id="ulcannarbor",
                    config=_make_config(),
                    active_index=active_index,
                ))

                self.assertEqual(html, "<!DOCTYPE html><html><body>live</body></html>")
                # Cache was written for future offline calls.
                self.assertTrue(active_index.is_file())
                self.assertEqual(
                    active_index.read_text(encoding="utf-8"),
                    html,
                )
                # And the fetch went to the right URL.
                mock_client.get.assert_awaited_once_with("https://ulcannarbor.info/")

    def test_fetch_overwrites_stale_cache(self):
        """A stale disk cache must NOT win over a successful live fetch."""
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = "<!DOCTYPE html>fresh"
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                active_index.parent.mkdir(parents=True)
                active_index.write_text("stale", encoding="utf-8")

                html = _run(_resolve_active_html(
                    client_id="ulcannarbor",
                    config=_make_config(),
                    active_index=active_index,
                ))

                self.assertEqual(html, "<!DOCTYPE html>fresh")
                self.assertEqual(
                    active_index.read_text(encoding="utf-8"),
                    "<!DOCTYPE html>fresh",
                )


class LiveFetchFailsTests(unittest.TestCase):
    def test_falls_back_to_disk_cache_on_http_error(self):
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("dns failure")
            )
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                active_index.parent.mkdir(parents=True)
                active_index.write_text("<!DOCTYPE html>cached", encoding="utf-8")

                html = _run(_resolve_active_html(
                    client_id="ulcannarbor",
                    config=_make_config(),
                    active_index=active_index,
                ))

                self.assertEqual(html, "<!DOCTYPE html>cached")

    def test_falls_back_to_disk_cache_on_timeout(self):
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ReadTimeout("slow origin")
            )
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                active_index.parent.mkdir(parents=True)
                active_index.write_text("<!DOCTYPE html>cached", encoding="utf-8")

                html = _run(_resolve_active_html(
                    client_id="ulcannarbor",
                    config=_make_config(),
                    active_index=active_index,
                ))

                self.assertEqual(html, "<!DOCTYPE html>cached")

    def test_fetch_failure_with_no_cache_raises_descriptive_error(self):
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ConnectError("dns failure")
            )
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                # No cache at all.
                with self.assertRaises(FileNotFoundError) as ctx:
                    _run(_resolve_active_html(
                        client_id="ulcannarbor",
                        config=_make_config(),
                        active_index=active_index,
                    ))

                msg = str(ctx.exception)
                self.assertIn("ulcannarbor", msg)
                self.assertIn("ulcannarbor.info", msg)
                self.assertIn("ConnectError", msg)


class NoDomainConfiguredTests(unittest.TestCase):
    def test_no_domain_uses_disk_cache_directly(self):
        # No live fetch should be attempted — patch httpx to fail loudly if it's called.
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = AssertionError(
                "httpx should not be called when no production_domain is set"
            )

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                active_index.parent.mkdir(parents=True)
                active_index.write_text("<!DOCTYPE html>cached", encoding="utf-8")

                html = _run(_resolve_active_html(
                    client_id="christshope",
                    config=_make_config(production_domain=None),
                    active_index=active_index,
                ))

                self.assertEqual(html, "<!DOCTYPE html>cached")

    def test_no_domain_no_cache_raises_promote_first_error(self):
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = AssertionError(
                "httpx should not be called when no production_domain is set"
            )

            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                active_index = Path(tmp) / "active" / "index.html"
                with self.assertRaises(FileNotFoundError) as ctx:
                    _run(_resolve_active_html(
                        client_id="christshope",
                        config=_make_config(production_domain=None),
                        active_index=active_index,
                    ))

                msg = str(ctx.exception)
                self.assertIn("christshope", msg)
                self.assertIn("Promote a homepage variation first", msg)


if __name__ == "__main__":
    unittest.main()
