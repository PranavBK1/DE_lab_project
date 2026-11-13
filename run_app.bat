@echo off
REM Start the MovieLens dashboard at http://localhost:8501  (Ctrl+C to stop).
REM Run setup.bat once before the first start.
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
streamlit run app\Home.py
