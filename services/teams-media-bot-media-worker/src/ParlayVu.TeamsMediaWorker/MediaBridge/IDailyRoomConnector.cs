// ── IDailyRoomConnector ───────────────────────────────────────────────────────
//
// Server-side connection to a Tavus/Daily.co WebRTC room.
//
// Tavus CVI conversations use Daily-powered WebRTC rooms. To bridge Nathan's
// avatar into Teams natively, the media worker must join that Daily room as a
// hidden server-side participant, subscribe to Nathan's audio+video tracks, and
// decode them into raw PCM/YUV frames for the Graph media socket.
//
// Implementation options (in priority order):
//
//   1. SIPSorcery WebRTC (.NET library, MIT licence)
//      https://github.com/sipsorcery-org/sipsorcery
//      Join the Daily room using a standard WebRTC peer connection. SIPSorcery
//      can receive RTP audio (Opus) and video (H.264/VP8) tracks server-side.
//      Requires Opus decode and H.264 decode before passing to Graph socket.
//
//   2. Daily server-side SDK (Node.js sidecar)
//      Run a minimal Node.js process that joins the Daily room using @daily-co/daily-js
//      (which supports headless Node usage). The sidecar exposes decoded frames
//      over a local Unix socket or named pipe to the .NET media worker.
//
//   3. libwebrtc via P/Invoke
//      Raw libwebrtc with a thin native shim. Highest performance, most complex.
//
// Start with option 1 (SIPSorcery) — it keeps everything in the .NET process.
// The placeholder below defines the contract; fill in the implementation once
// SIPSorcery WebRTC track reception is validated on the Windows VM.

namespace ParlayVu.TeamsMediaWorker.MediaBridge;

/// <summary>
/// Receives real-time audio/video from a Tavus Daily room server-side.
/// Calls the provided delegates with decoded PCM audio and YUV video frames
/// at the rate required by the Graph media socket (20 ms audio, ~30 fps video).
/// </summary>
internal interface IDailyRoomConnector : IAsyncDisposable
{
    /// <summary>
    /// Join the Daily room as a hidden server participant and begin receiving
    /// Nathan's audio/video tracks.
    /// </summary>
    /// <param name="roomUrl">The Daily room URL from the Tavus conversation response.</param>
    /// <param name="meetingToken">
    /// Optional meeting token for private rooms. Pass the <c>meeting_token</c> from the
    /// Tavus create-conversation response when present.
    /// </param>
    /// <param name="onAudioFrame">
    /// Called with 16-bit PCM audio, 16 kHz, mono, 20 ms (320 bytes per frame).
    /// This delegate must not block; copy the buffer if long-lived processing is needed.
    /// </param>
    /// <param name="onVideoFrame">
    /// Called with NV12 YUV video frames at the negotiated resolution (1280×720 target).
    /// Width and height are passed alongside the frame buffer.
    /// </param>
    /// <param name="cancellationToken">Cancelled when the session ends.</param>
    Task ConnectAsync(
        string roomUrl,
        string? meetingToken,
        Action<ReadOnlyMemory<byte>> onAudioFrame,
        Action<ReadOnlyMemory<byte>, int width, int height> onVideoFrame,
        CancellationToken cancellationToken);

    /// <summary>Leave the Daily room and release all resources.</summary>
    Task DisconnectAsync(CancellationToken cancellationToken);
}
