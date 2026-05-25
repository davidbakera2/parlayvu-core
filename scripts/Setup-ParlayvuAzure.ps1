<#
.SYNOPSIS
    Idempotent end-to-end setup of ParlayVU's Azure foundation in ParlayVU's
    own tenant. Safe to re-run; reports the final state of everything.

.DESCRIPTION
    Performs Phase 2 of MIGRATION-PLAN.md in one shot:
      1. Detects which Nathan identity is signed in (handles the case where
         multiple Nathan user objects exist in the tenant)
      2. Grants that exact identity Owner on the target subscription if
         not already granted
      3. Forces a token refresh so the new role takes effect
      4. Registers required resource providers
      5. Creates resource group, ACR (admin-enabled), Container Apps environment
      6. Prints a single status block with everything Phase 3+ will need

    Idempotent: skips creation steps for anything that already exists, only
    grants role if missing, exits cleanly if everything is already in place.

.PARAMETER SubscriptionId
    The Azure subscription ID to use. Defaults to the ParlayVU subscription
    (dc976926-046e-4ce8-8659-4dbf602da289).

.PARAMETER ResourceGroup
    Resource group name. Default: rg-parlayvu-prod.

.PARAMETER Location
    Azure region. Default: eastus.

.PARAMETER AcrName
    Preferred ACR name. If taken globally, the script falls back to a list
    of alternatives. Default: parlayvuacr.

.PARAMETER ContainerEnvName
    Container Apps environment name. Default: parlayvu-env.

.EXAMPLE
    .\Setup-ParlayvuAzure.ps1

.EXAMPLE
    .\Setup-ParlayvuAzure.ps1 -AcrName parlayvuagents

.NOTES
    Prerequisite: You must be signed into az CLI as a user with either
    (a) Owner on the subscription already, or
    (b) Global Admin in the tenant + we'll handle elevation.

    The script will tell you which case applies and what (if anything) to fix.
#>
param(
    [string]$SubscriptionId    = "dc976926-046e-4ce8-8659-4dbf602da289",
    [string]$ResourceGroup     = "rg-parlayvu-prod",
    [string]$Location          = "eastus",
    [string]$AcrName           = "parlayvuacr",
    [string]$ContainerEnvName  = "parlayvu-env"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg)   { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Skip($msg)   { Write-Host "[SKIP] $msg" -ForegroundColor DarkGray }
function Write-Fail($msg)   { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Warn($msg)   { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# -- Step 1: Confirm identity ----------------------------------------------
Write-Step "Step 1: Identify signed-in user"
$me = az ad signed-in-user show 2>$null | ConvertFrom-Json
if (-not $me) {
    Write-Fail "Not signed in. Run: az login --tenant <parlayvu-tenant-id>"
    exit 1
}
Write-Host "Signed in as: $($me.displayName)"
Write-Host "UPN:          $($me.userPrincipalName)"
Write-Host "Object ID:    $($me.id)"
$myId  = $me.id
$myUpn = $me.userPrincipalName

# -- Step 2: Confirm subscription access -----------------------------------
Write-Step "Step 2: Verify subscription access"
az account set --subscription $SubscriptionId 2>$null
$current = az account show 2>$null | ConvertFrom-Json
if (-not $current -or $current.id -ne $SubscriptionId) {
    Write-Fail "Cannot set subscription $SubscriptionId. Check you're signed in to the right tenant."
    exit 1
}
Write-Ok "Subscription '$($current.name)' selected"

# -- Step 3: Check & grant Owner if missing --------------------------------
Write-Step "Step 3: Ensure signed-in user has Owner on subscription"
# Query by object ID (avoids UPN aliasing weirdness when multiple users have similar names)
$existingAssignments = az role assignment list `
    --assignee-object-id $myId `
    --assignee-principal-type User `
    --scope "/subscriptions/$SubscriptionId" `
    --query "[?roleDefinitionName=='Owner']" | ConvertFrom-Json

if ($existingAssignments -and $existingAssignments.Count -gt 0) {
    Write-Ok "User $myUpn already has Owner on subscription"
} else {
    Write-Warn "User $myUpn does NOT have Owner. Attempting to grant..."
    try {
        az role assignment create `
            --assignee-object-id $myId `
            --assignee-principal-type User `
            --role "Owner" `
            --scope "/subscriptions/$SubscriptionId" | Out-Null
        Write-Ok "Granted Owner to $myUpn"
        Write-Host ""
        Write-Warn "IMPORTANT: Sign out and sign back in to pick up the new role."
        Write-Warn "Then re-run this script."
        Write-Host ""
        Write-Host "  az logout"
        Write-Host "  az login --tenant $($current.tenantId)"
        Write-Host "  .\scripts\Setup-ParlayvuAzure.ps1"
        exit 0
    } catch {
        Write-Fail "Could not grant Owner: $_"
        Write-Host ""
        Write-Host "If you're Global Admin in the tenant, elevate access first:" -ForegroundColor Yellow
        Write-Host '  az rest --method POST --url "https://management.azure.com/providers/Microsoft.Authorization/elevateAccess?api-version=2016-07-01"'
        Write-Host "  # then re-run this script"
        exit 1
    }
}

# -- Step 4: Register resource providers -----------------------------------
Write-Step "Step 4: Register resource providers"
foreach ($ns in @("Microsoft.App", "Microsoft.ContainerRegistry", "Microsoft.OperationalInsights")) {
    $state = az provider show --namespace $ns --query "registrationState" -o tsv 2>$null
    if ($state -eq "Registered") {
        Write-Skip "$ns already Registered"
    } else {
        Write-Host "Registering $ns (may take ~30 sec)..."
        az provider register --namespace $ns --wait | Out-Null
        Write-Ok "$ns Registered"
    }
}

# -- Step 5: Resource group ------------------------------------------------
Write-Step "Step 5: Resource group $ResourceGroup"
$rg = az group show --name $ResourceGroup 2>$null | ConvertFrom-Json
if ($rg) {
    Write-Skip "Resource group already exists in $($rg.location)"
} else {
    az group create --name $ResourceGroup --location $Location | Out-Null
    Write-Ok "Created in $Location"
}

# -- Step 6: ACR -----------------------------------------------------------
Write-Step "Step 6: Azure Container Registry"
$existingAcr = az acr list --resource-group $ResourceGroup --query "[0]" 2>$null | ConvertFrom-Json
if ($existingAcr) {
    $finalAcrName = $existingAcr.name
    Write-Skip "ACR $finalAcrName already exists"
    if (-not $existingAcr.adminUserEnabled) {
        Write-Host "Enabling admin auth on existing ACR..."
        az acr update --name $finalAcrName --admin-enabled true | Out-Null
        Write-Ok "Admin auth enabled"
    }
} else {
    $finalAcrName = $AcrName
    $available = az acr check-name --name $finalAcrName --query nameAvailable -o tsv
    if ($available -ne "true") {
        Write-Warn "$finalAcrName is taken globally. Trying alternatives..."
        foreach ($alt in @("parlayvuagents","parlayvuprod","parlayvuregistry","parlayvucr2026","parlayvuacr1")) {
            $a = az acr check-name --name $alt --query nameAvailable -o tsv
            if ($a -eq "true") { $finalAcrName = $alt; break }
        }
        if ($finalAcrName -eq $AcrName) {
            Write-Fail "No fallback ACR name was available. Re-run with -AcrName <something-unique>."
            exit 1
        }
    }
    Write-Host "Creating ACR: $finalAcrName"
    az acr create --resource-group $ResourceGroup --name $finalAcrName --sku Basic --admin-enabled true | Out-Null
    Write-Ok "Created $finalAcrName"
}

# Capture ACR creds
$acrCreds = az acr credential show --name $finalAcrName | ConvertFrom-Json
$acrServer = "$finalAcrName.azurecr.io"

# -- Step 7: Container Apps environment ------------------------------------
Write-Step "Step 7: Container Apps environment $ContainerEnvName"
$existingEnv = az containerapp env show --name $ContainerEnvName --resource-group $ResourceGroup 2>$null | ConvertFrom-Json
if ($existingEnv -and $existingEnv.properties.provisioningState -eq "Succeeded") {
    Write-Skip "Environment already exists and is Succeeded"
} else {
    Write-Host "Creating Container Apps environment (this takes ~2-3 min)..."
    az containerapp env create --resource-group $ResourceGroup --name $ContainerEnvName --location $Location | Out-Null
    Write-Ok "Created"
}

# -- Step 8: Final summary -------------------------------------------------
Write-Step "Phase 2 complete - summary"
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Save these values - we'll use them in Phases 3-5" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tenant ID:                $($current.tenantId)"
Write-Host "Subscription ID:          $SubscriptionId"
Write-Host "Resource Group:           $ResourceGroup"
Write-Host "Location:                 $Location"
Write-Host ""
Write-Host "ACR_NAME:                 $finalAcrName"
Write-Host "ACR_LOGIN_SERVER:         $acrServer"
Write-Host "ACR_USERNAME:             $($acrCreds.username)"
Write-Host "ACR_PASSWORD:             $($acrCreds.passwords[0].value)"
Write-Host ""
Write-Host "Container Apps env:       $ContainerEnvName"
Write-Host ""
Write-Host "Signed-in user:           $myUpn"
Write-Host "Signed-in object ID:      $myId"
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Next: Phase 3 - create the ParlayVU Agents app registration." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
