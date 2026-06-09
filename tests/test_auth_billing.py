"""Tests for parlayvu.ai login (magic link) + Stripe subscription gating.

Mirrors the existing suite's pattern: in-memory SQLite + a fake ``session_scope``
patched into each module under test. Stripe and Resend are mocked.
"""
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth as auth_module
from app import billing as billing_module
from app.database import initialize_database
from app.main import app
from app.models import Account, LoginSession, Subscription


def build_fake_scope(Session):
    @contextmanager
    def fake_scope():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return fake_scope


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        initialize_database(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.scope = build_fake_scope(self.Session)

    def test_magic_link_create_and_consume(self):
        with patch("app.auth.session_scope", self.scope):
            token = auth_module.create_magic_link("Owner@Example.com ")
            account_id = auth_module.consume_magic_link(token)
            self.assertIsNotNone(account_id)
            # Single use: second consume fails.
            self.assertIsNone(auth_module.consume_magic_link(token))

        with self.Session() as s:
            acct = s.query(Account).one()
            self.assertEqual(acct.email, "owner@example.com")  # normalized

    def test_expired_magic_link_rejected(self):
        with patch("app.auth.session_scope", self.scope):
            token = auth_module.create_magic_link("a@b.com")
            # Force expiry.
            with self.Session() as s:
                from app.models import MagicLink

                link = s.query(MagicLink).one()
                link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
                s.commit()
            self.assertIsNone(auth_module.consume_magic_link(token))

    def test_session_create_resolve_and_revoke(self):
        with patch("app.auth.session_scope", self.scope):
            token = auth_module.create_magic_link("c@d.com")
            account_id = auth_module.consume_magic_link(token)
            sess_token = auth_module.create_session(account_id)

            acct = auth_module.account_for_session(sess_token)
            self.assertEqual(acct["email"], "c@d.com")

            auth_module.revoke_session(sess_token)
            self.assertIsNone(auth_module.account_for_session(sess_token))

    def test_request_link_route_does_not_enumerate(self):
        with patch("app.auth.session_scope", self.scope), patch(
            "app.auth.send_magic_link_email"
        ) as send:
            client = TestClient(app)
            resp = client.post(
                "/auth/request-link", data={"email": "new@user.com"},
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Check your email", resp.text)
            send.assert_called_once()


class DashboardGatingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        initialize_database(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.scope = build_fake_scope(self.Session)

    def _login(self, client, email):
        with patch("app.auth.session_scope", self.scope):
            token = auth_module.create_magic_link(email)
            account_id = auth_module.consume_magic_link(token)
            sess_token = auth_module.create_session(account_id)
        client.cookies.set("pv_session", sess_token)
        return account_id

    def test_anonymous_dashboard_redirects_to_login(self):
        with patch("app.auth.session_scope", self.scope):
            client = TestClient(app)
            resp = client.get("/dashboard", follow_redirects=False)
            self.assertEqual(resp.status_code, 303)
            self.assertEqual(resp.headers["location"], "/login")

    def test_logged_in_without_subscription_sees_subscribe(self):
        client = TestClient(app)
        self._login(client, "buyer@co.com")
        with patch("app.auth.session_scope", self.scope), patch(
            "app.billing.session_scope", self.scope
        ):
            resp = client.get("/dashboard")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Subscribe", resp.text)
            self.assertIn("$800", resp.text)

    def test_active_subscription_shows_manage_billing(self):
        client = TestClient(app)
        account_id = self._login(client, "member@co.com")
        with self.Session() as s:
            s.add(
                Subscription(
                    account_id=account_id,
                    stripe_subscription_id="sub_123",
                    status="active",
                    current_period_end=datetime.now(timezone.utc) + timedelta(days=14),
                )
            )
            s.commit()
        with patch("app.auth.session_scope", self.scope), patch(
            "app.billing.session_scope", self.scope
        ):
            resp = client.get("/dashboard")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Manage billing", resp.text)
            self.assertIn("Active", resp.text)


class WebhookSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        initialize_database(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.scope = build_fake_scope(self.Session)
        with self.Session() as s:
            s.add(Account(id="acct_1", email="w@co.com", stripe_customer_id="cus_1"))
            s.commit()

    def test_subscription_event_upserts_and_gates(self):
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_999",
                    "customer": "cus_1",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_end": 1893456000,
                    "items": {"data": [{"price": {"id": "price_abc"}}]},
                }
            },
        }
        with patch("app.billing.session_scope", self.scope):
            billing_module.handle_webhook_event(event)
            status = billing_module.get_subscription_status("acct_1")
            self.assertTrue(status["entitled"])
            self.assertEqual(status["status"], "active")

            # Cancellation flips entitlement off.
            event["data"]["object"]["status"] = "canceled"
            billing_module.handle_webhook_event(event)
            self.assertFalse(billing_module.get_subscription_status("acct_1")["entitled"])

    def test_period_end_falls_back_to_item_level(self):
        """Recent Stripe API versions put current_period_end on the subscription
        item, not the subscription object. The handler must fall back to it."""
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_item_pe",
                    "customer": "cus_1",
                    "status": "active",
                    "cancel_at_period_end": False,
                    # No top-level current_period_end — only on the item.
                    "items": {
                        "data": [
                            {"price": {"id": "price_abc"}, "current_period_end": 1893456000}
                        ]
                    },
                }
            },
        }
        with patch("app.billing.session_scope", self.scope):
            billing_module.handle_webhook_event(event)
            status = billing_module.get_subscription_status("acct_1")
            self.assertTrue(status["entitled"])
            self.assertIsNotNone(status["current_period_end"])

    def test_stripe_object_without_get_is_handled(self):
        """Regression: modern stripe-python objects are not dicts and lack .get();
        the handler must normalize them via to_dict_recursive() before access."""

        class FakeStripeObject:
            def __init__(self, data):
                self._data = data

            def __getattr__(self, name):  # mimic StripeObject: .get falls through
                try:
                    return self._data[name]
                except KeyError as exc:
                    raise AttributeError(name) from exc

            def to_dict_recursive(self):
                return self._data

        sub_obj = FakeStripeObject(
            {
                "id": "sub_obj_1",
                "customer": "cus_1",
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": 1893456000,
                "items": {"data": [{"price": {"id": "price_abc"}}]},
            }
        )
        # Sanity: it really does not support .get (would raise AttributeError).
        with self.assertRaises(AttributeError):
            sub_obj.get  # noqa: B018

        event = {"type": "customer.subscription.created", "data": {"object": sub_obj}}
        with patch("app.billing.session_scope", self.scope):
            billing_module.handle_webhook_event(event)
            self.assertTrue(billing_module.get_subscription_status("acct_1")["entitled"])

    def test_webhook_endpoint_rejects_bad_signature(self):
        with patch.object(
            billing_module, "get_settings"
        ) as gs:
            gs.return_value = type(
                "S", (), {"stripe_webhook_secret": "whsec_x", "stripe_secret_key": "sk_test_x"}
            )()
            with patch("app.billing._stripe") as stripe_factory:
                stripe_factory.return_value.Webhook.construct_event.side_effect = ValueError(
                    "bad sig"
                )
                client = TestClient(app)
                resp = client.post(
                    "/webhooks/stripe", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=bad"},
                )
                self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
