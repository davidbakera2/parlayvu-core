# parlayvu.ai — marketing site (source of record)

Static marketing homepage for **parlayvu.ai**, served by the Cloudflare Pages
project **`parlayvu-ai-site`** (DNS: `parlayvu.ai` + `www` CNAME → `parlayvu-ai-site.pages.dev`).

## History

The original Astro source was lost; the only leftover was a dead, empty Next.js
stub in `Documents/ParlayVU/Projects/parlayvu-ai/source` (stale Vercel notes,
no pages). On 2026-06-09 the live site was **mirrored** into this folder to
become the version-controlled source of record, and the **Podcast Parlay**
offering was added.

This is the rendered static output (HTML + compiled CSS in `_astro/` + assets in
`brand/`, `agents/`, `case-studies/`). It is not an Astro project anymore; edit
`index.html` directly. A future clean rebuild can replace it.

## Offering sections

- Nav links **Podcast Parlay** → `#podcast-parlay` and **Ads Parlay** →
  `#ads-parlay` (header + footer).
- Section `#podcast-parlay` pitches the $800 / 4-week subscription; section
  `#ads-parlay` pitches the $500 / month managed-Google-Ads subscription. Both
  link to **https://app.parlayvu.ai/login** (the login-first Stripe subscribe
  flow), where the dashboard now lists every offering as its own subscribe card.
- Both sections share the self-contained `<style>` block (`.pp-*`) in
  `index.html`, themed to the site's dark palette — it does not depend on the
  compiled Tailwind CSS.

## Preview locally

```powershell
python -m http.server 8090 --directory sites/parlayvu-ai
# open http://localhost:8090
```

## Deploy

Deploys to the existing Pages project (no DNS change). Requires a Cloudflare API
token with **Account → Cloudflare Pages → Edit** (the DNS-scoped `CLOUDFLARE_API`
token is NOT sufficient).

```powershell
$env:CLOUDFLARE_API_TOKEN="<pages-edit-token>"
$env:CLOUDFLARE_ACCOUNT_ID="<account-id>"
npx wrangler pages deploy . --project-name=parlayvu-ai-site --branch=main
```
