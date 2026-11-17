@echo off
REM Choose your own passwords for admin, demo_user1, demo_user2 and demo_user3.
REM What you type is hidden. They are saved in .env (never in git) and applied
REM to the database. PostgreSQL must be running.
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python etl\set_passwords.py
pause
