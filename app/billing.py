"""parlayvu.ai subscription billing via Stripe.

Single plan: $800 every 4 weeks (the Stripe price is created out-of-band; its
id is configured as STRIPE_PRICE_ID). Stripe hosts all payment UI — we use
Checkout for signup and the Customer Portal for card updates / cancellation.

The Stripe webhook is the source of truth: it keeps the local ``Subscription``
row in sync so the dashboard can gate access without calling Stripe on every
request.

Routes:
  GET  /dashboard          → gated landing; subscribe or manage billing
  POST /billing/checkout   → start a Stripe Checkout session (subscription mode)
  GET  /billing/success    → post-checkout return page
  GET  /billing/cancel     → checkout-cancelled return page
  POST /billing/portal     → open the Stripe Customer Portal
  POST /webhooks/stripe     → signature-verified subscription sync
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import plans as plans_catalog
from app.auth import current_account
from app.database import session_scope
from app.models import Account, Subscription
from app.settings import get_settings
from app.web import templates

logger = logging.getLogger("parlayvu.billing")

router = APIRouter(tags=["billing"])

# Stripe subscription statuses that grant access to the product.
ENTITLED_STATUSES = {"active", "trialing"}


def _stripe():
    """Return the configured stripe module, or raise if not set up."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing is not configured")
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def _ts_to_dt(value: Optional[int]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _to_plain_dict(obj) -> dict:
    """Normalize a Stripe object to a plain nested dict.

    Modern stripe-python ``StripeObject`` instances are not ``dict`` subclasses
    and do not support ``.get()``; this gives us uniform dict access whether the
    input is a live Stripe object (webhook / API) or a plain dict (tests)."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


# ───────────────────────────── core logic ──────────────────────────────────


def ensure_stripe_customer(account_id: str) -> str:
    """Return the account's Stripe customer id, creating one if needed."""
    stripe = _stripe()
    with session_scope() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if account.stripe_customer_id:
            return account.stripe_customer_id
        customer = stripe.Customer.create(
            email=account.email, metadata={"account_id": account.id}
        )
        account.stripe_customer_id = customer["id"]
        return customer["id"]


def get_subscription_status(account_id: str) -> dict:
    """Return {entitled, status, current_period_end, cancel_at_period_end}."""
    with session_scope() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.account_id == account_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if sub is None:
            return {"entitled": False, "status": None, "current_period_end": None,
                    "cancel_at_period_end": False}
        return {
            "entitled": sub.status in ENTITLED_STATUSES,
            "status": sub.status,
            "current_period_end": sub.current_period_end,
            "cancel_at_period_end": sub.cancel_at_period_end,
        }


def get_subscriptions_by_plan(account_id: str) -> dict:
    """Return ``{plan_slug: status_dict}`` for every plan in the catalog.

    A plan's status reflects the most recent local ``Subscription`` whose
    ``price_id`` matches that plan's configured Stripe price. A subscription
    whose price is unrecognized (e.g. legacy rows written before the catalog,
    or a price that predates a rotation) is attributed to the default plan so
    existing single-product subscribers keep their entitlement. Plans with no
    matching subscription come back not-entitled.
    """
    result = {
        slug: {"entitled": False, "status": None, "current_period_end": None,
               "cancel_at_period_end": False}
        for slug in plans_catalog.PLANS
    }
    with session_scope() as session:
        subs = (
            session.query(Subscription)
            .filter(Subscription.account_id == account_id)
            .order_by(Subscription.created_at.desc())
            .all()
        )
        seen: set[str] = set()
        for sub in subs:
            plan = plans_catalog.plan_for_price_id(sub.price_id)
            slug = plan.slug if plan is not None else plans_catalog.DEFAULT_PLAN
            if slug in seen:  # keep only the most recent per plan
                continue
            seen.add(slug)
            result[slug] = {
                "entitled": sub.status in ENTITLED_STATUSES,
                "status": sub.status,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end,
            }
    return result


def _upsert_subscription_from_stripe(stripe_subscription: dict) -> None:
    """Create or update the local Subscription row from a Stripe object,
    mapping it to the local account via the Stripe customer id."""
    stripe_subscription = _to_plain_dict(stripe_subscription)
    customer_id = stripe_subscription.get("customer")
    stripe_sub_id = stripe_subscription.get("id")
    status = stripe_subscription.get("status", "incomplete")
    cancel_at_period_end = bool(stripe_subscription.get("cancel_at_period_end"))
    items = (stripe_subscription.get("items") or {}).get("data") or []
    # Recent Stripe API versions moved current_period_end from the subscription
    # object down to the subscription item; fall back to the item if the
    # top-level field is absent.
    period_end_ts = stripe_subscription.get("current_period_end")
    if not period_end_ts and items:
        period_end_ts = items[0].get("current_period_end")
    period_end = _ts_to_dt(period_end_ts)
    price_id = (items[0].get("price") or {}).get("id") if items else None

    with session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.stripe_customer_id == customer_id)
            .one_or_none()
        )
        if account is None:
            logger.warning("Stripe webhook for unknown customer %s; ignoring", customer_id)
            return
        sub = (
            session.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_sub_id)
            .one_or_none()
        )
        if sub is None:
            sub = Subscription(account_id=account.id, stripe_subscription_id=stripe_sub_id)
            session.add(sub)
        sub.account_id = account.id
        sub.status = status
        sub.price_id = price_id
        sub.current_period_end = period_end
        sub.cancel_at_period_end = cancel_at_period_end


def handle_webhook_event(event: dict) -> None:
    """Route a verified Stripe event to subscription sync."""
    event = _to_plain_dict(event)
    event_type = event.get("type", "")
    obj = _to_plain_dict((event.get("data") or {}).get("object"))

    if event_type.startswith("customer.subscription."):
        _upsert_subscription_from_stripe(obj)
    elif event_type == "checkout.session.completed":
        # The session references the subscription id; fetch full object for items.
        sub_id = obj.get("subscription")
        if sub_id:
            stripe = _stripe()
            full = stripe.Subscription.retrieve(sub_id)
            _upsert_subscription_from_stripe(full)
    else:
        logger.debug("Unhandled Stripe event type: %s", event_type)


# ───────────────────────────────── routes ──────────────────────────────────


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, account: Optional[dict] = Depends(current_account)):
    if account is None:
        return RedirectResponse(url="/login", status_code=303)
    statuses = get_subscriptions_by_plan(account["id"])
    plan_views = [
        {
            "slug": plan.slug,
            "name": plan.name,
            "tagline": plan.tagline,
            "price_label": plan.price_label,
            "period_label": plan.period_label,
            "features": plan.features,
            "subscription": statuses[plan.slug],
        }
        for plan in plans_catalog.PLANS.values()
    ]
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"account": account, "plans": plan_views},
    )


@router.post("/billing/checkout")
def checkout(
    request: Request,
    plan: str = Form(plans_catalog.DEFAULT_PLAN),
    account: Optional[dict] = Depends(current_account),
):
    if account is None:
        return RedirectResponse(url="/login", status_code=303)
    selected = plans_catalog.get_plan(plan)
    if selected is None:
        raise HTTPException(status_code=404, detail="Unknown plan")
    price_id = selected.price_id()
    if not price_id:
        raise HTTPException(status_code=503, detail="Billing price is not configured")
    settings = get_settings()
    stripe = _stripe()
    customer_id = ensure_stripe_customer(account["id"])
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.app_base_url}/billing/success",
        cancel_url=f"{settings.app_base_url}/billing/cancel",
        allow_promotion_codes=True,
        metadata={"plan": selected.slug},
    )
    return RedirectResponse(url=checkout_session["url"], status_code=303)


@router.post("/billing/portal")
def portal(request: Request, account: Optional[dict] = Depends(current_account)):
    if account is None:
        return RedirectResponse(url="/login", status_code=303)
    settings = get_settings()
    stripe = _stripe()
    customer_id = ensure_stripe_customer(account["id"])
    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.app_base_url}/dashboard",
    )
    return RedirectResponse(url=portal_session["url"], status_code=303)


@router.get("/billing/success", response_class=HTMLResponse)
def billing_success(request: Request):
    return templates.TemplateResponse(request=request, name="subscribe_success.html", context={})


@router.get("/billing/cancel", response_class=HTMLResponse)
def billing_cancel(request: Request):
    return templates.TemplateResponse(request=request, name="subscribe_cancel.html", context={})


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    stripe = _stripe()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception as exc:  # invalid payload or signature
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature")
    handle_webhook_event(event)
    return {"received": True}
