# Christ's Hope International

ParlayVU client folder. Folder structure mirrors RamAir's; see [client_artifacts/ramair/README.md](../ramair/README.md) for the canonical layout reference.

- `client_id`: `christshope`
- Teams channel binding: see `config.yaml`
- Meeting notes template: `06_Templates/Meeting_Notes_Template.docx` — same path for every client; only the docx content differs. Canonical copy lives in the Teams `06_Templates/` folder once uploaded; the repo copy is a starter and cold-start fallback.

## Onboarding TODO

- [x] Tavus persona: `p7017121a743` (Nathan Ellis for Christ's Hope), wired with `X-Parlayvu-Client-Id: christshope` header.
- [x] First client brief: `00_Client_Brief/client-brief.md` drafted — fill in TBD team contacts when known.
- [ ] Upload meeting-notes template to Teams: drag `06_Templates/Meeting_Notes_Template.docx` into the Christ's Hope Teams channel's `06_Templates/` folder so the client can edit it directly in Word.
- [ ] Template branding: the template was copied from RamAir's; visible header/footer text still says "RamAir" and needs a pass in Word (the `{{PLACEHOLDER}}` tokens are correct and render regardless).
