@echo off
REM ==========================================================================
REM  One-time setup: Python environment + download + clean + load database.
REM  Prerequisites: Python 3.11+ and PostgreSQL 17 installed and running.
REM  Usage: double-click, or run  setup.bat  from this folder.
REM  Takes about 30-45 minutes the first time (download 250 MB, clean ~5 min,
REM  load ~15-25 min). Re-running reloads the whole database.
REM ==========================================================================
cd /d "%~dp0"

where python >nul 2>nul || (echo [ERROR] Python not found. Install Python 3.11+ and tick "Add to PATH". & pause & exit /b 1)

if not exist .env (
    copy .env.example .env >nul
    echo [STOP] Created .env from .env.example.
    echo        Open .env, set PG_SUPERPASSWORD to your PostgreSQL "postgres" password,
    echo        and replace every other "change-me" with a password of your choice.
    echo        Then run setup.bat again.
    pause & exit /b 1
)
findstr /c:"change-me" .env >nul && (echo [STOP] .env still contains "change-me". Edit it first. & pause & exit /b 1)

if not exist .venv (
    echo [1/5] Creating virtual environment .venv
    python -m venv .venv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat

echo [2/5] Installing Python packages
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (pause & exit /b 1)

echo [3/5] Downloading MovieLens 25M (skipped if already present)
python etl\download.py || (pause & exit /b 1)

if exist data\clean\ratings.csv (
    echo [4/5] Cleaned data already present, skipping etl\clean.py
) else (
    echo [4/5] Cleaning data
    python etl\clean.py || (pause & exit /b 1)
)

echo [5/5] Loading PostgreSQL (tables, indexes, triggers, roles, demo accounts)
python etl\load.py || (pause & exit /b 1)

echo.
echo Setup complete. Start the dashboard with  run_app.bat
pause
