"""Apply schema fixes to an already-loaded database, without reloading.

Usage:  python etl/migrate.py

Runs every file in sql/migrations/ in name order, then re-runs sql/triggers.sql
(CREATE OR REPLACE, so it is safe). Every file is re-runnable.
"""
from db import ROOT, run_sql_file

SQL_DIR = ROOT / "sql"


def main():
    for path in sorted((SQL_DIR / "migrations").glob("*.sql")):
        run_sql_file(path)
    run_sql_file(SQL_DIR / "triggers.sql")


if __name__ == "__main__":
    main()
