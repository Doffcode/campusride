# Start CampusRide. Run from anywhere:  powershell -ExecutionPolicy Bypass -File mvp\run.ps1
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv)) {
    Write-Host "First run: creating .venv and installing packages..."
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py -or $py -like "*WindowsApps*") { $py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" }
    & $py -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
}
if (-not $env:SARVAM_API_KEY -and -not (Test-Path .env)) {
    Write-Host "No SARVAM_API_KEY found. Voice is off; typing and map booking still work." -ForegroundColor Yellow
    Write-Host "Add it: create a file named .env in this folder containing  SARVAM_API_KEY=sk_..." -ForegroundColor Yellow
}
Write-Host "Open http://localhost:8000  (Ctrl+C to stop)" -ForegroundColor Green
.\.venv\Scripts\python.exe -m uvicorn mvp.server:app --port 8000
