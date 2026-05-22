# Resend setup (ParlayVU — all client sites)

## One-time (agency)

1. Create account at [resend.com](https://resend.com).
2. Create API key → store in repo `.env` as `RESEND_API` or `RESEND_API_KEY` (never commit).

## Per client domain

1. Resend dashboard → **Domains** → **Add** `clientdomain.com`.
2. Add the DNS records Resend shows (SPF/DKIM at the client’s DNS host — Cloudflare, GoDaddy, etc.).
3. Wait until status is **Verified**.

## Per Pages project

[Cloudflare Pages → project → Settings → Environment variables](https://dash.cloudflare.com/)

| Name | Type | Value |
|------|------|--------|
| `RESEND_API_KEY` | **Secret** | `re_...` (push from `.env`: `node sites/scripts/push-resend-secret.mjs PROJECT_NAME`) |
| `CONTACT_TO_EMAIL` | Plain | from `site.contact.json` → `contact.to` |
| `CONTACT_FROM_EMAIL` | Plain | `contact.from` (must be on verified domain) |
| `CONTACT_FROM_NAME` | Plain | `contact.fromName` |

Set for **Production** (and Preview if you test previews).

`wrangler.toml` `[vars]` can hold the three `CONTACT_*` values; **only** the API key stays a dashboard secret.

## Test

```bash
curl -s -X POST https://CLIENT_DOMAIN/api/contact \
  -F "name=Test" -F "email=test@example.com" -F "message=Hello" -F "website="
```

Expect: `{"ok":true}`

## Agent checklist

1. Read `sites/<client>/site.contact.json`.
2. Confirm domain verified in Resend.
3. Confirm Pages env vars (four names above).
4. `npm run pages:deploy` in client folder.
5. POST test `/api/contact`.
