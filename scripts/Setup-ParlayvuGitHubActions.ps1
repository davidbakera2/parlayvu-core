<#
.SYNOPSIS
    Phase 5 of MIGRATION-PLAN.md - set up GitHub Actions CI/CD against the
    new ParlayVU Azure subscription.

.DESCRIPTION
    Creates the parlayvu-github-actions service principal in ParlayVU's
    Entra tenant, grants it the rights it needs to push images and update
    the Container App, adds an OIDC federated credential so GitHub Actions
    can authenticate without storing a client secret, and prints all the
    secret values you need to set in the GitHub repo settings.

    Idempotent: reuses existing SP if it exists; only adds missing
    federated credentials and role assignments.

.PARAMETER GitHubRepo
    GitHub repo in owner/name form. Default: davidbakera2/parlayvu-core.

.PARAMETER ResourceGroup
    Resource group the SP gets Contributor on. Default: rg-parlayvu-prod.

.PARAMETER AcrName
    ACR the SP gets AcrPush on. Default: parlayvuacr.

.PARAMETER SpName
    Service principal display name. Default: parlayvu-github-actions.

.EXAMPLE
    .\Setup-ParlayvuGitHubActions.ps1
#>
param(
    [string]$GitHubRepo    = "davidbakera2/parlayvu-core",
    [string]$ResourceGroup = "rg-parlayvu-prod",
    [string]$AcrName       = "parlayvuacr",
    [string]$SpName        = "parlayvu-github-actions"
)

$ErrorActionPreference = "Stop"
$env:AZURE_CORE_ONLY_SHOW_ERRORS = "true"

function Write-Step($msg)   { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Skip($msg)   { Write-Host "[SKIP] $msg" -ForegroundColor DarkGray }
function Write-Fail($msg)   { Write-Host "[FAIL] $msg" -ForegroundColor Red }

# -- Step 1: Context -------------------------------------------------------
Write-Step "Step 1: Verify context"
$me = az ad signed-in-user show | ConvertFrom-Json
$current = az account show | ConvertFrom-Json
Write-Host "Signed in as: $($me.userPrincipalName)"
Write-Host "Subscription: $($current.name) ($($current.id))"
$subId = $current.id
$tenantId = $current.tenantId

# -- Step 2: Create or find service principal ------------------------------
Write-Step "Step 2: Service principal '$SpName'"
$existingSps = az ad sp list --filter "displayName eq '$SpName'" -o json | ConvertFrom-Json
if ($existingSps -and $existingSps.Count -gt 0) {
    $sp = $existingSps[0]
    Write-Skip "Service principal exists (appId=$($sp.appId))"
    $appId = $sp.appId
} else {
    Write-Host "Creating service principal..."
    # Use create-for-rbac WITHOUT a secret (we'll add OIDC federation instead)
    $created = az ad sp create-for-rbac `
        --name $SpName `
        --role Contributor `
        --scopes "/subscriptions/$subId/resourceGroups/$ResourceGroup" | ConvertFrom-Json
    $appId = $created.appId
    Write-Ok "Created (appId=$appId)"
    Start-Sleep -Seconds 5
}

# -- Step 3: Grant AcrPush on the ACR --------------------------------------
Write-Step "Step 3: Grant AcrPush on $AcrName"
$acrId = az acr show --name $AcrName --resource-group $ResourceGroup --query id -o tsv
$existingAcrRole = az role assignment list `
    --assignee $appId `
    --scope $acrId `
    --query "[?roleDefinitionName=='AcrPush']" -o json | ConvertFrom-Json
if ($existingAcrRole -and $existingAcrRole.Count -gt 0) {
    Write-Skip "Already has AcrPush"
} else {
    az role assignment create --assignee $appId --role AcrPush --scope $acrId | Out-Null
    Write-Ok "Granted AcrPush"
}

# -- Step 4: Add federated credential for GitHub main branch ---------------
Write-Step "Step 4: OIDC federated credential for GitHub main branch"
$fcName = "parlayvu-github-main"
$existingFcs = az ad app federated-credential list --id $appId -o json | ConvertFrom-Json
$alreadyHas = $false
foreach ($fc in $existingFcs) {
    if ($fc.name -eq $fcName) { $alreadyHas = $true; break }
}
if ($alreadyHas) {
    Write-Skip "Federated credential '$fcName' already exists"
} else {
    # az on Windows is a .cmd wrapper, and PowerShell's argument passing
    # strips/transforms the quotes in ConvertTo-Json output before az
    # sees it. The result is invalid JSON like {name:foo} instead of
    # {"name":"foo"}. The reliable workaround is to write the JSON to a
    # temp file and use az's `--parameters @file` syntax.
    $tmp = New-TemporaryFile
    @"
{
  "name": "$fcName",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:${GitHubRepo}:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}
"@ | Set-Content -Path $tmp -Encoding ASCII
    try {
        az ad app federated-credential create --id $appId --parameters "@$tmp" | Out-Null
        Write-Ok "Federated credential created: $fcName"
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

# -- Step 5: Capture ACR admin credentials (still needed for docker push) --
Write-Step "Step 5: Capture ACR admin credentials"
$acrCreds = az acr credential show --name $AcrName | ConvertFrom-Json
$acrUser = $acrCreds.username
$acrPass = $acrCreds.passwords[0].value
Write-Ok "ACR credentials captured"

# -- Step 6: Summary -------------------------------------------------------
Write-Step "Phase 5 - Set these 5 secrets in GitHub"
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  GO TO: https://github.com/${GitHubRepo}/settings/secrets/actions" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Add (or UPDATE) these 5 repository secrets:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  AZURE_CLIENT_ID         $appId"
Write-Host "  AZURE_TENANT_ID         $tenantId"
Write-Host "  AZURE_SUBSCRIPTION_ID   $subId"
Write-Host "  ACR_USERNAME            $acrUser"
Write-Host "  ACR_PASSWORD            $acrPass"
Write-Host ""
Write-Host "Notes:" -ForegroundColor DarkGray
Write-Host "  - The old AZURE_CREDENTIALS secret (if still there) can be deleted."
Write-Host "  - AZURE_CLIENT_SECRET is NOT needed (OIDC handles auth)."
Write-Host "  - The 3 AZURE_* secrets are new values - overwrite the Baker Strategy ones."
Write-Host "  - The ACR_USERNAME/PASSWORD are also new (parlayvuacr, not parlayvucore)."
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "After updating the secrets, tell me and I'll push the workflow" -ForegroundColor Green
Write-Host "update that points CI at the new infra. Then we trigger a run" -ForegroundColor Green
Write-Host "and confirm it deploys successfully to the new Container App." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
