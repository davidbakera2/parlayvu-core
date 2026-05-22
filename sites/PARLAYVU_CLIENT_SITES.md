# ParlayVU client site playbook

One method for every client marketing site: **light, agentic, developer-friendly.**

## Stack

| Layer | Choice |
|-------|--------|
| Site | **Astro** (static) + **Tailwind CSS v4** |
| Interactivity | `.astro` + **React island** only when needed (`client:load`) |
| Host | **Cloudflare Pages** — `dist/` + `functions/` |
| Contact | `POST /api/contact` → **Resend** |

Reference: `sites/baker-strategy/`. Email setup: `sites/RESEND_SETUP.md`.

## Layout

```
sites/<client-slug>/
  astro.config.mjs          # static, format: file, trailingSlash: never
  package.json                # dev | build | pages:deploy
  wrangler.toml               # pages_build_output_dir = "./dist", [vars] CONTACT_*
  site.contact.json           # domain, contact.to/from, pagesProject, zoneId
  src/pages/*.astro
  src/components/ContactForm.astro
  functions/api/contact.js    # Resend only
  public/
  DEPLOY.md
```

## Commands

```bash
cd sites/<client-slug>
npm install
npm run dev
npm run pages:deploy
```

## Contact form

- `ContactForm.astro` — vanilla script, POST `/api/contact`, inline success/error.
- `contact.js` — requires `RESEND_API_KEY` + `CONTACT_*` env on Pages.
- `from` must use a **verified** domain in Resend; `to` is any inbox.

## New client (launch script)

```bash
node sites/scripts/launch-client.mjs ramair \
  --domain ramair.co \
  --to sales@ramair.co \
  --from contact@ramair.co \
  --brand "RamAir" \
  --deploy
```

Or copy `sites/_template/` manually and edit `site.contact.json` (schema: `sites/site.contact.schema.json`).

Then:

1. Resend: verify sending domain.
2. Pages: `RESEND_API_KEY` secret on the project.
3. Cloudflare: custom domain + DNS.
4. `npm run pages:deploy` in `sites/<client-slug>/`.
5. Test `POST /api/contact`.

## Motion defaults

1. Tailwind transitions / hover.
2. Optional Astro View Transitions.
3. React island for complex UI only.

## Not used

- Next.js for new sites
- FormSubmit / Web3Forms / mailto
- Cloudflare Email Routing / Mailchannels for contact forms
