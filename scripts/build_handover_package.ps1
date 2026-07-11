param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutZip = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutZip) {
    $OutZip = Join-Path $Root "delivery\KitchensProduction-handover.zip"
}

$dump = Join-Path $Root "delivery\kitchens_bot_handover.dump"
if (-not (Test-Path $dump)) {
    throw "DB dump missing: $dump. Run export from server first."
}

$staging = Join-Path $env:TEMP "KitchensProduction-handover-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $staging -Force | Out-Null

$exclude = @(
    ".venv", "venv", "__pycache__", ".pytest_cache", ".git",
    ".env", "kitchens-bot.tgz", "InputData", "logs", "myNotes.md", "Task.md"
)

Get-ChildItem -Path $Root -Force | Where-Object {
    $name = $_.Name
    $name -notin $exclude
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination (Join-Path $staging $_.Name) -Recurse -Force
}

if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $OutZip -CompressionLevel Optimal
Remove-Item $staging -Recurse -Force

$sizeMb = [math]::Round((Get-Item $OutZip).Length / 1MB, 2)
Write-Host "Package: $OutZip ($sizeMb MB)"
