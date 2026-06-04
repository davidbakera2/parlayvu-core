"""Tests for the Podcast Parlay state machine + approval loop.

These lock in the fixes from the Grok-Build triage (Stage 3):
- The stage / action_type vocabulary is consistent across parlay_state.py,
  video_parlay_tools.py and nathan_llm.py (the bug class where 'clips' produced
  'video_clips' instead of the publish-guard's 'video_clip_package').
- Client approval decisions actually advance the state machine.
- The publish gate is enforced deterministically (not on the LLM's say-so).
- The /approvals decision endpoints sync the parlay state (the loop hook that
  was previously missing, leaving episodes stuck at the review stage forever).
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import parlay_state as ps
from app.approvals import decide_approval, request_approval
from app.database import initialize_database
from app.main import _sync_parlay_decision


def build_fake_scope(Session):
    def fake_scope():
        class Scope:
            def __enter__(self):
                self.session = Session()
                return self.session

            def __exit__(self, exc_type, exc, traceback):
                if exc_type:
                    self.session.rollback()
                else:
                    self.session.commit()
                self.session.close()

        return Scope()

    return fake_scope


class VocabularyInvariantsTests(unittest.TestCase):
    """Pure invariants — no DB. These would have caught the original mismatch."""

    def test_action_types_cover_review_stages(self):
        self.assertEqual(set(ps.ACTION_TYPE_FOR_STAGE), ps.REVIEW_STAGES)

    def test_publish_guards_reference_real_action_types(self):
        valid = set(ps.ACTION_TYPE_FOR_STAGE.values())
        for publish_stage, required in ps.PUBLISH_GUARDS.items():
            self.assertIn(required, valid, f"{publish_stage} guard wants unknown action_type {required!r}")

    def test_clips_maps_to_clip_package_not_clips(self):
        # The exact bug: f"video_{stage}" would have produced "video_clips".
        self.assertEqual(ps.ACTION_TYPE_FOR_STAGE[ps.CLIPS], "video_clip_package")


class StateMachineDbTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        self.fake = build_fake_scope(self.Session)

    def _patches(self):
        # parlay_state imports session_scope from app.database at call time;
        # approvals binds it at module import. Patch both so they share the DB.
        return patch("app.database.session_scope", self.fake), patch("app.approvals.session_scope", self.fake)

    def test_approved_decision_advances_stage(self):
        p1, p2 = self._patches()
        with p1, p2:
            pid = ps.parlay_project_id("ramair", "Ep05")
            ps.set_stage(pid, ps.LONGFORM_DRAFT, client_id="ramair", force=True)
            state = ps.record_decision(pid, stage=ps.LONGFORM_DRAFT, decision="approved", client_id="ramair")
            self.assertEqual(state["stage"], ps.LONGFORM_APPROVED)

    def test_changes_requested_keeps_stage(self):
        p1, p2 = self._patches()
        with p1, p2:
            pid = ps.parlay_project_id("ramair", "Ep05")
            ps.set_stage(pid, ps.LONGFORM_CAPTIONED, client_id="ramair", force=True)
            state = ps.record_decision(pid, stage=ps.LONGFORM_CAPTIONED, decision="changes_requested", client_id="ramair")
            self.assertEqual(state["stage"], ps.LONGFORM_CAPTIONED)

    def test_publish_blocked_without_approval_then_allowed(self):
        p1, p2 = self._patches()
        with p1, p2:
            pid = ps.parlay_project_id("ramair", "Ep05")
            ps.set_stage(pid, ps.CAPTIONED_APPROVED, client_id="ramair", force=True)

            # No approved captioned approval yet → hard gate blocks publish.
            with self.assertRaises(ps.ParlayPublishNotApproved):
                ps.set_stage(pid, ps.LONGFORM_PUBLISHED, client_id="ramair")

            # Create + approve the captioned approval the gate requires.
            ap = request_approval(
                client_id="ramair",
                project_id=pid,
                requested_by_agent="nathan",
                action_type=ps.ACTION_TYPE_FOR_STAGE[ps.LONGFORM_CAPTIONED],
                title="Review captioned long-form",
            )
            decide_approval(approval_id=ap["id"], status="approved", approver="client")

            state = ps.set_stage(pid, ps.LONGFORM_PUBLISHED, client_id="ramair")
            self.assertEqual(state["stage"], ps.LONGFORM_PUBLISHED)


class SyncParlayDecisionTests(unittest.TestCase):
    """The loop hook wired into the /approvals decision endpoints."""

    def test_video_approval_advances_state(self):
        approval = {
            "id": "ap-1",
            "project_id": "ramair-Ep05",
            "metadata": {"action_type": "video_longform_captioned", "stage": "longform_captioned"},
        }
        with patch("app.parlay_state.record_decision") as rd:
            _sync_parlay_decision(approval, status="approved", notes="lgtm")
        rd.assert_called_once()
        _, kwargs = rd.call_args
        self.assertEqual(kwargs["stage"], "longform_captioned")
        self.assertEqual(kwargs["decision"], "approved")

    def test_non_video_approval_is_ignored(self):
        approval = {
            "id": "ap-2",
            "project_id": "ramair-website",
            "metadata": {"action_type": "deploy_site"},
        }
        with patch("app.parlay_state.record_decision") as rd:
            _sync_parlay_decision(approval, status="approved", notes=None)
        rd.assert_not_called()

    def test_missing_stage_is_ignored(self):
        approval = {"id": "ap-3", "project_id": "ramair-Ep05", "metadata": {"action_type": "video_longform_draft"}}
        with patch("app.parlay_state.record_decision") as rd:
            _sync_parlay_decision(approval, status="approved", notes=None)
        rd.assert_not_called()

    def test_none_approval_is_safe(self):
        with patch("app.parlay_state.record_decision") as rd:
            _sync_parlay_decision(None, status="approved", notes=None)
        rd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
