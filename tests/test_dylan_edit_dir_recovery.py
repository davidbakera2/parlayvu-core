"""Tests for `ensure_edit_dir_on_disk` — the preview-fetch recovery path that
makes Dylan edit approvals survive ephemeral container restarts.

Why this exists: the edit-creation step writes
client_artifacts/<client>/03_Deliverables/sites/edits/<slug>/index.html to
local container disk, then deploys the whole sites/ tree to the client's
preview Pages project. If the container is recycled before the user clicks
Approve in Teams, the on-disk edit dir is gone and promote_to_production
fails with "source_dir not found". Recovery re-fetches the HTML from the
preview deploy (which lives on Cloudflare, not the container) and writes it
back to disk before promotion proceeds.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services import client_deploy
from app.services.dylan_edit_service import ensure_edit_dir_on_disk


def _run(coro):
    return asyncio.run(coro)


class EnsureEditDirOnDiskTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = patch.object(client_deploy, "CLIENT_ARTIFACTS_ROOT", self.root)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _edit_dir(self, client_id: str, slug: str) -> Path:
        return (
            self.root / client_id / "03_Deliverables" / "sites" / "edits" / slug
        ).resolve()

    def test_returns_existing_dir_without_fetching(self):
        slug = "edit-2026-05-27T200640Z"
        edit_dir = self._edit_dir("ulcannarbor", slug)
        edit_dir.mkdir(parents=True)
        (edit_dir / "index.html").write_text("<html>existing</html>", encoding="utf-8")

        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = AssertionError(
                "httpx should not be called when the edit dir already exists"
            )
            result = _run(ensure_edit_dir_on_disk(
                client_id="ulcannarbor",
                edit_slug=slug,
                preview_url="https://ulcannarbor-previews.pages.dev/edits/edit-2026-05-27T200640Z/",
            ))

        self.assertEqual(result, edit_dir)
        self.assertEqual(
            (edit_dir / "index.html").read_text(encoding="utf-8"),
            "<html>existing</html>",
        )

    def test_recovers_from_preview_when_disk_wiped(self):
        slug = "edit-2026-05-27T200640Z"
        preview_url = "https://ulcannarbor-previews.pages.dev/edits/edit-2026-05-27T200640Z/"

        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = "<html>recovered from preview</html>"
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = _run(ensure_edit_dir_on_disk(
                client_id="ulcannarbor",
                edit_slug=slug,
                preview_url=preview_url,
            ))

        expected_dir = self._edit_dir("ulcannarbor", slug)
        self.assertEqual(result, expected_dir)
        self.assertTrue((expected_dir / "index.html").is_file())
        self.assertEqual(
            (expected_dir / "index.html").read_text(encoding="utf-8"),
            "<html>recovered from preview</html>",
        )
        mock_client.get.assert_awaited_once_with(preview_url)

    def test_missing_dir_with_no_preview_url_raises(self):
        slug = "edit-2026-05-27T200640Z"
        with self.assertRaises(FileNotFoundError) as ctx:
            _run(ensure_edit_dir_on_disk(
                client_id="ulcannarbor",
                edit_slug=slug,
                preview_url=None,
            ))
        msg = str(ctx.exception)
        self.assertIn(slug, msg)
        self.assertIn("no preview_url", msg)

    def test_missing_dir_with_failing_preview_fetch_raises(self):
        slug = "edit-2026-05-27T200640Z"
        preview_url = "https://ulcannarbor-previews.pages.dev/edits/edit-2026-05-27T200640Z/"

        with patch("app.services.dylan_edit_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("dns failure"))
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with self.assertRaises(FileNotFoundError) as ctx:
                _run(ensure_edit_dir_on_disk(
                    client_id="ulcannarbor",
                    edit_slug=slug,
                    preview_url=preview_url,
                ))

        msg = str(ctx.exception)
        self.assertIn(preview_url, msg)
        self.assertIn("ConnectError", msg)


if __name__ == "__main__":
    unittest.main()
