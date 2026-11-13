"""Database connections for the Streamlit app.

The app NEVER connects as the superuser. It uses one of two restricted roles
(created by sql/roles.sql, passwords in .env):

    with user_conn(user_id) as conn:   # movie_app_user: read all, write own ratings
        ...
    with admin_conn() as conn:         # movie_admin: full control (Admin page)
        ...

One `with` block = one transaction: it commits at the end, or rolls back if an
exception is raised (or if commit=False, which the tests use).
"""
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _connect(role, password_key):
    return psycopg.connect(
        host=os.environ["PG_HOST"],
        port=os.environ["PG_PORT"],
        dbname=os.environ["PG_DB"],
        user=role,
        password=os.environ[password_key],
    )


@contextmanager
def user_conn(user_id=None, commit=True):
    """Connect as movie_app_user. If user_id is given, tell the database who is
    logged in for this transaction; the row-level security policies on ratings
    compare against it, so only that user's ratings can be inserted or updated.
    """
    conn = _connect("movie_app_user", "MOVIE_APP_USER_PASSWORD")
    try:
        if user_id is not None:
            # is_local = true: the setting lasts only until this transaction ends.
            conn.execute("SELECT set_config('app.current_user_id', %s, true)", (str(user_id),))
        yield conn
        if commit:
            conn.commit()
    finally:
        conn.close()            # closing without commit rolls back


@contextmanager
def admin_conn(commit=True):
    """Connect as movie_admin (Admin page only)."""
    conn = _connect("movie_admin", "MOVIE_ADMIN_PASSWORD")
    try:
        yield conn
        if commit:
            conn.commit()
    finally:
        conn.close()
