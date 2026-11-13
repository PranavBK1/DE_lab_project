# Project Brief: MovieLens Data Engineering Dashboard

Work phase by phase. At the end of each phase, show the results and wait for approval before starting the next one.

## Confirmed decisions (2026-11-13)
- PostgreSQL 17 (installed via winget, port 5432), Streamlit + Plotly, Python 3.13, bcrypt users table, .env for credentials.

## 1. Context
Course: DS5003 Data Engineering Lab, IIT Palakkad. Load the MovieLens 25M CSVs into a database, analyse them with SQL, and build a dashboard with login and roles that answers 7 questions. A slide deck for a live demo is also required.
Dataset: https://files.grouplens.org/datasets/movielens/ml-25m.zip. It has 6 files: movies, ratings, tags, links, genome-tags and genome-scores.

## 3. Required features
- Process the CSVs into a database; the data may be reorganised into different tables.
- Query and visualise the data.
- A dashboard that answers questions (a)–(g).
- Roles: admin and user. Users may modify only movie ratings.
- Must include: login with roles, data cleaning, visualisations, user interaction. Deliverables: slides and a live demo.

## 5. Phases
1. **Setup** (DONE): folder structure, requirements, .env.example, .gitignore, README. Download ml-25m and print row counts.
2. **Cleaning** (etl/clean.py) (DONE)
   - movies: extract release_year with `\((\d{4})\)\s*$`, strip it from the title, trim. Count titles with no year (NULL).
   - genres: split on `|`. Treat "(no genres listed)" as no genre and count those movies.
   - ratings: values must be in {0.5..5.0}. Convert the timestamp to a datetime. Drop duplicate (user, movie) pairs, keeping the latest.
   - tags: trim, lowercase, drop empty tags, drop duplicate (user, movie, tag), convert timestamps.
   - links: imdbId as a string; tmdbId nullable.
   - genome: relevance must be in [0, 1]; check that the foreign keys exist.
   - Check that ratings, tags and genome movieIds exist in movies.
   - Process ratings and genome-scores in chunks.
   - Write reports/cleaning_report.md with counts.
3. **Schema** (DONE): sql/schema.sql (tables, PKs, CHECKs), sql/constraints.sql (FKs, indexes; applied after the load), sql/triggers.sql (movie_stats triggers, incl. TRUNCATE), etl/db.py, reports/er_diagram.md
   - Tables: movies, genres, movie_genres, users (every MovieLens userId gets a row with no password; demo accounts get passwords; role is admin or user), ratings (NUMERIC(2,1) between 0.5 and 5.0, PK(user, movie)), tags, genome_tags, genome_scores, links.
   - movie_stats(count, sum, avg), kept current by a trigger on ratings.
   - Indexes: ratings(movie_id), tags(movie_id), movie_genres(genre_id), movies(release_year), genome_scores(movie_id, relevance DESC).
   - ER diagram in reports/.
4. **Load** (etl/load.py) (DONE): COPY, idempotent. Populate movie_stats. Print a reconciliation table and the load time. Order: schema.sql → COPY → fill movie_stats → constraints.sql → triggers.sql. Results in reports/load_report.md (a full run writes it with step timings; `--report-only` rewrites it from the live DB without reloading). Fixes to an already-loaded DB go in sql/migrations/ (applied by etl/migrate.py) AND in the source SQL files.
5. **Roles and authentication** (DONE): sql/roles.sql, etl/setup_security.py (called by load.py), app/db.py, app/auth.py, app/ratings.py, app/Home.py, tests/test_security.py, reports/security.md
   - movie_admin: all privileges + BYPASSRLS. movie_app_user: SELECT on all tables except users (column-level SELECT without password_hash), plus INSERT (user_id, movie_id, rating, rated_at) and UPDATE (rating, rated_at) on ratings only; no DELETE.
   - Row-level security on ratings: users can modify only their own ratings, enforced by the DATABASE via app.current_user_id (set per transaction by app/db.py user_conn).
   - bcrypt login (cost 12) checked INSIDE PostgreSQL by the SECURITY DEFINER function auth_login(username, password) with pgcrypto crypt(); the hash never leaves the DB. Hashes are made with crypt(%s, gen_salt('bf', 12)) in setup_security.py (Python bcrypt's $2b$ hashes do not verify in pgcrypto). Session state holds the role.
   - Demo accounts: admin (id 200000) and demo_user1..3 → MovieLens user_ids 1, 2, 4. Passwords only in .env.
   - App code: use user_conn(user_id) for user actions and admin_conn() on Admin pages; never the superuser. One `with` block = one transaction.
   - **Grants rule:** every new table / view / materialized view the app reads must be added BY NAME to the movie_app_user GRANT list in sql/roles.sql (no ALTER DEFAULT PRIVILEGES), and load.py must create it BEFORE setup_security runs.
6. **Queries** (DONE) (sql/queries/, one per question), each tested against pandas, each under ~2 s:
   - Files: a_top_tags_for_movie, b_top_movies, c_popular_tags_by_genre, d_rating_distribution + d_movie_summary, e_ratings_per_movie_distribution + e_ratings_per_movie_summary, f_top_genre_for_year + f_years, g_genre_coverage, movie_search, genres_list. Run ONLY through app/queries.py (one function per file, read-only user_conn, returns a DataFrame).
   - New DB objects (sql/analysis.sql, run by load.py after triggers.sql and before setup_security; granted by name in roles.sql): tag_stoplist (the ONE stop list for (c), 19 tags), mv_popular_tags_genre (distinct users + applications per genre x tag; rebuilt on every load; tags are not editable in the app).
   - Titles: MovieLens stores "Matrix, The". Always show titles through queries.display_title(); search through queries.search_movies(), which also tries the stored form ("the matrix" -> "matrix, the").
   - Tests: tests/test_queries.py (pandas, marked slow), tests/test_titles.py. Benchmark: scripts/benchmark_queries.py -> reports/query_performance.md. Results for slides: reports/query_results.md.
   - **movie_stats rule (applies to every query):** a movie that loses its last rating keeps its movie_stats row with rating_count = 0 and avg_rating NULL. Every query that reads movie_stats must filter on `rating_count >= threshold` (question b) or `rating_count > 0` (anything else). Movies never rated have no movie_stats row at all.
   - Always LEFT JOIN movie_stats; treat a missing row as rating_count = 0; filter rating_count >= threshold for question (b) and rating_count > 0 elsewhere; avg_rating may be NULL. (3,376 of the 62,423 movies have no ratings, so an INNER JOIN would silently drop them.)
   - a. Top-5 genome tags for a movie by relevance. Show "No genome data" when there is none.
   - b. Top-10 by average rating, overall and per release year, from movie_stats, with an adjustable minimum-ratings threshold (default 50).
   - c. Most popular user tags per genre (ROW_NUMBER), excluding junk tags such as "in netflix queue".
   - d. Rating distribution for a movie, every value 0.5–5.0, including zero counts.
   - e. Histogram of rating_count per movie, on a log scale.
   - f. Genre with the most releases in a selected year. Show all genres and handle ties.
   - g. Count and % of movies per genre. Note that the %s add up to more than 100%.
7. **Dashboard**
   - Login, then a sidebar filtered by role. One page per question, each with a chart and a "show table" toggle.
   - Controls: title autocomplete (a, d), year selector (b, f), genre selector (c), min-ratings slider (b).
   - My Ratings page. Admin page.
   - Use st.cache_data and clear it after a rating changes.
   - The Admin page must catch ForeignKeyViolation when deleting a user and show a clear message, or offer to delete that user's ratings and tags first after confirmation. (ratings/tags FKs to users have no ON DELETE CASCADE, on purpose.)
8. **Testing**: run all tests, click through both roles, take screenshots, write the README.
9. **Slides**: 12–15 slides (title, problem, architecture, cleaning, ER, security, a–g, demo script, learnings).

## 6. Rules
- Ask before changing the stack decisions or the Phase 6 definitions.
- Never commit .env, raw data or passwords.
- Use parameterised SQL only; never build queries by string formatting.
- Keep code simple and readable; it must be explained in a demo.
- After each phase, report what was done, what was verified, and anything unresolved.
