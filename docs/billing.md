# parlayvu.ai login + subscription

Customer-facing login and recurring billing for the **Podcast Parlay
subscription** ($800 every 4 weeks). Built into the FastAPI app as
server-rendered pages; Stripe hosts all payment UI.

## What a customer sees

1. `GET /login` — enters their email.
2. Receives a **magic-link** email (Resend), valid 15 minutes, single use.
3. Clicking it creates a 30-day session cookie and lands on `GET /dashboard`.
4. Dashboard shows subscription status:
   - Not subscribed → **Subscribe** → Stripe Checkout ($800 / 4 weeks).
   - Subscribed → renewal/cancel date → **Manage billing** → Stripe Customer Portal.

Stripe webhooks keep the local `subscriptions` table in sync, so access is
gated without calling Stripe on every request.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET  | `/login` | Email entry form |
| POST | `/auth/request-link` | Mint token, email sign-in link |
| GET  | `/auth/verify?token=` | Validate, set session cookie, → `/dashboard` |
| POST | `/auth/logout` | Revoke session |
| GET  | `/dashboard` | Gated; subscribe or manage |
| POST | `/billing/checkout` | Start Stripe Checkout (subscription) |
| POST | `/billing/portal` | Open Stripe Customer Portal |
| GET  | `/billing/success` `/billing/cancel` | Checkout return pages |
| POST | `/webhooks/stripe` | Signature-verified subscription sync |

## One-time setup

### 1. Install deps & run the migration
```powershell
pip install -r requirements.txt
alembic upgrade head   # creates accounts, magic_links, login_sessions, subscriptions
```

### 2. Stripe
1. Create a Stripe account; grab the **secret key** (`sk_test_…` to start).
2. Create the recurring price:
   ```powershell
   $env:STRIPE_SECRET_KEY="sk_test_..."; python scripts/setup_stripe.py
   ```
   Copy the printed `STRIPE_PRICE_ID` into `.env`.
3. Add a **webhook endpoint** in the Stripe dashboard pointing to
   `https://<your-domain>/webhooks/stripe`, subscribed to:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `customer.subscription.created`
   Copy its **signing secret** (`whsec_…`) into `STRIPE_WEBHOOK_SECRET`.
4. Enable the **Customer Portal** in Stripe (Settings → Billing → Customer portal).

Local webhook testing:
```powershell
stripe listen --forward-to localhost:8000/webhooks/stripe
```

### 3. Resend (magic-link email)
1. Verify a sending domain (e.g. `parlayvu.ai`) in Resend.
2. Set `RESEND_API_KEY` and `EMAIL_FROM` (a verified sender, e.g.
   `ParlayVU <login@parlayvu.ai>`).
   > If `RESEND_API_KEY` is unset, the app logs the magic link instead of
   > emailing it — handy for local dev, never for production.

### 4. App config
```
APP_BASE_URL=https://your-domain        # used to build links + Stripe redirects
SESSION_SECRET=<python -c "import secrets;print(secrets.token_urlsafe(48))">
```

## Notes
- This build covers login + self-serve subscribe/cancel. Surfacing each
  subscriber's rendered Podcast Parlays (from `video_system` / `GeneratedOutput`)
  on the dashboard is a planned follow-up.
- One-time $200 single-podcast purchases are intentionally out of scope.
