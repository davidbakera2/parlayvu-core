// ── GraphMediaSession ─────────────────────────────────────────────────────────
//
// Application-hosted media session implementation.
// This class wires the Graph Communications Media SDK audio/video sockets to the
// Tavus Daily room via IDailyRoomConnector.
//
// SCAFFOLD STATE: The Graph SDK types (ICall, IAudioSocket, IVideoSocket) require
// the Windows-only Microsoft.Graph.Communications.Calls.Media package. Wire the
// actual SDK types in once the package is restored on the Windows VM and the
// correct SDK version is confirmed to work with .NET 8.
//
// When a Graph call reaches the "established" state, Graph assigns audio and video
// sockets to our process. We subscribe to those sockets' Send delegates and feed
// them decoded frames from the Daily room connector.

using ParlayVu.TeamsMediaWorker.MediaBridge;

namespace ParlayVu.TeamsMediaWorker.MediaBridge;

internal sealed class GraphMediaSession : IGraphMediaSession
{
    private readonly IDailyRoomConnector _dailyConnector;
    private readonly ILogger<GraphMediaSession> _logger;
    private CancellationTokenSource? _cts;

    public string GraphCallId { get; }
    public string DailyRoomUrl { get; }
    public MediaBridgeState State { get; private set; } = MediaBridgeState.Pending;

    public GraphMediaSession(
        string graphCallId,
        string dailyRoomUrl,
        IDailyRoomConnector dailyConnector,
        ILogger<GraphMediaSession> logger)
    {
        GraphCallId = graphCallId;
        DailyRoomUrl = dailyRoomUrl;
        _dailyConnector = dailyConnector;
        _logger = logger;
    }

    public async Task StartBridgeAsync(CancellationToken cancellationToken)
    {
        if (State != MediaBridgeState.Pending)
            throw new InvalidOperationException($"Cannot start bridge from state {State}.");

        State = MediaBridgeState.Connecting;
        _logger.LogInformation(
            "Starting Tavus→Teams media bridge. CallId={CallId} DailyRoom={DailyRoom}",
            GraphCallId, DailyRoomUrl);

        _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);

        try
        {
            // TODO: Obtain audio and video sockets from the Graph Communications SDK.
            // The SDK delivers these via ICall.GetLocalMediaSession().AudioSocket and
            // ICall.GetLocalMediaSession().VideoSockets[0] once the call is established.
            // Store them as fields so the frame callbacks below can write to them.
            //
            // Example (requires Microsoft.Graph.Communications.Calls.Media):
            //   IAudioSocket audioSocket = call.GetLocalMediaSession().AudioSocket;
            //   IVideoSocket videoSocket = call.GetLocalMediaSession().VideoSockets[0];

            await _dailyConnector.ConnectAsync(
                roomUrl: DailyRoomUrl,
                meetingToken: null, // TODO: pass token from Tavus response when present
                onAudioFrame: frame => SendAudioFrame(frame),
                onVideoFrame: (frame, w, h) => SendVideoFrame(frame, w, h),
                cancellationToken: _cts.Token);

            State = MediaBridgeState.Bridging;
            _logger.LogInformation("Media bridge active. CallId={CallId}", GraphCallId);
        }
        catch (Exception ex)
        {
            State = MediaBridgeState.Failed;
            _logger.LogError(ex, "Media bridge failed to start. CallId={CallId}", GraphCallId);
            throw;
        }
    }

    public async Task StopBridgeAsync(string reason, CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Stopping media bridge. CallId={CallId} Reason={Reason}", GraphCallId, reason);

        _cts?.Cancel();
        await _dailyConnector.DisconnectAsync(cancellationToken);
        State = MediaBridgeState.Stopped;
    }

    private void SendAudioFrame(ReadOnlyMemory<byte> pcmFrame)
    {
        // TODO: Write PCM frame to Graph audio socket.
        // The socket expects 16-bit PCM, 16 kHz, mono, 320 bytes (20 ms at 16 kHz).
        //
        // Example (requires Microsoft.Graph.Communications.Calls.Media):
        //   var buffer = new AudioSendBuffer(pcmFrame, AudioFormat.Pcm16K20Ms);
        //   audioSocket.Send(buffer);
        //
        // For now: no-op placeholder until SDK types are wired.
        _ = pcmFrame;
    }

    private void SendVideoFrame(ReadOnlyMemory<byte> nv12Frame, int width, int height)
    {
        // TODO: Write NV12 YUV frame to Graph video socket.
        // The socket expects NV12 format at the negotiated resolution.
        // Typical Teams video is 1280×720 NV12 at 30 fps.
        //
        // Example (requires Microsoft.Graph.Communications.Calls.Media):
        //   var buffer = new VideoSendBuffer(nv12Frame, (uint)width, (uint)height, VideoFrameFormat.NV12);
        //   videoSocket.Send(buffer);
        //
        // For now: no-op placeholder until SDK types are wired.
        _ = nv12Frame;
        _ = width;
        _ = height;
    }

    public async ValueTask DisposeAsync()
    {
        if (State == MediaBridgeState.Bridging)
            await StopBridgeAsync("dispose", CancellationToken.None);

        _cts?.Dispose();
        await _dailyConnector.DisposeAsync();
    }
}
