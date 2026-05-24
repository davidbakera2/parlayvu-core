<#
.SYNOPSIS
    Provisions a Windows Server Azure VM for the ParlayVU Teams Media Worker.

.DESCRIPTION
    Creates an Azure VM (Standard_D4s_v3, Windows Server 2022) with the required
    network security rules for Microsoft Graph Communications application-hosted media.

    The Microsoft Graph Communications Media SDK requires:
    - Windows Server 2019 or later
    - 4+ vCPU, 16+ GB RAM for media processing
    - UDP 49152-65535 open for Graph media transport
    - A public HTTPS endpoint (configure with a TLS cert after provisioning)

    After provisioning, deploy ParlayVu.TeamsMediaWorker.exe to the VM and
    configure HTTPS (using IIS + Let's Encrypt, or an Azure Application Gateway).

.PARAMETER ResourceGroup
    Azure Resource Group (default: rg-parlayvu-demo)

.PARAMETER Location
    Azure region (default: eastus)

.PARAMETER VmName
    VM name (default: parlayvu-media-bot-vm)

.PARAMETER AdminUsername
    VM admin username (default: parlayvu-admin)

.PARAMETER VmSize
    VM SKU (default: Standard_D4s_v3 — minimum spec for media bot)

.PARAMETER DryRun
    Print the commands without executing them.

.EXAMPLE
    .\Provision-MediaBotVM.ps1 -DryRun
    .\Provision-MediaBotVM.ps1 -ResourceGroup rg-parlayvu-demo
#>
param(
    [string]$ResourceGroup    = "rg-parlayvu-demo",
    [string]$Location         = "eastus",
    [string]$VmName           = "parlayvu-media-bot-vm",
    [string]$AdminUsername    = "parlayvu-admin",
    [string]$VmSize           = "Standard_D4s_v3",
    [string]$NsgName          = "nsg-parlayvu-media-bot",
    [string]$VnetName         = "vnet-parlayvu-media-bot",
    [string]$SubnetName       = "subnet-media-bot",
    [string]$PublicIpName     = "pip-parlayvu-media-bot",
    [string]$NicName          = "nic-parlayvu-media-bot",
    [string]$OsDiskSku        = "Premium_LRS",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-Az {
    param([string[]]$Arguments, [string]$Description)
    $cmd = "az $($Arguments -join ' ')"
    Write-Host "[$Description]" -ForegroundColor Cyan
    Write-Host "  $cmd" -ForegroundColor Gray
    if (-not $DryRun) {
        $result = & az @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Command failed (exit $LASTEXITCODE): $result"
        }
        return $result
    }
}

Write-Host ""
Write-Host "=== ParlayVU Teams Media Worker — Windows VM Provisioning ===" -ForegroundColor Green
Write-Host "Resource Group : $ResourceGroup"
Write-Host "Location       : $Location"
Write-Host "VM Name        : $VmName"
Write-Host "VM Size        : $VmSize (Standard_D4s_v3 = 4 vCPU, 16 GB RAM)"
if ($DryRun) { Write-Host "[DRY RUN — no changes will be made]" -ForegroundColor Yellow }
Write-Host ""

# ── 1. Create NSG with Graph media rules ──────────────────────────────────────
Invoke-Az @("network","nsg","create",
    "--name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--location",$Location
) -Description "Create NSG"

# HTTPS inbound (Graph callback notifications)
Invoke-Az @("network","nsg","rule","create",
    "--nsg-name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--name","Allow-HTTPS-Inbound",
    "--priority","100",
    "--protocol","Tcp",
    "--destination-port-ranges","443",
    "--access","Allow",
    "--direction","Inbound"
) -Description "NSG: Allow HTTPS 443 inbound"

# HTTP inbound (for ACME/Let's Encrypt certificate issuance)
Invoke-Az @("network","nsg","rule","create",
    "--nsg-name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--name","Allow-HTTP-Inbound",
    "--priority","110",
    "--protocol","Tcp",
    "--destination-port-ranges","80",
    "--access","Allow",
    "--direction","Inbound"
) -Description "NSG: Allow HTTP 80 inbound (ACME cert)"

# App listen port (internal, for service on port 8080 behind IIS/YARP proxy)
Invoke-Az @("network","nsg","rule","create",
    "--nsg-name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--name","Allow-App-8080-Inbound",
    "--priority","120",
    "--protocol","Tcp",
    "--destination-port-ranges","8080",
    "--access","Allow",
    "--direction","Inbound"
) -Description "NSG: Allow app port 8080 inbound"

# UDP range required by Microsoft Graph Communications Media SDK
# Without this, audio/video transport fails silently
Invoke-Az @("network","nsg","rule","create",
    "--nsg-name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--name","Allow-GraphMedia-UDP-Inbound",
    "--priority","130",
    "--protocol","Udp",
    "--destination-port-ranges","49152-65535",
    "--access","Allow",
    "--direction","Inbound"
) -Description "NSG: Allow UDP 49152-65535 inbound (Graph media transport)"

Invoke-Az @("network","nsg","rule","create",
    "--nsg-name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--name","Allow-GraphMedia-UDP-Outbound",
    "--priority","100",
    "--protocol","Udp",
    "--destination-port-ranges","49152-65535",
    "--access","Allow",
    "--direction","Outbound"
) -Description "NSG: Allow UDP 49152-65535 outbound (Graph media transport)"

# RDP for initial setup (restrict source IP in production)
Invoke-Az @("network","nsg","rule","create",
    "--nsg-name",$NsgName,
    "--resource-group",$ResourceGroup,
    "--name","Allow-RDP-Inbound",
    "--priority","900",
    "--protocol","Tcp",
    "--destination-port-ranges","3389",
    "--access","Allow",
    "--direction","Inbound"
) -Description "NSG: Allow RDP 3389 (restrict source IP after initial setup)"

# ── 2. Create VNet and subnet ─────────────────────────────────────────────────
Invoke-Az @("network","vnet","create",
    "--name",$VnetName,
    "--resource-group",$ResourceGroup,
    "--location",$Location,
    "--address-prefixes","10.20.0.0/16",
    "--subnet-name",$SubnetName,
    "--subnet-prefixes","10.20.1.0/24"
) -Description "Create VNet and subnet"

# Attach NSG to subnet
Invoke-Az @("network","vnet","subnet","update",
    "--vnet-name",$VnetName,
    "--resource-group",$ResourceGroup,
    "--name",$SubnetName,
    "--network-security-group",$NsgName
) -Description "Attach NSG to subnet"

# ── 3. Create public IP ───────────────────────────────────────────────────────
Invoke-Az @("network","public-ip","create",
    "--name",$PublicIpName,
    "--resource-group",$ResourceGroup,
    "--location",$Location,
    "--sku","Standard",
    "--allocation-method","Static",
    "--dns-name","parlayvu-media-bot"
) -Description "Create static public IP"

# ── 4. Create NIC ─────────────────────────────────────────────────────────────
Invoke-Az @("network","nic","create",
    "--name",$NicName,
    "--resource-group",$ResourceGroup,
    "--location",$Location,
    "--vnet-name",$VnetName,
    "--subnet",$SubnetName,
    "--public-ip-address",$PublicIpName,
    "--network-security-group",$NsgName
) -Description "Create NIC"

# ── 5. Generate admin password and store in Key Vault ─────────────────────────
$adminPassword = if (-not $DryRun) {
    -join ((1..32) | ForEach-Object { [char](Get-Random -InputObject ([char[]]'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*')) })
} else {
    "<generated-at-runtime>"
}

Write-Host ""
Write-Host "=== IMPORTANT: Save the VM admin password ===" -ForegroundColor Yellow
Write-Host "Admin username : $AdminUsername"
Write-Host "Admin password : $adminPassword"
Write-Host "Store this in Azure Key Vault: az keyvault secret set --vault-name <vault> --name media-bot-vm-password --value <password>"
Write-Host ""

# ── 6. Create the Windows Server VM ──────────────────────────────────────────
Invoke-Az @("vm","create",
    "--name",$VmName,
    "--resource-group",$ResourceGroup,
    "--location",$Location,
    "--size",$VmSize,
    "--image","Win2022Datacenter",
    "--admin-username",$AdminUsername,
    "--admin-password",$adminPassword,
    "--nics",$NicName,
    "--os-disk-size-gb","128",
    "--storage-sku",$OsDiskSku,
    "--license-type","Windows_Server"
) -Description "Create Windows Server 2022 VM ($VmSize)"

# ── 7. Enable auto-shutdown at midnight UTC to save cost ──────────────────────
Invoke-Az @("vm","auto-shutdown",
    "--resource-group",$ResourceGroup,
    "--name",$VmName,
    "--time","0000"
) -Description "Enable auto-shutdown at midnight UTC"

# ── 8. Print next steps ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Provisioning complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Get the VM public IP:"
Write-Host "     az network public-ip show -g $ResourceGroup -n $PublicIpName --query ipAddress -o tsv"
Write-Host ""
Write-Host "  2. RDP into the VM and install prerequisites:"
Write-Host "     - .NET 8 Runtime (https://dotnet.microsoft.com/download/dotnet/8.0)"
Write-Host "     - IIS with URL Rewrite module (for HTTPS proxy)"
Write-Host "     - Win-ACME (https://www.win-acme.com) for Let's Encrypt TLS cert"
Write-Host ""
Write-Host "  3. Configure a DNS A record pointing to the public IP:"
Write-Host "     media-bot.yourdomain.com -> <public-ip>"
Write-Host ""
Write-Host "  4. Deploy the media worker:"
Write-Host "     dotnet publish -c Release -r win-x64 -o C:\parlayvu\media-worker"
Write-Host "     sc create ParlayVuMediaWorker binpath= 'dotnet C:\parlayvu\media-worker\ParlayVu.TeamsMediaWorker.dll' start= auto"
Write-Host "     sc start ParlayVuMediaWorker"
Write-Host ""
Write-Host "  5. Add Calls.AccessMedia.All to the Entra app registration:"
Write-Host "     Azure Portal -> Entra ID -> App registrations -> <bot-app> -> API permissions"
Write-Host "     -> Add permission -> Microsoft Graph -> Application -> Calls.AccessMedia.All"
Write-Host "     -> Grant admin consent"
Write-Host ""
Write-Host "  6. Set TEAMS_MEDIA_BOT_MEDIA_WORKER_URL on the management Container App:"
Write-Host "     az containerapp update --name parlayvu-teams-media-bot -g $ResourceGroup \"
Write-Host "       --set-env-vars TEAMS_MEDIA_BOT_MEDIA_WORKER_URL=https://media-bot.yourdomain.com"
Write-Host ""
Write-Host "  7. Verify the media worker health:"
Write-Host "     curl https://media-bot.yourdomain.com/health"
Write-Host ""
Write-Host "Cost estimate: Standard_D4s_v3 ~`$280/month (stop VM when not in use)"
