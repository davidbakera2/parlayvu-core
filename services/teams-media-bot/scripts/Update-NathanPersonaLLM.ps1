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
    - URL fetching (Jina - LinkedIn, company sites, social media)
    - Microsoft Teams file access
    - ParlayVU project context

    What Tavus sends to our endpoint:
    - The conversation history as OpenAI-format messages
    - The persona's system_prompt prepended as a system message
    - Our NATHAN_MEETING_SYSTEM prompt is merged in by our code

.PARAMETER TavusApiKey
    Your Tavus API key (TAVUS_API_KEY).

.PARAMETER PersonaId
    The Tavus persona ID to update. ParlayVU runs one persona per client
    (e.g. p03513c08d91 = RamAir's Nathan). Create a new persona in the
    Tavus UI for each additional client and pass its ID here.

.PARAMETER ClientId
    The ParlayVU client_id this persona represents (e.g. "ramair",
    "christshope"). The script injects an X-Parlayvu-Client-Id header into
    the persona's custom-LLM config; our /v1/chat/completions endpoint reads
    that header to load the right client_artifacts/<client_id>/config.yaml.

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
    # Dry run to review the payload (RamAir's Nathan persona)
    .\Update-NathanPersonaLLM.ps1 `
        -TavusApiKey $env:TAVUS_API_KEY `
        -PersonaId p03513c08d91 `
        -ClientId ramair `
        -ParlayVuApiUrl https://parlayvu-api.kindsmoke-12345678.eastus.azurecontainerapps.io `
        -DryRun

    # Live update for Christ's Hope (use the new persona ID created in Tavus UI)
    .\Update-NathanPersonaLLM.ps1 `
        -TavusApiKey $env:TAVUS_API_KEY `
        -PersonaId <ch-persona-id> `
        -ClientId christshope `
        -ParlayVuApiUrl https://parlayvu-api.kindsmoke-12345678.eastus.azurecontainerapps.io `
        -NathanLlmApiKey $env:NATHAN_LLM_API_KEY
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TavusApiKey,

    [Parameter(Mandatory = $true)]
    [string]$PersonaId,

    [Parameter(Mandatory = $true)]
    [string]$ClientId,

    [Parameter(Mandatory = $true)]
    [string]$ParlayVuApiUrl,

    [string]$NathanLlmApiKey = "",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$baseUrl = $ParlayVuApiUrl.TrimEnd("/")

# -- Verify the /v1/models endpoint is reachable -------------------------------
if (-not $DryRun) {
    Write-Host "Verifying ParlayVU /v1/models endpoint..." -ForegroundColor Cyan
    try {
        $modelsResp = Invoke-RestMethod -Method Get -Uri "$baseUrl/v1/models" -TimeoutSec 15
        Write-Host "  OK - models endpoint reachable. Models: $($modelsResp.data.Count)" -ForegroundColor Green
    } catch {
        Write-Warning "Could not reach $baseUrl/v1/models - $_"
        Write-Warning "Make sure the API is deployed and the URL is correct before updating the persona."
        $confirm = Read-Host "Continue anyway? (y/N)"
        if ($confirm -ne "y") { exit 1 }
    }
}

# -- Check Nathan's LLM status -------------------------------------------------
if (-not $DryRun) {
    Write-Host "Checking Nathan LLM status..." -ForegroundColor Cyan
    try {
        $statusResp = Invoke-RestMethod -Method Get -Uri "$baseUrl/nathan/llm/status" -TimeoutSec 15
        Write-Host "  Status: $($statusResp.status)" -ForegroundColor $(if ($statusResp.status -eq "ready") { "Green" } else { "Yellow" })
        Write-Host "  Tools:"
        $statusResp.tools.PSObject.Properties | ForEach-Object {
            $icon = if ($_.Value.configured) { "[OK]" } else { "[!] " }
            Write-Host "    $icon $($_.Name): $($_.Value.note)" -ForegroundColor $(if ($_.Value.configured) { "Green" } else { "Yellow" })
        }
        if ($statusResp.status -ne "ready") {
            Write-Warning "Nathan LLM is not fully ready. Check ANTHROPIC_API_KEY and TAVILY_API_KEY in Azure."
        }
    } catch {
        Write-Warning "Could not reach $baseUrl/nathan/llm/status - $_"
    }
    Write-Host ""
}

# -- Build the JSON Patch payload ----------------------------------------------
# Tavus persona schema (as of 2025) uses a `layers` object with `llm`,
# `tts`, and `conversational_flow` children. Custom LLM config lives at
# /layers/llm with fields `model`, `base_url`, `api_key`. The legacy
# top-level `custom_llm` field is not part of the current schema.
#
# RFC 6902 JSON Patch requires a top-level ARRAY of operations. Windows
# PowerShell 5.1's ConvertTo-Json unwraps single-element arrays into objects,
# which Tavus rejects. Build the operation as an object, serialize it, then
# wrap with square brackets so the wire format is always [{...}].

$llmLayerValue = [ordered]@{
    model    = "nathan-opus"
    # Tavus's custom LLM client follows the OpenAI convention: it appends
    # /chat/completions to the configured base_url. We host our routes under
    # /v1/, so the base_url must include that prefix or Tavus hits a 404.
    base_url = "$baseUrl/v1"
    api_key  = if ($NathanLlmApiKey) { $NathanLlmApiKey } else { "" }
    # Per-client binding: the ParlayVU API reads X-Parlayvu-Client-Id to
    # choose which client_artifacts/<id>/config.yaml drives meeting-note
    # publishing, pronunciation, and tone.
    headers  = [ordered]@{
        "X-Parlayvu-Client-Id" = $ClientId
    }
}

$operation = [ordered]@{
    # "add" is idempotent on object properties: creates if missing, replaces
    # if present. Required for first-time setup where /layers/llm doesn't exist.
    op    = "add"
    path  = "/layers/llm"
    value = $llmLayerValue
}

$operationJson = $operation | ConvertTo-Json -Depth 10 -Compress
$patchJson = "[$operationJson]"

Write-Host ""
Write-Host "=== Tavus Persona Patch ===" -ForegroundColor Cyan
Write-Host "Persona ID  : $PersonaId"
Write-Host "Client ID   : $ClientId"
Write-Host "path        : /layers/llm"
Write-Host "model       : nathan-opus"
Write-Host "base_url    : $baseUrl"
Write-Host "api_key set : $($NathanLlmApiKey -ne '')"
Write-Host "headers     : X-Parlayvu-Client-Id=$ClientId"
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

# -- Apply the patch -----------------------------------------------------------
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

    Write-Host "SUCCESS - Persona updated." -ForegroundColor Green
    Write-Host "Updated at: $($response.updated_at)"
    Write-Host ""
    Write-Host "Nathan's next Tavus conversation will use:" -ForegroundColor Cyan
    Write-Host "  POST $baseUrl/v1/chat/completions"
    Write-Host "  Model: Claude Opus 4.7 with web search, URL fetch, Teams files, project context"

} catch {
    Write-Error "Patch failed: $_"
    Write-Host ""
    Write-Host "If the error mentions path not found, Tavus may not support" -ForegroundColor Yellow
    Write-Host "/custom_llm at the root level. Try the /llm path instead:" -ForegroundColor Yellow
    Write-Host ""

    $altPatch = @(@{ op = "replace"; path = "/llm"; value = $customLlmValue }) | ConvertTo-Json -Depth 10 -Compress
    Write-Host "Alt payload: $altPatch"
    Write-Host ""
    Write-Host "Or check the latest Tavus persona API docs at https://docs.tavus.io"
}
