# Production mode on Windows: the API serves the built web app at http://localhost:8000 (one process, no dev server)
Set-Location (Join-Path $PSScriptRoot "..")
if (Test-Path .env) {
  Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
  }
}
if (-not (Test-Path frontend\dist\index.html)) {
  Write-Host "-> Building the web app (first run only)"
  Push-Location frontend; npm run build; Pop-Location
}
Write-Host "CodeTwin is starting at http://localhost:8000  (press Ctrl+C to stop)"
if (-not $env:CODETWIN_NO_BROWSER) { Start-Job { Start-Sleep 4; Start-Process "http://localhost:8000" } | Out-Null }
& backend\.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --port 8000
