# The project explained simply

This is a plain-language walk through the whole project, **in the order things happen**:
from the raw movie files on the internet, through cleaning and the database, to the
website you log into. Every file and every function is explained in one or two simple
sentences. (For the technical version, see [CODE_GUIDE.md](CODE_GUIDE.md).)

---

## The big picture in one minute

Think of the project as a **restaurant**:

| Restaurant | This project |
|---|---|
| Buying raw vegetables from the market | **Download** the MovieLens files from the internet (`etl/download.py`) |
| Washing and cutting them | **Clean** the files: fix bad rows, remove duplicates (`etl/clean.py`) |
| Putting everything on labelled shelves in the kitchen | **Load** the data into PostgreSQL tables (`etl/load.py` + `sql/*.sql`) |
| Locks on the doors, staff vs customer areas | **Security**: two database roles, passwords, "you can only change your own ratings" (`sql/roles.sql`, `etl/setup_security.py`) |
| Recipes | **Queries**: one SQL file per question (a)–(g) (`sql/queries/`) |
| The dining room and menu | **The Streamlit website**: login, pages, charts (`app/`) |
| The health inspector | **Tests** that check everything is right (`tests/`) |

The data: **MovieLens 25M** = 25 million star ratings (0.5 to 5 stars) that 162,541 people
gave to 62,423 movies, plus 1 million free-text tags ("funny", "twist ending") and a
"tag genome" (a score from 0 to 1 for how well each of 1,128 tags describes a movie).

**The order things run:**

```
ONE TIME (setup.bat):
  download.py  ->  clean.py  ->  load.py  ->  (schema.sql, COPY data, constraints.sql,
                                               triggers.sql, analysis.sql, setup_security.py)
EVERY TIME YOU USE THE APP (run_app.bat):
  Home.py (login + menu)  ->  a page in app/views/  ->  queries.py  ->  sql/queries/*.sql  ->  PostgreSQL
```

---

## Part 1. The files in the main folder (the "switches")

| File | In simple words |
|---|---|
| `setup.bat` | **The one-time "install everything" button.** Double-click it once. It checks Python is installed; makes your `.env` settings file if you don't have one (and stops so you can fill in passwords); refuses to continue while `.env` still says `change-me`; creates `.venv` (a private box of Python packages for this project); installs the packages; then runs download → clean → load. If any step fails, it stops there. |
| `run_app.bat` | **The "open the website" button.** Turns on `.venv`, installs any package that is missing, and starts Streamlit with `app\Home.py`. Then you open http://localhost:8501. |
| `set_passwords.bat` | **The "choose passwords" button.** Asks you for the passwords of admin, demo_user1, demo_user2, demo_user3 (typing is hidden) and saves them. |
| `.env` | **Your secret settings file.** Database address, and all passwords. Only on your laptop, never uploaded to GitHub. |
| `.env.example` | **An empty copy of `.env`** with `change-me` everywhere, so others know which settings exist. This one *is* on GitHub, so never put real passwords in it. |
| `requirements.txt` | **The shopping list of Python packages:** pandas/numpy (work with tables of data), psycopg/psycopg-pool (talk to PostgreSQL), python-dotenv (read `.env`), streamlit (the website), plotly (charts), pytest (tests). |
| `.gitignore` | **The "don't upload" list:** `.env`, the big data folders, `.venv`, caches. |
| `pytest.ini` | Tells the test tool where the tests are, and marks the slow ones. |
| `.streamlit/config.toml` | **Website settings:** never show scary error code to visitors, hide the developer menu, and the colours (white background, blue buttons). |
| `README.md` | The project's front page: what it is, results, how to run it. |
| `CODE_GUIDE.md` | The technical version of this guide. |
| `CLAUDE.md` | The project brief and working notes kept while building it. |

---

## Part 2. Getting and cleaning the data (ETL)

**ETL = Extract, Transform, Load**: get the data, fix it, put it in the database.

### `etl/download.py`: go to the market

Downloads `ml-25m.zip` (about 250 MB) from the GroupLens website and unpacks the six CSV
files into `data/raw/`. If the files are already there, it skips the work.

| Function | In simple words |
|---|---|
| `download()` | Downloads the zip. While downloading, it saves to a `.part` file and only renames it at the end, so a half-finished download is never mistaken for a good one. Skips if the zip is already there. |
| `extract()` | Takes the six CSV files out of the zip into `data/raw/`. Skips files already taken out. |
| `count_rows(path)` | Counts the lines in a CSV file (minus the header line) without loading the whole file into memory. |
| `main()` | Runs `download()` then `extract()`, prints each file's size and row count, and stops with an error if a file is missing. |

### `etl/clean.py`: wash and cut the vegetables

Reads the 6 raw CSVs, checks and fixes them, and writes **9 clean CSVs** into
`data/clean/`, one for each database table. Every check and how many rows it affected is
written into `reports/cleaning_report.md`.

Why 9 from 6? Because the raw `movies.csv` packs several things into one line, for example
`Toy Story (1995), Adventure|Animation|Children`. Clean data stores each fact once
(this is called **normalisation**), so it becomes a `movies` row, a `genres` list and a
`movie_genres` link table.

| Function | In simple words |
|---|---|
| `section(title)` | Starts a new section in the cleaning report (one per input file). |
| `log(check, count, action)` | Writes one line into the report: what was checked, how many rows were found, what was done. Also prints it. |
| `to_datetime_str(epoch_seconds)` | The raw files store time as "seconds since 1970" (e.g. 1147880044). This turns it into a normal date like `2006-05-17 15:34:04` (UTC time). |
| `clean_movies()` | Pulls the year out of the title ("Toy Story (1995)" → title "Toy Story", year 1995). Splits `Adventure|Animation|Children` into separate genres. Treats "(no genres listed)" as no genre. Returns the list of valid movie ids. |
| `clean_ratings(movie_ids)` | Cleans the 25 million ratings **in pieces of 2 million** (too big for memory at once). Removes empty rows, ratings outside 0.5–5, ratings for movies that don't exist, and duplicates (same person rating the same movie twice: keep the latest). Its small helper `process(df)` writes one cleaned piece to the output file. It is careful at the border between two pieces, so a duplicate can't hide across two pieces. |
| `clean_tags(movie_ids)` | Trims spaces and makes tags lowercase ("Funny " → "funny"), removes empty tags and duplicates, and gives each tag row its own number (`tag_row_id`), because the raw file has no id column. |
| `clean_links(movie_ids)` | Keeps the IMDb id as text, so leading zeros like `0114709` aren't lost. A missing TMDb id stays empty. |
| `clean_genome(movie_ids)` | Cleans the 1,128 genome tags, then checks the 15.6 million genome scores (in pieces): score between 0 and 1, the movie and tag exist, no duplicates. |
| `main()` | Runs all of the above in order, builds `users.csv` (every user id seen in ratings or tags), and writes the cleaning report. |

### `etl/db.py`: the key to the database (for the setup scripts only)

Connects to PostgreSQL as the **superuser** (the all-powerful owner), using the settings in
`.env`. Only the setup scripts use this; the website never does.

| Function | In simple words |
|---|---|
| `get_connection(dbname, autocommit)` | Opens a connection to PostgreSQL as the superuser. |
| `ensure_database()` | Creates the `movielens` database if it doesn't exist yet. |
| `run_sql_file(path, conn)` | Runs a whole `.sql` file. Either all of it succeeds, or nothing is changed (one "transaction"). |

---

## Part 3. Building the database (load)

### `etl/load.py`: put everything on the shelves

Loads the 9 clean CSVs into PostgreSQL and then builds everything around them. It deletes
and recreates the tables each time, so running it twice gives the same result. It takes
15–25 minutes.

**The trick for speed:** first pour all the data in, and only *afterwards* add the rules
(foreign keys) and indexes. Checking rules for 25 million rows one by one would be much slower.

| Function | In simple words |
|---|---|
| `header(n, title)` / `done(t0)` | Print "Step 3: loading..." and, at the end, "done in 42 s". |
| `preflight()` | Checks before starting: are all 9 clean CSVs there? Does the database exist (create it if not)? Is there at least 8 GB of free disk? |
| `copy_table(conn, table, columns)` | Pours one CSV into its table with PostgreSQL's fast `COPY` command, in 1 MB chunks, so even the 25-million-row file never has to fit in memory. Returns how many rows it loaded and how long it took. |
| `count_csv_rows(table)` | Counts the rows in one clean CSV (used for the report). |
| `load_csvs(conn)` | Loads all 9 tables in the right order (movies before ratings, because ratings point to movies) and prints the speed of each. |
| `apply_constraints(conn)` | Runs `sql/constraints.sql` one command at a time, timing each foreign key and index. |
| `show_fk_violations(conn, statement)` | If a foreign key fails (e.g. a rating points to a movie that doesn't exist), shows which rows are the problem. |
| `table_rows(conn, table)` | Counts rows in a table (for `users`, it leaves out the 4 app login accounts). |
| `check(results, label, left, right)` | Compares two numbers, prints OK or MISMATCH, and remembers the result. |
| `reconcile(conn, csv_rows)` | **The self-check.** Does every table have exactly as many rows as its CSV? Do the precomputed movie statistics match the real ratings? |
| `table_sizes(conn)` / `db_size(conn)` | Read how many MB each table and the whole database use. |
| `summary(conn, total_seconds)` | Prints the total time and the sizes. |
| `md_table(headers, rows)` | Turns a list of rows into a neat table for the report. |
| `write_report(...)` | Writes `reports/load_report.md` with all counts, checks, sizes and times. |
| `report_only()` | Only re-checks and rewrites the report, without reloading anything (`python etl/load.py --report-only`). |
| `full_load()` | **The whole thing, in order:** create tables (`schema.sql`) → pour in the CSVs → fill `movie_stats` (count, total and star histogram for each movie) → add rules and indexes (`constraints.sql`) → add triggers (`triggers.sql`) → add analysis helpers (`analysis.sql`) → set up security and logins → self-check → summary → report. |
| `main()` | Reads the command line: normal run = `full_load()`, with `--report-only` = `report_only()`. |

### The SQL files that `load.py` runs, in order

**`sql/schema.sql`: the shelves (10 tables).**

| Table | What one row is |
|---|---|
| `movies` | One movie: id, title, release year. |
| `genres` | One of the 19 genres (Action, Comedy, ...). |
| `movie_genres` | "Movie X belongs to genre Y". A movie with 3 genres has 3 rows. |
| `users` | One person. The 162,541 MovieLens people have only an id (they can't log in). The 4 app accounts also have a username, a scrambled password (hash) and a role (admin or user), with ids from 200000. |
| `ratings` | "User U gave movie M 4.5 stars at time T". Rules built in: only 0.5 to 5.0 in half steps; one rating per person per movie. |
| `tags` | "User U tagged movie M as 'funny' at time T". |
| `links` | A movie's IMDb and TMDb ids. |
| `genome_tags` | The 1,128 official genome tags. |
| `genome_scores` | "Tag T describes movie M with score 0.93". 15.6 million rows. |
| `movie_stats` | **A ready-made summary per movie:** number of ratings, total of stars, average, and how many ratings at each of the 10 star values (the "histogram"). A rule checks that the histogram always adds up to the count. This makes pages fast: no need to go through 25 million ratings each time. |

**`sql/constraints.sql`: the rules and the index cards.** Runs after the data is in.
- **Foreign keys (10):** "a rating must point to a real movie and a real user". If you delete a movie, its genres, links, genome scores and stats go with it, but a movie that still has ratings or tags **cannot** be deleted.
- **Indexes (7):** like the index at the back of a book, so PostgreSQL can jump straight to "all ratings of movie 1" or "movies from 1995" instead of reading everything.
- Ends with `ANALYZE`, which makes PostgreSQL count what's in each table so it can plan queries well.

**`sql/triggers.sql`: the automatic bookkeeper.**
- `movie_stats_sync()` + trigger `ratings_movie_stats`: **every time a rating is added, changed or deleted, the movie's statistics update by themselves** (count, total, histogram). That's why a new rating shows up on the chart immediately.
- `movie_stats_truncate()` + its trigger: if all ratings are wiped at once, the statistics are wiped too.
- They run with the owner's rights, so a normal user's rating can update the statistics even though the user isn't allowed to edit statistics directly.

**`sql/analysis.sql`: precomputed answers.**
- `tag_stoplist`: a small list of junk tags (like "seen it") that question (c) ignores.
- `mv_popular_tags_genre`: a **materialized view**, i.e. a saved answer: for each genre and tag, how many different people used it. Computing it live takes about 10 seconds; saved, it takes milliseconds.
- `mv_dataset_summary`: saved headline numbers for the Overview page (number of tags, rating period...).

**`sql/extensions.sql`:** switches on `pgcrypto`, PostgreSQL's tool for scrambling passwords (bcrypt).

**`sql/roles.sql`: the locks and keys (security).**
- **Two database "roles" (keys) for the website:**
  - `movie_admin`: can change anything (used only by the Admin page).
  - `movie_app_user`: can **read** all the movie data (but not password hashes) and can only **add or change ratings**. Nothing else.
- **Row-level security on `ratings`:** three rules: everyone can *read* all ratings, but you can only *add* or *change* a rating **with your own user id**. PostgreSQL itself enforces this, so even a bug in the website couldn't change someone else's rating.
- **`auth_login(username, password)`:** the login check, done **inside the database**. It compares the password with the stored scrambled version and returns only the user id, username and role, never the hash.

### `etl/setup_security.py`: hand out the keys

Runs `extensions.sql` and `roles.sql`, sets the role passwords, and creates the 4 login
accounts. Run at the end of every load, and can be run alone after changing passwords in `.env`.

| Function | In simple words |
|---|---|
| `env(key)` | Reads one setting from `.env`. Stops with a clear message if it's missing or still `change-me`. |
| `password_key(username)` | Says which line of `.env` holds an account's password: admin → `DEMO_ADMIN_PASSWORD`, demo_user2 → `DEMO_USER2_PASSWORD`, and so on. |
| `demo_password(username)` | Reads that account's password (for older `.env` files it falls back to one shared `DEMO_USER_PASSWORD`). |
| `set_role_passwords(conn)` | Sets the passwords of the two database keys (`movie_admin`, `movie_app_user`). |
| `pick_demo_user_ids(conn)` | Chooses which real MovieLens people become demo_user1–3: the lowest ids with 50–300 ratings, so the demo accounts already have a rating history (user ids 1, 2 and 4). |
| `seed_demo_accounts(conn)` | Creates or updates the admin account and the 3 demo users. The passwords are scrambled with bcrypt **inside PostgreSQL**; the plain password is never stored. |
| `setup(conn)` | Does all of the above in order. |
| `main()` | Connects as the superuser and calls `setup`. |

### `etl/set_passwords.py`: choose your own passwords (run by `set_passwords.bat`)

| Function | In simple words |
|---|---|
| `ask(username)` | Asks for the password twice, without showing what you type, and repeats until both match and the password is allowed. |
| `check(password)` | Refuses only passwords that would break the settings file: empty, starting/ending with a space, containing `'`, or `change-me`. Easy passwords are fine. |
| `write_env(values)` | Writes the 4 password lines into `.env` and leaves every other line untouched. |
| `main()` | Asks for all 4 passwords, saves them in `.env`, then runs `setup_security` so the database gets them. |

### `etl/migrate.py` and `sql/migrations/`: update without reloading

A full reload takes 15–25 minutes. When the database design changed after the data was
already loaded, a **migration** applies just the change in seconds.

| File / function | In simple words |
|---|---|
| `migrate.py` → `main()` | Runs every file in `sql/migrations/` in order, then re-applies the triggers, analysis helpers and security. |
| `001_phase4_fixes.sql` | New timestamps are stored in UTC; tag rows get automatic numbers. |
| `002_movies_identity.sql` | New movies get automatic ids (so the Admin page can add a movie). |
| `003_rating_histogram.sql` | Adds the 10-value star histogram to `movie_stats`. This made page (d) go from 6–10 seconds to a few milliseconds for big movies. |

---

## Part 4. The recipes: one SQL file per question (`sql/queries/`)

Each file is one question for the database. The website fills in the blanks (like which
movie) and runs it.

| File | The question it asks the database |
|---|---|
| `movie_search.sql` | "Which movies have a title like what I typed?" Titles that *start* with it come first, then the most-rated ones. |
| `overview_metrics.sql` | "How many movies, users, ratings, tags are there?" (Overview page) |
| `a_top_tags_for_movie.sql` | **(a)** "Which 5 genome tags describe this movie best?" |
| `genome_suggestions.sql` | "Give me some famous movies that *do* have genome data" (suggested when a movie has none). |
| `b_top_movies.sql` | **(b)** "Which 10 movies have the highest average rating, among those with at least N ratings (overall or in one year)?" Reads the ready-made `movie_stats`. |
| `c_popular_tags_by_genre.sql` | **(c)** "Which tags are used most for each genre?" (from the saved answer) |
| `genres_list.sql` | "List the 19 genres" (for the dropdown). |
| `d_movie_summary.sql` | **(d)** "This movie's title, year, number of ratings and average." |
| `d_rating_distribution.sql` | **(d)** "How many ratings at each of the 10 star values?" (from the stored histogram). |
| `e_ratings_per_movie_distribution.sql` | **(e)** "Group all movies by how many ratings they have (1, 2–5, 6–10, ...)." |
| `e_ratings_per_movie_summary.sql` | **(e)** "Fewest, middle, average and most ratings per movie, and what share of all ratings the top 10% of movies get." |
| `f_years.sql` | "Which release years exist?" (for the dropdown) |
| `f_top_genre_for_year.sql` | **(f)** "In year Y, which genre had the most movies?" (ties all shown) |
| `g_genre_coverage.sql` | **(g)** "What share of movies and of ratings does each genre have?" |
| `my_ratings.sql` | "Show me *my* ratings, newest first, one page at a time." |
| `my_rating_for_movie.sql` | "What did *I* rate this movie?" |

---

## Part 5. The website (`app/`)

Streamlit turns a Python file into a web page: every time you click something, Streamlit
runs the page's Python file again from top to bottom and redraws it.

Below, the files are listed **from the bottom layer (talking to the database) up to the
pages you see.**

### `app/db.py`: the website's keys to the database

The website **never** uses the superuser. It only has the two limited keys. It keeps a few
connections open and reuses them (a **connection pool**), which is much faster than
connecting for every click.

| Function | In simple words |
|---|---|
| `_pool(role)` | Creates the set of reusable connections for one key (1 to 4 connections). Made only once. |
| `_reset(conn)` | Cleans a connection when it's returned, so the next person starts fresh. |
| `reset_pools()` | Throws away all connections and starts over. Used after a database error (e.g. the database was reloaded). |
| `_borrow(role, commit)` | Borrows a connection for one job: saves the changes if everything went fine, undoes them if there was an error. |
| `user_conn(user_id, commit)` | A connection with the **user key**. It also tells PostgreSQL "the logged-in person is user 1", so the row-level security rules know whose ratings may be changed. |
| `admin_conn(commit)` | A connection with the **admin key**. Only the Admin page uses it. |

### `app/auth.py`: login and the page guards

| Function | In simple words |
|---|---|
| `login(username, password)` | Asks the database's `auth_login` "is this password right?". If yes, returns the user's id, username and role. If no (wrong password, unknown user, empty box), returns nothing. |
| `logout()` | Forgets who is logged in. |
| `current_user()` | "Who is logged in right now?" (or nobody). |
| `require_login()` | The first line of every page: if nobody is logged in, stop and show "please log in". |
| `require_role(role)` | Used by the Admin page: if you're not an admin, stop. |

### `app/navigation.py`: the menu for each role

| Function | In simple words |
|---|---|
| `pages_for(role)` | Gives the list of menu items: logged out → only Login; user → Overview, (a)–(g), My ratings; admin → the same plus Admin. |

### `app/Home.py`: the front door (the file Streamlit starts)

What it does, top to bottom: sets the browser tab title and icon → works out who is logged
in → builds the menu for that role → shows "Logged in as ..." and a Log out button in the
sidebar → runs the page you chose. If the database has a problem, you see a short friendly
message instead of an error, and the connections and cache are reset.

| Function | In simple words |
|---|---|
| `login_page()` | Draws the login page: Username box, hidden Password box, Log in button. When you click, it calls `login()`. Right password → remember you and reload into the Overview. Wrong → "Invalid username or password." (the same message for every mistake, so nobody can find out which usernames exist). |
| `build_navigation(user)` | Turns the list from `pages_for()` into Streamlit's menu. |

### `app/queries.py`: the waiter who takes the recipes to the kitchen

The **only** place the website runs the question SQL files. Each function reads one file
from `sql/queries/`, runs it with the user key in read-only mode, and returns the answer
as a table (a pandas DataFrame).

| Function | In simple words |
|---|---|
| `load_sql(name)` | Reads `sql/queries/<name>.sql` (once, then remembers it). |
| `run_query(name, params)` | Runs that SQL with the blanks filled in and returns the result table. |
| `display_title(title)` | MovieLens stores "Matrix, The"; this shows it as "The Matrix" (also handles foreign words like "Le", "Die", "El"). |
| `_with_display_titles(df)` | Applies `display_title` to every title in a result. |
| `stored_form(query)` | The reverse, for searching: "the matrix" → "matrix, the". |
| `_like_escape(text)` | Makes `%` and `_` in your search count as normal letters (in SQL they are wildcards). |
| `search_patterns(query)` | Prepares both forms of your search text ("the matrix" and "matrix, the"). |
| `search_movies(query, limit)` | The movie search box. |
| `list_genres()` / `list_years()` | The lists for the genre and year dropdowns. |
| `overview_metrics()` | The Overview numbers. |
| `top_tags_for_movie(movie_id)` | Question (a). |
| `genome_suggestions(limit)` | Movies to suggest when one has no genome data. |
| `top_movies(min_ratings, release_year)` | Question (b). |
| `popular_tags_by_genre(top_n, genre)` | Question (c). |
| `rating_distribution(movie_id)` / `movie_summary(movie_id)` | Question (d): the 10 bars, and the count and average. |
| `ratings_per_movie_distribution()` / `ratings_per_movie_summary()` | Question (e). |
| `top_genre_for_year(release_year)` | Question (f). |
| `genre_coverage()` | Question (g). |
| `my_ratings(user_id, limit, offset)` | One page of your own ratings. |
| `my_rating_for_movie(user_id, movie_id)` | Your own rating of one movie. |

### `app/data.py`: the memory (cache)

Questions that give **everybody the same answer** (like "top 10 movies") are remembered
for 10 minutes, so the second visitor gets the answer instantly without asking the
database again. Your personal data (My ratings) is **never** cached.

| Function | In simple words |
|---|---|
| `_cached(func)` | Wraps a query function so its answers are remembered for 10 minutes. |
| `clear()` | Forgets everything remembered. Called after every rating or admin change, so all charts show the new numbers immediately. |

### `app/charts.py`: one look for every chart

| Function | In simple words |
|---|---|
| `_style(fig, ...)` | Gives a chart the common look: white background, title, axis names, light grid lines. |
| `_labels(text, highlight)` | Decides which bars show their number: all bars if there are 10 or fewer, otherwise only the highlighted ones (so it doesn't get cluttered). |
| `hbar(labels, values, ...)` | Makes a horizontal bar chart, biggest at the top, optionally with some bars highlighted. |
| `vbar(labels, values, ...)` | Makes a vertical bar chart, in the given order. |

### `app/components.py`: Lego pieces used on many pages

| Function | In simple words |
|---|---|
| `fmt_int(n)` | Writes 25000095 as "25,000,095". |
| `fmt_year(year)` | Writes " (1999)", or nothing if the year is unknown. |
| `movie_label(row)` | One search result line: "The Matrix (1999) · 72,674 ratings". |
| `page_header(question, definition)` | The page title (the question from the assignment) and a short note on exactly how it is measured. |
| `flash(message, kind)` / `show_flash()` | Save a message ("Rating saved!") and show it after the page reloads. |
| `error_box(message, exc)` | Shows a friendly error; the technical details go only to the console. |
| `metric_row(items)` | A row of big number tiles (e.g. "Average 4.15 ★", "Ratings 72,674"). |
| `chart_with_table(fig, table, key)` | Shows the chart, plus a "Show data table" switch to see the exact numbers. |
| `movie_picker(key)` | The movie search box and result list. Remembers your chosen movie when you switch pages. Its helpers `_pick` and `set_movie` store the choice. |
| `selected_movie(movie_id)` | Gets the chosen movie's title, year, count and average. |
| `rating_control(user, movie_id, title, key)` | "Rate this movie": a slider from 0.5 to 5.0 and a Save button. After saving: clear the cache, show the new average, reload the page. |

### `app/ratings.py`: the only thing a normal user can change

| Function | In simple words |
|---|---|
| `validate_rating(rating)` | Checks the number is 0.5 to 5.0 in half steps, with a clear message if not. (The database checks again.) |
| `upsert_my_rating(user_id, movie_id, rating)` | "Upsert" = **up**date if it exists, in**sert** if not. Saves your rating using the user key with your id, so the database itself blocks changing anybody else's rating. The trigger then updates the movie's statistics. |

### `app/admin_ops.py`: everything the Admin page can do

Each action is one all-or-nothing database job with the admin key. If the admin makes a
fixable mistake (empty title...), it raises `AdminError` with a friendly message.
`HasActivity` is a special message meaning "this account still has ratings or tags"; its
`__init__` simply stores those two counts so the page can show them.

| Function | In simple words |
|---|---|
| `clean_title` | The title must not be empty. |
| `clean_year` | The year must be between 1870 and 2030, or unknown. |
| `clean_username` | The username must have at least 3 characters and can't be only digits (so it can't be confused with a user id). |
| `check_password` | New passwords made on the Admin page must have at least 8 characters. |
| `check_role` | The role must be `admin` or `user`. |
| `movie_detail(movie_id)` | A movie's details, its genres, and how many ratings/tags depend on it. |
| `update_movie(...)` | Change a movie's title, year and genres. Helper `_set_genres` replaces the genre list. |
| `add_movie(title, release_year, genre_ids)` | Add a new movie (the database picks the id). |
| `delete_movie(movie_id)` | Delete a movie. Refused if it has ratings or tags. |
| `list_accounts()` | List the login accounts with how many ratings and tags each has. |
| `create_account(username, password, role)` | Make a new login account (password scrambled inside PostgreSQL). |
| `set_role(user_id, role, acting_user_id)` | Make someone admin or user. You can't remove your own admin rights. |
| `reset_password(user_id, password)` | Give an account a new password. |
| `delete_account(...)` | Delete an account. If it has ratings or tags, first say how many and only delete them after the admin confirms. You can't delete yourself. |
| `user_ratings(user_id, limit)` | See any user's ratings. |
| `update_rating(...)` / `delete_rating(...)` | Change or delete any single rating. |

### `app/views/`: the pages you see

Every page does the same three things: **1)** check you're logged in, **2)** get its data
(through `data.py` cache or `queries.py`), **3)** draw it with `charts.py` and `components.py`.

| Page file | What you see and do |
|---|---|
| `overview.py` | Big number tiles about the dataset (62,423 movies, 162,541 users, 25 million ratings, ...) and a list of the questions you can explore. |
| `a_movie_tags.py` | **(a)** Search a movie → bar chart of the 5 tags that describe it best (score 0 to 1). If the movie has no genome data, it says so and suggests 3 famous movies that have it. |
| `b_top_movies.py` | **(b)** A slider "minimum number of ratings" and two tabs: Overall and By year. Its function `show(...)` draws the top-10 chart and table for one tab, or explains when fewer than 10 movies qualify. |
| `c_tags_by_genre.py` | **(c)** Pick a genre and how many tags → bar chart. "All genres" shows 19 small tables. |
| `d_rating_distribution.py` | **(d)** Search a movie → tiles (average, number of ratings, **your** rating) → bar chart of how many people gave each star value → "Rate this movie" slider. Save a rating and the chart changes instantly (the demo highlight). |
| `e_ratings_per_movie.py` | **(e)** Summary tiles and a bar chart of how many movies have 1, 2–5, 6–10, ... ratings, with a "log scale" checkbox (because a few movies have huge numbers). |
| `f_genre_by_year.py` | **(f)** Pick a year → a headline naming the top genre (all of them if tied) → bar chart of every genre with the winner highlighted. |
| `g_genre_coverage.py` | **(g)** Switch between "share of movies" and "share of ratings" → bar chart per genre, including "(no genre)". |
| `my_ratings.py` | Rate a movie, and a list of **your own** ratings (newest first, page by page). Pick a row to change it. Users can't delete ratings; the page explains this. |
| `admin.py` | **Admin only.** Three tabs: **Movies** (edit, add, delete), **Users** (create, change role, reset password, delete), **Ratings** (look up anyone's ratings, change or delete one). Its helpers: `attempt(...)` runs one action and turns a mistake into a friendly message; `done(...)` clears the cache and shows "done"; `genre_select(...)` is the multi-choice genre box. |

### Example: what happens when you rate *The Matrix* 5 stars on page (d)

1. You move the slider to 5.0 and click **Save** (`components.rating_control`).
2. `ratings.validate_rating` checks 5.0 is allowed.
3. `ratings.upsert_my_rating` borrows a **user key** connection from `db.user_conn`, which tells PostgreSQL "this is user 1".
4. PostgreSQL's **row-level security** checks the rating belongs to user 1 → allowed.
5. The **trigger** `movie_stats_sync` adds 1 to The Matrix's count, 5 to its total, and 1 to the "5.0" slot of its histogram.
6. `data.clear()` empties the cache, and the page reloads.
7. The page asks `d_movie_summary.sql` and `d_rating_distribution.sql` again → the new average and the taller 5.0 bar appear.

---

## Part 6. The checks (`tests/`)

Run them all with `pytest` (151 tests, about 1 minute). Tests that change data undo their
changes afterwards, so the database stays the same.

| File | What it checks, simply |
|---|---|
| `conftest.py` | **Shared helpers for all tests:** makes the `app/` code importable; `superuser_conn` (a database connection that never saves); `demo_password` (an account's password from `.env`, worked out by `_demo_password`); `demo1` (demo_user1's id, looked up by `_user_id`); `other_rating` (a rating that belongs to someone else); `unrated_movie` (a movie demo_user1 hasn't rated). |
| `test_titles.py` | "Matrix, The" ↔ "The Matrix" conversion and the search patterns work. No database needed. |
| `test_security.py` | **The locks work:** the user key can read movies but not password hashes; it can't change any table except ratings; you can add/change your own rating and the statistics follow; changing someone else's rating does nothing and adding one for them is refused; bad ratings (like 7 stars) are refused by Python *and* the database; login works only with the right password and never returns the hash; each demo user's password opens only their own account. |
| `test_queries.py` | **The answers are right:** every question (a)–(g) and the search is computed a second, independent way with pandas from the CSV files, and both answers must match. Small helpers (`read`, `movies`, `genres`, `ratings`, `tags`, `genome`, `expected_top`, ...) load the CSVs for this. |
| `test_app.py` | **The website works,** by clicking through it automatically (Streamlit's AppTest): the right menu per role; the login form has a hidden password box and shows no passwords; the right password logs you in with the right role; any wrong login gets the same message; a user can't reach Admin; every page opens without errors; saving a rating on (d) changes the count and average; the admin safety rules (can't delete or demote yourself, can't silently delete a user who has ratings, input checks, add/delete a movie, create/delete an account). Helpers: `app_as` (open the app as someone), `submit_login` (type and click Log in), `try_switch` (try to open a page), `titles`/`metric` (read the page). |

---

## Part 7. Extra scripts and reports

| File | In simple words |
|---|---|
| `scripts/benchmark_queries.py` | **Stopwatch for the queries.** `time_query` runs a query 5 times and times it; `explain` asks PostgreSQL *how* it ran a slow query; `main` times all 22 queries, fails if any takes over 2 seconds, and writes `reports/query_performance.md`. |
| `scripts/page_timings.py` | **Stopwatch for the pages.** `run_page` opens one page as a logged-in user and times it; `main` times all 12 pages "cold" (cache empty) and "warm" (from cache) and writes `reports/page_timings.md`. |
| `reports/cleaning_report.md` | Every cleaning check and how many rows it affected. |
| `reports/load_report.md` | Row counts vs the CSVs, the self-checks, sizes and load times. |
| `reports/er_diagram.md` | The diagram of all tables and how they connect. |
| `reports/security.md` | Who can do what, row-level security, and how login works. |
| `reports/query_results.md` | Each question's answer, with an insight. |
| `reports/query_performance.md` | How fast each query is (all under 2 seconds). |
| `reports/page_timings.md` | How fast each page opens. |

---

## Summary in five lines

1. **`setup.bat`** downloads 25 million ratings, **cleans** them and **loads** them into PostgreSQL (10 tables).
2. **Rules, indexes, a trigger and saved answers** keep the data correct and the pages fast.
3. **Two limited database keys + row-level security + bcrypt login** make sure users can only change their own ratings.
4. **`run_app.bat`** opens the Streamlit website: log in → menu for your role → pages (a)–(g) with charts → rate movies.
5. **151 tests** prove the answers, the security and the website all work.
