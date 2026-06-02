# Resolve Scripting Setup Guide (Windows)

**Goal:** Get the DaVinci Resolve Python API working reliably on your machine so we can script timeline creation, lower thirds, and automation from our plans.

This is the **critical first validation step** for the entire v2 system. Until this works cleanly, we cannot proceed to building the Resolve Project Template or the timeline builder.

---

## Prerequisites

1. **DaVinci Resolve Studio** must be installed and licensed (the free version has limited scripting support in some cases).
2. Resolve must be **running** when you execute any scripting code.
3. You should have a project open (even an empty test project is fine for initial validation).

---

## Step-by-Step Setup

### Step 1: Locate the DaVinciResolveScript Module

On Windows, Blackmagic does not install the module into your system Python. You must point Python at it manually.

Common locations (in order of likelihood for recent Resolve versions):

- `C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Python\Modules`
- `C:\Program Files\Blackmagic Design\DaVinci Resolve\Support\Developer\Python\Modules`
- `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Python\Modules`

**Action:** Open File Explorer and search for the folder containing `DaVinciResolveScript.py`.

If you find it, note the **full path** to the `Modules` folder.

### Step 2: Set the Environment Variable (Recommended)

The cleanest long-term method is to set a persistent environment variable.

1. Search for "Environment Variables" in the Windows Start menu → "Edit the system environment variables".
2. Click **Environment Variables...**
3. Under **User variables**, click **New**.
4. Variable name: `RESOLVE_PYTHON_API`
5. Variable value: the full path to the `Modules` folder you found in Step 1
   Example: `C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Python\Modules`
6. Click OK on all dialogs.
7. **Close and reopen** any terminals / VS Code / Cursor windows so they pick up the new variable.

### Step 3: Validate the Connection

With Resolve running and a project open:

```powershell
cd C:\Users\DavidBaker\parlayvu-core\video_system
python tools\resolve\test_connection.py
```

You should see output similar to:

```
DaVinci Resolve Python API Connection Test
==================================================
[1/4] Attempting to attach to running Resolve instance...
  ✓ Successfully attached to Resolve.
...
SUCCESS: Resolve scripting is working on this machine.
```

If it fails, proceed to the Troubleshooting section below.

---

## Troubleshooting (Common Windows Issues)

### Error: "Could not connect to DaVinci Resolve"

**Most common causes:**

1. **Resolve is not running** — It must be open.
2. **No project is open** inside Resolve.
3. **Wrong path** in `RESOLVE_PYTHON_API`.
4. **Python version mismatch** — Resolve bundles its own Python. Using a very new or very old system Python can cause import issues. Python 3.10–3.12 is usually fine.
5. **Antivirus / Windows Defender** blocking the module (rare).

**Diagnostic commands to run:**

```powershell
# Check if the env var is set
echo $env:RESOLVE_PYTHON_API

# Try to manually add the path and import (replace with your actual path)
$env:PYTHONPATH = "C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Python\Modules"
python -c "import DaVinciResolveScript as dvr; print(dvr.scriptapp('Resolve'))"
```

### Resolve says scripting is disabled

In Resolve, go to:
**Workspace > Scripts > Script Console**

If the Script Console does not appear or shows an error, scripting may be disabled in your Resolve installation (rare on Studio versions).

### Multiple versions of Resolve installed

If you have both Resolve 18 and 19/20, make sure the path points to the version you actually have open.

---

## Recommended Project Structure for Scripting Work

When working on automation:

1. Always have Resolve open with the project you want to script against.
2. Run scripts from the `video_system` directory (this keeps relative paths consistent).
3. For safety during development, work on a **copy** of real projects or a dedicated test project.

---

## Once the Connection Works

After `test_connection.py` succeeds, the next major milestone will be:

- Designing and creating the **Resolve Project Template** (the carrier of your visual language).
- Building the first version of the timeline builder that can create bins, import media, and drop Text+ lower thirds from a plan.

We will do those steps deliberately after this foundation is solid.

---

## Support

If you run the test and it still fails, copy the **full output** of `test_connection.py` (including any traceback) and paste it here. We will debug it together.

This step is intentionally the first real gate because the entire v2 capability rests on reliable Resolve scripting.

---

**Document version:** 2026-05-28 — Initial careful foundation version.