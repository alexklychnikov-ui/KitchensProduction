param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$DumpFile = "",
    [string]$ComposeFile = ""
)

$ErrorActionPreference = "Stop"

if (-not $DumpFile) { $DumpFile = Join-Path $Root "delivery\kitchens_bot_handover.dump" }
if (-not $ComposeFile) { $ComposeFile = Join-Path $Root "delivery\docker-compose.postgres.yml" }
$container = "kitchens-postgres"

if (-not (Test-Path $DumpFile)) {
    throw "Dump not found: $DumpFile"
}

Push-Location $Root
try {
    docker compose -f $ComposeFile up -d

    Write-Host "Waiting for Postgres..."
    for ($i = 0; $i -lt 30; $i++) {
        docker exec $container pg_isready -U kitchens -d kitchens_bot 2>$null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }

    docker cp $DumpFile "${container}:/tmp/kitchens_bot_handover.dump"
    docker exec $container pg_restore `
        -U kitchens `
        -d kitchens_bot `
        --clean `
        --if-exists `
        --no-owner `
        --no-acl `
        /tmp/kitchens_bot_handover.dump
    docker exec $container rm -f /tmp/kitchens_bot_handover.dump

    Write-Host "Database restored."
    Write-Host "DATABASE_URL=postgresql://kitchens:kitchens@127.0.0.1:5433/kitchens_bot"
}
finally {
    Pop-Location
}
