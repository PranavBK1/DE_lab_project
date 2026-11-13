"""Bulk-load the cleaned CSVs into PostgreSQL (Phase 4).

Usage:
    python etl/load.py                 full reload (drops and recreates every table)
    python etl/load.py --report-only   only write reports/load_report.md from the
                                       current database; nothing is reloaded

Idempotent: every run drops and recreates the tables, so running it twice
gives the same final state.

Order (constraints and triggers come AFTER the data, which is much faster):
    schema.sql -> COPY 9 CSVs -> fill movie_stats -> constraints.sql -> triggers.sql
    -> setup_security (roles.sql, role passwords, demo accounts)
    -> reconciliation -> reports/load_report.md

schema.sql drops the tables, which also drops their grants, the row-level
security policies and the demo accounts, so setup_security re-creates them.
"""
import argparse
import re
import shutil
import sys
import time
from datetime import datetime, timezone

import psycopg
from psycopg import sql

from db import ROOT, ensure_database, get_connection, run_sql_file
from setup_security import setup as setup_security

CLEAN = ROOT / "data" / "clean"
SQL_DIR = ROOT / "sql"
REPORT = ROOT / "reports" / "load_report.md"
BLOCK = 1024 * 1024            # stream each CSV to the server in 1 MB blocks
MIN_FREE_GB = 8
APP_USER_ID_START = 200000     # app accounts (users_user_id_seq); MovieLens ids are below this

# Load order, with the explicit column list of each table (= the CSV header).
TABLES = [
    ("genres",        ["genre_id", "name"]),
    ("movies",        ["movie_id", "title", "release_year"]),
    ("movie_genres",  ["movie_id", "genre_id"]),
    ("users",         ["user_id"]),
    ("links",         ["movie_id", "imdb_id", "tmdb_id"]),
    ("genome_tags",   ["tag_id", "tag"]),
    ("genome_scores", ["movie_id", "tag_id", "relevance"]),
    ("ratings",       ["user_id", "movie_id", "rating", "rated_at"]),
    ("tags",          ["tag_row_id", "user_id", "movie_id", "tag", "tagged_at"]),
]

# Pulls the pieces out of an "ALTER TABLE .. ADD CONSTRAINT .. FOREIGN KEY" statement.
FK_RE = re.compile(
    r"ALTER TABLE\s+(\w+)\s+ADD\s+CONSTRAINT\s+(\w+)\s+"
    r"FOREIGN KEY\s*\((\w+)\)\s+REFERENCES\s+(\w+)\s*\((\w+)\)", re.I)
INDEX_RE = re.compile(r"CREATE INDEX IF NOT EXISTS\s+(\w+)", re.I)

problems = []                  # filled by the reconciliation step
timings = []                   # (step title, seconds), written to the load report
_step = None                   # title of the step that is running


def header(n, title):
    global _step
    _step = f"[{n}] {title}"
    print(f"\n{_step}", flush=True)
    return time.perf_counter()


def done(t0):
    seconds = time.perf_counter() - t0
    timings.append((_step, seconds))
    print(f"    step time: {seconds:.1f} s", flush=True)


# ----------------------------------------------------------------- 1. pre-flight
def preflight():
    t0 = header(1, "Pre-flight checks")
    missing = [t for t, _ in TABLES if not (CLEAN / f"{t}.csv").exists()]
    if missing:
        sys.exit(f"    missing in data/clean/: {missing}. Run etl/clean.py first.")
    print(f"    all {len(TABLES)} cleaned CSVs found")

    ensure_database()

    with get_connection() as conn:
        data_dir = conn.execute("SHOW data_directory").fetchone()[0]
    free_gb = shutil.disk_usage(data_dir).free / 1024**3
    print(f"    PostgreSQL data directory: {data_dir}")
    print(f"    free disk space: {free_gb:.1f} GB")
    if free_gb < MIN_FREE_GB:
        print(f"    WARNING: less than {MIN_FREE_GB} GB free; the load may run out of space")
    done(t0)


# ----------------------------------------------------------------- 3. COPY
def copy_table(conn, table, columns):
    """Stream one CSV into its table. Returns (csv_data_rows, rows_loaded, seconds).

    FORMAT csv loads an empty unquoted field as NULL, which is what clean.py writes.
    The CSV rows are counted as newlines while streaming, so the big files are
    read only once and never held in memory.
    """
    path = CLEAN / f"{table}.csv"
    statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    t0 = time.perf_counter()
    lines = 0
    last = b"\n"
    with open(path, "rb") as f:
        first_line = f.readline().decode("utf-8").strip()
        if first_line != ",".join(columns):
            sys.exit(f"    {path.name}: header is '{first_line}', expected '{','.join(columns)}'")
        f.seek(0)
        with conn.cursor() as cur:
            with cur.copy(statement) as copy:
                while block := f.read(BLOCK):
                    copy.write(block)
                    lines += block.count(b"\n")
                    last = block[-1:]
            loaded = cur.rowcount
    if last != b"\n":              # last line without a trailing newline
        lines += 1
    return lines - 1, loaded, time.perf_counter() - t0     # minus the header line


def count_csv_rows(table):
    """Data rows in a cleaned CSV, counted the same way as copy_table (no COPY)."""
    lines = 0
    last = b"\n"
    with open(CLEAN / f"{table}.csv", "rb") as f:
        while block := f.read(BLOCK):
            lines += block.count(b"\n")
            last = block[-1:]
    if last != b"\n":
        lines += 1
    return lines - 1


def load_csvs(conn):
    t0 = header(3, "Bulk load with COPY (1 MB blocks)")
    csv_rows = {}
    print(f"    {'table':<15}{'rows':>12}{'seconds':>10}{'rows/s':>12}")
    for table, columns in TABLES:
        csv_rows[table], loaded, secs = copy_table(conn, table, columns)
        print(f"    {table:<15}{loaded:>12,}{secs:>10.1f}{loaded / secs:>12,.0f}", flush=True)
    # tags.tag_row_id is an identity column, but COPY loaded explicit ids. Move the
    # identity past them so the next generated id is max(tag_row_id) + 1.
    conn.execute("""
        SELECT setval(pg_get_serial_sequence('tags', 'tag_row_id'),
                      (SELECT coalesce(max(tag_row_id), 0) FROM tags) + 1, false)""")
    done(t0)
    return csv_rows


# ----------------------------------------------------------------- 5. constraints
def show_fk_violations(conn, statement):
    """Print a query that lists the rows breaking this foreign key, and its first 10 rows."""
    child, name, child_col, parent, parent_col = FK_RE.search(statement).groups()
    query = sql.SQL(
        "SELECT c.* FROM {child} c LEFT JOIN {parent} p ON p.{pcol} = c.{ccol} "
        "WHERE p.{pcol} IS NULL LIMIT 10"
    ).format(child=sql.Identifier(child), parent=sql.Identifier(parent),
             ccol=sql.Identifier(child_col), pcol=sql.Identifier(parent_col))
    print(f"\n    FOREIGN KEY {name} FAILED: {child}.{child_col} has values "
          f"that are not in {parent}.{parent_col}.")
    print(f"    Query for the violating rows:\n      {query.as_string(conn)}")
    for row in conn.execute(query):
        print(f"      {row}")


def apply_constraints(conn):
    """Run constraints.sql one statement at a time so each FK and index is timed."""
    t0 = header(5, "Foreign keys, indexes, ANALYZE (sql/constraints.sql)")
    text = (SQL_DIR / "constraints.sql").read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    for statement in (s.strip() for s in text.split(";")):
        if not statement:
            continue
        fk, index = FK_RE.search(statement), INDEX_RE.search(statement)
        label = (f"FK     {fk.group(2)}" if fk else
                 f"index  {index.group(1)}" if index else
                 "ANALYZE" if statement.upper() == "ANALYZE" else None)
        t1 = time.perf_counter()
        try:
            conn.execute(statement)
        except psycopg.errors.ForeignKeyViolation:
            show_fk_violations(conn, statement)
            sys.exit("    Load stopped: fix the data (etl/clean.py) and run the load again.")
        if label:                  # the quick "DROP CONSTRAINT IF EXISTS" lines are not printed
            print(f"    {label:<40}{time.perf_counter() - t1:>8.1f} s", flush=True)
    done(t0)


# ----------------------------------------------------------------- 7. reconciliation
def table_rows(conn, table):
    """Rows of a table that came from the CSVs. For users that excludes the app
    accounts (id >= 200000), which are seeded by setup_security.py, not loaded."""
    if table == "users":
        return conn.execute("SELECT count(*) FROM users WHERE user_id < %s",
                            (APP_USER_ID_START,)).fetchone()[0]
    return conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]


def check(results, label, left, right):
    ok = left == right
    if not ok:
        problems.append(label)
    results.append((label, left, right, ok))
    print(f"    {label:<46}{str(left):>12}{str(right):>12}   {'OK' if ok else 'MISMATCH'}")


def reconcile(conn, csv_rows):
    """Compare every table with its CSV, and movie_stats with ratings.
    Returns (table_results, stats_results) for the report."""
    t0 = header(7, "Reconciliation")
    table_results = []
    print(f"    {'table':<15}{'csv rows':>12}{'db rows':>12}   status")
    for table, _ in TABLES:
        db = table_rows(conn, table)
        ok = db == csv_rows[table]
        if not ok:
            problems.append(table)
        table_results.append((table, csv_rows[table], db, ok))
        print(f"    {table:<15}{csv_rows[table]:>12,}{db:>12,}   {'OK' if ok else 'MISMATCH'}")

    stats_results = []
    print(f"\n    {'movie_stats check':<46}{'movie_stats':>12}{'ratings':>12}   status")
    check(stats_results, "sum(rating_count) = count(*) of ratings",
          conn.execute("SELECT coalesce(sum(rating_count), 0) FROM movie_stats").fetchone()[0],
          conn.execute("SELECT count(*) FROM ratings").fetchone()[0])
    check(stats_results, "rows with rating_count > 0 = movies rated",
          conn.execute("SELECT count(*) FROM movie_stats WHERE rating_count > 0").fetchone()[0],
          conn.execute("SELECT count(DISTINCT movie_id) FROM ratings").fetchone()[0])
    sample = conn.execute(
        "SELECT movie_id, avg_rating FROM movie_stats WHERE rating_count > 0 "
        "ORDER BY random() LIMIT 3").fetchall()
    for movie_id, stats_avg in sample:
        direct = conn.execute(
            "SELECT round(avg(rating), 3) FROM ratings WHERE movie_id = %s", (movie_id,)
        ).fetchone()[0]
        check(stats_results, f"avg_rating of random movie {movie_id}", stats_avg, direct)
    done(t0)
    return table_results, stats_results


# ----------------------------------------------------------------- 8. summary
def table_sizes(conn):
    return conn.execute("""
        SELECT c.relname,
               pg_size_pretty(pg_total_relation_size(c.oid)),
               pg_size_pretty(pg_relation_size(c.oid))
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r'
         ORDER BY pg_total_relation_size(c.oid) DESC""").fetchall()


def db_size(conn):
    return conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]


def summary(conn, total_seconds):
    header(8, "Summary")
    print(f"    total load time: {total_seconds:.0f} s ({total_seconds / 60:.1f} min)")
    print(f"    database size:   {db_size(conn)}")
    print(f"\n    {'table':<15}{'total (with indexes)':>22}{'table only':>14}")
    for name, total, table_only in table_sizes(conn):
        print(f"    {name:<15}{total:>22}{table_only:>14}")


# ----------------------------------------------------------------- 9. report
def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def write_report(conn, table_results, stats_results, total_seconds=None):
    """Write reports/load_report.md from the current state of the database.
    total_seconds / timings are only known after a full load."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode = "full load" if total_seconds is not None else "`--report-only` (no reload)"
    out = [
        "# Load report: MovieLens 25M into PostgreSQL",
        "",
        f"Generated by `etl/load.py` on {now}, mode: {mode}.",
        "",
        "## Row counts: cleaned CSV vs database",
        "",
        "`users` counts only MovieLens users (user_id < 200000); app accounts are listed separately.",
        "",
        md_table(["table", "csv rows", "db rows", "status"],
                 [(t, f"{c:,}", f"{d:,}", "OK" if ok else "**MISMATCH**")
                  for t, c, d, ok in table_results]),
        "",
    ]
    app_accounts = conn.execute(
        "SELECT count(*) FROM users WHERE user_id >= %s OR username IS NOT NULL",
        (APP_USER_ID_START,)).fetchone()[0]
    out += [f"App accounts (have a username): {app_accounts}.", ""]

    out += ["## movie_stats vs ratings", "",
            md_table(["check", "movie_stats", "ratings", "status"],
                     [(label, f"{a:,}" if isinstance(a, int) else a,
                       f"{b:,}" if isinstance(b, int) else b, "OK" if ok else "**MISMATCH**")
                      for label, a, b, ok in stats_results]),
            ""]
    unrated = conn.execute("""
        SELECT count(*) FROM movies m
         WHERE NOT EXISTS (SELECT 1 FROM movie_stats s WHERE s.movie_id = m.movie_id AND s.rating_count > 0)
    """).fetchone()[0]
    out += [f"Movies with no ratings (no movie_stats row, or rating_count = 0): {unrated:,}. "
            "Queries must LEFT JOIN movie_stats.", ""]

    if total_seconds is not None:
        out += ["## Step timings", "",
                md_table(["step", "seconds"], [(s, f"{t:.1f}") for s, t in timings]),
                "", f"**Total load time: {total_seconds:.0f} s ({total_seconds / 60:.1f} min).**", ""]
    else:
        out += ["## Step timings", "",
                "Not measured: this report was written with `--report-only`. "
                "A full `python etl/load.py` run records every step here.", ""]

    fks = conn.execute("""
        SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
          FROM pg_constraint
         WHERE contype = 'f' AND connamespace = 'public'::regnamespace
         ORDER BY 1, 2""").fetchall()
    out += [f"## Foreign keys ({len(fks)})", "",
            md_table(["table", "constraint", "definition"], [(t, n, f"`{d}`") for t, n, d in fks]), ""]

    idx = conn.execute("""
        SELECT tablename, indexname, indexdef FROM pg_indexes
         WHERE schemaname = 'public' ORDER BY tablename, indexname""").fetchall()
    out += [f"## Indexes ({len(idx)}, including primary keys)", "",
            md_table(["table", "index", "definition"],
                     [(t, n, f"`{d.split(' USING ', 1)[-1]}`") for t, n, d in idx]), ""]

    trg = conn.execute("""
        SELECT t.tgrelid::regclass::text, t.tgname, p.proname, p.prosecdef
          FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
         WHERE NOT t.tgisinternal ORDER BY 1, 2""").fetchall()
    out += [f"## Triggers ({len(trg)})", "",
            md_table(["table", "trigger", "function", "SECURITY DEFINER"],
                     [(t, n, f"{f}()", "yes" if s else "no") for t, n, f, s in trg]), ""]

    rls = conn.execute("""
        SELECT tablename, policyname, cmd, array_to_string(roles, ', ')
          FROM pg_policies WHERE schemaname = 'public' ORDER BY 1, 2""").fetchall()
    if rls:
        out += [f"## Row-level security policies ({len(rls)})", "",
                md_table(["table", "policy", "command", "roles"], rls), ""]

    out += [f"## Size", "", f"Database size: **{db_size(conn)}**.", "",
            md_table(["table", "total (with indexes)", "table only"], table_sizes(conn)), ""]

    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"\nwrote {REPORT.relative_to(ROOT)}")


# ----------------------------------------------------------------- main
def report_only():
    """Reconcile and write the report from the live database; nothing is loaded."""
    start = time.perf_counter()
    print("Counting rows in the cleaned CSVs ...", flush=True)
    csv_rows = {table: count_csv_rows(table) for table, _ in TABLES}
    with get_connection(autocommit=True) as conn:
        table_results, stats_results = reconcile(conn, csv_rows)
        write_report(conn, table_results, stats_results)
    print(f"report-only run took {time.perf_counter() - start:.0f} s")
    if problems:
        sys.exit(f"\nMISMATCH in {problems}")


def full_load():
    start = time.perf_counter()
    preflight()

    # autocommit: each statement commits on its own, like psql.
    with get_connection(autocommit=True) as conn:
        # Session-level speed-ups only; postgresql.conf is not touched.
        conn.execute("SET maintenance_work_mem = '1GB'")         # faster index builds / FK checks
        conn.execute("SET max_parallel_maintenance_workers = 4")  # parallel index builds
        conn.execute("SET synchronous_commit = off")             # don't wait for WAL flush

        t0 = header(2, "Create tables (sql/schema.sql)")
        run_sql_file(SQL_DIR / "schema.sql", conn)
        done(t0)

        csv_rows = load_csvs(conn)

        t0 = header(4, "Populate movie_stats from ratings")
        cur = conn.execute("""
            INSERT INTO movie_stats (movie_id, rating_count, rating_sum)
            SELECT movie_id, count(*), sum(rating) FROM ratings GROUP BY movie_id""")
        print(f"    {cur.rowcount:,} movies have at least one rating")
        done(t0)

        apply_constraints(conn)

        t0 = header(6, "Create triggers (sql/triggers.sql)")
        run_sql_file(SQL_DIR / "triggers.sql", conn)
        done(t0)

        t0 = header("6b", "Roles, grants, RLS, demo accounts (etl/setup_security.py)")
        setup_security(conn)
        done(t0)

        table_results, stats_results = reconcile(conn, csv_rows)
        total = time.perf_counter() - start
        summary(conn, total)
        write_report(conn, table_results, stats_results, total)

    if problems:
        sys.exit(f"\nLOAD FAILED: mismatch in {problems}")
    print("\nLoad complete: all checks OK.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report-only", action="store_true",
                        help="write reports/load_report.md from the current database without reloading")
    args = parser.parse_args()
    report_only() if args.report_only else full_load()


if __name__ == "__main__":
    main()
