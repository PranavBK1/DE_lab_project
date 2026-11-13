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
                            #    roles + demo accounts, reconcile, write reports/load_report.md
python etl/setup_security.py # 4. roles, grants, row-level security, demo accounts
                            #    (load.py already runs this; run it alone after editing .env)
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
streamlit run app/Home.py   # login page; the dashboard pages come in Phase 7
pytest -v tests/            # security tests (every write is rolled back)
```

## Demo accounts
Seeded by `etl/setup_security.py`. The passwords are in `.env` (`DEMO_ADMIN_PASSWORD`,
and `DEMO_USER_PASSWORD` shared by the three users). They are never in this README or in git.

| username | role | MovieLens user_id | ratings at load |
|---|---|---|---|
| admin | admin | 200000 (new app account) | 0 |
| demo_user1 | user | 1 | 70 |
| demo_user2 | user | 2 | 184 |
| demo_user3 | user | 4 | 242 |

The demo users are the 3 lowest MovieLens user_ids with 50–300 ratings. Roles,
row-level security and the login flow are described in [reports/security.md](reports/security.md).

## Project layout
```
data/raw/      downloaded CSVs (git-ignored)
data/clean/    cleaned CSVs (git-ignored)
sql/           schema, constraints, triggers, roles, migrations/, queries/ (one per question)
etl/           download, clean, load, migrate, setup_security
app/           Streamlit app (Home.py = login, pages/)
tests/         query results checked against pandas
reports/       cleaning, load and security reports, ER diagram
slides/        presentation
```
