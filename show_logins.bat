@echo off
REM Shows the four dashboard logins (usernames and passwords) on your own screen.
REM The passwords are read from .env at that moment; none are stored in this file,
REM so it is safe to keep in git. Usage: double-click, or run  show_logins.bat
cd /d "%~dp0"
if not exist .env (
    echo [STOP] .env not found. Copy .env.example to .env and set the passwords first.
    pause & exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$e = @{}; Get-Content '.env' | Where-Object { $_ -match '^\s*([A-Z_]+)\s*=\s*(.*)$' } | ForEach-Object { $e[$Matches[1]] = $Matches[2].Trim() };" ^
  "$admin = $e['DEMO_ADMIN_USERNAME']; if (-not $admin) { $admin = 'admin' };" ^
  "Write-Host ''; Write-Host '  MovieLens dashboard logins' -ForegroundColor Cyan; Write-Host '  --------------------------';" ^
  "Write-Host ('  {0,-12} {1,-7} {2}' -f 'USERNAME', 'ROLE', 'PASSWORD');" ^
  "Write-Host ('  {0,-12} {1,-7} {2}' -f $admin, 'admin', $e['DEMO_ADMIN_PASSWORD']);" ^
  "foreach ($u in 'demo_user1', 'demo_user2', 'demo_user3') { Write-Host ('  {0,-12} {1,-7} {2}' -f $u, 'user', $e['DEMO_USER_PASSWORD']) };" ^
  "Write-Host ''; Write-Host '  Open http://localhost:8501 after starting run_app.bat';" ^
  "Write-Host '  To change a password: edit .env, then run  .venv\Scripts\python.exe etl\setup_security.py'; Write-Host ''"
pause
