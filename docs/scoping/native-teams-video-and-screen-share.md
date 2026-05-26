# Scoping: Native Teams video + screen sharing for Nathan

> **Status:** Scoping doc, not an implementation plan. Read before committing to a path.
> **Context:** Nathan today joins Teams meetings via Tavus's shared-window flow. This explores what it takes to upgrade Nathan to (a) a real Teams participant with his own video tile and (b) the ability to share screen with relevant content (websites, PDFs, images) during the discussion.
> **Last updated:** 2026-05-26

---

## The two halves of the ask

**Half A — Nathan as a real Teams participant.** Appears in the meeting gallery with his own video tile, joins and leaves like a human, his audio routes through Teams's normal channels instead of a shared window.

**Half B — Nathan shares screen with relevant content.** During discussion, he can present a webpage, PDF, image, or dashboard as a screen-share track that other participants see. Triggered by Nathan's own decision (a `share_content(...)` tool he calls when relevant), not by a human operator.

These are sequential. Half B depends on Half A's plumbing.

---

## The architecture that's already designed

The original scaffolding in `services/teams-media-bot/` and `services/teams-media-bot-media-worker/` implements a clever pattern that **keeps Tavus's avatar/voice quality** rather than throwing it away:

```
Tavus conversation (Daily room) ─── Nathan's avatar audio/video tracks
              │
              ▼
   Windows media worker (Azure VM)
              │
              │ joins the same Daily room server-side as a "headless" participant,
              │ receives Nathan's tracks
              ▼
   Microsoft Graph Communications API
              │
              │ pushes Nathan's tracks into the Teams call as a real participant
              ▼
      Teams meeting (Nathan appears in gallery)
```

The reverse path handles "other participants speak → Nathan hears them" by routing Teams audio back into the Tavus conversation as input.

The architectural win: we keep Phoenix-3 avatar fidelity, Tavus's STT/turn-taking pipeline, and all of Nathan's existing brain — and just add a real Teams participant surface. We don't have to rebuild the conversation stack.

---

## What's already scaffolded (Half A)

### `services/teams-media-bot/` (Linux, .NET 10 preview)

- Management service builds cleanly, runs as a Container App candidate
- `/meetings/join` orchestrator endpoint that starts a Tavus conversation, then delegates the media join to the Windows worker
- `/teams/calling/notifications` Graph webhook receiver (logs only, no handler logic)
- `/avatar/tavus/start` and `/avatar/tavus/{id}` lifecycle endpoints
- Builds the Graph `POST /communications/calls` payload shape (header reports `mediaJoinImplemented = false` honestly)
- Avatar provider abstraction (`AvatarProviderOptions`, `IAvatarProviderAdapter`) with config slots for HeyGen / D-ID / Soul Machines (config only, no implementations)
- README clearly states it's a scaffold, not a verified live media join

### `services/teams-media-bot-media-worker/` (Windows, .NET 8)

- Microsoft.Graph.Communications.{Common, Core, Calls, Calls.Media} v1.2.0.9 SDK references
- Windows-only runtime guard (the Calls.Media DLLs are Windows-native)
- `/media/join` endpoint signature with `MediaSessionRegistry` for in-memory tracking
- `IGraphMediaSession` interface — `StartBridgeAsync` / `StopBridgeAsync` defined; impl is TODO
- `IDailyRoomConnector` interface — three implementation paths documented in comments: **SIPSorcery WebRTC** (recommended, all-.NET), **Daily Node.js sidecar** (easier, second process), **libwebrtc** (lowest level, weeks of work)
- `GraphMediaSession.SendAudioFrame` / `SendVideoFrame` methods as TODO stubs
- `GraphCallClient.JoinWithAppHostedMediaAsync` builds the join request — uses a placeholder `MediaSessionToken` blob (`"PLACEHOLDER_REQUIRES_GRAPH_COMMUNICATIONS_MEDIA_SDK"`) that Graph rejects with 400 until replaced with a real SDK-generated value

---

## What's missing for Half A (real Teams participant)

| Gap | Specifically | Estimate |
|---|---|---|
| **Placeholder blob in `appHostedMediaConfig`** | `GraphCallClient.cs:356` — real SDK MediaSessionToken needed or Graph 400s the join | ~1 day |
| **`IDailyRoomConnector` implementation** | Pick one: SIPSorcery WebRTC (~3–5d, all-.NET, recommended), Daily Node sidecar (~2d, two processes), libwebrtc (~weeks, lowest level) | 2–5 days |
| **Graph audio/video socket wiring** | `GraphMediaSession.SendAudioFrame` / `SendVideoFrame` stubs become real SDK calls; PCM 16kHz audio + NV12 YUV video | 2–3 days |
| **Windows VM provisioning** | Azure Standard_D4s_v3+ Windows Server 2019+, deploy pipeline, monitoring | 1 day |
| **`.NET 10 preview` build issue** | Likely retarget management service to .NET 8 LTS to match the worker | Few hours |
| **End-to-end debugging** | A/V sync drift, codec negotiation, reconnection handling, audio echo loops | 2–3 days |
| **Subtotal** | | **~2–3 weeks focused work** |

---

## What's needed for Half B (screen sharing)

The scaffolding doesn't touch this at all — entirely greenfield.

| Piece | Specifically | Estimate |
|---|---|---|
| **`share_content(asset_url \| image_path)` tool** for Nathan | New tool in `app/tools/`; Nathan decides what to show, when. | Half day |
| **Content rendering pipeline** | URL → headless browser (Playwright or Puppeteer) on the Windows worker. PDF → page-by-page image render. PNG → direct frame. All output a video stream. | 3–5 days |
| **Graph content-sharing track** | The Calling SDK supports `IContentSharingSession` — pushes a video track as the "screen share." New code, documented. | 2–3 days |
| **Sync with Nathan's narration** | When Nathan says "look at this site," the share appears within 1–2s. Latency tuning + turn-taking integration. | 2–3 days |
| **Control surface** | Tool variants: `share_content`, `stop_sharing`, `replace_share(...)`. | Half day |
| **Subtotal** | | **~1.5–2 weeks** |

---

## **Total realistic scope: 4–5 weeks of focused work**

About a month of nothing-else, or 6–8 weeks with normal context-switching. This would be the single biggest piece of work on the ParlayVU roadmap.

---

## Risks and unknowns worth flagging

1. **Tavus might not allow server-side joins to their Daily rooms.** This is the load-bearing assumption of the whole architecture. We need to confirm with Tavus support or run a half-day spike before committing. If they block it, the architecture has to change (e.g., run our own Daily room and use a different Tavus integration mode if one exists).

2. **Microsoft Graph Communications API is notoriously finicky.** Reliability and latency aren't always great in production. Some teams running production Teams bots report needing dedicated SRE attention to keep them healthy.

3. **Windows-only hosting** for the media worker locks us into a more expensive Azure VM footprint vs. our current Container Apps setup. Not a dealbreaker, just a cost line on the budget.

4. **The original developer hit some wall** — the `.NET 10 preview` build issue and the stalled state of the scaffolding suggest discovery happened mid-build. Worth understanding what they ran into before re-committing.

5. **Audio echo / feedback loops** are common when bridging two A/V systems. Standard problem, solvable, but adds debugging time.

---

## Cheaper alternatives worth comparing

### Option α: Smart shared-window with content automation (~1 week)

Keep Tavus shared-window flow exactly as today, but build:

- A "presentation surface" in our app — when Nathan calls `share_content(url)`, our backend opens that URL in a controlled browser window.
- That browser window is the second thing the operator shares in Teams (or Nathan's window includes a side panel showing the content alongside his avatar).
- Nathan still doesn't appear as a real Teams participant, but he can effectively "drive" what's shown during the meeting.

**Gets ~70% of Half B's value with ~10% of the work.** Loses the "real participant tile" property of Half A.

### Option β: Vendor — Recall.ai or similar (~1 week + ongoing per-meeting cost)

Recall.ai and a few competitors solve "AI bot joins meetings as a real participant" for Teams / Zoom / Meet as a product. They handle the Graph Communications / Daily / WebRTC mess.

- Replace the entire `services/teams-media-bot*` stack with API calls to Recall
- Pipe their audio output into our Tavus pipeline (Nathan's brain stays ours)
- Get Teams audio back into Tavus the same way

**Risk:** doesn't trivially solve screen sharing — depends on whether their API exposes content-sharing tracks. Pricing is per-meeting-minute.

### Option γ: In-meeting Teams app (M365 Live Share SDK) (~2 weeks)

Different shape entirely. Instead of Nathan being a participant, ParlayVU becomes a Teams meeting app the host pins in the meeting. The app's surface shows whatever content Nathan wants, and we pipe avatar + voice through that surface.

Cleaner in some ways (no Graph Communications complexity), but Nathan is then "an app" not "a participant" — different UX, different mental model for the client.

---

## Recommendation

Before committing to the 4–5 week native build:

1. **Half-day spike**: confirm Tavus allows external server-side joins to their Daily rooms. If no → the whole architecture changes. (Either trial it directly or get an answer from Tavus support.)
2. **Half-day spike**: try Recall.ai's sandbox to see how their Teams-bot experience feels with our Nathan brain wired in. Cheap way to set the floor of what good looks like.
3. **Then decide:** full native build vs. Option α (smart shared-window) vs. Option β (Recall.ai) vs. Option γ (in-meeting app).

If you go full native: **put the screen-sharing piece first** even though it depends on participant join, because "Nathan drives the visual conversation" is the bigger UX unlock than "Nathan is a tile." Plan the work so Half B ships in the *first* shippable cut, not deferred.

---

## Key reference points in the existing scaffolding

If/when this work is picked up, start here:

- **`services/teams-media-bot/Program.cs`** — management service entry, especially `/meetings/join` (lines 101–166)
- **`services/teams-media-bot-media-worker/GraphCallClient.cs`** lines 328–400 — the placeholder blob is the first thing to replace
- **`services/teams-media-bot-media-worker/GraphMediaSession.cs`** — bridge skeleton; `StartBridgeAsync` (lines 42–81), `SendAudioFrame` (lines 93–104), `SendVideoFrame` (lines 106–120) are all TODO
- **`services/teams-media-bot-media-worker/IDailyRoomConnector.cs`** — interface and the three implementation-path comments
- **`docs/media-bridge-architecture.md`** — the original architectural intent document (worth re-reading even if some details have drifted)
- **`docs/avatar-provider-contract.md`** — provider-neutral contract; `mediaBridgeValidated` must stay `false` until a real Teams media injection is confirmed end-to-end
