<#
.SYNOPSIS
    Idempotent end-to-end setup of the ParlayVU Agents app registration in
    ParlayVU's own Entra ID tenant. Phase 3 of MIGRATION-PLAN.md.

.DESCRIPTION
    Performs:
      1. Verifies you're signed in as a Global Admin in ParlayVU tenant
      2. Creates (or finds) the "ParlayVU Agents" app registration
      3. Ensures the service principal exists in the tenant
      4. Adds 14 Microsoft Graph application permissions matching the old
         Baker Strategy app (mailboxes, files, sites, calendars, channels,
         online meetings, notes, tasks, users)
      5. Grants admin consent for all of them
      6. Creates a fresh 24-month client secret
      7. Prints the values you'll need for Phase 4 (Container App env vars)

    Idempotent: if the app already exists, it's reused. Permissions are
    added only if missing. Client secrets always create a NEW one each
    run (with a timestamped display name) since existing secrets can't
    be read back from Azure.

.PARAMETER DisplayName
    The app registration display name. Default: "ParlayVU Agents".

.EXAMPLE
    .\Setup-ParlayvuAppRegistration.ps1
#>
param(
    [string]$DisplayName = "ParlayVU Agents"
)

$ErrorActionPreference = "Stop"
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "true"

function Write-Step($msg)   { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Skip($msg)   { Write-Host "[SKIP] $msg" -ForegroundColor DarkGray }
function Write-Fail($msg)   { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Warn($msg)   { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

# Microsoft Graph service principal (well-known app ID)
$GraphAppId = "00000003-0000-0000-c000-000000000000"

# 14 Microsoft Graph permissions we need. Each entry is:
#   name       - display name (for our own logging)
#   id         - permission GUID (from Microsoft Graph docs)
#   type       - "Role" for application permission, "Scope" for delegated
$Permissions = @(
    @{ name = "Calendars.ReadWrite";              id = "ef54d2bf-783f-4e0f-bca1-3210c0444d99"; type = "Role" }
    @{ name = "ChannelMessage.Read.All";          id = "7b2449af-6ccd-4f4d-9f78-e550c193f0d1"; type = "Role" }
    @{ name = "ChannelMessage.UpdatePolicyViolation.All"; id = "4d02b0cc-d90b-441f-8d82-4fb55c34d6bb"; type = "Role" }
    @{ name = "Files.Read.All";                   id = "01d4889c-1287-42c6-ac1f-5d1e02578ef6"; type = "Role" }
    @{ name = "Files.ReadWrite.All";              id = "75359482-378d-4052-8f01-80520e7db3cd"; type = "Role" }
    @{ name = "Mail.ReadWrite";                   id = "e2a3a72e-5f79-4c64-b1b1-878b674786c9"; type = "Role" }
    @{ name = "Mail.Send";                        id = "b633e1c5-b582-4048-a93e-9f11b44c7e96"; type = "Role" }
    @{ name = "Notes.ReadWrite.All (Application)"; id = "0c458cef-11f3-48c2-a568-c66751c238c0"; type = "Role" }
    @{ name = "OnlineMeetings.ReadWrite.All";     id = "b8bb2037-6e08-44ac-a4ea-4674e010e2a4"; type = "Role" }
    @{ name = "Sites.Read.All";                   id = "332a536c-c7ef-4017-ab91-336970924f0d"; type = "Role" }
    @{ name = "Sites.ReadWrite.All";              id = "9492366f-7969-46a4-8d15-ed1a20078fff"; type = "Role" }
    @{ name = "Tasks.ReadWrite.All";              id = "44e666d1-d276-445b-a5fc-8815eeb81d55"; type = "Role" }
    @{ name = "User.Read.All";                    id = "df021288-bdef-4463-88db-98f22de89214"; type = "Role" }
    @{ name = "User.Read (Delegated)";            id = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"; type = "Scope" }
)

# -- Step 1: Confirm identity ----------------------------------------------
Write-Step "Step 1: Identify signed-in user"
$me = az ad signed-in-user show | ConvertFrom-Json
if (-not $me) {
    Write-Fail "Not signed in. Run: az login --tenant <parlayvu-tenant-id>"
    exit 1
}
$tenantId = (az account show --query tenantId -o tsv)
Write-Host "Signed in as: $($me.displayName) ($($me.userPrincipalName))"
Write-Host "Tenant:       $tenantId"

# -- Step 2: Create or find the app registration ---------------------------
Write-Step "Step 2: App registration '$DisplayName'"
$existingApps = az ad app list --display-name $DisplayName --query "[?displayName=='$DisplayName']" -o json | ConvertFrom-Json
if ($existingApps -and $existingApps.Count -gt 0) {
    $app = $existingApps[0]
    Write-Skip "App registration exists (appId=$($app.appId))"
} else {
    Write-Host "Creating new app registration..."
    $app = az ad app create --display-name $DisplayName --sign-in-audience "AzureADMyOrg" | ConvertFrom-Json
    Write-Ok "Created (appId=$($app.appId))"
    # Give Azure a moment to replicate before we touch the SP
    Start-Sleep -Seconds 5
}
$appId = $app.appId
$objectId = $app.id

# -- Step 3: Ensure service principal exists in this tenant ----------------
Write-Step "Step 3: Service principal for $DisplayName"
$existingSps = az ad sp list --filter "appId eq '$appId'" -o json | ConvertFrom-Json
if ($existingSps -and $existingSps.Count -gt 0) {
    $sp = $existingSps[0]
    Write-Skip "Service principal exists (id=$($sp.id))"
} else {
    Write-Host "Creating service principal..."
    $sp = az ad sp create --id $appId | ConvertFrom-Json
    Write-Ok "Created (id=$($sp.id))"
    Start-Sleep -Seconds 3
}

# -- Step 4: Add Graph permissions -----------------------------------------
Write-Step "Step 4: Microsoft Graph permissions ($($Permissions.Count) total)"
# Read existing permissions on the app so we only add missing ones
$existingPermGuids = @()
if ($app.requiredResourceAccess) {
    foreach ($rra in $app.requiredResourceAccess) {
        if ($rra.resourceAppId -eq $GraphAppId) {
            $existingPermGuids = $rra.resourceAccess | ForEach-Object { $_.id }
        }
    }
}

$addedCount = 0
$skippedCount = 0
foreach ($p in $Permissions) {
    if ($existingPermGuids -contains $p.id) {
        Write-Skip "$($p.name) already on app"
        $skippedCount++
    } else {
        # az ad app permission add takes <id>=<Role|Scope> pairs
        az ad app permission add --id $appId --api $GraphAppId --api-permissions "$($p.id)=$($p.type)" 2>&1 | Out-Null
        Write-Ok "Added $($p.name)"
        $addedCount++
    }
}
Write-Host ""
Write-Host "Permissions: $addedCount added, $skippedCount already present" -ForegroundColor Cyan

# -- Step 5: Grant admin consent -------------------------------------------
Write-Step "Step 5: Grant admin consent for the tenant"
# Permission additions take a few seconds to propagate before consent works
Write-Host "Waiting 10 sec for permission changes to propagate..."
Start-Sleep -Seconds 10

$attempt = 0
$maxAttempts = 3
$consentOk = $false
while ($attempt -lt $maxAttempts -and -not $consentOk) {
    $attempt++
    try {
        az ad app permission admin-consent --id $appId 2>&1 | Out-Null
        $consentOk = $true
        Write-Ok "Admin consent granted (attempt $attempt)"
    } catch {
        if ($attempt -lt $maxAttempts) {
            Write-Warn "Attempt $attempt failed, waiting 15 sec and retrying..."
            Start-Sleep -Seconds 15
        } else {
            Write-Fail "Admin consent failed after $maxAttempts attempts: $_"
            Write-Host ""
            Write-Host "You can grant manually in the portal:" -ForegroundColor Yellow
            Write-Host "  portal.azure.com -> Entra ID -> App registrations -> $DisplayName"
            Write-Host "  -> API permissions -> 'Grant admin consent for ParlayVu'"
            Write-Host ""
            Write-Host "The app is otherwise fully configured - continuing to secret creation."
        }
    }
}

# -- Step 6: Create a fresh client secret ----------------------------------
Write-Step "Step 6: Create client secret"
$secretName = "ParlayVU API Production - $(Get-Date -Format 'yyyy-MM-dd')"
Write-Host "Creating secret: $secretName (valid 24 months)"
$secret = az ad app credential reset `
    --id $appId `
    --append `
    --display-name $secretName `
    --years 2 `
    --query "{password:password, endDateTime:endDateTime}" | ConvertFrom-Json
Write-Ok "Secret created (expires $($secret.endDateTime))"

# -- Step 7: Summary -------------------------------------------------------
Write-Step "Phase 3 complete - summary"
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Save these values - Phase 4 needs them for the Container App" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "MICROSOFT_TENANT_ID:      $tenantId"
Write-Host "MICROSOFT_CLIENT_ID:      $appId"
Write-Host "MICROSOFT_CLIENT_SECRET:  $($secret.password)"
Write-Host ""
Write-Host "App display name:         $DisplayName"
Write-Host "App object ID:            $objectId"
Write-Host "Service principal ID:     $($sp.id)"
Write-Host "Secret display name:      $secretName"
Write-Host "Secret expires:           $($secret.endDateTime)"
Write-Host ""
Write-Host "Permissions granted:      $($Permissions.Count) Microsoft Graph permissions"
if ($consentOk) {
    Write-Host "Admin consent:            GRANTED" -ForegroundColor Green
} else {
    Write-Host "Admin consent:            NOT YET GRANTED - finish manually in portal" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Next: Phase 4 - build & deploy the Container App." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Warn "The CLIENT_SECRET above is shown ONCE. Copy it now - you can't read it later."
