param(
    [Parameter(Mandatory)][ValidateSet('Start','Demo')][string] $Action,
    [string] $AirCheckRepository,
    [string] $PostgresVersion = '18'
)
$ErrorActionPreference = 'Stop'
$revision = '206310cd90ad6bce6674cb274b1d3e9faa26afbb'
$stage = Join-Path $env:LOCALAPPDATA 'Temp\sapr-aircheck-206310c'
$localFile = Join-Path $stage 'local-settings.json'
$origin = 'http://127.0.0.1:3130'

if ($Action -eq 'Demo') {
    $local = Get-Content -LiteralPath $localFile -Raw | ConvertFrom-Json
    $previous = $env:SAPR_DEVICE_TOKEN
    try {
        $env:SAPR_DEVICE_TOKEN = $local.token
        & python (Join-Path $PSScriptRoot 'demo.py') --wsl --url $origin
        if ($LASTEXITCODE -ne 0) { throw "Demo failed with exit code $LASTEXITCODE." }
    } finally {
        $env:SAPR_DEVICE_TOKEN = $previous
    }
    return
}

if (!$AirCheckRepository) { throw 'Specify -AirCheckRepository with the checkout of air_check_system.' }
$repository = (Resolve-Path -LiteralPath $AirCheckRepository).Path
if (Get-NetTCPConnection -LocalPort 3130 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 3130 is in use. Stop the service on that port before starting a new test server."
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$frontend = Join-Path $stage 'frontend'
if (!(Test-Path -LiteralPath (Join-Path $frontend 'package-lock.json'))) {
    $zip = Join-Path $stage 'aircheck.zip'
    & git -C $repository archive --format=zip -o $zip $revision frontend database
    if ($LASTEXITCODE -ne 0) { throw "Could not archive AirCheck revision $revision." }
    Expand-Archive -LiteralPath $zip -DestinationPath $stage
}
if (!(Test-Path -LiteralPath $localFile)) {
    @{
        password = [Guid]::NewGuid().ToString('N')
        token = ([Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N'))
        auth = ([Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N'))
    } | ConvertTo-Json | Set-Content -LiteralPath $localFile -Encoding utf8
}
$local = Get-Content -LiteralPath $localFile -Raw | ConvertFrom-Json
if ($local.password -notmatch '^[a-f0-9]{32}$' -or $local.token -notmatch '^[a-f0-9]{64}$' -or
    $local.auth -notmatch '^[a-f0-9]{64}$') { throw 'Invalid isolated stand settings.' }

# An explicit WSL process keeps the isolated PostgreSQL service reachable.
$wslLifetime = Start-Process -FilePath wsl.exe -ArgumentList @('-d','Ubuntu','--','sleep','infinity') -WindowStyle Hidden -PassThru
try {
    $cluster = @(wsl -d Ubuntu -- pg_lsclusters -h | Where-Object { $_ -match "^$([regex]::Escape($PostgresVersion))\s+sapr\s+" })
    if ($LASTEXITCODE -ne 0) { throw 'Install PostgreSQL tools inside Ubuntu WSL first.' }
    if (!$cluster) {
        & wsl -d Ubuntu -u root -- pg_createcluster -p 55432 --start $PostgresVersion sapr
        if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the dedicated sapr cluster.' }
    } elseif ($cluster[0] -notmatch '\s55432\s') {
        throw 'The existing sapr cluster uses a different port. Inspect it before continuing.'
    } elseif ($cluster[0] -match '\sdown\s') {
        & wsl -d Ubuntu -u root -- pg_ctlcluster $PostgresVersion sapr start
        if ($LASTEXITCODE -ne 0) { throw 'Could not start the dedicated sapr cluster.' }
    }

    @"
    SELECT 'CREATE ROLE sapr LOGIN PASSWORD ''$($local.password)''' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sapr') \gexec
    SELECT 'CREATE DATABASE sapr OWNER sapr' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'sapr') \gexec
"@ | wsl -d Ubuntu -u postgres -- psql -p 55432 -d postgres -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw 'Could not create or verify the dedicated test database.' }

    Push-Location -LiteralPath $frontend
    try {
        if (!(Test-Path -LiteralPath 'node_modules/next/dist/bin/next')) {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Could not restore the pinned AirCheck dependencies.' }
        }
        $env:DATABASE_URL = "postgres://sapr:$($local.password)@127.0.0.1:55432/sapr"
        $env:MIGRATIONS_DIR = Join-Path $stage 'database\migrations'
        $env:AIRCHECK_SCHEMA_VERSION = '015'
        $env:DEVICE_ID = 'sapr-room-01'
        $env:SIMULATOR_DEVICE_TOKEN = $local.token
        $env:BETTER_AUTH_SECRET = $local.auth
        $env:BETTER_AUTH_URL = $origin
        $env:AIRCHECK_MODE = 'simulation'
        $env:AUTOMATION_ENABLED = 'false'
        $env:ALERTS_ENABLED = 'false'
        $env:NEXT_TELEMETRY_DISABLED = '1'
        & node scripts/migrate.mjs
        if ($LASTEXITCODE -ne 0) { throw 'AirCheck migrations failed.' }
        & node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3130
        if ($LASTEXITCODE -ne 0) { throw "AirCheck exited with code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
} finally {
    if (!$wslLifetime.HasExited) { Stop-Process -InputObject $wslLifetime }
}
