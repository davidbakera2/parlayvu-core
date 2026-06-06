# Podcast Parlay — Phased Build Plan

What we build to realize the [runbook](./podcast-parlay-runbook.md), in order. The guiding
principle: **get one real RamAir episode all the way through the pipe before building the
ambitious asset generation** — a working episode teaches more than more planning.

Start with the client who's *ready*: **RamAir already has a Show Kit**, so its next episode
needs no Show-Kit generation. Bob Jordan (no Show Kit yet) is onboarding, Phase 3.

## Phase 1 — Thin end-to-end slice (current)

**Goal:** one RamAir episode: `video_plan` → rendered `.mp4`. Prove the wiring.

- [x] Both halves on one branch (planning + `render_video.py`).
- [ ] **Wire `render_video.py` as an execute step** — a render service that takes a
      client + episode, locates the plan + assets + Show Kit template, invokes the renderer,
      returns the output mp4 path. The Execute adapter.
- [ ] **Smoke-render verification** — synthetic test media + minimal plan → mp4 out (proves
      wiring without real episode media).
- [ ] Document how to run a real RamAir episode (point the renderer at real project media).

Uses: RamAir's existing Show Kit; b-roll tier 1 (library or none).
Defers: trigger UX, stock/AI b-roll, onboarding.

**Render an episode now** (until the Teams trigger lands in Phase 2):
1. Put the episode media in `client_artifacts/<client>/03_Deliverables/podcast/<slug>/assets/`
   (`host.mp4`, `guest_01.mp4`, intro/show-image, plus the Show Kit's lower-third/logo assets).
2. Ensure the approved plan is at `02_Planning/podcast_plans/<slug>/video_plan.json`.
3. Render:
   ```python
   from app.services.podcast_render import render_episode
   render_episode(client_id="ramair", slug="<slug>", with_subtitles=True)
   ```
   Output lands in `.../03_Deliverables/podcast/<slug>/renders/final_*.mp4`.

Render host needs **ffmpeg + Pillow + fonts** (not required by the API itself — the renderer
runs as a subprocess).

### Show Kit (implemented)

The two-layer split is now real. A client's **Show Kit** —
`video_system/templates/visual_systems/<visual_system>/show_kit.json` — holds the constant
per-episode format: background video, music cues (`intro_music`/`outro_music`),
intro/show-image/outro bookends (intro plays its **full length**, probed from the clip),
render settings, and the asset map. The planner's Alex stage emits only the per-episode
**program scenes** (interview cuts, lower-third text, b-roll); `podcast_show_kit.merge_with_show_kit()`
wraps them into a complete Ep04-format `video_plan` (bookends, contiguous timeline, settings,
music, `intro_lower_third_scene_id` → first interview scene). Verified by rendering real
RamAir footage with full intro + background + lower-third + music.

## Phase 2 — The client loop in Teams

**Goal:** the runbook flow, in-channel.

- `@Nathan run the Podcast Parlay` trigger; client from channel binding.
- Gate 1: Nathan posts a plan summary + flags as an approval card.
- Render → Gate 2: draft video posted as an approval card.
- Deliver the final to `03_Deliverables`.

Uses: channel binding, approvals, Teams cards (all exist).
Defers: new-client onboarding.

## Phase 3 — Onboarding (Bob Jordan)

**Goal:** a new client's Show Kit, agent-generated, you approve.

- Generate a starter show image + lower-third/subtitle style + a **templated motion intro**
  (FFmpeg title card — not AI video) from a brand brief.
- Show-Kit edit surface (the same agentic-edit pattern as the website design-system).

Note: AI-generated *video* (intro/outro, b-roll) is intentionally **out of scope** here —
templated title cards are consistent and free.

## Phase 4 — Asset depth

**Goal:** richer sourcing.

- B-roll tier 2 (stock integration), then tier 3 (AI-generated) behind the same
  "library first" planner logic.
- Richer Show-Kit generation.

## Out of scope for now (revisit at scale)

- Async job queue / durable resumable workflows (few clients now — runs inline is fine).
- DB-backed multi-tenant migration off `client_artifacts/` flat files.
- Per-client credential vault.
- Social/Distribution Parlay (separate parlay, after the Podcast Parlay is solid).

These are real and we've designed seams for them — we just don't build them until demand
proves them out.
