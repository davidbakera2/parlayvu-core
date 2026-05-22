param(
    [string]$BotBaseUrl = "http://127.0.0.1:5000",
    [Parameter(Mandatory = $true)]
    [string]$JoinMeetingUrl,
    [string]$TeamsMeetingId = "",
    [string]$MeetingTitle = "RamAir Teams call",
    [string]$AgentName = "nathan",
    [string]$ClientId = "ramair",
    [string]$ProjectId = "ramair-straight-from-the-hart",
    [string]$ChatThreadId = "",
    [string]$ChatMessageId = "0",
    [string]$OrganizerUserId = "",
    [string]$OrganizerDisplayName = "",
    [string]$OrganizerTenantId = "",
    [string]$TenantId = "",
    [string]$CallbackUri = "",
    [switch]$AttemptGraphJoin,
    [switch]$SkipParlayVuRegistration,
    [switch]$PreviewOnly
)

$ErrorActionPreference = "Stop"

$payload = [ordered]@{
    meetingJoinUrl = $JoinMeetingUrl
    teamsMeetingId = if ($TeamsMeetingId) { $TeamsMeetingId } else { $null }
    meetingTitle = $MeetingTitle
    agentName = $AgentName
    clientId = $ClientId
    projectId = $ProjectId
    registerWithParlayVu = -not $SkipParlayVuRegistration.IsPresent
    attemptGraphJoin = $AttemptGraphJoin.IsPresent
    chatThreadId = if ($ChatThreadId) { $ChatThreadId } else { $null }
    chatMessageId = if ($ChatMessageId) { $ChatMessageId } else { "0" }
    organizerUserId = if ($OrganizerUserId) { $OrganizerUserId } else { $null }
    organizerDisplayName = if ($OrganizerDisplayName) { $OrganizerDisplayName } else { $null }
    organizerTenantId = if ($OrganizerTenantId) { $OrganizerTenantId } else { $null }
    tenantId = if ($TenantId) { $TenantId } else { $null }
    callbackUri = if ($CallbackUri) { $CallbackUri } else { $null }
    requestedModalities = @("audio")
    allowConversationWithoutHost = $true
}

$endpoint = if ($PreviewOnly) { "/meetings/join/graph-request-preview" } else { "/meetings/join" }
$uri = "$($BotBaseUrl.TrimEnd('/'))$endpoint"

$payload | ConvertTo-Json -Depth 10 | Write-Host
Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 10)
