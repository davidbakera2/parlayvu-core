# ParlayVU Setup

Single source of truth for **what env vars and Azure resources are required to run
parlayvu-api in production**. If something is documented here, it's needed. If
it's not here and you're being told to set it, ask why before adding it.

---

## 1. Azure resources

| Resource | Name | Purpose |
|---|---|---|
| Subscription | _(your sub)_ | Owns everything |
| Resource Group | `rg-parlayvu-demo` | Holds API + ACR + supporting infra |
| Container Registry | `parlayvucore` (loginServer `parlayvucore.azurecr.io`) | Hosts the API Docker image |
| Container App | `parlayvu-api` | Runs the FastAPI app, exposed on HTTPS |
| Container App Environment | _(provisioned with the app)_ | Networking + logging |

Future resources (not required for v1):
- `parlayvu-teams-media-bot` Container App (Bot Framework wrapper) — deployed only when needed
- Windows Server 2022 VM (Graph Media SDK host) — deferred indefinitely

---

## 2. Container App env vars — required

These must be set on the `parlayvu-api` Container App for the system to function.
Run from PowerShell:

```powershell
az containerapp update --name parlayvu-api --resource-group rg-parlayvu-demo --set-env-vars `
  "DATABASE_URL=postgresql://..." `
  "ANTHROPIC_API_KEY=sk-ant-..." `
  "TAVILY_API_KEY=tvly-..." `
  "MICROSOFT_TENANT_ID=..." `
  "MICROSOFT_CLIENT_ID=..." `
  "MICROSOFT_CLIENT_SECRET=..." `
  "TAVUS_API_KEY=..." `
  "TAVUS_PERSONA_ID=..." `
  "TAVUS_REPLICA_ID=..." `
  "NATHAN_MAILBOX=nathan@parlayvu.ai"
```

### What each one does

| Var | What it powers | Where it's read |
|---|---|---|
| `DATABASE_URL` | Neon Postgres for project memory + approvals | `app/database.py` |
| `ANTHROPIC_API_KEY` | Claude Opus 4.7 — Nathan's brain on `/v1/chat/completions` | `app/nathan_llm.py`, `app/settings.py` |
| `TAVILY_API_KEY` | Nathan's `web_search` tool | `app/tools/web_tools.py` |
| `MICROSOFT_TENANT_ID` + `MICROSOFT_CLIENT_ID` + `MICROSOFT_CLIENT_SECRET` | Microsoft Graph app — mail, OneNote, Teams files | `app/microsoft365.py` |
| `TAVUS_API_KEY` + `TAVUS_PERSONA_ID` + `TAVUS_REPLICA_ID` | Avatar provider (Tavus CVI) | `app/avatar/tavus.py` |
| `NATHAN_MAILBOX` | Nathan's M365 mailbox for email drafts | `app/microsoft365.py` |

### Optional but recommended

| Var | What it adds |
|---|---|
| `NATHAN_LLM_API_KEY` | Bearer token Tavus sends when calling `/v1/chat/completions` (auth) |
| `TEAMS_APP_ID` + `TEAMS_APP_PASSWORD` + `TEAMS_TENANT_ID` + `TEAMS_WEBHOOK_SECRET` | Bot Framework Teams bot integration |
| `M365_FILES_TEAM_ID` + `M365_FILES_CHANNEL_ID` | Default Teams channel for meeting note publishing |
| `<AGENT>_MAILBOX` | Each other agent's M365 mailbox |

---

## 3. Two distinct Azure AD identities

This is the part that previously caused confusion. There are two app registrations:

### Microsoft Graph app (`MICROSOFT_*`)
- Used for: mail, OneNote, SharePoint, Teams files (via Graph API)
- Required permissions: `Mail.Send`, `Mail.ReadWrite`, `Notes.ReadWrite.All`, `Files.Read.All`, `Sites.Read.All` (application permissions, admin consented)
- Read by: `app/microsoft365.py` and (via `MicrosoftGraphClient`) `app/tools/teams_files_tool.py`

### Bot Framework app (`TEAMS_APP_*`)
- Used for: receiving Teams messages, posting Teams replies (via Bot Framework / Azure Bot Service)
- Identity: registered through Azure Bot Service, not directly in Entra ID
- Read by: `app/teams.py`

**Do not consolidate the env var names.** They represent different identities and
may be different app registrations. The system requires both to be configured.

---

## 4. CI/CD — OIDC federated credentials

CI is split into three workflows:

| Workflow | Triggers on | Deploys |
|---|---|---|
| `.github/workflows/deploy-api.yml` | push to main (paths: `app/**`, `requirements.txt`, `Dockerfile`) | parlayvu-api |
| `.github/workflows/deploy-media-bot.yml` | `workflow_dispatch` only | parlayvu-teams-media-bot |
| `.github/workflows/build-media-worker.yml` | `workflow_dispatch` only | Windows artifact (manual xcopy to VM) |

All workflows authenticate to Azure via **OIDC federated credentials** — no client
secret stored in GitHub.

### One-time CI setup (run once)

```powershell
$sub = az account show --query id -o tsv
$sp = az ad sp create-for-rbac --name "parlayvu-github-actions" `
  --role contributor `
  --scopes /subscriptions/$sub/resourceGroups/rg-parlayvu-demo `
  | ConvertFrom-Json

# Federated credential for pushes to main
az ad app federated-credential create --id $sp.appId --parameters (@{
  name      = "parlayvu-github-main"
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = "repo:davidbakera2/parlayvu-core:ref:refs/heads/main"
  audiences = @("api://AzureADTokenExchange")
} | ConvertTo-Json -Compress)

# Federated credential for manual workflow_dispatch runs
az ad app federated-credential create --id $sp.appId --parameters (@{
  name      = "parlayvu-github-dispatch"
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = "repo:davidbakera2/parlayvu-core:ref:refs/heads/main"
  audiences = @("api://AzureADTokenExchange")
} | ConvertTo-Json -Compress)

# Print the 3 values you need in GitHub Secrets
Write-Host "AZURE_CLIENT_ID:       $($sp.appId)"
Write-Host "AZURE_TENANT_ID:       $($sp.tenant)"
Write-Host "AZURE_SUBSCRIPTION_ID: $sub"
```

Then go to **GitHub → Settings → Secrets and variables → Actions** and add:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

No client secret needed. OIDC handles auth.

The service principal also needs **AcrPull + AcrPush** on the ACR (so it can
push images during deploy):

```powershell
$acrId = az acr show --name parlayvucore --query id -o tsv
az role assignment create --assignee $sp.appId --role AcrPush --scope $acrId
```

---

## 5. Tavus persona setup

Tavus is configured **out of band** in the Tavus dashboard, then pointed at our
custom LLM endpoint:

1. Create a persona in Tavus dashboard, copy its `persona_id` → `TAVUS_PERSONA_ID`
2. Create a replica (likeness) for Nathan, copy `replica_id` → `TAVUS_REPLICA_ID`
3. After deploying parlayvu-api, run:

   ```powershell
   .\services\teams-media-bot\scripts\Update-NathanPersonaLLM.ps1 `
     -TavusApiKey "$env:TAVUS_API_KEY" `
     -PersonaId "$env:TAVUS_PERSONA_ID" `
     -ParlayVuApiUrl "https://parlayvu-api.<your-env>.azurecontainerapps.io"
   ```

   This PATCHes the persona's `custom_llm` field so Tavus calls our
   `/v1/chat/completions` instead of its built-in model.

---

## 6. Verifying a deploy

After a deploy goes green:

```powershell
$base = "https://parlayvu-api.<your-env>.azurecontainerapps.io"
Invoke-RestMethod "$base/health"
Invoke-RestMethod "$base/readiness"
Invoke-RestMethod "$base/nathan/llm/status"
```

- `/readiness` is the master check — `status: ready` means all required vars are set.
- `/nathan/llm/status` zooms in on the custom LLM endpoint Tavus uses.

---

## 7. What is NOT required

These were removed in Phase 2 cleanup. If you see them in old docs or scripts,
ignore them — they're not needed:

- `HEYGEN_*` — HeyGen was evaluated and removed. Tavus is the chosen provider.
- `M365_TENANT_ID` / `M365_CLIENT_ID` / `M365_CLIENT_SECRET` — duplicates of `MICROSOFT_*`.
- `TEAMS_BOT_APP_ID` / `TEAMS_BOT_PASSWORD` — duplicates of `TEAMS_APP_*`.
- `TEAMS_CLIENT_ID` / `TEAMS_CLIENT_SECRET` — Teams file access uses the same Graph credentials as `MICROSOFT_*`.
- `AZURE_CREDENTIALS` (the deprecated `--sdk-auth` JSON) — replaced by OIDC + the three individual `AZURE_*` secrets.
