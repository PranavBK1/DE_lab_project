# MovieLens Data Engineering Dashboard

DS5003 Data Engineering Lab, IIT Palakkad.

This project loads the MovieLens 25M dataset into PostgreSQL, analyses it with SQL, and serves a Streamlit dashboard with login and roles (admin and user). The dashboard answers questions (a)–(g).

## Stack
- PostgreSQL 17: tables, DB roles, triggers
- Python 3.11+ with pandas, SQLAlchemy and psycopg 3
- Streamlit + Plotly for the dashboard
- bcrypt for password hashing

## Prerequisites
- Python 3.11 or newer
- PostgreSQL 17 running locally on port 5432
- About 8 GB of free disk space

## Setup
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then edit the passwords in .env
```

## Run the pipeline
```powershell
python etl/download.py      # 1. download + unzip ml-25m into data/raw/
python etl/clean.py         # 2. clean, write data/clean/ and reports/cleaning_report.md
python etl/load.py          # 3. create schema, roles and triggers, then bulk-load (TODO)
```

## Run the app
```powershell
streamlit run app/Home.py   # (TODO)
```

## Demo accounts
TODO (Phase 5). Passwords will be kept in `.env`.

## Project layout
```
data/raw/      downloaded CSVs (git-ignored)
data/clean/    cleaned CSVs (git-ignored)
sql/           schema, roles, triggers, queries/ (one per question)
etl/           download, clean, load
app/           Streamlit app (Home.py = login, pages/)
tests/         query results checked against pandas
reports/       cleaning report, ER diagram
slides/        presentation
```
