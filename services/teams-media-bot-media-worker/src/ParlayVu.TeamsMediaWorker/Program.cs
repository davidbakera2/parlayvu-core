// ── ParlayVU Teams Media Worker ───────────────────────────────────────────────
//
// Windows-only application-hosted media bot.
//
// This process bridges Tavus Daily WebRTC audio/video into Microsoft Teams
// meetings as a native video participant using the Microsoft Graph Communications
// Media SDK (Microsoft.Graph.Communications.Calls.Media — Windows-only).
//
// REQUIREMENTS (all mandatory):
//   - Windows Server 2019 or later
//   - Azure VM: Standard_D4s_v3 or larger (4 vCPU, 16 GB RAM minimum)
//   - Public HTTPS endpoint with a valid TLS certificate on port 443
//   - UDP ports 49152–65535 open for Graph media transport (inbound + outbound)
//   - Graph app permissions: Calls.JoinGroupCall.All + Calls.AccessMedia.All
//     (both admin-consented on the same app registration as the management service)
//
// ARCHITECTURE:
//   - The management service (parlayvu-teams-media-bot Container App) handles
//     meeting join requests and Tavus conversation lifecycle.
//   - When the management service sets TEAMS_MEDIA_BOT_MEDIA_WORKER_URL, it
//     delegates app-hosted media join requests to this worker.
//   - This worker owns the Graph media socket lifetime and the Daily room bridge.
//
// START ORDER:
//   1. Provision Windows VM (scripts/Provision-MediaBotVM.ps1)
//   2. Deploy this service to the VM (see Dockerfile.windows)
//   3. Add Calls.AccessMedia.All permission to the Entra app registration
//   4. Set TEAMS_MEDIA_BOT_MEDIA_WORKER_URL on the management Container App
//   5. POST /media/join from the management service (or directly from Postman)
//
// See docs/media-bridge-architecture.md for the full diagram.

using System.Collections.Concurrent;
using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Extensions.Options;
using ParlayVu.TeamsMediaWorker.MediaBridge;

// ── Windows guard ─────────────────────────────────────────────────────────────
if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
{
    Console.Error.WriteLine(
        "FATAL: ParlayVU Teams Media Worker requires Windows Server 2019 or later. " +
        "The Microsoft Graph Communications Media SDK uses Windows-native media DLLs " +
        "and cannot run on Linux or macOS. " +
        "Deploy this service to an Azure VM (Standard_D4s_v3+, Windows Server 2019+). " +
        "See services/teams-media-bot-media-worker/docs/media-bridge-architecture.md.");
    return 1;
}

// ── Builder ───────────────────────────────────────────────────────────────────
var builder = WebApplication.CreateBuilder(args);

var env = new Dictionary<string, string?>();
Map("TEAMS_MEDIA_BOT_TENANT_ID",           "GraphBot:TenantId");
Map("TEAMS_MEDIA_BOT_APP_ID",              "GraphBot:AppId");
Map("TEAMS_MEDIA_BOT_APP_SECRET",          "GraphBot:AppSecret");
Map("TEAMS_MEDIA_BOT_CALLBACK_BASE_URL",   "GraphBot:CallbackBaseUrl");
Map("TEAMS_MEDIA_BOT_CALLING_WEBHOOK_PATH","GraphBot:CallingWebhookPath");
Map("TEAMS_MEDIA_WORKER_MEDIA_WORKER_URL", "MediaWorker:SelfBaseUrl");
Map("TAVUS_API_KEY",                       "Tavus:ApiKey");
Map("TAVUS_BASE_URL",                      "Tavus:BaseUrl");
builder.Configuration.AddInMemoryCollection(env);

builder.Services.Configure<GraphBotConfig>(builder.Configuration.GetSection("GraphBot"));
builder.Services.Configure<TavusConfig>(builder.Configuration.GetSection("Tavus"));
builder.Services.AddHttpClient<GraphCallClient>();
builder.Services.AddSingleton<MediaSessionRegistry>();
builder.Logging.AddConsole();

// ── App ───────────────────────────────────────────────────────────────────────
var app = builder.Build();

// ── Health ────────────────────────────────────────────────────────────────────
app.MapGet("/health", (
    IOptions<GraphBotConfig> graphBot,
    MediaSessionRegistry sessions) =>
{
    var cfg = graphBot.Value;
    return Results.Ok(new
    {
        status           = "ok",
        service          = "parlayvu-teams-media-worker",
        platform         = "windows",
        mediaSdkLoaded   = true,   // Windows guard above ensures we're running on Windows
        mediaBridgeValidated = false,
        graphConfigured  = cfg.IsConfigured,
        callbackBaseUrl  = cfg.CallbackBaseUrl,
        activeSessions   = sessions.Count,
        requirements = new[]
        {
            "Calls.JoinGroupCall.All — admin-consented",
            "Calls.AccessMedia.All — admin-consented",
            "Windows Server 2019+ with UDP 49152-65535 open",
            "Public HTTPS on port 443 with valid cert"
        }
    });
});

// ── POST /media/join ──────────────────────────────────────────────────────────
// Called by the management service to start an app-hosted media session.
// The management service has already started a Tavus conversation and obtained
// the Daily room URL. This endpoint joins Teams with appHostedMediaConfig,
// then bridges the Daily room into the Graph media socket.
app.MapPost("/media/join", async (
    MediaJoinRequest request,
    GraphCallClient graphCall,
    MediaSessionRegistry sessions,
    IOptions<GraphBotConfig> graphBot,
    ILoggerFactory loggerFactory,
    CancellationToken cancellationToken) =>
{
    var logger = loggerFactory.CreateLogger("MediaJoin");

    var cfg = graphBot.Value;
    if (!cfg.IsConfigured)
    {
        return Results.BadRequest(new
        {
            error = "GraphBot is not configured. Set TEAMS_MEDIA_BOT_TENANT_ID, TEAMS_MEDIA_BOT_APP_ID, " +
                    "TEAMS_MEDIA_BOT_APP_SECRET, and TEAMS_MEDIA_BOT_CALLBACK_BASE_URL."
        });
    }

    if (string.IsNullOrWhiteSpace(request.ChatThreadId))
        return Results.BadRequest(new { error = "chatThreadId is required." });

    if (string.IsNullOrWhiteSpace(request.OrganizerUserId))
        return Results.BadRequest(new { error = "organizerUserId is required." });

    if (string.IsNullOrWhiteSpace(request.DailyRoomUrl))
        return Results.BadRequest(new { error = "dailyRoomUrl (Tavus conversation_url) is required." });

    logger.LogInformation(
        "Media join request. Thread={Thread} Organizer={Organizer} DailyRoom={Room}",
        request.ChatThreadId, request.OrganizerUserId, request.DailyRoomUrl);

    try
    {
        // Step 1: Join Teams with appHostedMediaConfig (audio + video)
        var graphResponse = await graphCall.JoinWithAppHostedMediaAsync(request, cfg, cancellationToken);
        var callId = graphResponse.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "unknown" : "unknown";

        logger.LogInformation("Graph create-call accepted. CallId={CallId}", callId);

        // Step 2: Register the session — the bridge starts when Graph sends
        // the "established" lifecycle notification to POST /media/notifications
        var session = new PendingMediaSession(
            GraphCallId: callId,
            DailyRoomUrl: request.DailyRoomUrl,
            DailyMeetingToken: request.DailyMeetingToken);
        sessions.Register(callId, session);

        return Results.Accepted(value: new
        {
            status    = "join_requested",
            callId,
            note      = "Graph accepted the create-call request with appHostedMediaConfig. " +
                        "The audio/video bridge will start when Graph sends the 'established' " +
                        "lifecycle notification to POST /media/notifications.",
            dailyRoomUrl = request.DailyRoomUrl,
            mediaBridgeValidated = false
        });
    }
    catch (HttpRequestException ex)
    {
        logger.LogError(ex, "Graph create-call failed.");
        return Results.Problem(
            detail: ex.Message,
            statusCode: 502,
            title: "Graph API error");
    }
});

// ── POST /media/notifications ─────────────────────────────────────────────────
// Graph lifecycle callbacks for app-hosted media calls.
// Graph sends notifications here when call state changes (established, terminated, etc.)
// When the call reaches "established", audio/video sockets are ready and we start
// bridging the Daily room into Teams.
app.MapPost("/media/notifications", async (
    JsonElement notification,
    MediaSessionRegistry sessions,
    ILoggerFactory loggerFactory,
    CancellationToken cancellationToken) =>
{
    var logger = loggerFactory.CreateLogger("MediaNotifications");

    // Graph sends an array of notification values
    if (notification.ValueKind == JsonValueKind.Object &&
        notification.TryGetProperty("value", out var values) &&
        values.ValueKind == JsonValueKind.Array)
    {
        foreach (var item in values.EnumerateArray())
        {
            var callId       = item.TryGetProperty("resourceData", out var rd) &&
                               rd.TryGetProperty("id", out var idProp)
                               ? idProp.GetString() : null;
            var callState    = item.TryGetProperty("resourceData", out var rd2) &&
                               rd2.TryGetProperty("state", out var stateProp)
                               ? stateProp.GetString() : null;
            var changeType   = item.TryGetProperty("changeType", out var ct)
                               ? ct.GetString() : null;

            logger.LogInformation(
                "Graph notification: changeType={ChangeType} callId={CallId} state={State}",
                changeType, callId, callState);

            if (callState == "established" && callId != null && sessions.TryGet(callId, out var session))
            {
                // TODO: Obtain the Graph SDK ICall object for this callId, then:
                //   var audioSocket = call.GetLocalMediaSession().AudioSocket;
                //   var videoSocket = call.GetLocalMediaSession().VideoSockets[0];
                //   var bridge = new GraphMediaSession(callId, session.DailyRoomUrl, ...);
                //   await bridge.StartBridgeAsync(cancellationToken);
                //   sessions.SetBridge(callId, bridge);
                //
                // This requires the full Graph Communications SDK wiring.
                // The scaffold marks this as the next implementation step.
                logger.LogInformation(
                    "Call {CallId} established. Daily bridge ready to start from {Room}. " +
                    "SDK wiring required — see GraphMediaSession.cs.", callId, session.DailyRoomUrl);
            }

            if ((callState == "terminated" || changeType == "deleted") && callId != null)
            {
                if (sessions.TryRemove(callId, out var removedSession))
                {
                    logger.LogInformation("Call {CallId} terminated. Session removed.", callId);
                }
            }
        }
    }

    // Graph requires 200 OK with no body or a minimal body to acknowledge notifications
    return Results.Ok();
});

// ── DELETE /media/{callId} ────────────────────────────────────────────────────
// Stop a specific media session and hang up the Graph call.
app.MapDelete("/media/{callId}", async (
    string callId,
    GraphCallClient graphCall,
    MediaSessionRegistry sessions,
    IOptions<GraphBotConfig> graphBot,
    CancellationToken cancellationToken) =>
{
    sessions.TryRemove(callId, out _);

    try
    {
        await graphCall.HangUpAsync(callId, graphBot.Value, cancellationToken);
        return Results.Ok(new { status = "ended", callId });
    }
    catch (HttpRequestException ex)
    {
        return Results.Problem(ex.Message, statusCode: 502);
    }
});

app.Run();
return 0;

// ── Helpers ───────────────────────────────────────────────────────────────────
void Map(string envVar, string configKey)
{
    var value = Environment.GetEnvironmentVariable(envVar);
    if (!string.IsNullOrWhiteSpace(value))
        env[configKey] = value;
}

// ── Records ───────────────────────────────────────────────────────────────────

internal sealed record MediaJoinRequest(
    string ChatThreadId,
    string ChatMessageId = "0",
    string OrganizerUserId = "",
    string? OrganizerDisplayName = null,
    string? OrganizerTenantId = null,
    string? TenantId = null,
    string? CallbackUri = null,
    string DailyRoomUrl = "",
    string? DailyMeetingToken = null,
    bool AllowConversationWithoutHost = true);

internal sealed record PendingMediaSession(
    string GraphCallId,
    string DailyRoomUrl,
    string? DailyMeetingToken);

// ── Configuration ─────────────────────────────────────────────────────────────

internal sealed record GraphBotConfig
{
    public string? TenantId { get; init; }
    public string? AppId { get; init; }
    public string? AppSecret { get; init; }
    public string? CallbackBaseUrl { get; init; }
    public string CallingWebhookPath { get; init; } = "/media/notifications";
    public string GraphBaseUrl { get; init; } = "https://graph.microsoft.com";
    public string LoginBaseUrl { get; init; } = "https://login.microsoftonline.com";

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(TenantId)
        && !string.IsNullOrWhiteSpace(AppId)
        && !string.IsNullOrWhiteSpace(AppSecret)
        && !string.IsNullOrWhiteSpace(CallbackBaseUrl);

    public string MediaNotificationsUri =>
        string.IsNullOrWhiteSpace(CallbackBaseUrl)
            ? string.Empty
            : $"{CallbackBaseUrl.TrimEnd('/')}/{CallingWebhookPath.TrimStart('/')}";
}

internal sealed record TavusConfig
{
    public string? ApiKey { get; init; }
    public string BaseUrl { get; init; } = "https://tavusapi.com";
}

// ── GraphCallClient ───────────────────────────────────────────────────────────

internal sealed class GraphCallClient(HttpClient httpClient)
{
    private static readonly System.Text.Json.JsonSerializerOptions JsonOptions =
        new(System.Text.Json.JsonSerializerDefaults.Web);

    public async Task<JsonElement> JoinWithAppHostedMediaAsync(
        MediaJoinRequest request,
        GraphBotConfig cfg,
        CancellationToken cancellationToken)
    {
        var accessToken = await GetAccessTokenAsync(cfg, cancellationToken);

        var tenantId          = request.TenantId ?? cfg.TenantId!;
        var organizerTenantId = request.OrganizerTenantId ?? tenantId;
        var callbackUri       = request.CallbackUri ?? cfg.MediaNotificationsUri;

        // appHostedMediaConfig signals that THIS process will own the media socket.
        // The "blob" field is generated by the Graph Communications Media SDK;
        // it encodes media session parameters (codec preferences, ICE candidates, etc.).
        // TODO: Replace the placeholder blob with the real SDK-generated value.
        //   using var mediaSession = statefulClient.CreateMediaSession(...);
        //   var blob = mediaSession.MediaSessionToken;
        var payload = new Dictionary<string, object?>
        {
            ["@odata.type"]       = "#microsoft.graph.call",
            ["callbackUri"]       = callbackUri,
            ["requestedModalities"] = new[] { "audio", "video" },
            ["mediaConfig"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.appHostedMediaConfig",
                // IMPORTANT: Replace this placeholder with the real SDK blob before
                // attempting a live call. An invalid blob causes Graph to reject the
                // create-call request with 400 Bad Request.
                ["blob"] = "PLACEHOLDER_REQUIRES_GRAPH_COMMUNICATIONS_MEDIA_SDK"
            },
            ["chatInfo"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.chatInfo",
                ["threadId"]    = request.ChatThreadId,
                ["messageId"]   = request.ChatMessageId
            },
            ["meetingInfo"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.organizerMeetingInfo",
                ["organizer"] = new Dictionary<string, object?>
                {
                    ["@odata.type"] = "#microsoft.graph.identitySet",
                    ["user"] = new Dictionary<string, object?>
                    {
                        ["@odata.type"]   = "#microsoft.graph.identity",
                        ["id"]            = request.OrganizerUserId,
                        ["displayName"]   = request.OrganizerDisplayName,
                        ["tenantId"]      = organizerTenantId
                    }
                },
                ["allowConversationWithoutHost"] = request.AllowConversationWithoutHost
            },
            ["tenantId"] = tenantId
        };

        using var httpRequest = new System.Net.Http.HttpRequestMessage(
            System.Net.Http.HttpMethod.Post,
            $"{cfg.GraphBaseUrl.TrimEnd('/')}/v1.0/communications/calls")
        {
            Content = System.Net.Http.Json.JsonContent.Create(payload, options: JsonOptions)
        };
        httpRequest.Headers.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", accessToken);

        using var response = await httpClient.SendAsync(httpRequest, cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);

        if (!response.IsSuccessStatusCode)
            throw new System.Net.Http.HttpRequestException(
                $"Graph create-call returned {(int)response.StatusCode}: {body}");

        return System.Text.Json.JsonDocument.Parse(body).RootElement.Clone();
    }

    public async Task HangUpAsync(string callId, GraphBotConfig cfg, CancellationToken cancellationToken)
    {
        var accessToken = await GetAccessTokenAsync(cfg, cancellationToken);
        using var request = new System.Net.Http.HttpRequestMessage(
            System.Net.Http.HttpMethod.Delete,
            $"{cfg.GraphBaseUrl.TrimEnd('/')}/v1.0/communications/calls/{Uri.EscapeDataString(callId)}");
        request.Headers.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", accessToken);
        using var response = await httpClient.SendAsync(request, cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new System.Net.Http.HttpRequestException(
                $"Graph hang-up returned {(int)response.StatusCode}: {body}");
        }
    }

    private async Task<string> GetAccessTokenAsync(GraphBotConfig cfg, CancellationToken cancellationToken)
    {
        var endpoint = $"{cfg.LoginBaseUrl.TrimEnd('/')}/{Uri.EscapeDataString(cfg.TenantId!)}/oauth2/v2.0/token";
        using var tokenRequest = new System.Net.Http.HttpRequestMessage(System.Net.Http.HttpMethod.Post, endpoint)
        {
            Content = new System.Net.Http.FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["client_id"]     = cfg.AppId!,
                ["client_secret"] = cfg.AppSecret!,
                ["grant_type"]    = "client_credentials",
                ["scope"]         = "https://graph.microsoft.com/.default"
            })
        };

        using var tokenResponse = await httpClient.SendAsync(tokenRequest, cancellationToken);
        var responseBody = await tokenResponse.Content.ReadAsStringAsync(cancellationToken);

        if (!tokenResponse.IsSuccessStatusCode)
            throw new System.Net.Http.HttpRequestException(
                $"Token request returned {(int)tokenResponse.StatusCode}: {responseBody}");

        using var doc = System.Text.Json.JsonDocument.Parse(responseBody);
        return doc.RootElement.GetProperty("access_token").GetString()
            ?? throw new InvalidOperationException("Token response missing access_token.");
    }
}

// ── MediaSessionRegistry ──────────────────────────────────────────────────────

internal sealed class MediaSessionRegistry
{
    private readonly System.Collections.Concurrent.ConcurrentDictionary<string, PendingMediaSession>
        _sessions = new();

    public int Count => _sessions.Count;

    public void Register(string callId, PendingMediaSession session) =>
        _sessions[callId] = session;

    public bool TryGet(string callId, out PendingMediaSession? session) =>
        _sessions.TryGetValue(callId, out session);

    public bool TryRemove(string callId, out PendingMediaSession? session) =>
        _sessions.TryRemove(callId, out session);
}
