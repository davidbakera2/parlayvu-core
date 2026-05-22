# bakerstrategy.com

Astro + Cloudflare Pages + Resend. See `../PARLAYVU_CLIENT_SITES.md` and `../RESEND_SETUP.md`.

## Deploy

```bash
cd sites/baker-strategy
npm ci
npm run pages:deploy
```

Output: **`dist/`** → project `bakerstrategy-site`.

## Resend (required for contact form)

1. Verify **bakerstrategy.com** in Resend.
2. Pages → **bakerstrategy-site** → Environment variables:
   - `RESEND_API_KEY` (secret)
   - `CONTACT_TO_EMAIL` = `david@bakerstrategy.com`
   - `CONTACT_FROM_EMAIL` = `contact@bakerstrategy.com`
   - `CONTACT_FROM_NAME` = `Baker Strategy Website`

`wrangler.toml` already sets the three `CONTACT_*` vars; add the API key in the dashboard only.

## Assets

`public/case-studies/ramair-david-hart.png` for the ParlayVU case study image.
