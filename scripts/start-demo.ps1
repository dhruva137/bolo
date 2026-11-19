# Run the free local demo. First run installs its dependencies and speech model.
param([ValidateRange(1,65535)][int]$Port=8000, [switch]$Setup)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv/Scripts/python.exe'
$oldOffline = $env:BOLO_OFFLINE
Push-Location (Join-Path $root 'backend')
try {
    $env:BOLO_OFFLINE = '1'
    if (!(Test-Path -LiteralPath $python)) {
        $venv = Join-Path $root '.venv'
        if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv $venv }
        else { python -m venv $venv }
        if ($LASTEXITCODE) { throw 'Install Python 3.11 or later and try again.' }
        $Setup = $true
    }
    if ($Setup) {
        & $python -m pip install -r requirements.txt
        if ($LASTEXITCODE) { throw 'Dependency installation failed.' }
    }
    & $python -m voice.setup
    if ($LASTEXITCODE) { throw 'Speech model setup failed. Rerun this command to retry.' }
    Write-Host "Open http://127.0.0.1:$Port and choose Kirana demo."
    & $python -m uvicorn app:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE) { throw 'Bolo stopped with an error.' }
} finally {
    $env:BOLO_OFFLINE = $oldOffline
    Pop-Location
}
