<#
.SYNOPSIS
    Phase 4 of MIGRATION-PLAN.md - build the parlayvu-api image, push to
    parlayvuacr, and create the Container App in ParlayVU's subscription.

.DESCRIPTION
    End-to-end:
      1. Verify Azure context (signed in, ACR + env exist)
      2. Build the Docker image inside ACR (no Docker Desktop needed)
      3. Parse .env file to construct the env-var list
      4. Override MICROSOFT_* with the new ParlayVU values from Phase 3
      5. Generate a fresh NATHAN_LLM_API_KEY for the new deployment
      6. Create (or update) the parlayvu-api Container App with:
         - The freshly-built image
         - ACR registry credentials
         - All ~30 env vars from .env + overrides
      7. Output the new FQDN and the new NATHAN_LLM_API_KEY value

    After this script:
      - The new parlayvu-api should respond at the printed FQDN
      - GET /readiness should return status: ready
      - Phase 5 wires up CI/CD against the new infra
      - Phase 6 updates Tavus to point at the new FQDN + new bearer token

.PARAMETER MicrosoftTenantId
    The ParlayVU Entra tenant ID. From Phase 3 output.

.PARAMETER MicrosoftClientId
    The ParlayVU Agents app ID. From Phase 3 output.

.PARAMETER MicrosoftClientSecret
    The fresh client secret from Phase 3. Will be set on the container app
    but NOT logged.

.PARAMETER NathanLlmApiKey
    Optional. Bearer token Tavus sends to our /v1/chat/completions. If
    omitted, a new 48-char random token is generated and printed at the
    end so you can paste it into Tavus in Phase 6.

.PARAMETER EnvFile
    Path to the .env file. Default: .env in the repo root.

.PARAMETER ImageTag
    Image tag for this deployment. Default: "phase4-<timestamp>".

.EXAMPLE
    .\Setup-ParlayvuContainerApp.ps1 `
        -MicrosoftTenantId "45b63749-ebe1-48fa-928c-963050843179" `
        -MicrosoftClientId "c659cd27-5b3f-4a1a-8a85-655c7465c6a9" `
        -MicrosoftClientSecret "<paste secret here>"
#>
param(
    [Parameter(Mandatory=$true)][string]$MicrosoftTenantId,
    [Parameter(Mandatory=$true)][string]$MicrosoftClientId,
    [Parameter(Mandatory=$true)][string]$MicrosoftClientSecret,
    [string]$NathanLlmApiKey   = "",
    [string]$ResourceGroup     = "rg-parlayvu-prod",
    [string]$AcrName           = "parlayvuacr",
    [string]$ContainerEnvName  = "parlayvu-env",
    [string]$ContainerAppName  = "parlayvu-api",
    [string]$EnvFile           = ".env",
    [string]$ImageTag          = "phase4-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
)

$ErrorActionPreference = "Stop"
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "true"

function Write-Step($msg)   { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Skip($msg)   { Write-Host "[SKIP] $msg" -ForegroundColor DarkGray }
function Write-Fail($msg)   { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Warn($msg)   { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# -- Step 1: Sanity checks -------------------------------------------------
Write-Step "Step 1: Verify Azure context"
$me = az ad signed-in-user show | ConvertFrom-Json
$current = az account show | ConvertFrom-Json
Write-Host "Signed in as:  $($me.userPrincipalName)"
Write-Host "Subscription:  $($current.name) ($($current.id))"
Write-Host "Tenant:        $($current.tenantId)"

if ($current.tenantId -ne $MicrosoftTenantId) {
    Write-Fail "Signed-in tenant ($($current.tenantId)) does not match -MicrosoftTenantId ($MicrosoftTenantId)."
    Write-Host "Run: az logout; az login --tenant $MicrosoftTenantId"
    exit 1
}

$rgExists = (az group exists --name $ResourceGroup) -eq "true"
if (-not $rgExists) {
    Write-Fail "Resource group $ResourceGroup not found. Run Setup-ParlayvuAzure.ps1 first."
    exit 1
}
Write-Ok "Resource group $ResourceGroup found"

$acrJson = az acr show --name $AcrName --resource-group $ResourceGroup -o json
$acr = $acrJson | ConvertFrom-Json
if (-not $acr) {
    Write-Fail "ACR $AcrName not found in $ResourceGroup. Run Setup-ParlayvuAzure.ps1 first."
    exit 1
}
$acrLoginServer = $acr.loginServer
Write-Ok "ACR $AcrName ($acrLoginServer) found"

$envExists = az containerapp env list --resource-group $ResourceGroup --query "[?name=='$ContainerEnvName']" -o json | ConvertFrom-Json
if (-not $envExists -or $envExists.Count -eq 0) {
    Write-Fail "Container Apps environment $ContainerEnvName not found. Run Setup-ParlayvuAzure.ps1 first."
    exit 1
}
Write-Ok "Container Apps env $ContainerEnvName found"

# -- Step 2: Build image inside ACR ---------------------------------------
Write-Step "Step 2: Build image $($AcrName):$ImageTag inside ACR"
$dockerfilePath = Join-Path (Get-Location) "Dockerfile"
if (-not (Test-Path $dockerfilePath)) {
    Write-Fail "Dockerfile not found at $dockerfilePath. Run this from the repo root."
    exit 1
}

Write-Host "Submitting build to ACR (this is a server-side build, no Docker needed locally)..."
Write-Host "Build typically takes 3-5 min. Streaming output below..."
Write-Host ""
az acr build `
    --registry $AcrName `
    --image "parlayvu-api:${ImageTag}" `
    --image "parlayvu-api:latest" `
    --file Dockerfile `
    .
if ($LASTEXITCODE -ne 0) {
    Write-Fail "az acr build failed. Check the output above."
    Write-Host ""
    Write-Host "If you see 'TasksOperationsNotAllowed', this ACR tier doesn't support" -ForegroundColor Yellow
    Write-Host "server-side builds. Fall back to local Docker:" -ForegroundColor Yellow
    Write-Host "  az acr login --name $AcrName"
    Write-Host "  docker build -t $acrLoginServer/parlayvu-api:$ImageTag -t $acrLoginServer/parlayvu-api:latest ."
    Write-Host "  docker push $acrLoginServer/parlayvu-api:$ImageTag"
    Write-Host "  docker push $acrLoginServer/parlayvu-api:latest"
    exit 1
}
Write-Ok "Image built and pushed: $acrLoginServer/parlayvu-api:$ImageTag"

# -- Step 3: Parse .env file ----------------------------------------------
Write-Step "Step 3: Read environment variables from $EnvFile"
if (-not (Test-Path $EnvFile)) {
    Write-Fail ".env file not found at $EnvFile."
    exit 1
}

$envVars = @{}
foreach ($line in Get-Content $EnvFile) {
    $trimmed = $line.Trim()
    if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
    $eqIdx = $trimmed.IndexOf("=")
    if ($eqIdx -lt 1) { continue }
    $key = $trimmed.Substring(0, $eqIdx).Trim()
    $value = $trimmed.Substring($eqIdx + 1).Trim()
    # Strip surrounding quotes if present
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    $envVars[$key] = $value
}
Write-Ok "Parsed $($envVars.Count) variables from .env"

# -- Step 4: Apply Phase 3 overrides + generate Nathan key ---------------
Write-Step "Step 4: Override Microsoft creds + generate Nathan LLM API key"
$envVars["MICROSOFT_TENANT_ID"]      = $MicrosoftTenantId
$envVars["MICROSOFT_CLIENT_ID"]      = $MicrosoftClientId
$envVars["MICROSOFT_CLIENT_SECRET"]  = $MicrosoftClientSecret
$envVars["TEAMS_TENANT_ID"]          = $MicrosoftTenantId   # same tenant
Write-Ok "MICROSOFT_* + TEAMS_TENANT_ID set to new ParlayVU values"

if ([string]::IsNullOrWhiteSpace($NathanLlmApiKey)) {
    $NathanLlmApiKey = -join ((1..48) | ForEach-Object { [char]((48..57 + 65..90 + 97..122) | Get-Random) })
    Write-Ok "Generated new NATHAN_LLM_API_KEY (will be printed at the end)"
} else {
    Write-Ok "Using NATHAN_LLM_API_KEY supplied via parameter"
}
$envVars["NATHAN_LLM_API_KEY"] = $NathanLlmApiKey
$envVars["ENVIRONMENT"] = "production"
$envVars["PROJECT_MEMORY_ENABLED"] = "true"
$envVars["MICROSOFT_GRAPH_ALLOW_SEND"] = "false"

# Drop env vars that don't belong on the Container App (CI/local-only)
$exclude = @(
    "AZURE_CLIENT_ID","AZURE_CLIENT_SECRET","AZURE_TENANT_ID","AZURE_SUBSCRIPTION_ID",
    "ACR_USERNAME","ACR_PASSWORD","ACR_NAME"
)
foreach ($k in $exclude) { if ($envVars.ContainsKey($k)) { $envVars.Remove($k) | Out-Null } }

# -- Step 5: Construct env-var args ---------------------------------------
Write-Step "Step 5: Compose --env-vars argument list ($($envVars.Count) vars)"
$envArgs = @()
foreach ($k in $envVars.Keys | Sort-Object) {
    $v = $envVars[$k]
    if ([string]::IsNullOrEmpty($v)) { continue }
    $envArgs += "$k=$v"
}
Write-Ok "$($envArgs.Count) env vars will be set on the container app"

# -- Step 6: Get ACR creds for the container app to pull --------------
$acrCreds = az acr credential show --name $AcrName | ConvertFrom-Json
$acrUser = $acrCreds.username
$acrPass = $acrCreds.passwords[0].value

# -- Step 7: Create or update the container app ---------------------------
Write-Step "Step 7: Create or update Container App $ContainerAppName"
$existing = az containerapp list --resource-group $ResourceGroup --query "[?name=='$ContainerAppName']" -o json | ConvertFrom-Json
if ($existing -and $existing.Count -gt 0) {
    Write-Host "App already exists - updating with new image + env vars..."
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --image "$acrLoginServer/parlayvu-api:$ImageTag" `
        --set-env-vars @envArgs | Out-Null
    Write-Ok "Container App updated"
} else {
    Write-Host "Creating new Container App (this takes ~1-2 min)..."
    az containerapp create `
        --resource-group $ResourceGroup `
        --name $ContainerAppName `
        --environment $ContainerEnvName `
        --image "$acrLoginServer/parlayvu-api:$ImageTag" `
        --target-port 8000 `
        --ingress external `
        --transport auto `
        --registry-server $acrLoginServer `
        --registry-username $acrUser `
        --registry-password $acrPass `
        --min-replicas 1 `
        --max-replicas 3 `
        --cpu 0.5 `
        --memory 1Gi `
        --env-vars @envArgs | Out-Null
    Write-Ok "Container App created"
}

# -- Step 8: Get the new FQDN ---------------------------------------------
$fqdn = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv
$revName = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "properties.latestRevisionName" -o tsv

# -- Step 9: Summary -------------------------------------------------------
Write-Step "Phase 4 complete - summary"
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Save these values - Phase 5 (CI) and Phase 6 (Tavus) need them" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Container App:            $ContainerAppName"
Write-Host "Resource group:           $ResourceGroup"
Write-Host "Latest revision:          $revName"
Write-Host "Image:                    $acrLoginServer/parlayvu-api:$ImageTag"
Write-Host ""
Write-Host "API base URL:             https://$fqdn"
Write-Host "Tavus base_url:           https://$fqdn/v1"
Write-Host "Readiness check:          https://$fqdn/readiness"
Write-Host "Nathan LLM status:        https://$fqdn/nathan/llm/status"
Write-Host ""
Write-Host "NATHAN_LLM_API_KEY (Phase 6): $NathanLlmApiKey"
Write-Host ""
Write-Warn "Copy the NATHAN_LLM_API_KEY above NOW - it's only printed once."
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Verify the new app is healthy:" -ForegroundColor Green
Write-Host "  Invoke-RestMethod ""https://$fqdn/readiness"" | ConvertTo-Json -Depth 5"
Write-Host ""
Write-Host "Then Phase 5 - update CI to deploy to the new infra." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
