@echo off
REM Start the MovieLens dashboard at http://localhost:8501  (Ctrl+C to stop).
REM Run setup.bat once before the first start.
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
REM Install anything requirements.txt gained since setup (a few seconds when nothing is missing).
python -m pip install -q --disable-pip-version-check -r requirements.txt
streamlit run app\Home.py
