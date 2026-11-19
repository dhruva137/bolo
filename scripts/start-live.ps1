# Start Bolo for live WhatsApp testing (cloud speech + Twilio/Meta). Light on CPU/RAM: all AI runs in the cloud.
# Usage:  ./scripts/start-live.ps1        (then, in a second terminal:  cloudflared tunnel --url http://localhost:8000)
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!(Test-Path (Join-Path $root '.env'))) { Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env'); Write-Host "Created .env, fill in your keys first."; exit 1 }
Remove-Item Env:BOLO_OFFLINE -ErrorAction SilentlyContinue
Push-Location (Join-Path $root 'backend')
try {
    Write-Host "Checking providers (a few paise of credit)..."
    python smoke.py
    Write-Host "`nStarting Bolo on http://localhost:$Port  (Live watch shows WhatsApp chats)"
    Write-Host "Twilio sandbox: 'When a message comes in' = <PUBLIC_BASE_URL>/twilio (POST). It must match PUBLIC_BASE_URL exactly."
    python -m uvicorn app:app --host 127.0.0.1 --port $Port
} finally { Pop-Location }
