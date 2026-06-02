param(
    [Parameter(Mandatory=$true)][string]$Client,
    [Parameter(Mandatory=$true)][string]$Show,
    [Parameter(Mandatory=$true)][string]$Episode
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$starter = Join-Path $root "projects\_starter_project"
$clientDir = Join-Path (Join-Path $root "projects") $Client
$projectName = "$Show`_$Episode"
$project = Join-Path $clientDir $projectName

if (Test-Path -LiteralPath $project) {
    throw "Project already exists: $project"
}

New-Item -ItemType Directory -Path $clientDir -Force | Out-Null
Copy-Item -Path $starter -Destination $project -Recurse
Write-Host "Created project: $project"
