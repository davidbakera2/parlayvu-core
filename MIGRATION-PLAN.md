# Migration Plan: Baker Strategy → ParlayVU Tenant

> ✅ **STATUS: COMPLETED 2026-05-26.** All phases (1–9) finished. ParlayVU runs entirely
> in its own Entra tenant and Azure subscription; the old Baker Strategy resources are
> decommissioned. This document is retained for historical reference only — see
> [ARCHITECTURE.md](./ARCHITECTURE.md) §7 for the current production environment.

> **Goal:** Move every piece of ParlayVU infrastructure that currently lives in the Baker Strategy Group tenant into ParlayVU's own M365 + Azure environment.
>
> **Why:** ParlayVU is its own company now. Mailboxes, Teams channels, and project files are already in ParlayVU's M365 tenant. But the app registration, Graph permissions, and Azure resources are still in Baker Strategy — which is why Nathan got 403 on the meeting notes save. Application permissions are scoped per tenant, so an app reg in Baker Strategy cannot touch resources in ParlayVU.
>
> **Estimated total time:** 3–4 hours of focused work, mostly waiting on Azure provisioning.

---

## What's moving vs. what's staying

| Item | Current home | Destination |
|---|---|---|
| Entra app registration "ParlayVU Agents" | Baker Strategy tenant | **ParlayVU tenant** |
| 15 Graph application permissions | Baker Strategy tenant | **ParlayVU tenant (re-granted)** |
| Service principal `parlayvu-github-actions` | Baker Strategy tenant | **ParlayVU tenant** |
| Azure subscription | Baker Strategy's | **ParlayVU's** |
| Resource group `rg-parlayvu-demo` | Baker Strategy subscription | **New rg in ParlayVU subscription** |
| Container Registry `parlayvucore` | Baker Strategy subscription | **New registry in ParlayVU subscription** |
| Container App `parlayvu-api` | Baker Strategy subscription | **New container app in ParlayVU subscription** |
| Neon Postgres | External (no tenant) | No change |
| Tavus (persona, replica) | External | No change *(config updated to point at new URL)* |
| Tavily, Anthropic, Jina, Cloudflare, Resend | External | No change |
| GitHub repo `parlayvu-core` | Personal GitHub account | No change |
| Per-agent mailboxes `*@parlayvu.ai` | Already in ParlayVU tenant | No change |
| RamAir Teams channel | Already in ParlayVU tenant | No change |

**Rebuild, don't migrate.** The surface area is small (one Container App, one ACR, one resource group, one app reg). All state is external (Neon DB, Teams files). Rebuilding in ~2 hours is cleaner than wrestling Azure resource transfers for ~2 days.

---

## Phase 1 — Pre-work (David, ~15 min, before our morning session)

These need to be true before we start, or we'll get stuck waiting on procurement.

- [ ] **1.1** ParlayVU has an Azure subscription. Check: portal.azure.com → top-right → switch directory to ParlayVU tenant → Subscriptions. If there's nothing, create one (or get billing/credit card ready). If it's empty, that's fine.
- [ ] **1.2** You have Global Admin in ParlayVU's tenant. Check: at parlayvu.ai-tenant portal.azure.com → Entra ID → top of the page should say your account has admin roles.
- [ ] **1.3** Locate the ParlayVU tenant ID and primary domain. Run in PowerShell after switching account:
  ```powershell
  az login --tenant <parlayvu-tenant-id-or-domain>
  az account show --query "{tenantId:tenantId, subId:id, name:name}" -o table
  ```
  Write down `tenantId` and `subscriptionId`.
- [ ] **1.4** Confirm `parlayvu.ai` is the verified primary domain on ParlayVU's tenant. portal.azure.com → Entra ID → Custom domain names.

**Bring to our session:** ParlayVU tenant ID, ParlayVU subscription ID, and confirmation you're Global Admin.

---

## Phase 2 — ParlayVU Azure foundation (~30 min, both of us)

We'll spin up the same infra structure in ParlayVU's subscription as you had in Baker Strategy's.

- [ ] **2.1** Create resource group `rg-parlayvu-prod` (using "prod" not "demo" since this is the real home now):
  ```powershell
  az group create --name rg-parlayvu-prod --location eastus --subscription <parlayvu-sub-id>
  ```
- [ ] **2.2** Create new Azure Container Registry:
  ```powershell
  az acr create --resource-group rg-parlayvu-prod --name parlayvuacr --sku Basic --admin-enabled true
  ```
  *(Note: Azure requires lowercase, no hyphens for ACR. `parlayvucore` may be taken globally already — we'll pick whatever's available.)*
- [ ] **2.3** Create Container Apps environment:
  ```powershell
  az containerapp env create --resource-group rg-parlayvu-prod --name parlayvu-env --location eastus
  ```
- [ ] **2.4** Capture new ACR credentials (we'll need them for the GitHub `ACR_USERNAME`/`ACR_PASSWORD` secret update):
  ```powershell
  az acr credential show --name parlayvuacr
  ```

---

## Phase 3 — Identity & app registration in ParlayVU's tenant (~30 min, mostly clicking)

- [ ] **3.1** Switch portal to ParlayVU tenant. Top-right → Switch directory → ParlayVU.
- [ ] **3.2** Create new app registration:
  - Entra ID → App registrations → New registration
  - Name: `ParlayVU Agents`
  - Supported account types: **Accounts in this organizational directory only (ParlayVU only - Single tenant)**
  - Redirect URI: leave blank
- [ ] **3.3** Copy the new **Application (client) ID** and **Directory (tenant) ID**. Write them down — these become `MICROSOFT_CLIENT_ID` and `MICROSOFT_TENANT_ID` on the Container App.
- [ ] **3.4** Create a client secret:
  - Certificates & secrets → Client secrets → New client secret
  - Description: `ParlayVU API Production`
  - Expires: 24 months
  - **Copy the secret value immediately** (it's only shown once). This becomes `MICROSOFT_CLIENT_SECRET`.
- [ ] **3.5** Grant the 15 Graph application permissions we currently have in Baker Strategy. Add them all:
  - `Calendars.ReadWrite`
  - `ChannelMessage.Read.All`
  - `ChannelMessage.UpdatePolicyViolation.All`
  - `Files.Read.All`
  - `Files.ReadWrite.All`
  - `Mail.ReadWrite`
  - `Mail.Send`
  - `Notes.ReadWrite.All` (Application)
  - `Notes.ReadWrite.All` (Delegated) *(if originally added — optional)*
  - `OnlineMeetings.ReadWrite.All`
  - `Sites.Read.All`
  - `Sites.ReadWrite.All`
  - `Tasks.ReadWrite.All`
  - `User.Read` (Delegated)
  - `User.Read.All`
- [ ] **3.6** **Click "Grant admin consent for ParlayVU"** — this is the step that the migration is really about. Confirm each row shows ✅ "Granted for ParlayVU".

---

## Phase 4 — Container App rebuild (~30 min, mostly David running az commands)

- [ ] **4.1** Build and push the current API image to the **new** ACR:
  ```powershell
  cd C:\Users\DavidBaker\Projects\parlayvu-core
  az acr login --name parlayvuacr
  # Need Docker Desktop running for this; alternative: use az acr build if it works on this subscription
  docker build -t parlayvuacr.azurecr.io/parlayvu-api:initial .
  docker push parlayvuacr.azurecr.io/parlayvu-api:initial
  ```
  *(If ACR Tasks works on ParlayVU's subscription, `az acr build` is simpler — same command form as before.)*

- [ ] **4.2** Create the Container App in the new environment. We'll set all env vars in one shot. **Replace the angle-bracketed values with the new ones from Phase 3** and the existing values for things that didn't change:
  ```powershell
  az containerapp create `
    --resource-group rg-parlayvu-prod `
    --name parlayvu-api `
    --environment parlayvu-env `
    --image parlayvuacr.azurecr.io/parlayvu-api:initial `
    --target-port 8000 `
    --ingress external `
    --registry-server parlayvuacr.azurecr.io `
    --min-replicas 1 `
    --max-replicas 3 `
    --cpu 0.5 --memory 1Gi `
    --env-vars `
      "MICROSOFT_TENANT_ID=<new ParlayVU tenant ID>" `
      "MICROSOFT_CLIENT_ID=<new app reg client ID>" `
      "MICROSOFT_CLIENT_SECRET=<new app reg secret>" `
      "DATABASE_URL=<existing Neon connection string>" `
      "ANTHROPIC_API_KEY=<existing>" `
      "XAI_API_KEY=<existing>" `
      "TAVILY_API_KEY=<existing>" `
      "TAVUS_API_KEY=<existing>" `
      "TAVUS_PERSONA_ID=p03513c08d91" `
      "TAVUS_REPLICA_ID=rf4703150052" `
      "TAVUS_REPLICA_ID_NATHAN=ra534cde00e5" `
      "NATHAN_LLM_API_KEY=<existing or regenerate>" `
      "TEAMS_APP_ID=<existing>" `
      "TEAMS_APP_PASSWORD=<existing>" `
      "TEAMS_TENANT_ID=<new ParlayVU tenant ID>" `
      "TEAMS_WEBHOOK_SECRET=<existing>" `
      "M365_FILES_TEAM_ID=<existing>" `
      "M365_FILES_CHANNEL_ID=<existing>" `
      "NATHAN_MAILBOX=nathan@parlayvu.ai" `
      "ALEX_MAILBOX=alex@parlayvu.ai" `
      "AVA_MAILBOX=ava@parlayvu.ai" `
      # ... all other agent mailboxes
      "PROJECT_MEMORY_ENABLED=true" `
      "ENVIRONMENT=production" `
      "MICROSOFT_GRAPH_ALLOW_SEND=false"
  ```
  *(I'll generate the exact full command from your current Container App config during the session, so you don't have to type it all by hand.)*

- [ ] **4.3** Capture the new Container App FQDN:
  ```powershell
  az containerapp show --name parlayvu-api --resource-group rg-parlayvu-prod --query "properties.configuration.ingress.fqdn" -o tsv
  ```
  This becomes the new base URL for everything that calls our API (Tavus, Teams bot webhook, etc.).

- [ ] **4.4** Smoke test from your machine:
  ```powershell
  $base = "https://<new-fqdn>"
  Invoke-RestMethod "$base/readiness" | ConvertTo-Json -Depth 5
  Invoke-RestMethod "$base/nathan/llm/status" | ConvertTo-Json -Depth 5
  ```
  Both should return `status: ready` and all tools `configured: true`.

---

## Phase 5 — CI/CD (~20 min, both of us)

We need a new service principal in ParlayVU's tenant with OIDC federation to GitHub Actions.

- [ ] **5.1** Create the new GitHub Actions service principal in ParlayVU's tenant + subscription:
  ```powershell
  $sub = "<parlayvu-sub-id>"
  $sp = az ad sp create-for-rbac --name "parlayvu-github-actions" --role contributor --scopes /subscriptions/$sub/resourceGroups/rg-parlayvu-prod | ConvertFrom-Json
  ```
- [ ] **5.2** Add federated credential for GitHub on main branch:
  ```powershell
  az ad app federated-credential create --id $sp.appId --parameters (@{
    name      = "parlayvu-github-main"
    issuer    = "https://token.actions.githubusercontent.com"
    subject   = "repo:davidbakera2/parlayvu-core:ref:refs/heads/main"
    audiences = @("api://AzureADTokenExchange")
  } | ConvertTo-Json -Compress)

  $acrId = az acr show --name parlayvuacr --query id -o tsv
  az role assignment create --assignee $sp.appId --role AcrPush --scope $acrId

  Write-Host "AZURE_CLIENT_ID:       $($sp.appId)"
  Write-Host "AZURE_TENANT_ID:       $($sp.tenant)"
  Write-Host "AZURE_SUBSCRIPTION_ID: $sub"
  ```
- [ ] **5.3** Update GitHub repo secrets at github.com/davidbakera2/parlayvu-core/settings/secrets/actions:
  - `AZURE_CLIENT_ID` → new SP app ID
  - `AZURE_TENANT_ID` → ParlayVU tenant ID
  - `AZURE_SUBSCRIPTION_ID` → ParlayVU subscription ID
  - `ACR_USERNAME` → new ACR admin username (likely `parlayvuacr`)
  - `ACR_PASSWORD` → new ACR admin password (from Phase 2.4)
- [ ] **5.4** Update `.github/workflows/deploy-api.yml` env defaults:
  - `REGISTRY` → `parlayvuacr.azurecr.io`
  - `RESOURCE_GROUP` → `rg-parlayvu-prod`
- [ ] **5.5** Push a commit and watch CI succeed end-to-end at the new infra.

---

## Phase 6 — Update Tavus + external integrations (~15 min)

- [ ] **6.1** Update Nathan's Tavus persona to point at the new Container App URL:
  ```powershell
  $key = "<NATHAN_LLM_API_KEY value used in Phase 4>"
  .\services\teams-media-bot\scripts\Update-NathanPersonaLLM.ps1 `
    -TavusApiKey "<existing>" `
    -PersonaId "p03513c08d91" `
    -ParlayVuApiUrl "https://<new-fqdn>" `
    -NathanLlmApiKey $key
  ```
- [ ] **6.2** If the Teams bot webhook (Microsoft Bot Framework Channels Registration) points to the old FQDN, update it in the Azure portal → Bot Service → Configuration → Messaging endpoint → `https://<new-fqdn>/teams/messages`.
- [ ] **6.3** Anything else that holds the old FQDN as a callback URL — search the repo for `greengrass-202e3ea6` and update.

---

## Phase 7 — Verification (~15 min)

- [ ] **7.1** `GET /readiness` shows `status: ready`, every check passes.
- [ ] **7.2** Start a Tavus conversation with Nathan, ask about RamAir. Confirm project context works.
- [ ] **7.3** Ask Nathan to save meeting notes. Confirm the file actually lands in the RamAir Teams channel folder. **This is the test that proves the migration worked** — it requires writing to a ParlayVU-tenant resource using ParlayVU-tenant credentials.
- [ ] **7.4** Check `az containerapp logs show` for any 403s. Should be zero.

---

## Phase 7.5 — Recreate Azure Bot Service in ParlayVU tenant (~5 min) — *added 2026-05-26*

**Gap discovered while shipping Track 4** (one-Nathan-across-surfaces). The original migration carried over the AAD app registration (`TEAMS_APP_ID = 2dc8aa66-9c5b-4ff5-9151-48408f1f6554`) but did not recreate the **Azure Bot Service** resource that wraps it and enables the Microsoft Teams channel. Without that resource, Teams Admin Center rejects the bot manifest upload with "Invalid bot" — Microsoft has no record of a bot with this app ID in the ParlayVU tenant.

**Fix:** Run the idempotent script:

```powershell
.\scripts\Setup-ParlayvuBot.ps1
```

Or the equivalent two commands directly:

```powershell
az bot create `
    --resource-group rg-parlayvu-prod `
    --name parlayvu-bot `
    --app-type SingleTenant `
    --appid 2dc8aa66-9c5b-4ff5-9151-48408f1f6554 `
    --tenant-id 45b63749-ebe1-48fa-928c-963050843179 `
    --endpoint https://parlayvu-api.thankfulriver-96fed9c6.eastus.azurecontainerapps.io/teams/messages `
    --sku F0

az bot msteams create `
    --resource-group rg-parlayvu-prod `
    --name parlayvu-bot
```

After this lands, the Teams app manifest upload (via Teams Admin Center → Manage apps) succeeds and the bot can be installed in any team. See `infra/teams-app/README.md` for the install + verify checklist.

---

## Phase 8 — Decommission Baker Strategy resources (~15 min, ONLY after Phase 7 passes)

Don't delete anything in Baker Strategy's tenant until ParlayVU's version has been working for at least 24 hours. Then:

- [ ] **8.1** In Baker Strategy tenant → Entra ID → App registrations → `ParlayVU Agents` → Delete.
- [ ] **8.2** In Baker Strategy tenant → service principal `parlayvu-github-actions` → Delete.
- [ ] **8.3** In Baker Strategy Azure → `rg-parlayvu-demo` resource group → Delete (this kills the old Container App, ACR, environment in one shot).
- [ ] **8.4** Update this MIGRATION-PLAN.md with a closing note: "Completed YYYY-MM-DD, Baker Strategy resources decommissioned."

---

## Things I'll handle during the session (no prep needed from you)

- Generating the full `az containerapp create` command from your existing config so you can paste-and-go
- Updating `deploy-api.yml` and `SETUP.md` and `ARCHITECTURE.md` to reflect the new resource names
- Updating `.env.example` if anything in there changes
- Writing a verification script that hits every endpoint and reports pass/fail in one shot

## Things you'll need to do during the session (10 min total of clicking)

- Switch portal tenants a few times
- Grant admin consent for the new app reg's permissions
- Paste new secret/ID values into PowerShell when I prompt
- Update GitHub repo secrets
- One Tavus persona update (script handles it)

## What could go wrong

| Risk | Mitigation |
|---|---|
| You don't have a ParlayVU Azure subscription | Phase 1 catches this; if missing, we pause and create one before starting |
| ACR name `parlayvuacr` already taken globally | Try `parlayvuagents`, `parlayvuprod` — Azure will tell us instantly |
| Docker Desktop not available for image push | Use `az acr build` instead (no Docker needed); or import the image from old ACR with `az acr import` |
| Some env var value is missing because we didn't capture it | Phase 4.1 — I'll dump the current Container App config first so we have a complete inventory before destroying the old one |
| Tavus persona update fails | We already debugged all the JSON Patch edge cases; the script is solid now |
| Teams bot webhook breaks | Phase 6.2 catches this; if missed, /teams/messages 404s — easy to spot in logs |
| `client_artifacts/` not in new image | Already in Dockerfile + `.dockerignore` is correct; nothing to do |
| Database state lost | Database is in Neon — completely separate from Azure. No risk. |

---

## Open questions for tomorrow

1. **Does ParlayVU have an Azure subscription already, or do we need to create one?** (Affects Phase 1 timing.)
2. **Same Azure billing account or new credit card?** (Affects Phase 1 if subscription is brand new.)
3. **Keep `rg-parlayvu-demo` name or rename to `rg-parlayvu-prod`?** I recommend renaming — "demo" was when this was a side project, "prod" reflects what it is now.
4. **Move the GitHub Actions service principal cleanly, or just let it expire in Baker Strategy?** Cleaner to recreate in ParlayVU (Phase 5).
