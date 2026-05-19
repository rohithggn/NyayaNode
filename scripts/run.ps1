# Start NyayaNode API (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Backend = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "backend")).Path
Set-Location $Backend

if (-not (Test-Path ".env")) {
    Write-Host "Missing backend\.env — run: Copy-Item .env.example .env" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting NyayaNode on http://127.0.0.1:8000" -ForegroundColor Green
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
