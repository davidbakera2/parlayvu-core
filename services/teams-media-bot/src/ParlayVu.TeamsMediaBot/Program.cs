using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.Options;

var builder = WebApplication.CreateBuilder(args);

var environmentConfiguration = new Dictionary<string, string?>();
MapEnvironment("PARLAYVU_BASE_URL", "ParlayVu:BaseUrl");
MapEnvironment("PARLAYVU_API_KEY", "ParlayVu:ApiKey");
MapEnvironment("TEAMS_MEDIA_BOT_TENANT_ID", "GraphBot:TenantId");
MapEnvironment("TEAMS_MEDIA_BOT_APP_ID", "GraphBot:AppId");
MapEnvironment("TEAMS_MEDIA_BOT_APP_SECRET", "GraphBot:AppSecret");
MapEnvironment("TEAMS_MEDIA_BOT_CALLBACK_BASE_URL", "GraphBot:CallbackBaseUrl");
MapEnvironment("TEAMS_MEDIA_BOT_CALLING_WEBHOOK_PATH", "GraphBot:CallingWebhookPath");
MapEnvironment("TEAMS_MEDIA_BOT_GRAPH_BASE_URL", "GraphBot:GraphBaseUrl");
MapEnvironment("TEAMS_MEDIA_BOT_LOGIN_BASE_URL", "GraphBot:LoginBaseUrl");
MapEnvironment("TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED", "GraphBot:JoinEnabled");
MapEnvironment("TAVUS_API_KEY", "AvatarProviders:Tavus:ApiKey");
MapEnvironment("TAVUS_BASE_URL", "AvatarProviders:Tavus:BaseUrl");
MapEnvironment("TAVUS_REPLICA_ID", "AvatarProviders:Tavus:ReplicaId");
MapEnvironment("TAVUS_PERSONA_ID", "AvatarProviders:Tavus:PersonaId");
MapEnvironment("LIVEAVATAR_API_KEY", "AvatarProviders:HeyGenLiveAvatar:ApiKey");
MapEnvironment("LIVEAVATAR_BASE_URL", "AvatarProviders:HeyGenLiveAvatar:BaseUrl");
MapEnvironment("HEYGEN_API_KEY", "AvatarProviders:HeyGenLiveAvatar:ApiKey");
MapEnvironment("DID_API_KEY", "AvatarProviders:DID:ApiKey");
MapEnvironment("DID_AGENT_ID", "AvatarProviders:DID:AgentId");
MapEnvironment("DID_CLIENT_KEY", "AvatarProviders:DID:ClientKey");
MapEnvironment("SOUL_MACHINES_API_KEY", "AvatarProviders:SoulMachines:ApiKey");
builder.Configuration.AddInMemoryCollection(environmentConfiguration);

builder.Services.Configure<ParlayVuOptions>(builder.Configuration.GetSection("ParlayVu"));
builder.Services.Configure<GraphBotOptions>(builder.Configuration.GetSection("GraphBot"));
builder.Services.Configure<AvatarProviderOptions>(builder.Configuration.GetSection("AvatarProviders"));
builder.Services.AddHttpClient<ParlayVuClient>();
builder.Services.AddHttpClient<GraphCommunicationsClient>();

var app = builder.Build();

app.MapGet("/health", (
    IOptions<ParlayVuOptions> parlayVu,
    IOptions<GraphBotOptions> graphBot,
    IOptions<AvatarProviderOptions> avatarProviders) =>
{
    return Results.Ok(new
    {
        status = "ok",
        service = "parlayvu-teams-media-bot",
        parlayVuConfigured = parlayVu.Value.IsConfigured,
        graphBotConfigured = graphBot.Value.IsConfigured,
        graphJoinEnabled = graphBot.Value.JoinEnabled,
        graphCallingWebhook = graphBot.Value.CallingWebhookUri,
        graphJoinRequestImplemented = true,
        mediaJoinImplemented = false,
        notesPath = "teams-native-transcript-or-approved-upload",
        avatarProviders = avatarProviders.Value.ToStatus()
    });
});

app.MapGet("/avatar/providers/status", (IOptions<AvatarProviderOptions> avatarProviders) =>
{
    return Results.Ok(new
    {
        status = "scaffolded",
        contract = "docs/avatar-provider-contract.md",
        mediaBridgeValidated = false,
        providers = avatarProviders.Value.ToStatus()
    });
});

app.MapPost("/teams/calling/notifications", async (
    GraphNotification notification,
    ILoggerFactory loggerFactory,
    CancellationToken cancellationToken) =>
{
    var logger = loggerFactory.CreateLogger("GraphNotifications");
    logger.LogInformation(
        "Received Graph communications notification {ChangeType} for {Resource}",
        notification.ChangeType,
        notification.Resource);

    await Task.CompletedTask;
    return Results.Accepted(value: new
    {
        status = "accepted",
        note = "Lifecycle notification received. Graph call handling is scaffolded only."
    });
});

app.MapPost("/meetings/join", async (
    JoinMeetingRequest request,
    ParlayVuClient parlayVu,
    GraphCommunicationsClient graph,
    IOptions<GraphBotOptions> graphBot,
    CancellationToken cancellationToken) =>
{
    if (string.IsNullOrWhiteSpace(request.MeetingJoinUrl) && string.IsNullOrWhiteSpace(request.TeamsMeetingId))
    {
        return Results.BadRequest(new { error = "meetingJoinUrl or teamsMeetingId is required." });
    }

    JsonElement? session = null;
    object parlayVuRegistration;
    if (request.RegisterWithParlayVu)
    {
        var startRequest = new LiveMeetingStartRequest(
            AgentName: request.AgentName,
            ClientId: request.ClientId,
            ProjectId: request.ProjectId,
            MeetingTitle: request.MeetingTitle,
            ExpectedAttendees: request.ExpectedAttendees ?? [],
            HeygenSessionId: null,
            TeamsMeetingId: request.TeamsMeetingId,
            TeamsMeetingLink: request.MeetingJoinUrl,
            OperatorNotes: request.OperatorNotes);

        session = await parlayVu.StartLiveMeetingAsync(startRequest, cancellationToken);
        parlayVuRegistration = new { status = "registered", session };
    }
    else
    {
        parlayVuRegistration = new { status = "skipped", reason = "registerWithParlayVu=false" };
    }

    var graphJoin = await TryJoinGraphCallAsync(request, graph, graphBot.Value, cancellationToken);

    return Results.Ok(new
    {
        status = request.AttemptGraphJoin ? "join_request_processed" : "registered_with_parlayvu",
        parlayVuRegistration,
        graphJoin,
        nextSteps = new[]
        {
            "Deploy this service to supported Azure compute with a public HTTPS callback URL.",
            "Configure the Azure Bot Teams calling webhook to POST /teams/calling/notifications.",
            "Grant admin consent for Calls.JoinGroupCall.All and Calls.AccessMedia.All before application-hosted media work.",
            "Provide scheduled meeting chatInfo and organizer meetingInfo before setting attemptGraphJoin=true."
        }
    });
});

app.MapPost("/meetings/join/graph-request-preview", (
    JoinMeetingRequest request,
    IOptions<GraphBotOptions> graphBot) =>
{
    var joinRequest = GraphJoinMeetingRequest.From(request, graphBot.Value);
    var missing = joinRequest.Validate();

    return Results.Ok(new
    {
        status = missing.Count == 0 ? "ready_to_attempt" : "missing_required_graph_fields",
        missing,
        callbackUri = joinRequest.CallbackUri,
        requiredPermission = "Calls.JoinGroupCall.All",
        laterMediaBridgePermission = "Calls.AccessMedia.All",
        createCallEndpoint = $"{graphBot.Value.GraphBaseUrl.TrimEnd('/')}/v1.0/communications/calls",
        payload = joinRequest.BuildCreateCallPayload()
    });
});

app.MapPost("/meetings/{sessionId}/question", async (
    string sessionId,
    LiveQuestionRequest request,
    ParlayVuClient parlayVu,
    CancellationToken cancellationToken) =>
{
    if (string.IsNullOrWhiteSpace(request.Question))
    {
        return Results.BadRequest(new { error = "question is required." });
    }

    var response = await parlayVu.AskLiveQuestionAsync(sessionId, request, cancellationToken);
    return Results.Ok(response);
});

app.MapPost("/meetings/{sessionId}/notes", async (
    string sessionId,
    MeetingNotesRequest request,
    ParlayVuClient parlayVu,
    CancellationToken cancellationToken) =>
{
    if (string.IsNullOrWhiteSpace(request.Summary) && string.IsNullOrWhiteSpace(request.Transcript))
    {
        return Results.BadRequest(new { error = "summary or transcript is required." });
    }

    var response = await parlayVu.PublishMeetingNotesAsync(sessionId, request, cancellationToken);
    return Results.Ok(response);
});

app.Run();

async Task<object> TryJoinGraphCallAsync(
    JoinMeetingRequest request,
    GraphCommunicationsClient graph,
    GraphBotOptions graphBot,
    CancellationToken cancellationToken)
{
    if (!request.AttemptGraphJoin)
    {
        return new
        {
            status = "not_attempted",
            reason = "Set attemptGraphJoin=true only after Azure Bot calling, Graph permissions, and public HTTPS callback hosting are configured."
        };
    }

    if (!graphBot.JoinEnabled)
    {
        return new
        {
            status = "blocked_by_configuration",
            reason = "Set GraphBot:JoinEnabled=true or TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED=true on the hosted bot to allow live Graph join attempts."
        };
    }

    var joinRequest = GraphJoinMeetingRequest.From(request, graphBot);
    var missing = joinRequest.Validate();
    if (missing.Count > 0)
    {
        return new
        {
            status = "missing_required_graph_fields",
            missing,
            requiredPermission = "Calls.JoinGroupCall.All",
            note = "A Teams meeting join URL alone is not enough for Graph create-call join. Provide chatInfo.threadId/messageId and organizer meetingInfo."
        };
    }

    try
    {
        var response = await graph.JoinScheduledMeetingAsync(joinRequest, cancellationToken);
        return new
        {
            status = "join_requested",
            response,
            callbackUri = joinRequest.CallbackUri,
            note = "This only confirms Graph accepted the create-call request. Verify roster presence and lifecycle callbacks before claiming live join success."
        };
    }
    catch (HttpRequestException ex)
    {
        return new
        {
            status = "graph_request_failed",
            error = ex.Message,
            likelyCauses = new[]
            {
                "Missing admin consent for Calls.JoinGroupCall.All.",
                "Azure Bot Teams channel calling webhook is not enabled or does not match the public callback URL.",
                "The bot app registration, Azure Bot Microsoft App ID, and token credentials do not refer to the same application.",
                "The meeting chatInfo or organizer meetingInfo does not match the scheduled Teams meeting."
            }
        };
    }
}

void MapEnvironment(string variableName, string configurationKey)
{
    var value = Environment.GetEnvironmentVariable(variableName);
    if (!string.IsNullOrWhiteSpace(value))
    {
        environmentConfiguration[configurationKey] = value;
    }
}

internal sealed class ParlayVuClient(HttpClient httpClient, IOptions<ParlayVuOptions> options)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly ParlayVuOptions _options = options.Value;

    public async Task<JsonElement> StartLiveMeetingAsync(
        LiveMeetingStartRequest request,
        CancellationToken cancellationToken)
    {
        return await PostAsync("/heygen/live-meetings/start", request, cancellationToken);
    }

    public async Task<JsonElement> AskLiveQuestionAsync(
        string sessionId,
        LiveQuestionRequest request,
        CancellationToken cancellationToken)
    {
        return await PostAsync($"/heygen/live-meetings/{Uri.EscapeDataString(sessionId)}/question", request, cancellationToken);
    }

    public async Task<JsonElement> PublishMeetingNotesAsync(
        string sessionId,
        MeetingNotesRequest request,
        CancellationToken cancellationToken)
    {
        return await PostAsync($"/heygen/live-meetings/{Uri.EscapeDataString(sessionId)}/notes", request, cancellationToken);
    }

    private async Task<JsonElement> PostAsync<TRequest>(
        string path,
        TRequest request,
        CancellationToken cancellationToken)
    {
        if (!_options.IsConfigured)
        {
            throw new InvalidOperationException("ParlayVu:BaseUrl or PARLAYVU_BASE_URL must be configured.");
        }

        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, BuildUri(path))
        {
            Content = JsonContent.Create(request, options: JsonOptions)
        };

        if (!string.IsNullOrWhiteSpace(_options.ApiKey))
        {
            httpRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _options.ApiKey);
        }

        using var response = await httpClient.SendAsync(httpRequest, cancellationToken);
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"ParlayVU returned {(int)response.StatusCode} {response.ReasonPhrase}: {responseBody}");
        }

        return JsonSerializer.Deserialize<JsonElement>(responseBody, JsonOptions);
    }

    private Uri BuildUri(string path)
    {
        var baseUrl = _options.BaseUrl!.TrimEnd('/');
        return new Uri($"{baseUrl}{path}");
    }
}

internal sealed class GraphCommunicationsClient(HttpClient httpClient, IOptions<GraphBotOptions> options)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly GraphBotOptions _options = options.Value;

    public async Task<JsonElement> JoinScheduledMeetingAsync(
        GraphJoinMeetingRequest request,
        CancellationToken cancellationToken)
    {
        if (!_options.IsConfigured)
        {
            throw new InvalidOperationException(
                "GraphBot TenantId, AppId, AppSecret, and CallbackBaseUrl must be configured before Graph join.");
        }

        var accessToken = await GetAccessTokenAsync(cancellationToken);
        using var httpRequest = new HttpRequestMessage(
            HttpMethod.Post,
            $"{_options.GraphBaseUrl.TrimEnd('/')}/v1.0/communications/calls")
        {
            Content = JsonContent.Create(request.BuildCreateCallPayload(), options: JsonOptions)
        };
        httpRequest.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken);

        using var response = await httpClient.SendAsync(httpRequest, cancellationToken);
        var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Graph create call returned {(int)response.StatusCode} {response.ReasonPhrase}: {responseBody}");
        }

        return JsonSerializer.Deserialize<JsonElement>(responseBody, JsonOptions);
    }

    private async Task<string> GetAccessTokenAsync(CancellationToken cancellationToken)
    {
        var tokenEndpoint = $"{_options.LoginBaseUrl.TrimEnd('/')}/{Uri.EscapeDataString(_options.TenantId!)}/oauth2/v2.0/token";
        using var tokenRequest = new HttpRequestMessage(HttpMethod.Post, tokenEndpoint)
        {
            Content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["client_id"] = _options.AppId!,
                ["client_secret"] = _options.AppSecret!,
                ["grant_type"] = "client_credentials",
                ["scope"] = "https://graph.microsoft.com/.default"
            })
        };

        using var tokenResponse = await httpClient.SendAsync(tokenRequest, cancellationToken);
        var responseBody = await tokenResponse.Content.ReadAsStringAsync(cancellationToken);

        if (!tokenResponse.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"Microsoft identity token request returned {(int)tokenResponse.StatusCode} {tokenResponse.ReasonPhrase}: {responseBody}");
        }

        using var document = JsonDocument.Parse(responseBody);
        return document.RootElement.GetProperty("access_token").GetString()
            ?? throw new InvalidOperationException("Microsoft identity token response did not include access_token.");
    }
}

internal sealed record ParlayVuOptions
{
    public string? BaseUrl { get; init; }
    public string? ApiKey { get; init; }

    public bool IsConfigured => !string.IsNullOrWhiteSpace(BaseUrl);
}

internal sealed record GraphBotOptions
{
    public string? TenantId { get; init; }
    public string? AppId { get; init; }
    public string? AppSecret { get; init; }
    public string? CallbackBaseUrl { get; init; }
    public string CallingWebhookPath { get; init; } = "/teams/calling/notifications";
    public string GraphBaseUrl { get; init; } = "https://graph.microsoft.com";
    public string LoginBaseUrl { get; init; } = "https://login.microsoftonline.com";
    public bool JoinEnabled { get; init; }

    public string? CallingWebhookUri =>
        string.IsNullOrWhiteSpace(CallbackBaseUrl)
            ? null
            : $"{CallbackBaseUrl.TrimEnd('/')}/{CallingWebhookPath.TrimStart('/')}";

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(TenantId)
        && !string.IsNullOrWhiteSpace(AppId)
        && !string.IsNullOrWhiteSpace(AppSecret)
        && !string.IsNullOrWhiteSpace(CallbackBaseUrl);
}

internal sealed record GraphJoinMeetingRequest(
    string CallbackUri,
    string ChatThreadId,
    string ChatMessageId,
    string OrganizerUserId,
    string? OrganizerDisplayName,
    string OrganizerTenantId,
    string TenantId,
    IReadOnlyList<string> RequestedModalities,
    bool AllowConversationWithoutHost)
{
    public static GraphJoinMeetingRequest From(JoinMeetingRequest request, GraphBotOptions graphBot)
    {
        var callbackUri = !string.IsNullOrWhiteSpace(request.CallbackUri)
            ? request.CallbackUri
            : graphBot.CallingWebhookUri;
        var tenantId = !string.IsNullOrWhiteSpace(request.TenantId)
            ? request.TenantId
            : graphBot.TenantId;
        var organizerTenantId = !string.IsNullOrWhiteSpace(request.OrganizerTenantId)
            ? request.OrganizerTenantId
            : tenantId;

        return new GraphJoinMeetingRequest(
            CallbackUri: callbackUri ?? string.Empty,
            ChatThreadId: request.ChatThreadId ?? string.Empty,
            ChatMessageId: string.IsNullOrWhiteSpace(request.ChatMessageId) ? "0" : request.ChatMessageId,
            OrganizerUserId: request.OrganizerUserId ?? string.Empty,
            OrganizerDisplayName: request.OrganizerDisplayName,
            OrganizerTenantId: organizerTenantId ?? string.Empty,
            TenantId: tenantId ?? string.Empty,
            RequestedModalities: request.RequestedModalities is { Count: > 0 } ? request.RequestedModalities : ["audio"],
            AllowConversationWithoutHost: request.AllowConversationWithoutHost);
    }

    public IReadOnlyList<string> Validate()
    {
        var missing = new List<string>();
        AddIfMissing(missing, nameof(CallbackUri), CallbackUri);
        AddIfMissing(missing, nameof(ChatThreadId), ChatThreadId);
        AddIfMissing(missing, nameof(ChatMessageId), ChatMessageId);
        AddIfMissing(missing, nameof(OrganizerUserId), OrganizerUserId);
        AddIfMissing(missing, nameof(OrganizerTenantId), OrganizerTenantId);
        AddIfMissing(missing, nameof(TenantId), TenantId);
        return missing;
    }

    public Dictionary<string, object?> BuildCreateCallPayload() =>
        new()
        {
            ["@odata.type"] = "#microsoft.graph.call",
            ["callbackUri"] = CallbackUri,
            ["requestedModalities"] = RequestedModalities,
            ["mediaConfig"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.serviceHostedMediaConfig"
            },
            ["chatInfo"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.chatInfo",
                ["threadId"] = ChatThreadId,
                ["messageId"] = ChatMessageId
            },
            ["meetingInfo"] = new Dictionary<string, object?>
            {
                ["@odata.type"] = "#microsoft.graph.organizerMeetingInfo",
                ["organizer"] = new Dictionary<string, object?>
                {
                    ["@odata.type"] = "#microsoft.graph.identitySet",
                    ["user"] = new Dictionary<string, object?>
                    {
                        ["@odata.type"] = "#microsoft.graph.identity",
                        ["id"] = OrganizerUserId,
                        ["displayName"] = OrganizerDisplayName,
                        ["tenantId"] = OrganizerTenantId
                    }
                },
                ["allowConversationWithoutHost"] = AllowConversationWithoutHost
            },
            ["tenantId"] = TenantId
        };

    private static void AddIfMissing(List<string> missing, string name, string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            missing.Add(name);
        }
    }
}

internal sealed record AvatarProviderOptions
{
    public AvatarProviderConfiguration Tavus { get; init; } = new()
    {
        BaseUrl = "https://tavusapi.com",
        SessionEndpoint = "/v2/conversations"
    };

    public AvatarProviderConfiguration HeyGenLiveAvatar { get; init; } = new()
    {
        BaseUrl = "https://api.liveavatar.com",
        SessionEndpoint = "/v1/sessions/start"
    };

    public AvatarProviderConfiguration DID { get; init; } = new();

    public AvatarProviderConfiguration SoulMachines { get; init; } = new();

    public IReadOnlyList<AvatarProviderStatus> ToStatus() =>
    [
        Tavus.ToStatus("tavus", required: ["apiKey", "replicaId", "personaId"]),
        HeyGenLiveAvatar.ToStatus("heygen-liveavatar", required: ["apiKey"]),
        DID.ToStatus("did", required: ["agentId", "clientKey"]),
        SoulMachines.ToStatus("soul-machines", required: ["apiKey"])
    ];
}

internal sealed record AvatarProviderConfiguration
{
    public string? ApiKey { get; init; }
    public string? BaseUrl { get; init; }
    public string? SessionEndpoint { get; init; }
    public string? ReplicaId { get; init; }
    public string? PersonaId { get; init; }
    public string? AgentId { get; init; }
    public string? ClientKey { get; init; }

    public AvatarProviderStatus ToStatus(string name, IReadOnlyList<string> required)
    {
        var configuredFields = new Dictionary<string, bool>
        {
            ["apiKey"] = !string.IsNullOrWhiteSpace(ApiKey),
            ["baseUrl"] = !string.IsNullOrWhiteSpace(BaseUrl),
            ["sessionEndpoint"] = !string.IsNullOrWhiteSpace(SessionEndpoint),
            ["replicaId"] = !string.IsNullOrWhiteSpace(ReplicaId),
            ["personaId"] = !string.IsNullOrWhiteSpace(PersonaId),
            ["agentId"] = !string.IsNullOrWhiteSpace(AgentId),
            ["clientKey"] = !string.IsNullOrWhiteSpace(ClientKey)
        };

        return new AvatarProviderStatus(
            Name: name,
            Configured: required.All(field => configuredFields.GetValueOrDefault(field)),
            Required: required,
            ConfiguredFields: configuredFields);
    }
}

internal sealed record AvatarProviderStatus(
    string Name,
    bool Configured,
    IReadOnlyList<string> Required,
    IReadOnlyDictionary<string, bool> ConfiguredFields);

internal interface IAvatarProviderAdapter
{
    string ProviderName { get; }
    Task<AvatarProviderSession> StartSessionAsync(
        AvatarSessionStartRequest request,
        CancellationToken cancellationToken);
    Task<AvatarSpeakResult> SpeakAsync(
        AvatarSpeakRequest request,
        CancellationToken cancellationToken);
    Task StopSessionAsync(
        string providerSessionId,
        string reason,
        CancellationToken cancellationToken);
}

internal sealed record AvatarSessionStartRequest(
    string AgentName,
    string MeetingSessionId,
    string? ProviderHint,
    string? ConversationalContext,
    bool RequireVideo,
    bool RequireAudio);

internal sealed record AvatarProviderSession(
    string ProviderName,
    string ProviderSessionId,
    AvatarMediaAccess MediaAccess,
    bool MediaBridgeValidated,
    string? JoinUrl = null,
    string? WebRtcRoomUrl = null,
    string? ClientToken = null,
    string? AgentToken = null);

internal sealed record AvatarMediaAccess(
    string Transport,
    bool AudioAvailable,
    bool VideoAvailable,
    string? Notes);

internal sealed record AvatarSpeakRequest(
    string ProviderSessionId,
    string Text,
    string? VoiceInstructions,
    bool InterruptCurrentSpeech);

internal sealed record AvatarSpeakResult(
    string ProviderName,
    string ProviderSessionId,
    string Status,
    string? ProviderEventId);

internal sealed record GraphNotification(
    string? ChangeType,
    string? Resource,
    string? ResourceUrl,
    string? ClientState,
    JsonElement? EncryptedContent);

internal sealed record JoinMeetingRequest(
    string? MeetingJoinUrl,
    string? TeamsMeetingId,
    string MeetingTitle = "RamAir Teams call",
    string AgentName = "nathan",
    string ClientId = "ramair",
    string ProjectId = "ramair-straight-from-the-hart",
    IReadOnlyList<string>? ExpectedAttendees = null,
    string? OperatorNotes = null,
    bool RegisterWithParlayVu = true,
    bool AttemptGraphJoin = false,
    string? CallbackUri = null,
    string? ChatThreadId = null,
    string? ChatMessageId = "0",
    string? OrganizerUserId = null,
    string? OrganizerDisplayName = null,
    string? OrganizerTenantId = null,
    string? TenantId = null,
    IReadOnlyList<string>? RequestedModalities = null,
    bool AllowConversationWithoutHost = true);

internal sealed record LiveMeetingStartRequest(
    string AgentName,
    string ClientId,
    string ProjectId,
    string MeetingTitle,
    IReadOnlyList<string> ExpectedAttendees,
    string? HeygenSessionId,
    string? TeamsMeetingId,
    string? TeamsMeetingLink,
    string? OperatorNotes);

internal sealed record LiveQuestionRequest(
    string Question,
    string AgentName = "nathan",
    string ClientId = "ramair",
    string ProjectId = "ramair-straight-from-the-hart",
    string? SpeakerName = null,
    string? ProviderEventId = null,
    string? MeetingId = null);

internal sealed record MeetingNotesRequest(
    string? Title = null,
    string? Summary = null,
    string? Transcript = null,
    string ClientId = "ramair",
    string? ClientName = "RamAir",
    string ProjectId = "ramair-straight-from-the-hart",
    string? ProjectName = null,
    string? TeamId = null,
    string? ChannelId = null,
    string? FolderPath = null);
