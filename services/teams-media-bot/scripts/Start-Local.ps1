param(
    [string]$ParlayVuBaseUrl = "http://127.0.0.1:8000",
    [string]$ParlayVuApiKey = "",
    [string]$TenantId = "",
    [string]$AppId = "",
    [string]$AppSecret = "",
    [string]$CallbackBaseUrl = "",
    [switch]$EnableGraphJoin
)

$ErrorActionPreference = "Stop"
$env:PARLAYVU_BASE_URL = $ParlayVuBaseUrl
if ($ParlayVuApiKey) { $env:PARLAYVU_API_KEY = $ParlayVuApiKey }
if ($TenantId) { $env:TEAMS_MEDIA_BOT_TENANT_ID = $TenantId }
if ($AppId) { $env:TEAMS_MEDIA_BOT_APP_ID = $AppId }
if ($AppSecret) { $env:TEAMS_MEDIA_BOT_APP_SECRET = $AppSecret }
if ($CallbackBaseUrl) { $env:TEAMS_MEDIA_BOT_CALLBACK_BASE_URL = $CallbackBaseUrl }
$env:TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED = $EnableGraphJoin.IsPresent.ToString().ToLowerInvariant()

dotnet run --project "$PSScriptRoot\..\src\ParlayVu.TeamsMediaBot\ParlayVu.TeamsMediaBot.csproj"
