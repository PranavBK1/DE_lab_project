"""Bulk-load the cleaned CSVs into PostgreSQL (Phase 4).

Usage:  python etl/load.py

Idempotent: every run drops and recreates the tables, so running it twice
gives the same final state.

Order (constraints and triggers come AFTER the data, which is much faster):
    schema.sql -> COPY 9 CSVs -> fill movie_stats -> constraints.sql -> triggers.sql
"""
import re
import shutil
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

from db import ROOT, ensure_database, get_connection, run_sql_file

CLEAN = ROOT / "data" / "clean"
SQL_DIR = ROOT / "sql"
BLOCK = 1024 * 1024            # stream each CSV to the server in 1 MB blocks
MIN_FREE_GB = 8

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


def header(n, title):
    print(f"\n[{n}] {title}", flush=True)
    return time.perf_counter()


def done(t0):
    print(f"    step time: {time.perf_counter() - t0:.1f} s", flush=True)


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


def load_csvs(conn):
    t0 = header(3, "Bulk load with COPY (1 MB blocks)")
    csv_rows = {}
    print(f"    {'table':<15}{'rows':>12}{'seconds':>10}{'rows/s':>12}")
    for table, columns in TABLES:
        csv_rows[table], loaded, secs = copy_table(conn, table, columns)
        print(f"    {table:<15}{loaded:>12,}{secs:>10.1f}{loaded / secs:>12,.0f}", flush=True)
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
def check(label, left, right):
    ok = left == right
    if not ok:
        problems.append(label)
    print(f"    {label:<46}{str(left):>12}{str(right):>12}   {'OK' if ok else 'MISMATCH'}")


def reconcile(conn, csv_rows):
    t0 = header(7, "Reconciliation")
    print(f"    {'table':<15}{'csv rows':>12}{'db rows':>12}   status")
    for table, _ in TABLES:
        db = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
        ok = db == csv_rows[table]
        if not ok:
            problems.append(table)
        print(f"    {table:<15}{csv_rows[table]:>12,}{db:>12,}   {'OK' if ok else 'MISMATCH'}")

    print(f"\n    {'movie_stats check':<46}{'movie_stats':>12}{'ratings':>12}   status")
    check("sum(rating_count) = count(*) of ratings",
          conn.execute("SELECT sum(rating_count) FROM movie_stats").fetchone()[0],
          conn.execute("SELECT count(*) FROM ratings").fetchone()[0])
    check("rows = count(DISTINCT movie_id) of ratings",
          conn.execute("SELECT count(*) FROM movie_stats").fetchone()[0],
          conn.execute("SELECT count(DISTINCT movie_id) FROM ratings").fetchone()[0])
    sample = conn.execute(
        "SELECT movie_id, avg_rating FROM movie_stats WHERE rating_count > 0 "
        "ORDER BY random() LIMIT 3").fetchall()
    for movie_id, stats_avg in sample:
        direct = conn.execute(
            "SELECT round(avg(rating), 3) FROM ratings WHERE movie_id = %s", (movie_id,)
        ).fetchone()[0]
        check(f"avg_rating of random movie {movie_id}", stats_avg, direct)
    done(t0)


# ----------------------------------------------------------------- 8. summary
def summary(conn, total_seconds):
    header(8, "Summary")
    print(f"    total load time: {total_seconds:.0f} s ({total_seconds / 60:.1f} min)")
    size = conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    print(f"    database size:   {size}")
    print(f"\n    {'table':<15}{'total (with indexes)':>22}{'table only':>14}")
    rows = conn.execute("""
        SELECT c.relname,
               pg_size_pretty(pg_total_relation_size(c.oid)),
               pg_size_pretty(pg_relation_size(c.oid))
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r'
         ORDER BY pg_total_relation_size(c.oid) DESC""")
    for name, total, table_only in rows:
        print(f"    {name:<15}{total:>22}{table_only:>14}")


# ----------------------------------------------------------------- main
def main():
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

        reconcile(conn, csv_rows)
        summary(conn, time.perf_counter() - start)

    if problems:
        sys.exit(f"\nLOAD FAILED: mismatch in {problems}")
    print("\nLoad complete: all checks OK.")


if __name__ == "__main__":
    main()
