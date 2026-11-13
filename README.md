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
python etl/load.py          # 3. create tables, COPY ~41.9M rows, FKs, indexes, triggers,
                            #    reconcile, write reports/load_report.md
```

`etl/load.py` drops and reloads every table, so it is safe to re-run. The loaded
database takes **3.4 GB** (ratings 1.9 GB and genome_scores 1.3 GB, both including
indexes); see [reports/load_report.md](reports/load_report.md) for every table.
The load time of the current database was not recorded (the report was added
afterwards); the next full run writes each step's time into the report.

Other ETL commands:
```powershell
python etl/load.py --report-only   # rewrite the load report from the live DB, no reload (~15 s)
python etl/migrate.py              # apply sql/migrations/ to an already-loaded DB, no reload
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
