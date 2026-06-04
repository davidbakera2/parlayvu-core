#!/usr/bin/env python3
"""
Generate a clickable, self-contained HTML project dashboard for viewing all Parlays.

Run from repo root:

    python tools/generate_parlays_dashboard.py

This produces: video_system/docs/Parlays_Dashboard.html (or docs/...)

Double-click the .html to open in browser. No server needed.

It shows:
- All known clients (from client_artifacts/*/config.yaml)
- For each client, associated "Parlays" (primarily Podcast Parlay episodes from video_system/projects, plus other project activity)
- Current status per parlay (using parlay_state if DB available, else file inference)
- Pending approvals across everything
- Iteration/preview history
- One-click links to:
  - The per-parlay workflow viewer (the Podcast_Parlay_Workflow.html or per-episode status)
  - Run visualize command
  - Open project folder (file:// links)
  - Client artifacts
- Overview metrics

Why not LangGraph Studio?
- LangGraph Studio is for debugging/visualizing *LangGraph execution graphs* (nodes, edges, state during runs of LangGraph agents).
- Our Parlays are higher-level business workflows (multi-stage with human approvals in Teams, file-based assets in video_system/projects, state in Project.metadata_json + parlay_state.py state machine, integration with approvals, memory, Nathan tools).
- We already have a custom, auditable, approval-gated state machine in app/parlay_state.py that is tightly integrated with the rest of ParlayVU (DB, Teams cards, file mirrors, Nathan).
- A dashboard here is a *project/portfolio view* over many parlays/episodes/clients — tables, cards, status, links — not a per-execution graph debugger.
- We keep it simple, portable (static HTML or FastAPI-served), versionable, and aligned with our lean philosophy (no extra heavy infra like LangGraph Platform/Studio unless it adds unique value).

To make it live/dynamic: you can also add a route in app/main.py that calls the same logic and serves this HTML (or JSON + frontend). The generator here gives you an immediately usable clickable artifact.

The HTML is self-contained (Tailwind + Mermaid via CDN).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Make app importable
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from app import client_config
    from app.project_memory import list_projects as pm_list_projects
except Exception:
    client_config = None
    pm_list_projects = None

try:
    from app import parlay_state as ps
except Exception:
    ps = None

try:
    from app.approvals import list_approvals as list_all_approvals
except Exception:
    list_all_approvals = None

VIDEO_PROJECTS_ROOT = REPO_ROOT / "video_system" / "projects"
CLIENT_ARTIFACTS_ROOT = REPO_ROOT / "client_artifacts"
OUTPUT_HTML = REPO_ROOT / "video_system" / "docs" / "Parlays_Dashboard.html"


def scan_clients() -> list[str]:
    if client_config:
        try:
            return client_config.list_clients()
        except Exception:
            pass
    # Fallback scan
    clients = []
    if CLIENT_ARTIFACTS_ROOT.exists():
        for p in CLIENT_ARTIFACTS_ROOT.glob("*/config.yaml"):
            clients.append(p.parent.name)
    return sorted(set(clients))


def scan_video_parlays() -> list[dict[str, Any]]:
    """Find Podcast Parlay episodes (video projects)."""
    parlays = []
    if not VIDEO_PROJECTS_ROOT.exists():
        return parlays
    for client_dir in sorted(VIDEO_PROJECTS_ROOT.iterdir()):
        if not client_dir.is_dir():
            continue
        cid = client_dir.name.lower()
        for ep_dir in sorted(client_dir.iterdir()):
            if not ep_dir.is_dir():
                continue
            slug = ep_dir.name
            project_id = f"{cid}-{slug}"
            parlays.append({
                "client_id": cid,
                "episode_slug": slug,
                "project_id": project_id,
                "project_dir": str(ep_dir.relative_to(REPO_ROOT)),
                "absolute_dir": str(ep_dir),
                "type": "podcast_parlay",
            })
    return parlays


def get_parlay_status(parlay: dict[str, Any]) -> dict[str, Any]:
    """Get rich status using parlay_state if possible, else file inference."""
    project_id = parlay["project_id"]
    pdir = Path(parlay["absolute_dir"])

    status = {
        "project_id": project_id,
        "stage": "unknown",
        "stage_label": "Unknown",
        "pending_approval": None,
        "latest_preview": None,
        "iterations": [],
        "history": [],
        "source": "file",
    }

    if ps:
        try:
            if ps._db_available():
                db_status = ps.compute_status(project_id, project_dir=pdir)
                status.update(db_status)
                status["source"] = "db"
                return status
        except Exception:
            pass

    # File inference fallback (similar to visualize script)
    has_plan = (pdir / "planning" / "video_plan.json").exists()
    renders = []
    rdir = pdir / "renders"
    if rdir.exists():
        renders = sorted([str(x.relative_to(pdir)) for x in rdir.glob("**/*.mp4")])
    has_draft = any("draft" in r.name.lower() for r in rdir.glob("**/*.mp4")) if rdir.exists() else False
    has_captioned = any("caption" in r.name.lower() for r in rdir.glob("**/*.mp4")) if rdir.exists() else False

    if has_captioned:
        stage = "longform_captioned"
        label = "Captioned long-form — in review (or approved)"
    elif has_draft:
        stage = "longform_draft"
        label = "Long-form draft — in review"
    elif has_plan:
        stage = "planning"
        label = "Planning (intro, scenes, music, b-roll)"
    else:
        stage = "intake"
        label = "Intake (assets + transcript)"

    status.update({
        "stage": stage,
        "stage_label": label,
        "renders_on_disk": renders,
        "source": "file_inference",
    })
    return status


def collect_pending_approvals() -> list[dict[str, Any]]:
    if not list_all_approvals:
        return []
    try:
        return [a for a in list_all_approvals(status="pending") if a.get("status") == "pending"]
    except Exception:
        return []


def build_dashboard_html(clients: list[str], parlays: list[dict], pending: list[dict], *, web_mode: bool = False) -> str:
    """Return a complete self-contained HTML string for the dashboard.

    web_mode=True adjusts internal links to work when served from the FastAPI
    app under /static/ (for MS Teams tabs etc.). Local file:// links are kept
    for the double-click version.
    """
    now = datetime.now().isoformat(timespec="seconds")

    # Group parlays by client
    by_client: dict[str, list[dict]] = {}
    for p in parlays:
        by_client.setdefault(p["client_id"], []).append(p)

    # Enrich parlays with status
    enriched = []
    for p in parlays:
        st = get_parlay_status(p)
        p2 = dict(p)
        p2["status"] = st
        enriched.append(p2)

    # Simple cards HTML
    cards_html = ""
    for p in enriched:
        st = p["status"]
        stage = st.get("stage", "unknown")
        label = st.get("stage_label", stage)
        pending_ap = st.get("pending_approval")
        latest = st.get("latest_preview") or (pending_ap or {}).get("metadata", {}).get("preview_url") if pending_ap else None
        source = st.get("source", "unknown")

        color = "bg-slate-100 text-slate-700"
        if "approved" in stage or "published" in stage or "complete" in stage:
            color = "bg-emerald-100 text-emerald-800"
        elif "draft" in stage or "in_review" in stage or "captioned" in stage:
            color = "bg-amber-100 text-amber-800"
        elif "planning" in stage or "intake" in stage:
            color = "bg-sky-100 text-sky-800"

        card = f"""
        <div class="border border-slate-200 rounded-3xl p-5 bg-white shadow-sm hover:shadow transition">
            <div class="flex justify-between items-start">
                <div>
                    <div class="font-semibold text-lg">{p['client_id']} / {p['episode_slug']}</div>
                    <div class="text-xs text-slate-500 mt-0.5">project_id: {p['project_id']}</div>
                </div>
                <span class="text-[10px] px-2 py-0.5 rounded-full {color} font-mono tracking-wider">{stage}</span>
            </div>

            <div class="mt-3 text-sm">
                <div class="font-medium text-slate-700">{label}</div>
            </div>

            {f'<div class="mt-2 text-xs"><a href="{latest}" target="_blank" class="text-sky-600 hover:underline">Latest preview →</a></div>' if latest else ''}

            <div class="mt-3 text-xs text-slate-500">
                Source: {source}<br>
                Renders on disk: {len(st.get('renders_on_disk', []))}
            </div>

            <div class="mt-4 flex flex-wrap gap-2 text-xs">
                <a href="{'/static/Podcast_Parlay_Workflow.html' if web_mode else 'Podcast_Parlay_Workflow.html'}" class="px-3 py-1 bg-slate-900 text-white rounded-2xl hover:bg-black">Open Workflow Spec</a>
                <a href="#" onclick="alert('Run in terminal: python video_system/tools/visualize_parlay_status.py {p["project_dir"]} --client {p["client_id"]}')" class="px-3 py-1 border border-slate-300 rounded-2xl hover:bg-slate-50">View Live Status</a>
                <a href="file://{p['absolute_dir']}" class="px-3 py-1 border border-slate-300 rounded-2xl hover:bg-slate-50">Open Folder</a>
            </div>

            {"<div class='mt-2 text-[10px] text-amber-600'>⏳ Pending approval</div>" if pending_ap else ""}
        </div>
        """
        cards_html += card

    # Pending approvals global list
    pending_html = ""
    if pending:
        for ap in pending:
            meta = ap.get("metadata") or {}
            pending_html += f"""
            <div class="text-sm border-l-4 border-amber-400 pl-3 py-1">
                <div><span class="font-mono text-xs">{ap.get('id','')[:8]}…</span> — {meta.get('title') or ap.get('project_id')}</div>
                <div class="text-xs text-slate-500">client/project: {ap.get('project_id')} • requested by {ap.get('requested_by_agent')}</div>
            </div>
            """
    else:
        pending_html = "<div class='text-sm text-slate-500'>No pending approvals across tracked projects.</div>"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ParlayVU • Parlays Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
.card {{ transition: box-shadow .2s; }}
.card:hover {{ box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); }}
</style>
</head>
<body class="bg-slate-50">
<div class="max-w-7xl mx-auto p-8">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h1 class="text-4xl font-semibold tracking-tight">ParlayVU Parlays Dashboard</h1>
      <p class="text-slate-500 mt-1">View all active parlays, their current stage, approvals, and previews. Generated {now}</p>
    </div>
    <div class="text-right text-sm">
      <div class="text-emerald-600">● Live (file + optional DB)</div>
      <a href="{'/static/PODCAST_PARLAY_FULL_WORKFLOW.md' if web_mode else 'PODCAST_PARLAY_FULL_WORKFLOW.md'}" class="text-sky-600 hover:underline">Edit Workflow Spec →</a>
    </div>
  </div>

  <div class="mb-6 p-4 bg-white border rounded-3xl text-sm">
    <strong>Quick start:</strong> Run <code>python tools/generate_parlays_dashboard.py</code> to refresh the static file.<br>
    When served from the API (recommended for Teams): visit <code>/parlays/dashboard</code> (always fresh).<br>
    Individual episode status: <code>python video_system/tools/visualize_parlay_status.py video_system/projects/&lt;Client&gt;/&lt;Ep&gt; --client &lt;cid&gt;</code>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
    <div class="bg-white p-4 rounded-3xl border">
      <div class="text-xs uppercase tracking-widest text-slate-500">Clients</div>
      <div class="text-3xl font-semibold mt-1">{len(clients)}</div>
    </div>
    <div class="bg-white p-4 rounded-3xl border">
      <div class="text-xs uppercase tracking-widest text-slate-500">Podcast Parlays (episodes)</div>
      <div class="text-3xl font-semibold mt-1">{len(enriched)}</div>
    </div>
    <div class="bg-white p-4 rounded-3xl border">
      <div class="text-xs uppercase tracking-widest text-slate-500">Pending Approvals</div>
      <div class="text-3xl font-semibold mt-1 text-amber-600">{len(pending)}</div>
    </div>
  </div>

  <h2 class="text-xl font-semibold mb-4">Active Parlays by Client</h2>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
    {cards_html or '<div class="col-span-2 text-slate-500">No video parlays found. Add projects under video_system/projects/&lt;Client&gt;/&lt;Show_EpXX&gt;</div>'}
  </div>

  <h2 class="text-xl font-semibold mb-4">Global Pending Approvals</h2>
  <div class="bg-white border rounded-3xl p-6 mb-10">
    {pending_html}
  </div>

  <div class="text-xs text-slate-400">
    This dashboard is generated from client_artifacts configs, video_system/projects folders, parlay_state (if DB connected), and approvals.<br>
    Not using LangGraph Studio — we use our custom parlay_state.py state machine + approvals system + file mirrors for visibility and control.
  </div>
</div>
<script>
  // Tailwind script if needed for future interactivity
  console.log('%c[ParlayVU] Parlays dashboard loaded', 'color:#64748b');
</script>
</body>
</html>"""
    return html


def main():
    print("Scanning clients and parlays...")
    clients = scan_clients()
    parlays = scan_video_parlays()
    pending = collect_pending_approvals() if list_all_approvals else []

    print(f"Found {len(clients)} clients, {len(parlays)} podcast parlays, {len(pending)} pending approvals.")

    html = build_dashboard_html(clients, parlays, pending, web_mode=False)

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"\n✅ Dashboard written to: {OUTPUT_HTML}")
    print("   Double-click the .html file to open in your browser.")
    print("   Re-run this script after changes to episodes, approvals, or state to refresh.")


if __name__ == "__main__":
    main()
