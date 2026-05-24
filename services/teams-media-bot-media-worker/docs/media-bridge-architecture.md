# Nathan Native Teams Video — Media Bridge Architecture

Updated May 24, 2026.

## Goal

Nathan Ellis appears in Teams meetings as a native video participant — his avatar face shows in the Teams gallery, audio comes through the Teams call, no one has to screen-share a browser tab.

## Why This Is Hard

Microsoft Graph's application-hosted media uses native Windows DLLs (`Microsoft.Skype.Bots.Media`) for real-time media processing. These DLLs cannot run on Linux, so the existing Linux Container App cannot do audio/video injection. A Windows server is required.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Teams Meeting                                                  │
│  ┌─────────────┐  ┌──────────────────────────────────────────┐ │
│  │  Attendees  │  │  Nathan Ellis (bot participant)          │ │
│  │  (humans)   │  │  ┌────────┐  Video: Nathan's face       │ │
│  └─────────────┘  │  │ 🎥📷  │  Audio: Nathan's voice      │ │
│                   │  └────────┘                              │ │
│                   └──────────────────────────────────────────┘ │
└───────────────────────────────────┬────────────────────────────┘
                                    │ Graph app-hosted media
                                    │ (appHostedMediaConfig)
                                    │ audio frames (PCM 16kHz)
                                    │ video frames (NV12 1280×720)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  ParlayVU Teams Media Worker                                    │
│  Windows Server 2022 Azure VM (Standard_D4s_v3)                 │
│                                                                 │
│  - Microsoft Graph Communications Media SDK                     │
│  - Audio socket: sends 20ms PCM frames to Teams                 │
│  - Video socket: sends NV12 frames to Teams                     │
│  - Daily room connector: receives Nathan's WebRTC tracks        │
│                                                                 │
│  POST /media/join        ◄── management service delegates here  │
│  POST /media/notifications ◄── Graph lifecycle callbacks        │
│  DELETE /media/{callId}  ◄── end session                        │
└────────────────┬────────────────────────────────────────────────┘
                 │ WebRTC (SIPSorcery or Daily Node sidecar)
                 │ audio: Opus decode → PCM
                 │ video: H.264/VP8 decode → NV12
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Tavus CVI Conversation (Daily.co WebRTC room)                  │
│                                                                 │
│  - Nathan's avatar video track (H.264 or VP8)                   │
│  - Nathan's audio track (Opus)                                  │
│  - Started via POST /avatar/tavus/start (management service)   │
│  - conversation_url = Daily room URL used by media worker       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ParlayVU Teams Media Bot (existing, Linux Container App)       │
│                                                                 │
│  - Meeting join requests (POST /meetings/join)                  │
│  - Tavus conversation lifecycle (POST /avatar/tavus/*)          │
│  - ParlayVU live meeting registration                           │
│  - Delegates media join to Windows media worker when configured │
└─────────────────────────────────────────────────────────────────┘
```

## Join Flow (After Infrastructure Is Ready)

```
Operator                  Mgmt Service              Media Worker         Graph
   │                          │                          │                 │
   │  POST /meetings/join      │                          │                 │
   │  + chatThreadId           │                          │                 │
   │  + organizerUserId        │                          │                 │
   │──────────────────────────►│                          │                 │
   │                          │  POST /avatar/tavus/start │                 │
   │                          │──────────────────────────►│                 │
   │                          │  ◄── {conversationUrl}   │                 │
   │                          │  (Daily room URL)         │                 │
   │                          │                          │                 │
   │                          │  POST /media/join         │                 │
   │                          │  + chatThreadId           │                 │
   │                          │  + organizerUserId        │                 │
   │                          │  + dailyRoomUrl           │                 │
   │                          │──────────────────────────►│                 │
   │                          │                          │  POST /communications/calls
   │                          │                          │  appHostedMediaConfig
   │                          │                          │  modalities: [audio, video]
   │                          │                          │─────────────────►│
   │                          │                          │  ◄── 201 {id}   │
   │                          │  ◄── {callId, accepted}  │                 │
   │  ◄── {status: accepted}  │                          │                 │
   │                          │                          │                 │
   │                          │         POST /media/notifications (established)
   │                          │                          │◄────────────────│
   │                          │                          │                 │
   │                          │                          │ Join Daily room │
   │                          │                          │ (WebRTC)        │
   │                          │                          │ Receive Nathan's│
   │                          │                          │ audio+video     │
   │                          │                          │                 │
   │                          │                Nathan's face appears in Teams
```

## Implementation Steps (Ordered)

### Step 1 — Add Calls.AccessMedia.All (do this now, 5 minutes)

In Azure Portal:
1. Entra ID → App registrations → `parlayvu-teams-media-bot` (your bot app)
2. API permissions → Add a permission → Microsoft Graph → Application permissions
3. Search `Calls.AccessMedia` → check `Calls.AccessMedia.All` → Add permission
4. Grant admin consent (the blue button)

### Step 2 — Provision Windows VM (30 minutes)

```powershell
cd services/teams-media-bot-media-worker/scripts
.\Provision-MediaBotVM.ps1 -DryRun   # review commands first
.\Provision-MediaBotVM.ps1           # provision
```

### Step 3 — Configure HTTPS on the VM

The media worker needs a real TLS cert. The simplest path:
- Buy or reuse a domain (e.g., `media-bot.parlayvu.ai`)
- Point DNS A record to the VM's static public IP
- Use [win-acme](https://www.win-acme.com) on the VM to issue a Let's Encrypt cert
- Configure IIS as a reverse proxy to port 8080

### Step 4 — Deploy Media Worker to VM

```powershell
# From your dev machine (or from CI — see deploy.yml job build-teams-media-worker)
dotnet publish src/ParlayVu.TeamsMediaWorker/ParlayVu.TeamsMediaWorker.csproj `
    -c Release -r win-x64 -o publish

# Copy publish/ to VM via RDP or SCP
# On the VM:
sc.exe create ParlayVuMediaWorker `
    binpath= "dotnet C:\parlayvu\media-worker\ParlayVu.TeamsMediaWorker.dll" `
    start= auto
sc.exe start ParlayVuMediaWorker
```

### Step 5 — Wire Management Service to Media Worker

```bash
az containerapp update \
  --name parlayvu-teams-media-bot \
  --resource-group rg-parlayvu-demo \
  --set-env-vars TEAMS_MEDIA_BOT_MEDIA_WORKER_URL=https://media-bot.parlayvu.ai
```

### Step 6 — Implement Daily Room Connector

This is the engineering-heavy step. The `IDailyRoomConnector` interface is defined.
Implement it using **SIPSorcery** (recommended first attempt):

1. Add `SIPSorcery` NuGet package to the media worker project
2. Join the Daily room using `RTCPeerConnection` + Daily room signaling
3. Receive audio (Opus) and video (H.264/VP8) tracks via RTP callbacks
4. Decode audio using OpusDecoder → PCM 16kHz mono
5. Decode video using H.264 decoder → NV12 YUV frames
6. Feed decoded frames into Graph audio/video sockets

```csharp
// Target code shape (SIPSorcery):
var pc = new RTCPeerConnection();
pc.OnAudioFormatsNegotiated += formats => { /* choose Opus */ };
pc.OnVideoFormatsNegotiated += formats => { /* choose H.264 */ };
pc.ontrack += (trackEvent) => {
    if (trackEvent.Track.Kind == SDPMediaTypesEnum.audio) {
        trackEvent.Track.OnRawRtpEvent += (hdr, payload) => {
            var pcm = opusDecoder.Decode(payload.Span);
            onAudioFrame(pcm);
        };
    }
};
```

### Step 7 — Wire Graph Communications Media SDK

Replace the placeholder `blob` in `appHostedMediaConfig` with the real SDK-generated token:

```csharp
// Using Microsoft.Graph.Communications.Calls.Media
var mediaSession = statefulClient.CreateMediaSession(
    audioSocketSettings: new AudioSocketSettings { StreamDirections = StreamDirection.SendOnly },
    videoSocketSettings: new[] { new VideoSocketSettings { StreamDirections = StreamDirection.SendOnly } });

var blob = mediaSession.MediaSessionToken;
// Use this blob in appHostedMediaConfig instead of the placeholder
```

Then wire the audio/video socket callbacks to the Daily connector output in `GraphMediaSession.cs`.

## Current State (May 2026)

| Component | Status |
|-----------|--------|
| Management service (Linux Container App) | ✅ Running |
| Nathan joins Teams as roster participant | ✅ Milestone 2 done |
| Tavus conversation started from bot | ✅ Milestone 3 done |
| Tavus persona grounded (no hallucination) | ✅ Done |
| `Calls.AccessMedia.All` permission | ⬜ Add this next |
| Windows VM provisioned | ⬜ Run Provision-MediaBotVM.ps1 |
| Media worker deployed to VM | ⬜ After VM |
| Daily room connector (SIPSorcery) | ⬜ Engineering work |
| Graph Media SDK blob wired | ⬜ Engineering work |
| **Nathan appears as native video participant** | ⬜ Target |

## Cost

| Resource | SKU | Est. Monthly |
|----------|-----|-------------|
| Windows VM | Standard_D4s_v3 (4 vCPU, 16 GB) | ~$280 |
| Premium SSD OS disk | 128 GB P10 | ~$20 |
| Static public IP | Standard | ~$4 |
| **Total** | | **~$304/month** |

Stop the VM between test sessions to reduce cost. The auto-shutdown at midnight UTC is enabled by the provisioning script.
