# EvacuateSim developer script (Windows PowerShell).
# Sets up the venv, installs dependencies, and starts backend + frontend dev servers.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/dev.ps1           # setup + run
#   powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -TestOnly # run checks only

param(
    [switch]$TestOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== EvacuateSim dev setup ($root) ===" -ForegroundColor Cyan

# --- Python venv ---
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    python -m venv (Join-Path $root ".venv")
}
Write-Host "Installing backend dependencies..."
& $venvPython -m pip install --quiet -e "$($root)\backend[dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# --- Frontend deps ---
Push-Location (Join-Path $root "frontend")
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies (npm)..."
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }
}
Pop-Location

if ($TestOnly) {
    Write-Host "=== Running backend tests ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root "backend")
    & $venvPython -m pytest tests/
    $pytestExit = $LASTEXITCODE
    & $venvPython -m ruff check app tests
    $ruffExit = $LASTEXITCODE
    Pop-Location
    Write-Host "=== Running frontend tests ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root "frontend")
    npm test
    $vitestExit = $LASTEXITCODE
    Pop-Location
    if ($pytestExit -ne 0 -or $ruffExit -ne 0 -or $vitestExit -ne 0) {
        throw "One or more checks failed (pytest=$pytestExit ruff=$ruffExit vitest=$vitestExit)"
    }
    Write-Host "All checks passed." -ForegroundColor Green
    exit 0
}

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
$backend = Start-Process -FilePath $venvPython -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000" -WorkingDirectory (Join-Path $root "backend") -PassThru

Write-Host "Starting frontend dev server on http://localhost:5173 ..."
Push-Location (Join-Path $root "frontend")
$frontend = Start-Process -FilePath "npm" -ArgumentList "run","dev" -PassThru -NoNewWindow
Pop-Location

Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8000  (API docs: /docs)" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the frontend; backend PID: $($backend.Id)"
try { Wait-Process -Id $backend.Id } finally { if (-not $frontend.HasExited) { Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue } }
