$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install requirements-build.txt first.' }
# ESP-IDF rejects project directories containing spaces. Stage the exact sources in an ASCII path.
$stage = Join-Path $env:LOCALAPPDATA ('Temp\sapr-esp32-' + [Guid]::NewGuid().ToString('N'))
if ($stage -match '[^\x21-\x7E]') { throw 'ESP-IDF staging requires an ASCII path without spaces.' }
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    foreach ($name in 'platformio.ini', 'CMakeLists.txt', 'sdkconfig.defaults', 'partitions.csv', 'src', 'include') {
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $stage -Recurse
    }
    & $python -m platformio run -d $stage -j 2
    if ($LASTEXITCODE -ne 0) { throw "PlatformIO failed with exit code $LASTEXITCODE." }
    $output = Join-Path $root 'build\esp32'
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    Copy-Item (Join-Path $stage '.pio\build\sapr\firmware.*') -Destination $output -Force
    Copy-Item -LiteralPath (Join-Path $stage '.pio\build\sapr\bootloader.bin'),(Join-Path $stage '.pio\build\sapr\partitions.bin') -Destination $output -Force
    Write-Output "Firmware files: $output"
} finally {
    $resolved = (Resolve-Path -LiteralPath $stage).Path
    $temp = (Resolve-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'Temp')).Path
    if ([IO.Path]::GetDirectoryName($resolved) -eq $temp -and [IO.Path]::GetFileName($resolved) -match '^sapr-esp32-[0-9a-f]{32}$') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
