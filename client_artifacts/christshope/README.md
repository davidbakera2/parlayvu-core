# Christ's Hope International

ParlayVU client folder. Folder structure mirrors RamAir's; see [client_artifacts/ramair/README.md](../ramair/README.md) for the canonical layout reference.

- `client_id`: `christshope`
- Teams channel binding: see `config.yaml`
- Meeting notes template: `00_Client_Brief/Templates/Christs Hope Meeting Notes Template.docx`

## Onboarding TODO

- [ ] Tavus persona: create a Christ's Hope Nathan persona in the Tavus UI, then run `services/teams-media-bot/scripts/Update-NathanPersonaLLM.ps1 -PersonaId <new-id> -ClientId christshope ...` to wire the `X-Parlayvu-Client-Id` header.
- [ ] Template branding: the template was copied from RamAir's; visible header/footer text still says "RamAir" and needs a pass in Word (the `{{PLACEHOLDER}}` tokens are correct and will render).
- [ ] First client brief: drop a `00_Client_Brief/client-brief.md` describing the engagement.
