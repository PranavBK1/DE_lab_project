"""Bring an already-loaded database up to date with the source SQL, without reloading.

Usage:  python etl/migrate.py

Runs, in order (every step is re-runnable):
  1. every file in sql/migrations/, in name order (schema fixes)
  2. sql/triggers.sql   (CREATE OR REPLACE)
  3. sql/analysis.sql   (stop list, rebuilds the materialized view)
  4. etl/setup_security (extensions, roles, grants, RLS, demo accounts)
A full `python etl/load.py` produces the same end state.
"""
from db import ROOT, get_connection, run_sql_file
from setup_security import setup as setup_security

SQL_DIR = ROOT / "sql"


def main():
    for path in sorted((SQL_DIR / "migrations").glob("*.sql")):
        run_sql_file(path)
    run_sql_file(SQL_DIR / "triggers.sql")
    run_sql_file(SQL_DIR / "analysis.sql")
    with get_connection() as conn:          # one transaction: commits on success
        setup_security(conn)
    print("migration complete")


if __name__ == "__main__":
    main()
