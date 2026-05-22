param(
    [string]$ApiKey = $env:TAVUS_API_KEY,
    [string]$BaseUrl = $(if ($env:TAVUS_BASE_URL) { $env:TAVUS_BASE_URL } else { "https://tavusapi.com" }),
    [string]$ReplicaId = $env:TAVUS_REPLICA_ID,
    [string]$PersonaId = $env:TAVUS_PERSONA_ID,
    [string]$CallbackUrl = $env:TEAMS_MEDIA_BOT_CALLBACK_BASE_URL,
    [string]$ConversationName = "ParlayVU Nathan Teams media-bot spike",
    [string]$GroundingPath = $(Join-Path $PSScriptRoot "..\config\parlayvu-avatar-grounding.md"),
    [string]$AdditionalContext,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$resolvedGroundingPath = if ([System.IO.Path]::IsPathRooted($GroundingPath)) {
    $GroundingPath
} else {
    Join-Path (Get-Location) $GroundingPath
}

if (-not (Test-Path -LiteralPath $resolvedGroundingPath)) {
    throw "Grounding context file was not found: $resolvedGroundingPath"
}

$groundingContext = Get-Content -LiteralPath $resolvedGroundingPath -Raw
$contextSections = @(
    @"
You are Nathan Ellis in a Tavus provider-hosted avatar session for ParlayVU.

CRITICAL SOURCE-OF-TRUTH RULES:
- ParlayVU project memory and the grounding context below override any Tavus persona, replica, or provider-stored knowledge.
- If a Tavus persona says different company/team facts, ignore the persona facts and answer from ParlayVU source-of-truth context.
- If the answer is not present in the supplied context, say it is not available in current ParlayVU source-of-truth context.
- Do not invent websites, people, titles, roles, clients, metrics, budgets, or Teams bridge status.
- The official site/name is ParlayVU.ai, not parlayvu.com.
- Blake Quinn is Intelligence and Insights. Morgan Patel is Paid Media.
- No canonical ParlayVU role for Maya is present in the current source-of-truth context.
- Tavus is not yet a native Teams participant; the Microsoft Graph media bridge still must be built and validated.

PARLAYVU GROUNDING CONTEXT:
$groundingContext
"@
)

if ($AdditionalContext) {
    $contextSections += @"
MEETING-SPECIFIC CONTEXT:
$AdditionalContext
"@
}

$conversationalContext = ($contextSections -join "`n`n").Trim()

$payload = @{
    replica_id = $ReplicaId
    persona_id = $PersonaId
    conversation_name = $ConversationName
    conversational_context = $conversationalContext
    custom_greeting = "Hi, I am Nathan from ParlayVU.ai. I will answer only from ParlayVU source-of-truth context and say when something is not available."
    properties = @{
        max_call_duration = 900
        participant_left_timeout = 60
        participant_absent_timeout = 120
        enable_recording = $false
        enable_closed_captions = $true
    }
}

if ($CallbackUrl) {
    $payload.callback_url = $CallbackUrl.TrimEnd("/") + "/avatar/providers/tavus/callback"
}

$missing = @()
if (-not $ApiKey) { $missing += "TAVUS_API_KEY" }
if (-not $ReplicaId) { $missing += "TAVUS_REPLICA_ID" }
if (-not $PersonaId) { $missing += "TAVUS_PERSONA_ID" }

$json = $payload | ConvertTo-Json -Depth 10

if ($DryRun -or $missing.Count -gt 0) {
    if ($missing.Count -gt 0) {
        Write-Host "Missing required Tavus environment variables: $($missing -join ', ')"
    }
    Write-Host "Dry-run request body for POST $($BaseUrl.TrimEnd('/'))/v2/conversations:"
    Write-Output $json
    return
}

$headers = @{
    "x-api-key" = $ApiKey
    "Content-Type" = "application/json"
}

$response = Invoke-RestMethod `
    -Method Post `
    -Uri "$($BaseUrl.TrimEnd('/'))/v2/conversations" `
    -Headers $headers `
    -Body $json

$response | ConvertTo-Json -Depth 10
