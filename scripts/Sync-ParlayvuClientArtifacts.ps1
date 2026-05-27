<#
.SYNOPSIS
  Sync the repo's canonical product docs into client_artifacts/parlayvu/00_Client_Brief/
  so the Nathan-as-Chief-of-Staff tenant always reads source-of-truth content.

.DESCRIPTION
  The ParlayVU internal tenant (client_id=parlayvu) uses the repo itself as its
  source material. ARCHITECTURE.md, ROADMAP.md, DECISIONS.md, and MIGRATION-PLAN.md
  are the canonical product docs — they live at the repo root and are edited there.

  This script copies them into client_artifacts/parlayvu/00_Client_Brief/ so
  get_project_context() picks them up when Nathan answers questions in the
  ParlayVU Teams team.

  Idempotent — safe to re-run. Run it after every meaningful edit to the
  canonical docs (or wire it into a pre-commit hook later).

.EXAMPLE
  pwsh scripts/Sync-ParlayvuClientArtifacts.ps1
#>

[CmdletBinding()]
param(
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"

$BriefDir = Join-Path $RepoRoot "client_artifacts\parlayvu\00_Client_Brief"

if (-not (Test-Path $BriefDir)) {
  throw "Expected $BriefDir to exist. Scaffold client_artifacts/parlayvu/ first."
}

# Canonical docs that ARE Nathan's source material for the ParlayVU tenant.
# Edit the originals at the repo root; rerun this script to push into 00_Client_Brief.
$CanonicalDocs = @(
  "ARCHITECTURE.md",
  "ROADMAP.md",
  "DECISIONS.md",
  "MIGRATION-PLAN.md"
)

$Copied = 0
$Skipped = 0
foreach ($doc in $CanonicalDocs) {
  $src = Join-Path $RepoRoot $doc
  $dst = Join-Path $BriefDir $doc

  if (-not (Test-Path $src)) {
    Write-Warning "Source doc not found: $src (skipping)"
    $Skipped++
    continue
  }

  # Only copy if content differs (avoids touching mtime when nothing changed).
  $needsCopy = $true
  if (Test-Path $dst) {
    $srcHash = (Get-FileHash $src -Algorithm SHA256).Hash
    $dstHash = (Get-FileHash $dst -Algorithm SHA256).Hash
    if ($srcHash -eq $dstHash) {
      $needsCopy = $false
    }
  }

  if ($needsCopy) {
    Copy-Item -Path $src -Destination $dst -Force
    Write-Host "Synced $doc -> client_artifacts/parlayvu/00_Client_Brief/"
    $Copied++
  } else {
    Write-Host "Up to date: $doc"
    $Skipped++
  }
}

Write-Host ""
Write-Host "Sync complete. Copied: $Copied, Up-to-date/skipped: $Skipped"
