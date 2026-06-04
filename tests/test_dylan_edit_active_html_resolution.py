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


def _mock_stream_client(*, body: str = "", enter_exc: Exception | None = None,
                        raise_for_status_exc: Exception | None = None):
    """Build a mock httpx.AsyncClient whose `.stream("GET", url)` yields `body`.

    The resolver now uses streaming + a body-size cap (`_get_html_capped`)
    instead of `.get(...).text`, so tests mock `.stream()` accordingly.
      - enter_exc: raised when entering the stream context (connect/timeout).
      - raise_for_status_exc: raised by response.raise_for_status().
    """
    mock_client = AsyncMock()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=raise_for_status_exc)

    async def _aiter_bytes():
        if body:
            yield body.encode("utf-8")
    mock_response.aiter_bytes = _aiter_bytes

    stream_cm = MagicMock()
    if enter_exc is not None:
        stream_cm.__aenter__ = AsyncMock(side_effect=enter_exc)
    else:
        stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    stream_cm.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=stream_cm)
    return mock_client


class LiveFetchSucceedsTests(unittest.TestCase):
    def test_returns_live_html_and_writes_cache(self):
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_stream_client(
                body="<!DOCTYPE html><html><body>live</body></html>"
            )
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
                mock_client.stream.assert_called_once_with("GET", "https://ulcannarbor.info/")

    def test_fetch_overwrites_stale_cache(self):
        """A stale disk cache must NOT win over a successful live fetch."""
        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = _mock_stream_client(body="<!DOCTYPE html>fresh")
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
            mock_client = _mock_stream_client(enter_exc=httpx.ConnectError("dns failure"))
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
            mock_client = _mock_stream_client(enter_exc=httpx.ReadTimeout("slow origin"))
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
            mock_client = _mock_stream_client(enter_exc=httpx.ConnectError("dns failure"))
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


class DirectImagePatchTests(unittest.TestCase):
    """Tests for the new reliable direct patch for photo updates (no LLM)."""

    def test_updates_img_src_and_aria(self):
        from app.services.dylan_edit_service import _try_direct_image_patch
        html = '''<div role="img" aria-label="Old photo of the building" class="hero"></div>'''
        desc = 'update the hero photo to /images/new-ulc.jpg with description "The ULC building on a sunny day"'
        result = _try_direct_image_patch(html, desc)
        self.assertIn('data-src="/images/new-ulc.jpg"', result)  # or background, but our heuristic
        self.assertIn('aria-label="The ULC building on a sunny day"', result)

    def test_no_change_for_non_image_request(self):
        from app.services.dylan_edit_service import _try_direct_image_patch
        html = '<div>some text</div>'
        result = _try_direct_image_patch(html, "change the headline to Hello")
        self.assertEqual(result, html)

    def test_updates_existing_img_src(self):
        from app.services.dylan_edit_service import _try_direct_image_patch
        html = '<img src="/old.jpg" alt="old">'
        desc = 'replace the photo src with /new.png and alt "A bright new campus photo"'
        result = _try_direct_image_patch(html, desc)
        self.assertIn('src="/new.png"', result)
        self.assertIn('alt="A bright new campus photo"', result)
        self.assertNotIn("/old.jpg", result)


class SsrfGuardTests(unittest.TestCase):
    """The fetch path must refuse internal/non-public targets (SSRF defense)."""

    def test_rejects_localhost_and_private_and_scheme(self):
        from app.services.dylan_edit_service import _validate_public_http_url
        for bad in (
            "http://localhost/",
            "https://127.0.0.1/",
            "https://10.0.0.5/admin",
            "https://169.254.169.254/latest/meta-data/",  # cloud metadata
            "file:///etc/passwd",
            "https://user:pass@example.com/",
        ):
            with self.assertRaises(ValueError, msg=f"should reject {bad}"):
                _validate_public_http_url(bad)

    def test_allows_normal_public_https(self):
        from app.services.dylan_edit_service import _validate_public_http_url
        # Should not raise.
        _validate_public_http_url("https://ulcannarbor.info/")

    def test_body_size_cap_aborts_oversized_fetch(self):
        from app.services.dylan_edit_service import _get_html_capped

        async def _aiter():
            yield b"x" * 10
            yield b"y" * 10

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = _aiter
        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        http = MagicMock()
        http.stream = MagicMock(return_value=stream_cm)

        with self.assertRaises(ValueError):
            _run(_get_html_capped(http, "https://example.com/", max_bytes=15))


class BasicValidationTests(unittest.TestCase):
    def test_rejects_major_content_loss(self):
        from app.services.dylan_edit_service import _basic_html_validation
        original = "<!DOCTYPE html><html><head></head><body>" + ("x" * 4000) + "</body></html>"
        # Gutted is well over the 100-char floor but less than half the original.
        gutted = "<!DOCTYPE html><html><head></head><body>" + ("x" * 200) + "</body></html>"
        ok, reason = _basic_html_validation(gutted, original, "tweak the footer")
        self.assertFalse(ok)
        self.assertIn("lost", reason)

    def test_allows_small_edit(self):
        from app.services.dylan_edit_service import _basic_html_validation
        original = "<!DOCTYPE html><html><head></head><body>" + ("x" * 1000) + "</body></html>"
        edited = original.replace("xxx", "yyy", 1)
        ok, reason = _basic_html_validation(edited, original, "tweak")
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
