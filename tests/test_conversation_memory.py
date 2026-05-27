"""Tests for the Teams conversation-memory layer in app.project_memory.

These mirror the in-memory-SQLite + session_scope monkey-patch pattern
established by test_project_memory_services.py so we exercise the real
SQLAlchemy model rather than a mock.
"""
from __future__ import annotations

import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import initialize_database
from app.models import ConversationTurn
from app.project_memory import (
    CONVERSATION_MAX_CHARS,
    load_conversation_history,
    reset_conversation_history,
    save_conversation_turn,
)
from app.teams import is_conversation_reset_request


def _build_scope():
    """Fresh in-memory SQLite + session_scope override. Returns (scope, Session)."""
    engine = create_engine("sqlite:///:memory:")
    initialize_database(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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

    return fake_scope, Session


class DisabledByDefaultTests(unittest.TestCase):
    def test_save_no_op_when_memory_disabled(self):
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "false"}):
            turn_id = save_conversation_turn(
                conversation_id="conv-1", role="user", content="hi"
            )
        self.assertIsNone(turn_id)

    def test_load_returns_empty_when_memory_disabled(self):
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "false"}):
            history = load_conversation_history(conversation_id="conv-1")
        self.assertEqual(history, [])

    def test_reset_no_op_when_memory_disabled(self):
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "false"}):
            deleted = reset_conversation_history(conversation_id="conv-1")
        self.assertEqual(deleted, 0)


class SaveLoadRoundTripTests(unittest.TestCase):
    def test_save_load_two_turns_in_chronological_order(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                save_conversation_turn(
                    conversation_id="conv-A",
                    client_id="ulcannarbor",
                    role="user",
                    content="Generate 5 home pages for ulcannarbor.info",
                )
                time.sleep(0.002)
                save_conversation_turn(
                    conversation_id="conv-A",
                    client_id="ulcannarbor",
                    role="assistant",
                    content="On it — Dylan is producing 5 drafts.",
                )
                history = load_conversation_history(
                    conversation_id="conv-A", client_id="ulcannarbor"
                )

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("5 home pages", history[0]["content"])
        self.assertEqual(history[1]["role"], "assistant")
        self.assertIn("5 drafts", history[1]["content"])

    def test_empty_conversation_id_skips_save(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                turn_id = save_conversation_turn(
                    conversation_id="", role="user", content="hi"
                )
        self.assertIsNone(turn_id)

    def test_bad_role_rejected(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                turn_id = save_conversation_turn(
                    conversation_id="conv-A", role="system", content="x"
                )
        self.assertIsNone(turn_id)


class CapTests(unittest.TestCase):
    def test_max_turns_cap_keeps_most_recent(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                for i in range(25):
                    save_conversation_turn(
                        conversation_id="conv-A",
                        client_id="ulc",
                        role="user" if i % 2 == 0 else "assistant",
                        content=f"turn-{i}",
                    )
                    # Force a distinct created_at on each insert. Real Teams
                    # turns are seconds apart; this just sidesteps tight-loop
                    # timestamp collisions in SQLite.
                    time.sleep(0.002)
                history = load_conversation_history(
                    conversation_id="conv-A", client_id="ulc", max_turns=20
                )

        self.assertEqual(len(history), 20)
        # Oldest 5 dropped; newest 20 (turn-5 .. turn-24) kept in order.
        self.assertEqual(history[0]["content"], "turn-5")
        self.assertEqual(history[-1]["content"], "turn-24")

    def test_max_age_cap_excludes_stale_turns(self):
        fake_scope, Session = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                # Save a recent turn through the normal path.
                save_conversation_turn(
                    conversation_id="conv-A",
                    client_id="ulc",
                    role="user",
                    content="recent",
                )
                # Backdate one row directly via the session to simulate an
                # old turn (older than the max_age_hours window).
                with Session() as s:
                    stale = ConversationTurn(
                        conversation_id="conv-A",
                        client_id="ulc",
                        role="user",
                        content="ancient",
                    )
                    stale.created_at = datetime.now(timezone.utc) - timedelta(hours=200)
                    s.add(stale)
                    s.commit()

                history = load_conversation_history(
                    conversation_id="conv-A", client_id="ulc", max_age_hours=72
                )

        contents = [t["content"] for t in history]
        self.assertIn("recent", contents)
        self.assertNotIn("ancient", contents)

    def test_char_cap_drops_oldest_first(self):
        fake_scope, _ = _build_scope()
        big = "x" * 1000  # 1KB per turn
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                for i in range(5):
                    save_conversation_turn(
                        conversation_id="conv-A",
                        client_id="ulc",
                        role="user",
                        content=f"{i}:{big}",  # ~1002 chars each
                    )
                    time.sleep(0.002)  # distinct created_at per turn
                # 5 turns ≈ 5010 chars; capping at 3000 should drop oldest.
                history = load_conversation_history(
                    conversation_id="conv-A",
                    client_id="ulc",
                    max_chars=3000,
                )

        # At ~1KB each, 3000 char budget fits ~2-3 newest turns.
        self.assertGreaterEqual(len(history), 2)
        self.assertLessEqual(len(history), 3)
        # The newest turn must always survive char trimming.
        self.assertTrue(history[-1]["content"].startswith("4:"))


class IsolationTests(unittest.TestCase):
    def test_separate_conversations_do_not_see_each_other(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                save_conversation_turn(
                    conversation_id="conv-A",
                    client_id="ulc",
                    role="user",
                    content="ULC's question",
                )
                save_conversation_turn(
                    conversation_id="conv-B",
                    client_id="bakerstrategy",
                    role="user",
                    content="BSG's question",
                )

                ulc_history = load_conversation_history(
                    conversation_id="conv-A", client_id="ulc"
                )
                bsg_history = load_conversation_history(
                    conversation_id="conv-B", client_id="bakerstrategy"
                )

        self.assertEqual(len(ulc_history), 1)
        self.assertEqual(ulc_history[0]["content"], "ULC's question")
        self.assertEqual(len(bsg_history), 1)
        self.assertEqual(bsg_history[0]["content"], "BSG's question")

    def test_client_id_scope_blocks_cross_client_replay(self):
        # Same conversation_id (could theoretically happen if Teams reuses an
        # ID for some odd reason) but different client_ids must not bleed.
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                save_conversation_turn(
                    conversation_id="conv-shared",
                    client_id="ulc",
                    role="user",
                    content="ULC secret",
                )
                history = load_conversation_history(
                    conversation_id="conv-shared", client_id="bakerstrategy"
                )

        self.assertEqual(history, [])


class ResetTests(unittest.TestCase):
    def test_reset_clears_only_target_conversation(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                save_conversation_turn(
                    conversation_id="conv-A", client_id="ulc",
                    role="user", content="keep me",
                )
                save_conversation_turn(
                    conversation_id="conv-A", client_id="ulc",
                    role="assistant", content="me too",
                )
                save_conversation_turn(
                    conversation_id="conv-B", client_id="ulc",
                    role="user", content="untouched",
                )

                deleted = reset_conversation_history(
                    conversation_id="conv-A", client_id="ulc"
                )
                conv_a = load_conversation_history(
                    conversation_id="conv-A", client_id="ulc"
                )
                conv_b = load_conversation_history(
                    conversation_id="conv-B", client_id="ulc"
                )

        self.assertEqual(deleted, 2)
        self.assertEqual(conv_a, [])
        self.assertEqual(len(conv_b), 1)
        self.assertEqual(conv_b[0]["content"], "untouched")

    def test_reset_returns_zero_when_nothing_to_clear(self):
        fake_scope, _ = _build_scope()
        with patch.dict(os.environ, {"PROJECT_MEMORY_ENABLED": "true"}):
            with patch("app.project_memory.session_scope", fake_scope):
                deleted = reset_conversation_history(
                    conversation_id="conv-empty", client_id="ulc"
                )
        self.assertEqual(deleted, 0)


class ResetDetectorTests(unittest.TestCase):
    def test_recognizes_common_reset_phrasings(self):
        positives = [
            "start over",
            "Start Over",
            "let's start over please",
            "reset conversation",
            "new conversation",
            "forget that",
            "forget everything we just discussed",
            "@Nathan clear history",
            "Nathan, fresh start",
            "new chat",
        ]
        for text in positives:
            self.assertTrue(
                is_conversation_reset_request(text),
                f"expected reset for: {text!r}",
            )

    def test_does_not_trigger_on_substantive_questions(self):
        # Conservative on purpose — single-word "reset" must NOT trigger.
        negatives = [
            "what's our reset policy on subscriptions?",
            "I'm starting research on a new client",
            "new homepage please",
            "forget my last instruction about pricing — use the new one",
            "let's chat about strategy",
            "",
            "    ",
        ]
        for text in negatives:
            self.assertFalse(
                is_conversation_reset_request(text),
                f"unexpected reset for: {text!r}",
            )

    def test_forget_my_last_instruction_is_a_real_edge_case(self):
        # "forget my last instruction" doesn't contain any of the explicit
        # reset patterns, so it stays a normal Nathan turn (which is what
        # we want — user is talking about content, not memory).
        self.assertFalse(is_conversation_reset_request(
            "forget my last instruction about pricing"
        ))


class DefaultsTests(unittest.TestCase):
    def test_default_constants_match_spec(self):
        # Guard against accidental drift. The session decision was 20/72/60K.
        from app.project_memory import (
            CONVERSATION_MAX_TURNS,
            CONVERSATION_MAX_AGE_HOURS,
        )
        self.assertEqual(CONVERSATION_MAX_TURNS, 20)
        self.assertEqual(CONVERSATION_MAX_AGE_HOURS, 72)
        self.assertEqual(CONVERSATION_MAX_CHARS, 60_000)


if __name__ == "__main__":
    unittest.main()
