"""Create (idempotently) the parlayvu.ai Podcast Parlay subscription price in Stripe.

Run once after setting STRIPE_SECRET_KEY in your environment / .env:

    python scripts/setup_stripe.py

It creates a Product "Podcast Parlay Subscription" and a recurring price of
$800 every 4 weeks (interval=week, interval_count=4), then prints the price id
to paste into STRIPE_PRICE_ID. Re-running reuses the existing product/price
found by lookup_key, so it is safe to run again.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

PRODUCT_NAME = "Podcast Parlay Subscription"
PRICE_LOOKUP_KEY = "podcast_parlay_800_per_4w"
AMOUNT_CENTS = 80000  # $800.00
CURRENCY = "usd"


def main() -> int:
    secret = os.getenv("STRIPE_SECRET_KEY", "")
    if not secret:
        print("ERROR: STRIPE_SECRET_KEY is not set.", file=sys.stderr)
        return 1

    import stripe

    stripe.api_key = secret

    # Reuse an existing price by lookup_key if present.
    existing = stripe.Price.list(lookup_keys=[PRICE_LOOKUP_KEY], active=True, limit=1)
    if existing.data:
        price = existing.data[0]
        print(f"Found existing price: {price.id}")
        print(f"\nSTRIPE_PRICE_ID={price.id}")
        return 0

    # Find or create the product.
    product = None
    for prod in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        if prod.name == PRODUCT_NAME:
            product = prod
            break
    if product is None:
        product = stripe.Product.create(
            name=PRODUCT_NAME,
            description="Recurring Podcast Parlay production — $800 every 4 weeks.",
        )
        print(f"Created product: {product.id}")
    else:
        print(f"Found product: {product.id}")

    price = stripe.Price.create(
        product=product.id,
        unit_amount=AMOUNT_CENTS,
        currency=CURRENCY,
        recurring={"interval": "week", "interval_count": 4},
        lookup_key=PRICE_LOOKUP_KEY,
        nickname="$800 / 4 weeks",
    )
    print(f"Created price: {price.id}")
    print(f"\nSTRIPE_PRICE_ID={price.id}")
    print("\nPaste that into your .env (and your deployment secrets).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
