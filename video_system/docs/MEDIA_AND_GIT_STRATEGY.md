# Media & Git Strategy for video_system (Cross-Device / GitHub Workflow)

**Purpose:** Define how to keep `video_system` safely version-controlled and portable across machines while respecting the realities of large video media and DaVinci Resolve projects.

**Core Principle:** The **plan** is the portable source of truth. Media and active Resolve timelines are local or on shared storage.

---

## 1. What Goes in Git vs. What Does Not

| Category                          | In Git? | Reason |
|-----------------------------------|---------|--------|
| Python tools, scripts             | Yes     | Core logic |
| Resolve integration code          | Yes     | New v2 layer |
| Design docs & visual spec         | Yes     | Architectural record |
| Templates (layouts, styles, Resolve master project) | Yes | Reusable visual system |
| Planning files (`video_plan.xlsx`, `.json`, `.srt`, transcripts) | Yes | The "intent" layer — small and critical |
| Small branding assets (logo, show_image, lower third graphic, music sting, short intro) | Yes | Part of the template |
| Raw camera footage (`host.mp4`, `guest_*.mp4`, b-roll) | **No** | Gigabytes per episode |
| Large client assets (PDFs, high-res stills, long b-roll) | **No** | Size + client IP |
| All renders (`renders/`, `final_*.mp4`, drafts) | **No** | Derivative + huge |
| Work files, segments, overlays    | **No** | Temporary |
| Active Resolve project databases  | **Usually No** | Path-dependent, large, fragile |
| Previews / QA frames              | Optional | Useful for history but can be regenerated |

---

## 2. Recommended Media Storage Patterns (Cross-Device)

### Option A — Recommended (You have a dedicated fast external SSD)

Since you have a fast external SSD dedicated to video work, this is now your primary media location.

**Recommended structure:**

```
E:\ParlayVU_Video\                    ← Your dedicated fast SSD (assign a fixed drive letter)
├── Clients\
│   ├── RamAir\
│   │   └── Straight_From_The_Hart_Ep06\
│   │       ├── assets\               ← All raw camera + b-roll media
│   │       ├── renders\              ← Final and draft renders
│   │       └── work\                 ← Optional temp work files
│   └── NewClient\
│       └── ...
├── Templates\
│   └── ParlayVU_Interview_v1\        ← Your master Resolve project template (Network project recommended)
├── Archives\                         ← Exported .drp project archives (for moving between machines)
└── Planning\                         ← Optional central location for copies of video_plan files
```

**Critical Windows Step:**
1. Plug in your SSD.
2. Open **Disk Management** (right-click Start button).
3. Right-click your SSD → **Change Drive Letter and Paths**.
4. Assign it a **fixed letter** you will always use (e.g. `E:` or `V:` for Video). Do this on every machine you use.

This prevents Resolve from losing media links when the drive letter changes.

**Workflow:**
- Clone the git repo to your internal drive (or wherever is convenient).
- Keep all large media + active Resolve work on the external SSD.
- Planning files (`video_plan.json`, etc.) can live in both git and on the SSD.

### Option B — Cloud Sync (OneDrive / Dropbox / Synology)

- Use selective sync aggressively.
- Only sync the `planning/` folder + small assets by default.
- Manually sync specific `assets/` folders when actively working on that episode.
- **Warning:** Do not let OneDrive sync active Resolve projects or large render folders.

### Option C — NAS / Local Network Storage (Best for Team)

- Central fast NAS.
- Both machines mount it with consistent paths (or use path-mapping in Resolve).

---

## 3. Handling Resolve Projects Across Machines (Updated for Your Setup)

With a dedicated external SSD, here is the cleanest approach:

**Recommended Setup:**

- **Resolve Project Type**: Create as a **Network** project pointing to `localhost` (even on a single machine). This is more reliable long-term than pure Local projects.
- **Project Database**: Can live on your internal drive or the external SSD (many people keep it on internal for speed).
- **Media**: Always lives on the external SSD (`E:\ParlayVU_Video\...`).

**When moving between machines:**

1. Plug the SSD into the second machine (use the same drive letter you assigned).
2. Best method: Duplicate your master Resolve Project Template, then run the future timeline builder script against the plan + media on the SSD.
3. Fallback: Use **File → Export Project Archive** from Resolve and import it on the other machine (media should relink automatically if drive letter is consistent).

This combination (Network project + fixed drive letter on external SSD + plan-driven workflow) gives you the best balance of reliability and portability.

---

## 4. Safe Workflow for Moving Between Devices

### Starting Work on Machine A
```powershell
# 1. Pull latest
git pull

# 2. Create new episode (or continue existing)
.\tools\new_project.ps1 -Client "RamAir" -Show "Straight_From_The_Hart" -Episode "Ep06"

# 3. Copy raw assets into the media storage location (external drive / NAS)
# 4. Work in Resolve or run planning tools
```

### Moving to Machine B
```powershell
# 1. On Machine A: Commit only what should be in git
git add -A
git commit -m "Ep06 planning updates + lower third refinements"
git push

# 2. On Machine B:
git pull

# 3. Ensure media is present on Machine B's storage (external drive, NAS, or selective sync)
# 4. Open Resolve, duplicate the master template, and run the timeline builder against the plan
```

**Never** do this:
- `git add projects/RamAir/...` when it contains large media or renders.

---

## 5. .gitignore Rules (Enforced)

See the `.gitignore` file at the root of `video_system/`.

Key protections:
- All `projects/**/assets/` (with a few explicit exceptions for template assets)
- `renders/`, `work/`, `previews/`
- Common video/audio extensions at the assets level
- Resolve project artifacts

You can still force-add small intentional files using `git add -f` when truly needed (rare).

---

## 6. One-Time Cleanup (If You've Already Committed Large Files)

If large media has already been committed to history:

```powershell
# Use git-filter-repo or BFG to remove large files from history.
# This is destructive — coordinate with anyone else who has clones.
```

For now, the priority is preventing future problems.

---

## 7. Future Enhancements

- Automated "media manifest" that lists required assets for a plan (so the timeline builder can warn you about missing files).
- Optional LFS (Git Large File Storage) for a small number of high-value small assets if needed.
- Script to "package an episode for handoff" that zips only the planning + small assets + references to media.

---

## Summary

- **Git** = plans, code, templates, knowledge.
- **External fast storage** = media.
- **Resolve** = creative realization environment (rebuilt from plans when moving machines).

This model gives us excellent portability, clean git history, fast local performance in Resolve, and architectural integrity.

Follow this strategy and you will be able to push/pull and continue work across devices without pain.

---

**Last updated:** 2026-05-28 (initial version during v2 foundation phase)