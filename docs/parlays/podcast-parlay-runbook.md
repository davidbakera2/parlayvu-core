# Podcast Parlay — Client Operating Runbook (v1)

How a real episode flows from a client interview to a delivered video, and who acts at each
step. Companion to [podcast-parlay.md](./podcast-parlay.md) (the design) and
[podcast-parlay-build-plan.md](./podcast-parlay-build-plan.md) (what we build, in order).

## Operating model

- The client's **Teams channel is the workspace.** Clients never see the app, the plan
  JSON, the renderer, or the agents.
- **Nathan is the interface** — acknowledges, plans, renders, posts drafts, delivers, all
  in-channel.
- **You (David) are a light-touch producer** — you *steer* (approve or one-line redirect),
  you don't hand-build. The system pulls you in only when it flags something.
- **Two approval gates: you, then the client.** Your gate is fast.

## Two layers (important)

| | **Show Kit** (per client) | **Video Plan** (per episode) |
|---|---|---|
| What | Show image, logo, intro/outro, lower-third + subtitle style, b-roll library | Scenes, lower-third text, b-roll placement, timing for one episode |
| Cadence | Set once at onboarding; edited occasionally | Produced every episode |
| Lives in | `video_system/templates/visual_systems/<client>/` | `client_artifacts/<client>/02_Planning/podcast_plans/<episode>/video_plan.json` |
| Edit surface | **Show Kit edits** — occasional, affect every episode | **Plan edits** — per-episode, your Gate 1 |

The Podcast Parlay *assumes a Show Kit exists.* Creating one is onboarding (Step 0).

## Step 0 — Onboarding (once per client)

Build the client's **Show Kit**. Agent-generated from a brand brief, you approve:
- Nathan/Alex generate a starter show image, lower-third + subtitle style, and a templated
  motion intro/outro (FFmpeg title card from the show image + name).
- You refine via **Show Kit edits** ("make the lower-third navy, use this logo").
- RamAir: already done. New clients (e.g. Bob Jordan / The Mitigation Handbook): required first.

## The per-episode loop

1. **Record** — client records the interview on Riverside, light cleanup, exports video +
   transcript (timestamps + speaker labels).
2. **Drop** — client drops the exports into their Teams channel (`01_Source_Material`).
3. **Trigger** — someone posts **`@Nathan run the Podcast Parlay`** in the channel. The
   **client is inferred from the channel binding** (RamAir channel → RamAir). Nathan uses the
   latest dropped recording/transcript (or asks "which episode?").
4. **Plan** — Blake analyzes the transcript into segments; Alex composes the `video_plan`,
   planning **only against assets that exist** (the client's b-roll library / Show Kit).
5. **Gate 1 — your producer pass (fast):** Nathan posts a plan summary **plus anything it's
   unsure about** (low-confidence cuts, ambiguous lower-thirds, beats with no available
   b-roll). You ✅ approve or drop a one-liner. The system revises.
6. **Render** — the FFmpeg renderer produces a draft `.mp4` from the approved plan.
7. **Gate 2 — client review:** Nathan posts the draft + a short summary as an approval card.
   Client ✅ approves or comments.
8. **Revise** — client comments → system re-plans/re-renders the changed parts → back to the
   client. You only re-enter if the ask needs producer judgment.
9. **Deliver** — on client approval, the final video lands in `03_Deliverables` and is
   recorded in project memory (plan + approvals + edit deltas captured — fuel for learning).

## B-roll sourcing (tiered)

The planner picks per beat: **client/your library first → stock fallback → AI-generated when
needed.** If a beat wants b-roll and none is available, fall back to a no-b-roll layout
(`2cam`) and flag it at Gate 1.

## Flag handling (v1)

- Bad/missing transcript → Nathan asks the client to re-export.
- Low-confidence plan or missing asset → flagged to **you** at Gate 1, not the client.
- Render failure → flagged to **you**, never surfaced to the client.

## "Done" =

A client-approved `final_with_subtitles.mp4` (+ no-subtitles version) in `03_Deliverables`,
with the run recorded in project memory.

## Where your "light touch" lives

One default gate (Step 5); the system flags when Step 8 needs you. Everything else runs
without you. As confidence grows, Gate 1 auto-passes for clean episodes — the dial turns down.
