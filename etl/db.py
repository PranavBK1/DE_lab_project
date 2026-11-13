"""Small database helper shared by the ETL scripts.

    from etl.db import get_connection, run_sql_file, ensure_database

Connection settings come from .env (PG_HOST, PG_PORT, PG_DB, PG_SUPERUSER,
PG_SUPERPASSWORD). Passwords are never printed.
"""
import os
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def get_connection(dbname=None, autocommit=False):
    """Return a psycopg 3 connection as the superuser (ETL/setup only)."""
    return psycopg.connect(
        host=os.environ["PG_HOST"],
        port=os.environ["PG_PORT"],
        dbname=dbname or os.environ["PG_DB"],
        user=os.environ["PG_SUPERUSER"],
        password=os.environ["PG_SUPERPASSWORD"],
        autocommit=autocommit,
    )


def ensure_database():
    """Create the PG_DB database if it does not exist yet."""
    name = os.environ["PG_DB"]
    # CREATE DATABASE cannot run inside a transaction, hence autocommit.
    with get_connection(dbname="postgres", autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
        ).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            print(f"created database {name}")
        else:
            print(f"database {name} already exists")


def run_sql_file(path, conn=None):
    """Execute a whole .sql file in one transaction.

    psycopg runs a multi-statement string as-is when no parameters are passed,
    so the file may contain several statements and plpgsql $$ bodies.
    If `conn` is given the caller controls commit/rollback; otherwise a new
    connection is opened and the file is committed (or rolled back on error).
    """
    text = Path(path).read_text(encoding="utf-8")
    if conn is not None:
        conn.execute(text)
        return
    with get_connection() as own:          # commits on success, rolls back on error
        own.execute(text)
    print(f"applied {Path(path).name}")


if __name__ == "__main__":
    ensure_database()
