<#
.SYNOPSIS
    Idempotent creation of the Azure Bot Service resource that wraps the
    ParlayVU Teams bot AAD app and enables the Microsoft Teams channel.

.DESCRIPTION
    The original Baker Strategy → ParlayVU tenant migration (MIGRATION-PLAN.md
    Phases 1–5) carried over the AAD app registration (TEAMS_APP_ID) but did
    not recreate the Azure Bot Service resource. Without that resource, the
    Teams app manifest upload fails with "Invalid bot" because Microsoft has
    no record of a bot with this app ID in the ParlayVU tenant.

    This script:
      1. Ensures the Microsoft.BotService resource provider is registered
      2. Creates a registration-only Azure Bot resource named parlayvu-bot
         in rg-parlayvu-prod that uses the existing AAD app as its identity
      3. Sets the messaging endpoint to the production Container App's
         /teams/messages route
      4. Enables the Microsoft Teams channel on the bot

    Safe to re-run: skips creation if the bot already exists; verifies channel
    state at the end. Run after Setup-ParlayvuAzure.ps1, before uploading the
    Teams app manifest via Teams Admin Center.

.PARAMETER ResourceGroup
    Resource group name. Default: rg-parlayvu-prod.

.PARAMETER BotName
    Bot Service resource name. Default: parlayvu-bot.

.PARAMETER TeamsAppId
    The AAD app ID that the bot authenticates as. This MUST match the
    TEAMS_APP_ID env var on the parlayvu-api Container App and the `id`
    field in infra/teams-app/manifest.json.

.PARAMETER TenantId
    Entra tenant ID. Default: ParlayVU tenant.

.PARAMETER MessagingEndpoint
    Public URL Microsoft Teams will POST activities to. Default: the live
    parlayvu-api Container App's /teams/messages route.

.PARAMETER AppType
    "SingleTenant" or "MultiTenant". Default: SingleTenant. If the AAD app
    was created as multi-tenant, this must be MultiTenant or `az bot create`
    will reject the registration.

.EXAMPLE
    .\Setup-ParlayvuBot.ps1

.EXAMPLE
    .\Setup-ParlayvuBot.ps1 -AppType MultiTenant

.NOTES
    Prerequisite: az CLI signed in as a user with Contributor (or higher)
    on the target subscription. The Microsoft.BotService resource provider
    auto-registers on first use (~30s).
#>
param(
    [string]$ResourceGroup     = "rg-parlayvu-prod",
    [string]$BotName           = "parlayvu-bot",
    [string]$TeamsAppId        = "2dc8aa66-9c5b-4ff5-9151-48408f1f6554",
    [string]$TenantId          = "45b63749-ebe1-48fa-928c-963050843179",
    [string]$MessagingEndpoint = "https://parlayvu-api.thankfulriver-96fed9c6.eastus.azurecontainerapps.io/teams/messages",
    [ValidateSet("SingleTenant", "MultiTenant")]
    [string]$AppType           = "SingleTenant",
    [string]$Sku               = "F0"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Write-Ok($msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Info($msg) {
    Write-Host "    $msg" -ForegroundColor Gray
}

# -- 1. Register the resource provider (idempotent) ----------------------------
Write-Step "Ensure Microsoft.BotService provider is registered"
$state = az provider show --namespace Microsoft.BotService --query registrationState -o tsv 2>$null
if ($state -eq "Registered") {
    Write-Ok "Already registered"
} else {
    Write-Info "Provider state: $state - registering..."
    az provider register --namespace Microsoft.BotService | Out-Null
    # Poll until registered (usually ~30s)
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        $state = az provider show --namespace Microsoft.BotService --query registrationState -o tsv 2>$null
        if ($state -eq "Registered") {
            Write-Ok "Registered"
            break
        }
        Write-Info "Still $state..."
    }
    if ($state -ne "Registered") {
        throw "Microsoft.BotService provider failed to register within 3 minutes."
    }
}

# -- 2. Create the bot resource (idempotent) -----------------------------------
Write-Step "Ensure Bot Service resource '$BotName' exists in $ResourceGroup"
$existing = az bot show --resource-group $ResourceGroup --name $BotName 2>$null
if ($LASTEXITCODE -eq 0 -and $existing) {
    $existingAppId = az bot show --resource-group $ResourceGroup --name $BotName --query "properties.msaAppId" -o tsv
    if ($existingAppId -eq $TeamsAppId) {
        Write-Ok "Bot already exists with matching AAD app ID"
    } else {
        Write-Host "    [WARN] Bot $BotName exists but msaAppId=$existingAppId does not match expected $TeamsAppId" -ForegroundColor Yellow
        Write-Host "           Either rename your bot, or use the existing app ID in the Teams manifest." -ForegroundColor Yellow
    }
} else {
    Write-Info "Creating bot..."
    az bot create `
        --resource-group $ResourceGroup `
        --name $BotName `
        --app-type $AppType `
        --appid $TeamsAppId `
        --tenant-id $TenantId `
        --endpoint $MessagingEndpoint `
        --sku $Sku | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "az bot create failed. If the error mentions 'app type', try re-running with -AppType MultiTenant."
    }
    Write-Ok "Bot created"
}

# -- 3. Ensure the messaging endpoint matches what we expect -------------------
Write-Step "Verify messaging endpoint"
$currentEndpoint = az bot show --resource-group $ResourceGroup --name $BotName --query "properties.endpoint" -o tsv
if ($currentEndpoint -eq $MessagingEndpoint) {
    Write-Ok $currentEndpoint
} else {
    Write-Info "Current: $currentEndpoint"
    Write-Info "Expected: $MessagingEndpoint"
    Write-Info "Updating..."
    az bot update --resource-group $ResourceGroup --name $BotName --endpoint $MessagingEndpoint | Out-Null
    Write-Ok "Updated"
}

# -- 4. Enable the Microsoft Teams channel (idempotent) ------------------------
Write-Step "Ensure Microsoft Teams channel is enabled"
$channelState = az bot msteams show --resource-group $ResourceGroup --name $BotName --query "properties.properties.isEnabled" -o tsv 2>$null
if ($channelState -eq "true") {
    Write-Ok "Teams channel already enabled"
} else {
    Write-Info "Enabling Teams channel..."
    az bot msteams create --resource-group $ResourceGroup --name $BotName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "az bot msteams create failed."
    }
    Write-Ok "Teams channel enabled"
}

# -- 5. Final state report -----------------------------------------------------
Write-Step "Final state"
$bot = az bot show --resource-group $ResourceGroup --name $BotName | ConvertFrom-Json
$teamsChannel = az bot msteams show --resource-group $ResourceGroup --name $BotName | ConvertFrom-Json

Write-Host ""
Write-Host "=== ParlayVU Bot Setup Complete ===" -ForegroundColor Cyan
Write-Host "  Resource group  : $($bot.resourceGroup)"
Write-Host "  Bot name        : $($bot.name)"
Write-Host "  Bot ID (msaApp) : $($bot.properties.msaAppId)"
Write-Host "  Endpoint        : $($bot.properties.endpoint)"
Write-Host "  Teams channel   : enabled = $($teamsChannel.properties.properties.isEnabled), state = $($teamsChannel.properties.provisioningState)"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. python infra/teams-app/build_app_package.py   # rebuild the zip"
Write-Host "  2. Upload infra/teams-app/parlayvu-teams-app.zip via https://admin.teams.microsoft.com -> Teams apps -> Manage apps"
Write-Host "  3. Install in target team(s): ... menu -> Manage team -> Apps -> Add -> ParlayVU"
Write-Host "  4. Test: in a channel of that team, post '@ParlayVU what's the status?'"
