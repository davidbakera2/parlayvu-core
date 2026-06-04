"""Tests for per-client workflow-package gating (Stage 5 of the triage).

Locks in DECISIONS #3/#7/#11:
- Tools register conditionally on a client's active packages; base tools always
  show. An un-migrated client (active_workflows omitted) keeps everything.
- Prompt injection is surface-aware: full prose on text surfaces, a terse
  pointer on the Tavus voice surface.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app import workflow_packages as wp


# A representative slice of Nathan's real tool list (base + package-owned).
FAKE_TOOLS = [
    {"name": "web_search"},            # base
    {"name": "get_project_context"},   # base
    {"name": "save_meeting_notes"},    # meeting-notes
    {"name": "dylan_generate_variations"},  # client-site
    {"name": "dylan_edit_active_site"},     # client-site
    {"name": "init_podcast_parlay_project"},  # podcast-parlay
    {"name": "generate_video_draft"},         # podcast-parlay
    {"name": "request_video_approval"},       # podcast-parlay
    {"name": "record_parlay_decision"},       # podcast-parlay
    {"name": "get_parlay_status"},            # podcast-parlay
]


def _names(tools):
    return {t["name"] for t in tools}


class _Cfg:
    def __init__(self, active_workflows):
        self.active_workflows = active_workflows


class BuildNathanToolsTests(unittest.TestCase):
    def test_unmigrated_client_keeps_all_tools(self):
        # active_workflows is None (key omitted) → all packages active.
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg(None)):
            tools = wp.build_nathan_tools("ramair", FAKE_TOOLS)
        self.assertEqual(_names(tools), _names(FAKE_TOOLS))

    def test_subset_gates_other_package_tools(self):
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg(["client-site"])):
            tools = wp.build_nathan_tools("ulcannarbor", FAKE_TOOLS)
        got = _names(tools)
        # Base tools + client-site tools present.
        self.assertIn("web_search", got)
        self.assertIn("get_project_context", got)
        self.assertIn("dylan_generate_variations", got)
        self.assertIn("dylan_edit_active_site", got)
        # Other packages' tools gated out.
        self.assertNotIn("generate_video_draft", got)
        self.assertNotIn("save_meeting_notes", got)

    def test_explicit_empty_keeps_only_base_tools(self):
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg([])):
            tools = wp.build_nathan_tools("someclient", FAKE_TOOLS)
        self.assertEqual(_names(tools), {"web_search", "get_project_context"})

    def test_podcast_parlay_active_exposes_video_tools(self):
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg(["podcast-parlay"])):
            tools = wp.build_nathan_tools("ramair", FAKE_TOOLS)
        got = _names(tools)
        for t in ("init_podcast_parlay_project", "generate_video_draft", "request_video_approval",
                  "record_parlay_decision", "get_parlay_status"):
            self.assertIn(t, got)
        self.assertNotIn("dylan_generate_variations", got)

    def test_none_client_id_keeps_all(self):
        tools = wp.build_nathan_tools(None, FAKE_TOOLS)
        self.assertEqual(_names(tools), _names(FAKE_TOOLS))


class InjectPackageContextSurfaceTests(unittest.TestCase):
    def test_tavus_surface_is_terse(self):
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg(["podcast-parlay"])):
            out = wp.inject_package_context("ramair", "BASE", surface="tavus")
        self.assertIn("BASE", out)
        self.assertIn("Active workflow package", out)
        # The heavy markdown prose must NOT be on the voice path.
        self.assertNotIn("### ACTIVE PACKAGE", out)
        self.assertNotIn("Key principles", out)

    def test_teams_surface_has_full_prose(self):
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg(["podcast-parlay"])):
            out = wp.inject_package_context("ramair", "BASE", surface="teams_chat")
        self.assertIn("### ACTIVE PACKAGE", out)
        self.assertIn("longform_draft", out)

    def test_no_active_packages_returns_base_unchanged(self):
        with patch("app.workflow_packages.load_client_config", return_value=_Cfg([])):
            out = wp.inject_package_context("someclient", "BASE", surface="teams_chat")
        self.assertEqual(out, "BASE")


if __name__ == "__main__":
    unittest.main()
