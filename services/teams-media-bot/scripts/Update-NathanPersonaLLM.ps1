<#
.SYNOPSIS
    Configure Nathan's Tavus persona to use the ParlayVU custom LLM endpoint.

.DESCRIPTION
    Updates Nathan's Tavus persona with a custom LLM configuration that points
    to the ParlayVU FastAPI backend. When set, Tavus calls our
    POST /v1/chat/completions endpoint (powered by Claude Opus 4.7 with tools)
    instead of Tavus's built-in model.

    This gives Nathan:
    - Claude Opus 4.7 as his brain (vs Tavus's default LLM)
    - Web search (Tavily)
    - URL fetching (Jina — LinkedIn, company sites, social media)
    - Microsoft Teams file access
    - ParlayVU project context

    What Tavus sends to our endpoint:
    - The conversation history as OpenAI-format messages
    - The persona's system_prompt prepended as a system message
    - Our NATHAN_MEETING_SYSTEM prompt is merged in by our code

.PARAMETER TavusApiKey
    Your Tavus API key (TAVUS_API_KEY).

.PARAMETER PersonaId
    Nathan's Tavus persona ID (TAVUS_PERSONA_ID). Default: p03513c08d91

.PARAMETER ParlayVuApiUrl
    The base URL of the ParlayVU API. Used as the custom_llm base_url.
    Example: https://parlayvu-api.kindsmoke-12345678.eastus.azurecontainerapps.io

.PARAMETER NathanLlmApiKey
    Optional: the value of NATHAN_LLM_API_KEY on the ParlayVU API.
    Tavus will send this as a Bearer token when calling our endpoint.
    Leave empty if NATHAN_LLM_API_KEY is not set on the API.

.PARAMETER DryRun
    Print the PATCH payload without sending it.

.EXAMPLE
    # Dry run to review the payload
    .\Update-NathanPersonaLLM.ps1 `
        -TavusApiKey $env:TAVUS_API_KEY `
        -PersonaId p03513c08d91 `
        -ParlayVuApiUrl https://parlayvu-api.kindsmoke-12345678.eastus.azurecontainerapps.io `
        -DryRun

    # Live update
    .\Update-NathanPersonaLLM.ps1 `
        -TavusApiKey $env:TAVUS_API_KEY `
        -PersonaId p03513c08d91 `
        -ParlayVuApiUrl https://parlayvu-api.kindsmoke-12345678.eastus.azurecontainerapps.io `
        -NathanLlmApiKey $env:NATHAN_LLM_API_KEY
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TavusApiKey,

    [string]$PersonaId = "p03513c08d91",

    [Parameter(Mandatory = $true)]
    [string]$ParlayVuApiUrl,

    [string]$NathanLlmApiKey = "",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$baseUrl = $ParlayVuApiUrl.TrimEnd("/")

# ── Verify the /v1/models endpoint is reachable ───────────────────────────────
if (-not $DryRun) {
    Write-Host "Verifying ParlayVU /v1/models endpoint..." -ForegroundColor Cyan
    try {
        $modelsResp = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/models" -TimeoutSec 15
        Write-Host "  OK — models endpoint reachable. Models: $($modelsResp.data.Count)" -ForegroundColor Green
    } catch {
        Write-Warning "Could not reach $baseUrl/v1/models — $_"
        Write-Warning "Make sure the API is deployed and the URL is correct before updating the persona."
        if (-not ($DryRun)) {
            $confirm = Read-Host "Continue anyway? (y/N)"
            if ($confirm -ne "y") { exit 1 }
        }
    }
}

# ── Check Nathan's LLM status ─────────────────────────────────────────────────
if (-not $DryRun) {
    Write-Host "Checking Nathan LLM status..." -ForegroundColor Cyan
    try {
        $statusResp = Invoke-RestMethod -Method Get -Uri "$baseUrl/nathan/llm/status" -TimeoutSec 15
        Write-Host "  Status: $($statusResp.status)" -ForegroundColor $(if ($statusResp.status -eq "ready") { "Green" } else { "Yellow" })
        Write-Host "  Tools:"
        $statusResp.tools.PSObject.Properties | ForEach-Object {
            $icon = if ($_.Value.configured) { "✓" } else { "⚠" }
            Write-Host "    $icon $($_.Name): $($_.Value.note)" -ForegroundColor $(if ($_.Value.configured) { "Green" } else { "Yellow" })
        }
        if ($statusResp.status -ne "ready") {
            Write-Warning "Nathan LLM is not fully ready. Check ANTHROPIC_API_KEY and TAVILY_API_KEY in Azure."
        }
    } catch {
        Write-Warning "Could not reach $baseUrl/nathan/llm/status — $_"
    }
    Write-Host ""
}

# ── Build the JSON Patch payload ──────────────────────────────────────────────
$customLlmValue = @{
    model_name = "nathan-opus"
    base_url   = $baseUrl
    api_key    = if ($NathanLlmApiKey) { $NathanLlmApiKey } else { "" }
}

$patch = @(
    @{
        op    = "replace"
        path  = "/custom_llm"
        value = $customLlmValue
    }
)

$patchJson = $patch | ConvertTo-Json -Depth 10 -Compress

Write-Host ""
Write-Host "=== Tavus Persona Patch ===" -ForegroundColor Cyan
Write-Host "Persona ID  : $PersonaId"
Write-Host "base_url    : $baseUrl"
Write-Host "model_name  : nathan-opus"
Write-Host "api_key set : $($NathanLlmApiKey -ne '')"
Write-Host ""
Write-Host "Patch payload:"
Write-Host $patchJson
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY RUN] No changes were made." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To apply, run without -DryRun."
    exit 0
}

# ── Apply the patch ───────────────────────────────────────────────────────────
$headers = @{
    "x-api-key"    = $TavusApiKey
    "Content-Type" = "application/json"
}

Write-Host "Applying patch to Tavus persona $PersonaId..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod `
        -Method Patch `
        -Uri "https://tavusapi.com/v2/personas/$PersonaId" `
        -Headers $headers `
        -Body $patchJson `
        -ContentType "application/json"

    Write-Host "SUCCESS — Persona updated." -ForegroundColor Green
    Write-Host "Updated at: $($response.updated_at)"
    Write-Host ""
    Write-Host "Nathan's next Tavus conversation will use:" -ForegroundColor Cyan
    Write-Host "  POST $baseUrl/v1/chat/completions"
    Write-Host "  Model: Claude Opus 4.7 with web search, URL fetch, Teams files, project context"

} catch {
    Write-Error "Patch failed: $_"
    Write-Host ""
    Write-Host "If the error is 'path not found' or similar, Tavus may not support" -ForegroundColor Yellow
    Write-Host "/custom_llm at the root level. Try the /llm path instead:" -ForegroundColor Yellow
    Write-Host ""

    $altPatch = @(@{ op = "replace"; path = "/llm"; value = $customLlmValue }) | ConvertTo-Json -Depth 10 -Compress
    Write-Host "Alt payload: $altPatch"
    Write-Host ""
    Write-Host "Or check the latest Tavus persona API docs at https://docs.tavus.io"
}
