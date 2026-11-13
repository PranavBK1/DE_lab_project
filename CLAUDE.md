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
4. **Load** (etl/load.py) (DONE): COPY, idempotent. Populate movie_stats. Print a reconciliation table and the load time. Order: schema.sql → COPY → fill movie_stats → constraints.sql → triggers.sql. Results in reports/load_report.md.
5. **Roles and authentication**
   - movie_admin: all privileges. movie_app_user: SELECT on all tables, plus INSERT and UPDATE on ratings only.
   - bcrypt login; session state holds the role. Users rate only their own movies (`WHERE user_id = :me`). Admin page to manage movies and users.
   - Demo accounts: 1 admin and 2–3 users mapped to real userIds. Credentials go in .env or the README, never in code.
6. **Queries** (sql/queries/, one per question), each tested against pandas, each under ~2 s:
   - **movie_stats rule (applies to every query):** a movie that loses its last rating keeps its movie_stats row with rating_count = 0 and avg_rating NULL. Every query that reads movie_stats must filter on `rating_count >= threshold` (question b) or `rating_count > 0` (anything else). Movies never rated have no movie_stats row at all.
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
8. **Testing**: run all tests, click through both roles, take screenshots, write the README.
9. **Slides**: 12–15 slides (title, problem, architecture, cleaning, ER, security, a–g, demo script, learnings).

## 6. Rules
- Ask before changing the stack decisions or the Phase 6 definitions.
- Never commit .env, raw data or passwords.
- Use parameterised SQL only; never build queries by string formatting.
- Keep code simple and readable; it must be explained in a demo.
- After each phase, report what was done, what was verified, and anything unresolved.
