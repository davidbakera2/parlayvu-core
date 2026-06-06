# Podcast Parlay

**Status:** Draft v1  
**Owner:** ParlayVU Core  
**Last Updated:** 2026-05-28

## Overview

The **Podcast Parlay** is a repeatable, agentic workflow for turning client interviews into high-quality, branded long-form video content (and supporting short-form assets).

It is one of the core Parlays in the ParlayVU system, focused on client-facing thought leadership and interview-style video production at scale.

### Goals

- Dramatically reduce manual decision-making in editing and planning.
- Enable scaling from ~1 video/week to 20–40 videos/week.
- Maintain (or improve) brand consistency and production quality.
- Create a feedback loop so the system gets smarter with every video produced.
- Integrate cleanly with the rest of the ParlayVU architecture (memory, approvals, specialist agents, delivery).

## Parlay Structure

| Stage              | Primary Actor          | Key Activities                                      | Output                              |
|--------------------|------------------------|-----------------------------------------------------|-------------------------------------|
| **Ingestion**      | Riverside + Human     | Record interview, light cleanup, export rich data  | Raw video, enhanced audio, transcript with timestamps |
| **Agentic Planning** | AI Agents (Nathan + specialists) | Scene cuts, layouts, lower thirds, b-roll selection, pacing, graphics | Structured `video_plan.json` equivalent |
| **Human Review**   | Human (with approvals) | Review plan, adjust tone/accuracy, approve key elements | Approved plan + any change requests |
| **Execution**      | FFmpeg renderer (scripted) | Assemble final video with compositing, graphics, subtitles | `final_no_subtitles.mp4`, `final_with_subtitles.mp4` |
| **Delivery**       | Agents + Tools        | Long-form delivery + social cutdowns               | Published assets + metadata         |
| **Metrics & Learning** | System + Agents     | Performance tracking, client feedback, refinement  | Updated preferences, improved agent prompts |

## Ingestion Layer (Riverside)

Riverside serves as the **high-quality capture and light enhancement** tool for the Podcast Parlay. It is **not** the primary creative workspace.

### Recommended Riverside Workflow

1. Record the full interview (host + guest(s) on separate tracks when possible).
2. Run Riverside voice enhancement on the tracks.
3. Perform only **light cleanup**:
   - Remove major technical issues or long disasters.
   - Trim obvious start/stop points.
4. Export the following (in priority order):

   **Must-have exports:**
   - Full video file(s)
   - Enhanced host audio track
   - Enhanced guest audio track(s)
   - High-quality transcript with accurate timestamps and speaker labels (export as `.srt` + `.txt` or JSON if available)

   **Nice-to-have:**
   - Mixed audio track
   - Any chapters or notes created during recording
   - Riverside AI summary (as additional context)

This rich, timestamped, speaker-separated data is critical for downstream agents to make high-quality planning decisions.

### What Not to Do in Riverside

- Make final creative decisions about scene cuts.
- Write lower third text.
- Select or time b-roll.
- Design the overall episode structure.

These activities move to the Agentic Planning layer.

## Agentic Planning Layer

This is the highest-leverage part of the Parlay for scaling.

Agents (led by Nathan, supported by specialists such as Alex for visuals, Ava for copy, Blake for research, etc.) take the raw Riverside output + any client source material and produce a structured plan.

Key responsibilities of the agents in this Parlay:

- Analyze the full transcript for natural beats, strong moments, and pacing.
- Propose scene cuts and camera layout decisions (`1cam`, `2cam`, `2cam_broll`, etc.).
- Generate lower third text (top and bottom rows) that matches brand voice.
- Identify high-value b-roll opportunities and suggest placement.
- Suggest graphics (name cards, b-roll cards, callouts).
- Flag sections that may need human review or client approval.

The output should be a structured, machine-readable plan (evolving from the current `video_plan.json` model) that can directly drive the FFmpeg renderer.

## Human Review & Approvals

Because this is client-facing work, human oversight remains important, but it should be **lightweight** at scale.

Approval gates should include:

- Overall episode structure and tone.
- Client-facing lower third text and claims.
- Any b-roll or graphics that could create legal or brand risk.

The existing ParlayVU Approvals system will be used here.

## Execution Layer (FFmpeg)

Final video assembly is done by a **scripted FFmpeg renderer** that consumes the approved
`video_plan` directly.

Rationale:
- Fully programmatic and headless — no GUI app or per-render licensing in the loop.
- Reads `video_plan.json` straight through (one scene → one render step), so the approved
  plan drives the render with no manual tweaking for standard episodes.
- Already built: `video_system/tools/render_video.py` renders intro/show-image/program/outro
  scenes, lower thirds, graphics, and subtitles from the plan. (DaVinci Resolve was an
  earlier candidate for the execution layer and has been dropped.)

The goal is for the approved plan from the Agentic Planning layer to drive the FFmpeg
render end-to-end, with minimal manual tweaking for standard episodes.

## Delivery & Metrics

- Long-form videos delivered to client channels (YouTube, website, etc.).
- Supporting social cutdowns (initially via Riverside Magic Clips as a fast parallel track; later potentially improved via agents).
- Performance data and client feedback captured back into ParlayVU project memory.
- Continuous improvement of agent prompts, templates, and planning logic based on what actually performs.

## Current State

- Riverside is already being used successfully for recording.
- **Agentic planning layer is implemented** (`app/agents/workflows/podcast_parlay.py`):
  Blake analyzes the transcript into timestamped segments; Alex composes a structured
  `video_plan` (scenes, lower thirds, graphics, b-roll). Exposed at
  `POST /parlays/podcast/plan`. Output contract: `docs/parlays/video-plan-schema.md`.
  The plan is persisted under `client_artifacts/<client>/02_Planning/podcast_plans/` and,
  when a client + project are supplied, a `video_plan` approval is requested before render.
- Execution is the FFmpeg renderer at `video_system/tools/render_video.py`, which reads a
  `video_plan.json` in the documented schema directly (verified end-to-end against plans
  in this schema). The planning output targets that contract.

## Roadmap

1. ✅ Formalize Podcast Parlay definition and data contracts (this document + `video-plan-schema.md`).
2. ✅ Build initial agentic planning agents that propose cuts, lower thirds, and b-roll from transcripts.
3. ✅ Wire the planning output into approvals + persist plans to `client_artifacts` (a `video_plan` approval is requested before render; plans saved under `02_Planning/podcast_plans/`).
4. ✅ Confirm the planning output drives the FFmpeg renderer (`render_video.py`) end-to-end.
5. Pilot the full flow on 1–2 episodes.
6. Gradually reduce human time in the planning phase while maintaining quality.
7. Evolve Shorts production into its own sub-Parlay or integrated flow.

## Related Parlays & Systems

- **Website Parlay** (for client marketing sites)
- **Content Repurposing Parlay** (turning long-form into multiple asset types)
- Integration with ParlayVU project memory, approvals, and client config systems.

---

*This document will evolve as the Podcast Parlay is implemented and refined.*