# RamAir Channel Starter Kit

This folder mirrors the standard `Files` structure for the RamAir Teams channel. Copy or upload these files to the channel SharePoint folder after the channel is created, then bind the channel to project memory from `Posts`.

Binding command:

```text
@ParlayVU bind this channel to RamAir
```

Standard tabs:

- `Posts` for updates, Nathan questions, approvals, and decisions.
- `Files` for the canonical project documents in this folder structure.
- `Planner` or `Tasks` for milestones, interviews, deliverables, and approval gates.
- `Meeting notes in Files` for Nathan-published `.md` and `.docx` recaps.
- `Performance dashboard` for Power BI in Teams backed by CSV files in SharePoint.
- `ParlayVU/Nathan` for project memory and next actions.

Operating rules:

- Keep client-facing decisions in `Posts`.
- Use approval IDs when Nathan surfaces pending decisions.
- Store source material before asking Nathan to summarize it.
- Do not invent metrics. Use `05_Performance/data/` and `05_Performance/social-performance-dashboard-spec.md` for the Power BI starter, and keep `05_Performance/performance-snapshot.md` as the manual narrative fallback.
