param(
  [string]$RepoRoot = "",
  [string]$SourceDir = "scraping/output",
  [string]$BackupDir = "",
  [switch]$MoveSourceAfterZip
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
}
if (-not $BackupDir) {
  $BackupDir = Join-Path $RepoRoot "backups"
}

$fullSource = Join-Path $RepoRoot $SourceDir
if (-not (Test-Path $fullSource)) {
  throw "Source folder not found: $fullSource"
}

New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$zipPath = Join-Path $BackupDir "AuctionHousesApp_scraping_output_$stamp.zip"

Compress-Archive -Path (Join-Path $fullSource "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force
Write-Host "Backup created: $zipPath"

if ($MoveSourceAfterZip) {
  $archiveDir = Join-Path $BackupDir "scraping_output_$stamp"
  Move-Item -Path $fullSource -Destination $archiveDir -Force
  Write-Host "Moved source folder to: $archiveDir"
}
