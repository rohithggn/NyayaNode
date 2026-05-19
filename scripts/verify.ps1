# Smoke-test NyayaNode after clone (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Backend = (Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "backend")).Path

Write-Host "==> Python version" -ForegroundColor Cyan
python --version

$envFile = Join-Path $Backend ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "WARN: backend/.env missing. Copy backend/.env.example to backend/.env" -ForegroundColor Yellow
}

Push-Location $Backend
python scripts\verify_setup.py
$code = $LASTEXITCODE
Pop-Location

if ($code -ne 0) { exit $code }
Write-Host ""
Write-Host "All checks passed. Start server with scripts/run.ps1" -ForegroundColor Green
