"""Subscription product catalog for parlayvu.ai.

Each productized offering (Podcast Parlay, Ads Parlay, …) is one :class:`Plan`.
The Stripe price id for a plan is read at runtime from the environment variable
named in ``price_env`` so prices can be rotated without code changes; the
``lookup_key`` lets ``scripts/setup_stripe.py`` create the Stripe price
idempotently.

This is the single source of truth shared by the billing routes, the dashboard,
and the Stripe setup script. Adding a new offering = adding one ``Plan`` here.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    slug: str
    name: str
    tagline: str
    price_env: str          # env var holding the Stripe price id
    lookup_key: str         # Stripe price lookup_key (for setup_stripe.py)
    amount_cents: int
    interval: str           # Stripe recurring interval: "week" | "month"
    interval_count: int
    price_label: str        # e.g. "$800"
    period_label: str       # e.g. "every 4 weeks"
    product_description: str # Stripe product description
    features: tuple[str, ...]

    def price_id(self) -> str:
        """The configured Stripe price id, or "" if unset."""
        return os.getenv(self.price_env, "")


PODCAST_PARLAY = Plan(
    slug="podcast_parlay",
    name="Podcast Parlay",
    tagline="One weekly podcast, parlayed into a full week of multi-channel content.",
    price_env="STRIPE_PRICE_ID",
    lookup_key="podcast_parlay_800_per_4w",
    amount_cents=80000,
    interval="week",
    interval_count=4,
    price_label="$800",
    period_label="every 4 weeks",
    product_description="Recurring Podcast Parlay production — $800 every 4 weeks.",
    features=(
        "A produced weekly video podcast episode",
        "Short clips for YouTube, Instagram, and TikTok",
        "Daily social posts across LinkedIn, X, Facebook, and Instagram",
        "Blog posts and transcript insights for your website",
        "Case studies and product sell sheets from each episode",
        "Nathan's specialist agents orchestrating it end to end",
    ),
)

ADS_PARLAY = Plan(
    slug="ads_parlay",
    name="Ads Parlay",
    tagline="Managed Google Ads — your account run and optimized like a growth engine.",
    price_env="STRIPE_PRICE_ID_ADS_PARLAY",
    lookup_key="ads_parlay_500_per_month",
    amount_cents=50000,
    interval="month",
    interval_count=1,
    price_label="$500",
    period_label="per month",
    product_description="Managed Google Ads — monthly account management and optimization, $500/month.",
    features=(
        "Month-one account audit and optimization roadmap",
        "Ongoing bidding, budget, and campaign-structure management",
        "Keyword, match-type, and negative-keyword management",
        "Ad and asset management with disapproval monitoring",
        "Geographic expansion and competitor-intercept strategy",
        "Monthly performance report and Looker Studio dashboard",
    ),
)

# Insertion order is the display order on the dashboard.
PLANS: dict[str, Plan] = {p.slug: p for p in (PODCAST_PARLAY, ADS_PARLAY)}

DEFAULT_PLAN = PODCAST_PARLAY.slug


def get_plan(slug: str) -> Plan | None:
    return PLANS.get(slug)


def plan_for_price_id(price_id: str) -> Plan | None:
    """Resolve a Stripe price id back to its catalog Plan, or None."""
    if not price_id:
        return None
    for plan in PLANS.values():
        if plan.price_id() == price_id:
            return plan
    return None
