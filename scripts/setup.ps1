# One-time setup for local development (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command java -ErrorAction SilentlyContinue)) { Write-Warning "JDK 17+ not found - Java projects cannot be analysed until it is installed." }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Node.js 18+ is required" }
Write-Host "-> Python environment"
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install --upgrade pip | Out-Null
backend\.venv\Scripts\pip install -r backend\requirements.txt
Write-Host "-> JS/TS analyzer"
Push-Location backend\analyzers\js; npm install --no-audit --no-fund; Pop-Location
Write-Host "-> Web app"
Push-Location frontend; npm install --no-audit --no-fund; Pop-Location
# The ShopVerse demo history is generated automatically when the sample is imported.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "Setup complete. Run .\scripts\dev.ps1"
