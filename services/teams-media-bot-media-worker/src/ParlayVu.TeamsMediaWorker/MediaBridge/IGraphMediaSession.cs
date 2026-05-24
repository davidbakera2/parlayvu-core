// ── IGraphMediaSession ────────────────────────────────────────────────────────
//
// A single application-hosted media session in a Teams call.
// The Graph Communications Media SDK calls into this when the call is connected
// and audio/video sockets are ready to receive frames.
//
// Implementation notes:
//   - Audio socket expects 16-bit PCM, 16 kHz, mono, 20 ms frames (320 bytes each).
//   - Video socket expects NV12 YUV frames at the negotiated resolution (typically 1280×720).
//   - Both sockets are push-only from our side; Teams participants' inbound media
//     arrives on the same sockets and is discarded (we do not record it).
//
// See: https://microsoftgraph.github.io/microsoft-graph-comms-samples/docs/bot_media/

namespace ParlayVu.TeamsMediaWorker.MediaBridge;

/// <summary>
/// Represents a live audio/video bridge between a Tavus Daily room and a Teams call.
/// Each Teams call gets one session. Session lifetime matches the Graph call lifetime.
/// </summary>
internal interface IGraphMediaSession : IAsyncDisposable
{
    /// <summary>Unique identifier assigned by Graph when the call was created.</summary>
    string GraphCallId { get; }

    /// <summary>The Tavus Daily room URL this session is bridging from.</summary>
    string DailyRoomUrl { get; }

    /// <summary>Current bridge state.</summary>
    MediaBridgeState State { get; }

    /// <summary>
    /// Start bridging Tavus Daily audio/video into the Teams call.
    /// Call this once Graph signals the call is in the <c>established</c> state
    /// and audio/video sockets are available.
    /// </summary>
    Task StartBridgeAsync(CancellationToken cancellationToken);

    /// <summary>
    /// Stop the bridge and release all media resources.
    /// Called when the Graph call ends or when the operator explicitly stops the session.
    /// </summary>
    Task StopBridgeAsync(string reason, CancellationToken cancellationToken);
}

/// <summary>Lifecycle states for the Tavus→Teams media bridge.</summary>
internal enum MediaBridgeState
{
    /// <summary>Session created, not yet connected to Daily or Graph sockets.</summary>
    Pending,

    /// <summary>Connecting to Daily room and waiting for audio/video socket readiness.</summary>
    Connecting,

    /// <summary>Audio/video is actively flowing from Tavus Daily into Teams.</summary>
    Bridging,

    /// <summary>Bridge stopped cleanly.</summary>
    Stopped,

    /// <summary>Bridge stopped due to an error.</summary>
    Failed
}
