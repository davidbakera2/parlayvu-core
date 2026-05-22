# Investor Demo Runbook

This runbook demonstrates ParlayVU as an agentic content operating system with Teams as the front door, Nathan as the orchestrator, project memory as grounding, Dylan as web/deployment agent, M365 as agent mailbox infrastructure, HeyGen as live avatar presence, and approvals as the human control gate.

## Generate The Command Runbook

```powershell
python scripts/demo_runbook.py
```

The script prints a step-by-step PowerShell runbook. It does not deploy, send email, or call external systems by itself.

## Demo Story

1. Start the FastAPI backend.
2. Seed the RamAir project memory.
3. Check readiness.
4. Send a Teams-style message to Nathan.
5. Generate a Dylan campaign site.
6. Request deployment approval instead of deploying automatically.
7. Show Teams approval cards.
8. Create an agent email draft and approval request.
9. Ask a HeyGen LiveAvatar-style project question.

## Investor Talk Track

- ParlayVU turns one source asset into a repeatable content engine.
- Nathan is the orchestrator and Teams front door.
- Specialist agents create, route, deploy, draft, and support work inside explicit approval gates.
- Project memory keeps answers grounded to a specific client and campaign.
- Microsoft 365 gives agents operational identities.
- HeyGen LiveAvatar gives agents a real-time presence in Teams meetings.
- Approvals keep client-facing actions under human control.

## Safety Notes

- Dylan deploys are approval-gated.
- M365 sends are disabled by default.
- M365 drafts can create approval requests.
- HeyGen answers are bounded to project memory and flag pending approvals.
- The readiness report does not expose secrets.
