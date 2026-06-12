"""Create (idempotently) the parlayvu.ai subscription prices in Stripe.

Run once after setting STRIPE_SECRET_KEY in your environment / .env:

    python scripts/setup_stripe.py

For every offering in the product catalog (``app/plans.py``) it ensures a Stripe
Product and a recurring Price exist, then prints the ``<PRICE_ENV>=<price_id>``
line to paste into your .env (and deployment secrets). Existing prices are
reused by ``lookup_key``, so re-running is safe.

By default it uses the TEST key in ``STRIPE_SECRET_KEY``. Pass ``--live`` to use
``STRIPE_SECRET_KEY_LIVE`` instead (it refuses anything that is not an ``sk_live_``
key) — this is how you create the production prices:

    python scripts/setup_stripe.py            # test mode
    python scripts/setup_stripe.py --live     # production prices

Current catalog:
  - Podcast Parlay  → $800 every 4 weeks   → STRIPE_PRICE_ID
  - Ads Parlay      → $500 / month         → STRIPE_PRICE_ID_ADS_PARLAY
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Make ``app`` importable when run as ``python scripts/setup_stripe.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv(override=True)

from app.plans import PLANS  # noqa: E402

CURRENCY = "usd"


def main() -> int:
    live = "--live" in sys.argv[1:]
    if live:
        secret = os.getenv("STRIPE_SECRET_KEY_LIVE", "")
        if not secret:
            print("ERROR: --live given but STRIPE_SECRET_KEY_LIVE is not set.", file=sys.stderr)
            return 1
        if not secret.startswith("sk_live_"):
            print("ERROR: STRIPE_SECRET_KEY_LIVE is not a live key (sk_live_...). Aborting.", file=sys.stderr)
            return 1
        print(">>> LIVE MODE — creating PRODUCTION prices.\n")
    else:
        secret = os.getenv("STRIPE_SECRET_KEY", os.getenv("STRIPE_API_KEY", ""))
        if not secret:
            print("ERROR: STRIPE_SECRET_KEY is not set.", file=sys.stderr)
            return 1
        if secret.startswith("sk_live_"):
            print("ERROR: STRIPE_SECRET_KEY is a LIVE key. Re-run with --live to confirm "
                  "you intend to create production prices.", file=sys.stderr)
            return 1

    import stripe

    stripe.api_key = secret

    env_lines: list[str] = []
    for plan in PLANS.values():
        product_name = f"{plan.name} Subscription"
        print(f"\n=== {plan.name} ({plan.price_label} {plan.period_label}) ===")

        # Reuse an existing price by lookup_key if present.
        existing = stripe.Price.list(lookup_keys=[plan.lookup_key], active=True, limit=1)
        if existing.data:
            price = existing.data[0]
            print(f"Found existing price: {price.id}")
            env_lines.append(f"{plan.price_env}={price.id}")
            continue

        # Find or create the product.
        product = None
        for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
            if prod.name == product_name:
                product = prod
                break
        if product is None:
            product = stripe.Product.create(
                name=product_name, description=plan.product_description
            )
            print(f"Created product: {product.id}")
        else:
            print(f"Found product: {product.id}")

        price = stripe.Price.create(
            product=product.id,
            unit_amount=plan.amount_cents,
            currency=CURRENCY,
            recurring={"interval": plan.interval, "interval_count": plan.interval_count},
            lookup_key=plan.lookup_key,
            nickname=f"{plan.price_label} {plan.period_label}",
        )
        print(f"Created price: {price.id}")
        env_lines.append(f"{plan.price_env}={price.id}")

    print("\nPaste these into your .env (and your deployment secrets):\n")
    for line in env_lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
