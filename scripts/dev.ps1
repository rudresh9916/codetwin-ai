# Start API (http://localhost:8000) and web app (http://localhost:5173) on Windows
Set-Location (Join-Path $PSScriptRoot "..")
if (Test-Path .env) {
  Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
  }
}
$api = Start-Process -PassThru -NoNewWindow -FilePath "backend\.venv\Scripts\uvicorn.exe" -ArgumentList "app.main:app","--reload","--reload-dir","app","--port","8000" -WorkingDirectory "backend"
try { Push-Location frontend; npm run dev } finally { Pop-Location; Stop-Process -Id $api.Id -ErrorAction SilentlyContinue }
