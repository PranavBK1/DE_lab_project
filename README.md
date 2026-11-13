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
streamlit run app/Home.py   # run from the project root, so .streamlit/config.toml is used
```
Open http://localhost:8501 and log in with a demo account (below). The menu depends on
the role: a user sees the Overview, the 7 question pages and **My ratings**; an admin
also sees **Admin**. Logged out, only the login page exists.

The app connects as `movie_app_user` (and `movie_admin` on the Admin page) through small
connection pools, never as the superuser. Shared results are cached for 10 minutes,
and every rating change or admin edit clears the cache, so all charts show the new
numbers at once. If PostgreSQL is down, pages show "Database unavailable, please try
again" instead of an error trace.

### Pages
| page | question | controls |
|---|---|---|
| Overview | dataset at a glance | links to every page |
| (a) Tags of a movie | top-5 genome tags for a movie | movie search |
| (b) Top-rated movies | top 10 by average rating, overall and per year | min-ratings slider, *Overall / By year* tabs, year |
| (c) Popular tags by genre | most popular user tags per genre | genre (or all genres), tags per genre |
| (d) Rating distribution | how a movie's ratings spread over 0.5–5.0 stars | movie search, **rate this movie** |
| (e) Ratings per movie | histogram of ratings per movie | log-scale toggle |
| (f) Top genre by year | genre with the most releases in a year (ties shown) | year |
| (g) Genre coverage | count and % of movies (or ratings) per genre | share of movies / share of ratings |
| My ratings | the user's own ratings, newest first, editable | movie search, page, select a row to edit |
| Admin (admin only) | manage movies, accounts and ratings | tabs *Movies / Users / Ratings* |

Every analysis page has a "Show data table" toggle under its chart.

### Browser check list
Use the passwords from `.env`. Steps 6–8 use *Sabrina (1995)* (12k ratings, loads in under 1 s); see
Known behaviour for blockbusters on page (d).

1. Open http://localhost:8501 while logged out. Only **Log in** is in the menu, and there is no Admin entry.
2. Log in as `demo_user1`. The sidebar shows "Logged in as **demo_user1** (user)", and the menu has Overview, (a)–(g) and My ratings, **but no Admin**.
3. **Overview:** the tiles show 62,423 movies, about 25.0M ratings, 1,093,350 tags, and 13,816 movies with genome data (22.1%). The links open each page.
4. **(a):** search `the matrix`, pick *The Matrix (1999)*. You get 5 bars (dystopic future, scifi, cyberpunk, …) on a 0–1 axis. Then search `terminator: dark` and pick *Terminator: Dark Fate (2019)*, which has no genome data (it is too recent). You get the info message and 3 suggestion buttons, and clicking one loads its tags.
5. **(b):** the overall top 10 starts with *Planet Earth II*. Move the slider to 1,000 and the list changes. In the *By year* tab, 1995 starts with *The Usual Suspects*. With the slider at 1,000, pick 1915: it should say that fewer than 10 (or no) movies qualify.
6. **(d) rating, the live-demo moment:** search `sabrina`, pick *Sabrina (1995)*. Note the average and the count. Under **Rate this movie**, choose 5.0 and click **Save rating**. A green message shows the new average, the count goes up by 1, "Your rating" shows 5.0 ★, and the 5.0 bar grows by 1.
7. **Cache cleared after the rating:** open **Overview**. The *Ratings* tile is exactly 1 higher than in step 3 (e.g. 25,000,096). On (g), *Share of ratings*, the Comedy and Romance rating counts in the data table also went up by 1. This works because every write clears the shared cache.
8. **My ratings:** *Sabrina* is at the top of the list (newest first). Select its row, change the rating to 2.0 and save; the average updates again. The page explains that users cannot delete ratings.
9. **(c), (e), (f), (g):**
   - (c) *All genres* shows a grid of 19 small tables; choosing *Horror* gives a bar chart.
   - (e) tick *Log scale*.
   - (f) 1995 says Drama (297 movies); 1916 shows a tie between **Comedy and Drama**, both bars in blue.
   - (g) switch between *Share of movies* and *Share of ratings*, and check the note saying the shares add up to more than 100%.
10. Log out, then log in as `admin`. The menu now has **Admin**.
11. **Admin edit:**
    - *Movies* tab: search `sabrina`, add the genre *Drama* (or change the title), then save. A green message appears. Undo the change.
    - *Ratings* tab: user_id `1` lists demo_user1's ratings. Set the Sabrina rating back, or delete it with the confirmation checkbox, to restore the original state.
12. **Blocked user delete:** in *Users*, choose `demo_user2` and open **Delete this account** → **Delete account**. You should see "This user has 184 ratings and 0 tags. Delete them first?" with a confirm checkbox. **Do not confirm.** Then choose your own `admin` account: delete and demote are not offered.
13. **Logout:** click **Log out**. You are back on the login page, and refreshing does not log you in again.

## Tests and benchmark
```powershell
pytest                          # everything (~45 s): security, titles, queries vs pandas
pytest -m "not slow"            # skip the pandas comparisons that load the big CSVs (~12 s)
python scripts/benchmark_queries.py   # every query 5x as movie_app_user -> reports/query_performance.md
python scripts/page_timings.py        # cold/warm load of every page -> reports/page_timings.md
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
- Sequence and identity values are not transactional, so rolled-back inserts (for example by the tests) leave harmless gaps in ids such as `tags.tag_row_id` and `movies.movie_id`.
- **Page (d) for blockbusters is slow the first time (6–10 s)**, e.g. Forrest Gump, The Matrix or Toy Story. Their ratings are spread over about 53,000 pages of the 1.2 GB `ratings` table, which this laptop cannot keep in memory. After the first load, the page comes from the cache in under 0.1 s, until the next rating change clears it. A movie with a few hundred ratings takes under 1 s. The fix options are in [reports/query_performance.md](reports/query_performance.md).
- The (c) tag counts and the Overview's tag / genome / rating-period tiles come from materialized views built at load time. An admin's genre edits show up in (c) after the next `python etl/migrate.py` or full load.

## Project layout
```
data/raw/      downloaded CSVs (git-ignored)
data/clean/    cleaned CSVs (git-ignored)
sql/           schema, constraints, triggers, analysis, extensions, roles, migrations/, queries/ (one per question)
etl/           download, clean, load, migrate, setup_security
app/           Streamlit app: Home.py (login + navigation), views/ (one page each), queries, data (cache), charts, components, admin_ops
.streamlit/    Streamlit config (theme, no error details for users)
tests/         security, queries vs pandas, titles, app (AppTest)
scripts/       query benchmark, page timings
reports/       cleaning, load, security, query results and performance reports; ER diagram
slides/        presentation
```
