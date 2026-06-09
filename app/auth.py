"""parlayvu.ai customer authentication — passwordless magic-link login.

Flow:
  1. GET  /login                 → email form
  2. POST /auth/request-link      → mint a single-use token, email a sign-in link
  3. GET  /auth/verify?token=…    → validate, create a session cookie, → /dashboard
  4. POST /auth/logout            → revoke session, clear cookie

Tokens (magic-link and session) are high-entropy random strings. We email /
set the raw token but persist only its SHA-256 hash, so a database read alone
cannot impersonate a user. Email delivery uses Resend.

DB access goes through ``session_scope`` (patched in tests, mirroring
app/approvals.py).
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import session_scope
from app.models import Account, LoginSession, MagicLink
from app.settings import get_settings
from app.web import SESSION_COOKIE, templates

logger = logging.getLogger("parlayvu.auth")

router = APIRouter(tags=["auth"])

MAGIC_LINK_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    """Normalize possibly-naive datetimes from the DB to UTC-aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ───────────────────────────── core logic ──────────────────────────────────


def create_magic_link(email: str) -> str:
    """Find-or-create the account for ``email`` and return a raw magic-link token."""
    email = email.strip().lower()
    raw_token = secrets.token_urlsafe(32)
    with session_scope() as session:
        account = session.query(Account).filter(Account.email == email).one_or_none()
        if account is None:
            account = Account(email=email)
            session.add(account)
            session.flush()
        session.add(
            MagicLink(
                account_id=account.id,
                token_hash=_hash_token(raw_token),
                expires_at=_now() + MAGIC_LINK_TTL,
            )
        )
    return raw_token


def consume_magic_link(raw_token: str) -> Optional[str]:
    """Validate a magic-link token and mark it used. Returns the account id or None."""
    token_hash = _hash_token(raw_token)
    with session_scope() as session:
        link = session.query(MagicLink).filter(MagicLink.token_hash == token_hash).one_or_none()
        if link is None or link.used_at is not None:
            return None
        if _aware(link.expires_at) < _now():
            return None
        link.used_at = _now()
        return link.account_id


def create_session(account_id: str) -> str:
    """Create a login session for an account and return the raw session token."""
    raw_token = secrets.token_urlsafe(32)
    with session_scope() as session:
        session.add(
            LoginSession(
                account_id=account_id,
                token_hash=_hash_token(raw_token),
                expires_at=_now() + SESSION_TTL,
            )
        )
    return raw_token


def revoke_session(raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    with session_scope() as session:
        login = (
            session.query(LoginSession)
            .filter(LoginSession.token_hash == token_hash)
            .one_or_none()
        )
        if login is not None and login.revoked_at is None:
            login.revoked_at = _now()


def account_for_session(raw_token: Optional[str]) -> Optional[dict]:
    """Resolve a raw session cookie to a plain account dict, or None."""
    if not raw_token:
        return None
    token_hash = _hash_token(raw_token)
    with session_scope() as session:
        login = (
            session.query(LoginSession)
            .filter(LoginSession.token_hash == token_hash)
            .one_or_none()
        )
        if login is None or login.revoked_at is not None:
            return None
        if _aware(login.expires_at) < _now():
            return None
        account = session.get(Account, login.account_id)
        if account is None:
            return None
        return {
            "id": account.id,
            "email": account.email,
            "stripe_customer_id": account.stripe_customer_id,
            "client_id": account.client_id,
        }


def send_magic_link_email(to_email: str, link: str) -> None:
    """Send the sign-in link via Resend. Logs (and, in dev, surfaces) if unconfigured."""
    settings = get_settings()
    if not settings.resend_api_key:
        # Dev fallback: no email provider configured — log the link so local
        # testing still works. Never do this in production.
        logger.warning("RESEND_API_KEY not set — magic link for %s: %s", to_email, link)
        return
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to_email],
                "subject": "Your parlayvu.ai sign-in link",
                "html": (
                    "<p>Click below to sign in to parlayvu.ai. "
                    "This link expires in 15 minutes and can be used once.</p>"
                    f'<p><a href="{link}">Sign in to parlayvu.ai</a></p>'
                    f'<p>Or paste this URL into your browser:<br>{link}</p>'
                ),
            },
            timeout=15,
        )
        response.raise_for_status()
    except Exception:  # pragma: no cover - network failure path
        logger.exception("Failed to send magic-link email to %s", to_email)
        raise


# ──────────────────────────── dependencies ─────────────────────────────────


def current_account(request: Request) -> Optional[dict]:
    """FastAPI dependency: the logged-in account dict, or None."""
    return account_for_session(request.cookies.get(SESSION_COOKIE))


# ───────────────────────────────── routes ──────────────────────────────────


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.post("/auth/request-link", response_class=HTMLResponse)
def request_link(request: Request, email: str = Form(...)):
    clean = email.strip().lower()
    # Always behave the same way regardless of whether the account exists,
    # so this endpoint can't be used to enumerate customers.
    if "@" in clean and "." in clean.split("@")[-1]:
        raw_token = create_magic_link(clean)
        settings = get_settings()
        link = f"{settings.app_base_url}/auth/verify?token={raw_token}"
        try:
            send_magic_link_email(clean, link)
        except Exception:
            logger.exception("magic link send failed for %s", clean)
    return templates.TemplateResponse(
        request=request, name="check_email.html", context={"email": clean}
    )


@router.get("/auth/verify")
def verify(token: str):
    account_id = consume_magic_link(token)
    if account_id is None:
        return RedirectResponse(url="/login?error=invalid", status_code=303)
    raw_session = create_session(account_id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        raw_session,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=settings.app_base_url.startswith("https"),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/auth/logout")
def logout(request: Request):
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        revoke_session(raw)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
