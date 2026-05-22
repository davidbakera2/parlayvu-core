# ParlayVU Core — agent guide

## Client marketing sites (`sites/`)

**Read first:** [sites/PARLAYVU_CLIENT_SITES.md](sites/PARLAYVU_CLIENT_SITES.md)

| Task | Command / tool |
|------|----------------|
| New client site | `node sites/scripts/launch-client.mjs <slug> --domain … --to … --from …` |
| Or via Dylan | `scaffold_parlayvu_client_site(...)` |
| Deploy | `cd sites/<slug> && npm run pages:deploy` |
| Email setup | [sites/RESEND_SETUP.md](sites/RESEND_SETUP.md) |
| Config | `sites/<slug>/site.contact.json` |

Stack: **Astro** → `dist/` → **Cloudflare Pages** → **Resend** (`/api/contact`).

Reference implementation: `sites/baker-strategy/`.

## Campaign landings (`generated_sites/`)

Dylan’s `generate_astro_site` builds one-off ParlayVU-style campaign pages under `generated_sites/`. Not the same as the client-site template.

## Secrets

- Repo `.env`: `CLOUDFLARE_API`, `RESEND_API` (gitignored)
- Pages production: `RESEND_API_KEY` secret per project (dashboard)

## Do not

- Use Next.js for new `sites/` clients
- Use Cloudflare Email Routing for contact forms on client sites
