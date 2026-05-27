# Baker Strategy Group (holding-company tenant)

Nathan-as-Chief-of-Staff for Baker Strategy Group — David's holding company. Used in the **Baker Strategy** Teams team for portfolio-level coordination, business development, and internal strategy discussion.

- `client_id`: `bakerstrategy`
- Tavus persona: **none** (Teams-chat-only for now; add one if avatar-Nathan becomes useful for holding-company meetings)
- Teams team binding: see `config.yaml`
- Meeting notes template: `06_Templates/Meeting_Notes_Template.docx` (canonical filename)

## Source material

`01_Source_Material/` is empty at scaffold time. Populate with portfolio briefs, strategic plans, BD notes, financial summaries, etc. as engagements happen. Anything dropped into this client's Teams channel can also be pulled in via:

```
python -m app.services.client_file_ingester bakerstrategy
```

…which summarizes PDFs/.docx into structured markdown under `01_Source_Material/reports/` for zero-latency context loading.

## Why this tenant exists

Baker Strategy Group is a real business with its own meetings, planning, and stakeholders — distinct from any single ParlayVU client engagement and distinct from ParlayVU the product company. Modeling it as its own tenant keeps holding-company conversations from polluting client contexts and gives David a coordinated space for portfolio work.

## Onboarding TODO

- [x] Folder scaffold + config.yaml + template
- [ ] Install ParlayVU bot in the Baker Strategy Teams team (David — via Teams UI)
- [ ] Run `@ParlayVU bind this channel to Baker Strategy` in the General channel
- [ ] (As needed) drop initial source material into `01_Source_Material/` or the team's Teams channel + run the ingester
