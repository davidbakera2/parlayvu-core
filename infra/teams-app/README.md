# ParlayVU Teams App Package

The Teams app manifest + icons that let users install the ParlayVU bot
(Nathan Ellis) into a Teams team or chat. This is the missing piece that
makes Nathan appear in the `@` mention dropdown — without it, the bot
service is reachable but invisible to Teams users.

## What's here

- `manifest.json` — Teams app manifest (v1.17 schema). Contains two
  distinct identifiers — keep them straight:
  - **`id`** (the catalog identity): `2dc8aa66-9c5b-4ff5-9151-48408f1f6554`.
    This MUST stay stable across uploads, otherwise Teams treats the
    upload as a brand-new app and the 5 existing team installs are
    orphaned. Do NOT change this even if the underlying bot changes.
  - **`bots[0].botId`** (the Bot Framework appId): currently
    `ea0775e7-a6ae-4f70-9f4b-3409a06a29a5`. This MUST equal the
    Azure Bot Service's msaAppId AND the Container App's TEAMS_APP_ID.
    Update it when the bot's AAD app reg changes.
- `build_app_package.py` — generates placeholder icons (192×192 color,
  32×32 outline) if missing, then zips everything into
  `parlayvu-teams-app.zip`. Re-run any time to rebuild.
- `parlayvu-teams-app.zip` — the artifact you upload to Teams Admin
  Center. **Not committed to git** (it's regenerated from sources). The
  build script writes it alongside this README.

## One-time install (per Teams tenant)

```powershell
.\.venv\Scripts\python.exe -m pip install Pillow  # one-time, for icon generation
.\.venv\Scripts\python.exe infra\teams-app\build_app_package.py
```

That produces `infra/teams-app/parlayvu-teams-app.zip`. Then:

1. **Upload to Teams Admin Center**
   - Open https://admin.teams.microsoft.com
   - Teams apps → **Manage apps** → top-right **Upload new app** → choose `parlayvu-teams-app.zip`
   - Approve for org-wide use (or scope via permission policy)

2. **Install in a specific team** (e.g., RamAir)
   - In Teams desktop: open the RamAir team → `…` menu → **Manage team** → **Apps** tab → **Add an app**
   - Search "ParlayVU" → **Add** → confirm
   - Bot is now installed in every channel of that team.

3. **Verify**
   - In any channel of that team, type `@` — **ParlayVU** should appear in the autocomplete dropdown (separate from the `nathan@parlayvu.ai` mailbox).
   - Send a test message: `@ParlayVU what's the status of the HVAC paper?`
   - Nathan should respond within a few seconds with a markdown-formatted answer pulled from the ingested project context.

## If something goes wrong

| Symptom | Most likely cause | Fix |
|---|---|---|
| Bot doesn't appear in `@` dropdown | App not installed in this team | Step 2 above |
| Bot appears but never responds | Messaging endpoint misconfigured | Azure portal → Bot Services → `parlayvu-bot` (or similar) → Configuration → set Messaging endpoint to `https://parlayvu-api.thankfulriver-96fed9c6.eastus.azurecontainerapps.io/teams/messages` |
| Bot responds with "I'm having trouble" | `ANTHROPIC_API_KEY` / Microsoft auth issue on Container App | Check Container App logs: `az containerapp logs show --name parlayvu-api --resource-group rg-parlayvu-prod --tail 100` |
| Logs show `Error sending Bot Framework reply: ... 400 Bad Request for url '.../oauth2/v2.0/token'` | `TEAMS_APP_ID` / `TEAMS_APP_PASSWORD` on the Container App don't match a live app registration in this tenant | Run `az ad app show --id <TEAMS_APP_ID>` — if it 404s, the appId is wrong or pointing at a different tenant (the 2026-05-26 outage). Create a fresh app reg + secret, update env vars on the Container App, and recreate the Azure Bot Service to point at the new appId (msaAppId is immutable). |
| Upload to Teams Admin Center creates a NEW app entry instead of offering Update | `manifest.id` was changed | Restore `manifest.id` to the original GUID (so it matches the existing catalog entry), rebuild the zip, re-upload. Only `bots[0].botId` should ever change between releases. |
| Bot replies but ignores message text | Mention parsing missed the bot mention | Verify the bot's display name in your tenant — the code currently strips `<at>ParlayVU</at>` (see `app/teams.py` `strip_bot_mentions`). If the bot has a different display name, update the manifest's `name.short` to match, rebuild, re-upload. |

## Updating the bot later

When you change manifest fields (display name, description, command list, etc.):

1. Bump `version` in `manifest.json` (e.g., `1.0.0` → `1.0.1`)
2. Re-run `build_app_package.py`
3. Teams Admin Center → Manage apps → ParlayVU → **Update** → upload the new zip
4. Existing installations automatically pick up the new version on next launch

## Branding follow-up

The placeholder icons are a dark slate "P". Replace `color.png` (192×192)
and `outline.png` (32×32, white-on-transparent) with real ParlayVU
branding when you have artwork — re-run the build script (it will not
overwrite existing icons), then re-upload via the update flow above.

## Adding / Developing Dashboards as Teams Tabs

The manifest now includes `staticTabs` for:

- "Parlays Dashboard" → `/parlays/dashboard` (rich, dynamic view of clients, episodes, stages, approvals — uses the parlay_state machine)
- "Podcast Parlay Workflow" → the detailed Mermaid viewer for the current Podcast Parlay spec

**Why the local HTML path was causing errors:**

Teams tabs are embedded web views that **require a public https URL**. A raw local path like `C:\...\Podcast_Parlay_Workflow.html` or even `file://...` will not load (security + Teams doesn't have access to your local FS in the tab context). That's the error you were seeing.

**For local development (ngrok required):**

1. Start the API:
   ```powershell
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. Expose it with ngrok (https):
   ```powershell
   ngrok http 8000
   ```
   Copy the https forwarding URL, e.g. `https://abc123.ngrok.io`

3. Temporarily test the dashboard in browser: `https://abc123.ngrok.io/parlays/dashboard` and `https://abc123.ngrok.io/static/Podcast_Parlay_Workflow.html`

4. Update the manifest (for testing):
   - Edit `infra/teams-app/manifest.json`
   - Change the `contentUrl` and `websiteUrl` in the two staticTabs to use your ngrok https URL.
   - Bump `version` (e.g. 1.0.1 → 1.0.2)
   - Rebuild: `python infra/teams-app/build_app_package.py`
   - Re-upload the zip via Teams Admin Center (Update).

5. Add the updated app (or update existing) in your team. The tabs should now appear alongside the bot.

**For production:**

- Deploy the Container App (it already serves the routes).
- Update `contentUrl` / `websiteUrl` to the real prod URL (e.g. `https://parlayvu-api.../parlays/dashboard`).
- Add the prod domain to `validDomains` in the manifest if not already there.
- Rebuild + update the app package.

**Future metrics dashboard:**

We'll add e.g. `/parlays/metrics` (or a new tab) that pulls from project_memory, approvals, agent_events, generated_outputs, parlay iterations, etc. Same tab pattern. We can use the existing parlay_state + queries for nice charts (simple HTML/JS or embed Power BI if you have it in the tenant).

**Rebuilding the package after manifest changes:**

Always:
```powershell
python infra/teams-app/build_app_package.py
```
Then update in Teams Admin Center.

Add `localhost` or your ngrok domain to `validDomains` during dev (as we did).

This gives you a first-class dashboard *inside* MS Teams (as a tab in the ParlayVU app), while the bot (Nathan) handles the conversational side.
