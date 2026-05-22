# Run once after: gh auth login
# Creates private repo parlayvu-core (if missing) and pushes main.

$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$gh = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $gh)) {
    throw "GitHub CLI not found. Install: winget install GitHub.cli"
}

& $gh auth status
if ($LASTEXITCODE -ne 0) {
    Write-Host "Run first: gh auth login"
    exit 1
}

$remote = git remote get-url origin 2>$null
if (-not $remote) {
    Write-Host "Creating private GitHub repo parlayvu-core ..."
    & $gh repo create parlayvu-core --private --source=. --remote=origin --description "ParlayVU.ai core — agentic marketing OS"
}

Write-Host "Pushing main ..."
git push -u origin main

Write-Host "Done. Remote:"
git remote -v
