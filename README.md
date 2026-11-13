# MovieLens Data Engineering Dashboard

DS5003 Data Engineering Lab, IIT Palakkad.

This project loads the MovieLens 25M dataset into PostgreSQL, analyses it with SQL, and serves a Streamlit dashboard with login and roles (admin and user). The dashboard answers questions (a)–(g).

## Stack
- PostgreSQL 17: tables, DB roles, triggers
- Python 3.11+ with pandas, SQLAlchemy and psycopg 3
- Streamlit + Plotly for the dashboard
- bcrypt password hashing inside PostgreSQL (pgcrypto); the hash never reaches the app

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

`etl/load.py` drops and reloads every table, so it is safe to re-run. A full load
takes **13–23 minutes** on this laptop (two measured runs on 2026-11-13) and the
loaded database uses **3.4 GB** (about 3,450 MB: ratings 1.9 GB and genome_scores
1.3 GB, both including indexes).

| step | run 1 | run 2 |
|---|---:|---:|
| COPY of the 9 CSVs (41.9M rows) | 520 s | 460 s |
| populate movie_stats | 26 s | 29 s |
| foreign keys, indexes, ANALYZE | 71 s | 605 s |
| analysis objects (stop list, materialized view) | – | 33 s |
| roles, grants, RLS, demo accounts | 1 s | 2 s |
| reconciliation (counts + movie_stats checks) | 144 s | 225 s |
| **total** | **762 s** | **1,357 s** |

The difference is almost all in the database-wide `ANALYZE` (about 10 s in run 1,
544 s in run 2). Every index and foreign key took the same time in both runs, so the
variation comes from the machine's disk I/O, not from the load. Run 1 predates the
analysis-objects step.

See [reports/load_report.md](reports/load_report.md) for every step and table.

Other ETL commands:
```powershell
python etl/load.py --report-only   # rewrite the load report from the live DB, no reload (~15 s)
python etl/migrate.py              # apply sql/migrations/ to an already-loaded DB, no reload
```

## Run the app
```powershell
streamlit run app/Home.py   # login page; the dashboard pages come in Phase 7
```

## Tests and benchmark
```powershell
pytest                          # everything (~45 s): security, titles, queries vs pandas
pytest -m "not slow"            # skip the pandas comparisons that load the big CSVs (~12 s)
python scripts/benchmark_queries.py   # every query 5x as movie_app_user -> reports/query_performance.md
```
Every test that writes runs in a transaction that is rolled back, so the database is
left unchanged. The analysis queries are in `sql/queries/` and are described, with
sample results, in [reports/query_results.md](reports/query_results.md).

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

## Manual login check
Start `streamlit run app/Home.py` and open http://localhost:8501. Use the passwords from `.env`.

1. **Admin:** log in as `admin` with `DEMO_ADMIN_PASSWORD`. You should see "Logged in as **admin** (admin)".
2. **User:** log out, then log in as `demo_user1` with `DEMO_USER_PASSWORD`. You should see "Logged in as **demo_user1** (user)".
3. **Wrong password:** log in as `demo_user1` with any other password. You should see "Invalid username or password." and stay on the login form.
4. **MovieLens user with no password:** MovieLens users have no username or password. Type a MovieLens id, e.g. `3`, as the username with any password. You should see the same generic message, with no hint whether the user exists.
5. **Logout:** log in as `demo_user1`, then click **Log out**. The login form should be back, and refreshing the page should not log you in again.

## Known behaviour
- Sequence and identity values are not transactional, so rolled-back inserts (for example by the tests) leave harmless gaps in ids such as `tags.tag_row_id`.

## Project layout
```
data/raw/      downloaded CSVs (git-ignored)
data/clean/    cleaned CSVs (git-ignored)
sql/           schema, constraints, triggers, analysis, extensions, roles, migrations/, queries/ (one per question)
etl/           download, clean, load, migrate, setup_security
app/           Streamlit app (Home.py = login, pages/)
tests/         security tests; query results checked against pandas
scripts/       query benchmark
reports/       cleaning, load, security, query results and performance reports; ER diagram
slides/        presentation
```
