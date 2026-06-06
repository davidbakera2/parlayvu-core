# Work anywhere (Cursor + ParlayVU)

Use this checklist before travel (e.g. Pentwater). Goal: same repo, same agent context, same secrets—on a laptop that is **not** dependent on OneDrive sync for the git working tree.

## Tonight (home machine)

### 1. Install Git (Windows)

If PowerShell says `git is not recognized`, install Git and **open a new terminal**:

```powershell
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
```

Close PowerShell, open a new window, then verify:

```powershell
git --version
```

Should print something like `git version 2.54.0.windows.1`.

**If it still fails** (common in a Cursor terminal opened before install):

1. **Restart Cursor completely** (quit the app, reopen)—integrated terminals inherit PATH from when Cursor started.
2. Or fix the **current** window immediately:

```powershell
$env:Path += ";C:\Program Files\Git\cmd"
git --version
```

3. Or call Git by full path (always works):

```powershell
& "C:\Program Files\Git\cmd\git.exe" --version
```

**Wrong command:** `git remote -git --version` — use `git --version` only.

### 2. Put the repo on Git (required)

OneDrive alone is fragile for development (sync conflicts, different paths). Use GitHub (or Azure DevOps) as source of truth.

```powershell
cd "C:\Users\DavidBaker\OneDrive - Baker Strategy Group\Documents\parlayvu-core"
git status
git remote -v
```

If you see `not a git repository`, initialize once:

```powershell
git init
git add -A
git status
```

Review that `.env` is **not** staged (it must be in `.gitignore`).

If there is no `origin`, create a **private** repo and push:

```powershell
git add -A
git commit -m "WIP: sync before travel"
git push -u origin main
```

If you have uncommitted work you are not ready to commit, at minimum copy the whole folder to a USB drive or zip as backup—but still prefer git push.

### 2. Save secrets outside the repo

Copy `.env` via a password manager (1Password, Bitwarden, etc.) or an encrypted note. **Never** commit `.env`.

Minimum keys for building tomorrow (local API optional):

| Variable | Why |
|----------|-----|
| `XAI_API_KEY` (or OpenAI/Groq) | Nathan / agents |
| `DATABASE_URL` + `PROJECT_MEMORY_ENABLED=true` | RamAir memory (if using Neon) |
| `CLOUDFLARE_API` | Only if deploying sites |

For Nathan/M365 demos later in the week, also export M365 and HeyGen vars from `.env.example`.

### 3. Push any RamAir / EP04 files

Add Episode 04 transcript, notes, or `client_artifacts/ramair/` updates before push so Pentwater work does not depend on files only on the home PC.

### 4. Optional: hosted API

You do **not** need Azure for coding with Cursor. Hosted API only matters if you want Nathan endpoints without running Python locally.

---

## Tomorrow (travel laptop)

### 1. Install once

- [Cursor](https://cursor.com) — sign in with the **same account** as home.
- [Git for Windows](https://git-scm.com/download/win)
- [Python 3.11+](https://www.python.org/downloads/) — check "Add to PATH"
- Node.js LTS — only if editing `sites/` or running launch scripts

### 2. Clone (preferred path)

```powershell
mkdir $HOME\Projects -ErrorAction SilentlyContinue
cd $HOME\Projects
git clone <your-repo-url> parlayvu-core
cd parlayvu-core
```

Paste `.env` into the repo root (from password manager).

### 3. Python deps + smoke test

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/readiness
```

### 4. Open in Cursor

`File → Open Folder` → `~\Projects\parlayvu-core`

Agent rules and `AGENTS.md` travel with the repo. Chat history may **not** fully sync between machines; re-open this doc or summarize goals in the first Pentwater message.

### 5. OneDrive fallback (not ideal)

If git is not ready tonight, copy the folder to the travel machine—but **do not** edit the same OneDrive path from two PCs at once. Copy to `~\Projects\parlayvu-core` and work only there.

---

## Daily loop while traveling

```powershell
cd $HOME\Projects\parlayvu-core
git pull
# ... work in Cursor ...
git add -A
git commit -m "Describe change"
git push
```

Pull on the home machine when you return.

---

## Connectivity

- Hotel Wi‑Fi is enough for git + Cursor + API calls.
- If `pip` or `npm` fail, use phone hotspot once packages are installed.
- Offline: you can still edit files; agent and LLM calls need network.

---

## Incremental costs

See [Cost summary](#cost-summary) below.

## Cost summary

| Item | Extra cost for "work anywhere"? |
|------|----------------------------------|
| **Cursor** | **No** — same subscription; second install with same login does not double the bill. Usage limits are account-wide, not per device. |
| **Git / GitHub private repo** | **No** — within normal free or existing paid plan. |
| **Python, Git, Node** | **No** — free installers. |
| **This setup (clone + local uvicorn)** | **No** recurring charge — runs on your laptop. |
| **xAI / OpenAI / Groq API** | **Maybe** — you pay per token when agents run; same as at home, not higher because of location. More chatting = more usage. |
| **Neon Postgres** | **Maybe** — free tier is often enough for demos; paid tier if you exceed storage/compute. Enabling `PROJECT_MEMORY_ENABLED` does not add a "travel fee," only normal DB billing. |
| **Microsoft 365 / Teams / nathan@ mailbox** | **No** incremental — existing tenant licenses. |
| **HeyGen, Resend, Cloudflare** | **No** incremental for travel — existing subscriptions/usage; API calls same as home. |
| **Azure Container Apps / Teams media bot VM** | **Yes, if you turn them on** — hosting is per hour/month. **Not required** for Pentwater coding with Cursor. |
| **New laptop** | **Only if you buy hardware** — not required if you bring your current machine. |
| **Hotel / phone data** | Your usual travel costs — not ParlayVU-specific. |

**Bottom line:** Treat "work anywhere" as **git + Cursor + `.env` on a second machine** → **$0 incremental** if you stay local-only. Costs only rise if you **spin up new cloud hosting** or **use more LLM/API** than you would at home.

---

## Minimal Pentwater stack (recommended)

1. Git push tonight → clone tomorrow  
2. Cursor + Python venv + `.env`  
3. Skip new Azure hosting unless you need a public API URL  
4. Build parlay template + EP04 in repo; save M365/HeyGen live demo for after readiness at home or hosted env  

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `git` not found | Install Git for Windows; restart terminal |
| `python` not found | Reinstall Python with "Add to PATH" |
| Agent cannot find repo rules | Open folder root `parlayvu-core`, not a parent |
| `.env` missing | Paste from password manager; never commit |
| OneDrive conflict | Work only under `~\Projects\parlayvu-core` clone |
| Readiness red for M365/HeyGen | Expected on travel laptop; fix when back or use hosted `.env` |
