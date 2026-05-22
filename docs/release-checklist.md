# Pitch-Readiness Release Checklist

Use this checklist before showing ParlayVU to an angel investor or moving the backend into a hosted demo environment.

## 1. Secret Safety

- Rotate any credentials that were stored in local `.env`.
- Confirm `.env` is ignored and never shared.
- Move production values into AWS Secrets Manager under `/parlayvu/prod/<NAME>`.
- Keep `MICROSOFT_GRAPH_ALLOW_SEND=false` unless send approvals have been fully tested.

## 2. Local Verification

- Install dependencies.
- Run the full test suite.
- Confirm the test count and result.
- Run syntax checks for scripts and app modules.

```powershell
python -m unittest discover -s tests
```

## 3. Demo Memory

- Initialize the configured database.
- Seed the RamAir investor demo project.
- Confirm `/memory/projects/ramair-straight-from-the-hart` returns project context.

```powershell
python scripts/seed_demo.py
```

## 4. Readiness

- Start the API.
- Confirm `/health` returns `healthy`.
- Confirm `/readiness` shows expected configured sections.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/readiness" | ConvertTo-Json -Depth 20
```

## 5. Demo Rehearsal

- Generate the investor demo runbook.
- Walk through Teams, Nathan, Dylan, approvals, M365 draft, and HeyGen live question flow.
- Confirm risky actions request approval instead of executing automatically.

```powershell
python scripts/demo_runbook.py
```

## 6. Container And Fargate

- Build the Docker image.
- Review `infra/aws/ecs-task-definition.template.json`.
- Confirm all required secrets exist in AWS Secrets Manager.
- Print and review the AWS deployment checklist.

```powershell
python scripts/aws_deploy_checklist.py
```

## 7. Pitch Materials

- Live site is available.
- RamAir case study proof point is visible.
- Architecture story is clear: Teams front door, Nathan orchestration, specialist agents, project memory, M365 identities, HeyGen presence, approval gates, Cloudflare output, Fargate backend.
- Demo fallback path is ready if any external integration is unavailable.

## Final Gate

Do not pitch from a shared or production-facing environment until:

- Secrets are rotated.
- Readiness is reviewed.
- The demo runbook is rehearsed.
- Approval gates are confirmed.
- The current deployment target is known: local, staging, or Fargate.
