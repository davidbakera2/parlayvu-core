# Agent guide: `sites/`

Read **`PARLAYVU_CLIENT_SITES.md`** and **`RESEND_SETUP.md`**.

## Deploy

```bash
cd sites/<client>
npm run pages:deploy
```

## Contact

| File | Purpose |
|------|---------|
| `site.contact.json` | `contact.to`, `contact.from`, domain |
| `functions/api/contact.js` | Resend — needs `RESEND_API_KEY` on Pages |
| `src/components/ContactForm.astro` | UI |

## Env (Pages)

- `RESEND_API_KEY` — secret, never in git
- `CONTACT_TO_EMAIL`, `CONTACT_FROM_EMAIL`, `CONTACT_FROM_NAME` — in `wrangler.toml` or dashboard

## Do not

- Add Mailchannels / Cloudflare Send Email for contact forms
- Use Next.js or deploy `out/`
- Commit `RESEND_API_KEY`
