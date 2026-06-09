"""End-to-end smoke test for the parlayvu.ai Stripe subscription half.

Runs against your Stripe TEST API (refuses live keys). It:
  1. Ensures the $800/4-week price exists (idempotent via lookup_key).
  2. Logs a user in via the real magic-link flow.
  3. Drives the real POST /billing/checkout route and verifies it redirects to a
     live checkout.stripe.com session URL (this also creates the Stripe customer).
  4. Creates a real test subscription (test card pm_card_visa) and runs the
     resulting Stripe object through our webhook handler.
  5. Confirms GET /dashboard now shows the subscription as Active.
  6. Cleans up: cancels the subscription and deletes the test customer.

Prereqs: STRIPE_SECRET_KEY=sk_test_... in your environment / .env.

    python scripts/smoke_stripe_flow.py
"""
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

# Throwaway DB, set before importing the app (engine builds at import time).
_db_path = Path(tempfile.gettempdir()) / "parlayvu_smoke_stripe.db"
if _db_path.exists():
    _db_path.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path.as_posix()}"
os.environ.pop("RESEND_API_KEY", None)
os.environ.pop("RESEND_API", None)
os.environ["APP_BASE_URL"] = "http://localhost:8000"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PRICE_LOOKUP_KEY = "podcast_parlay_800_per_4w"
EMAIL = "smoke-stripe@example.com"


def fail(msg: str):
    print(f"  [FAIL] {msg}")
    raise SystemExit(1)


def main() -> int:
    # Prefer an explicit test key; never silently use the live one.
    secret = (
        os.getenv("STRIPE_SECRET_KEY_TEST")
        or os.getenv("STRIPE_TEST_SECRET_KEY")
        or os.getenv("STRIPE_SECRET_KEY", os.getenv("STRIPE_API_KEY", ""))
    )
    if not secret:
        print("No Stripe key found. Add STRIPE_SECRET_KEY_TEST=sk_test_... to .env and retry.")
        return 1
    if secret.startswith("sk_live_"):
        print("Refusing to run against a LIVE key. Set STRIPE_SECRET_KEY_TEST=sk_test_... in .env.")
        return 1
    if not secret.startswith("sk_test_"):
        print("The selected key is not a recognizable test key (sk_test_...). Aborting.")
        return 1

    import stripe

    stripe.api_key = secret

    print("1. Ensure $800/4-week price exists")
    existing = stripe.Price.list(lookup_keys=[PRICE_LOOKUP_KEY], active=True, limit=1)
    if existing.data:
        price = existing.data[0]
        print(f"  [PASS] found existing price {price.id}")
    else:
        product = stripe.Product.create(name="Podcast Parlay Subscription")
        price = stripe.Price.create(
            product=product.id,
            unit_amount=80000,
            currency="usd",
            recurring={"interval": "week", "interval_count": 4},
            lookup_key=PRICE_LOOKUP_KEY,
            nickname="$800 / 4 weeks",
        )
        print(f"  [PASS] created price {price.id}")
    # Make the price visible to the billing module via env.
    os.environ["STRIPE_PRICE_ID"] = price.id

    # Import the app only now that env (DB + price) is in place.
    from fastapi.testclient import TestClient

    from app import auth, billing
    from app.database import get_engine, initialize_database
    from app.main import app

    # Importing app.main ran load_dotenv(override=True), which reloaded the LIVE
    # key from .env into the environment. Force the billing module back onto the
    # TEST key for the duration of this smoke test, and verify it took.
    os.environ["STRIPE_SECRET_KEY"] = secret
    os.environ["STRIPE_API_KEY"] = secret
    from app.settings import get_settings

    if get_settings().stripe_secret_key != secret:
        fail("could not force the billing module onto the test key — aborting before any live call")
    print("  [PASS] billing module pinned to the test key")

    initialize_database(get_engine())
    client = TestClient(app)
    customer_id = None
    subscription_id = None

    try:
        print("2. Log in via magic-link flow")
        token = auth.create_magic_link(EMAIL)
        account_id = auth.consume_magic_link(token)
        session_token = auth.create_session(account_id)
        client.cookies.set("pv_session", session_token)
        if not account_id:
            fail("could not establish a logged-in account")
        print(f"  [PASS] logged in as {EMAIL} (account {account_id})")

        print("3. POST /billing/checkout -> live Stripe Checkout URL")
        r = client.post("/billing/checkout", follow_redirects=False)
        location = r.headers.get("location", "")
        if r.status_code != 303 or "checkout.stripe.com" not in location:
            fail(f"expected 303 to checkout.stripe.com, got {r.status_code} {location[:80]}")
        print(f"  [PASS] redirected to {location[:60]}...")

        # The route created/saved a Stripe customer on the account.
        customer_id = billing.ensure_stripe_customer(account_id)
        print(f"  [PASS] Stripe customer {customer_id}")

        print("4. Create a real test subscription and sync via webhook handler")
        pm = stripe.PaymentMethod.attach("pm_card_visa", customer=customer_id)
        stripe.Customer.modify(
            customer_id, invoice_settings={"default_payment_method": pm.id}
        )
        sub = stripe.Subscription.create(
            customer=customer_id, items=[{"price": price.id}]
        )
        subscription_id = sub["id"]
        print(f"  [PASS] subscription {subscription_id} status={sub['status']}")
        billing.handle_webhook_event(
            {"type": "customer.subscription.created", "data": {"object": sub}}
        )
        status = billing.get_subscription_status(account_id)
        if not status["entitled"]:
            fail(f"local subscription not entitled after sync: {status}")
        print(f"  [PASS] local DB synced: entitled, status={status['status']}")

        print("5. Dashboard reflects the active subscription")
        r = client.get("/dashboard")
        if r.status_code != 200 or "Manage billing" not in r.text or "Active" not in r.text:
            fail("dashboard did not show an active subscription")
        print("  [PASS] /dashboard shows Active + Manage billing")

        print()
        print("STRIPE SMOKE TEST PASSED — checkout + subscription sync work end-to-end.")
        return 0
    finally:
        # Tidy the Stripe test account.
        try:
            if subscription_id:
                stripe.Subscription.cancel(subscription_id)
        except Exception:
            pass
        try:
            if customer_id:
                stripe.Customer.delete(customer_id)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        code = main()
    finally:
        try:
            from app.database import get_engine

            get_engine().dispose()
        except Exception:
            pass
        if _db_path.exists():
            try:
                _db_path.unlink()
            except OSError:
                pass
    raise SystemExit(code)
