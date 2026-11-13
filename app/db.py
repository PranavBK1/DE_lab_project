"""Database connections for the Streamlit app.

The app NEVER connects as the superuser. It uses one of two restricted roles
(created by sql/roles.sql, passwords in .env), each with its own small
connection pool, created once per process (st.cache_resource):

    with user_conn(user_id) as conn:   # movie_app_user: read all, write own ratings
        ...
    with admin_conn() as conn:         # movie_admin: full control (Admin page)
        ...

One `with` block = one transaction: it commits at the end, or rolls back if an
exception is raised (or if commit=False, which the tests use). The logged-in
user is set with set_config(.., is_local = true), so it lasts only for that
transaction and can never leak to the next borrower of a pooled connection.
"""
import atexit
import logging
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
import streamlit as st
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool, PoolTimeout

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

log = logging.getLogger("movielens.db")

# Errors that mean "the database cannot be reached": the pages show one
# friendly message for these instead of a traceback (see Home.py).
DB_UNAVAILABLE = (psycopg.OperationalError, PoolTimeout)

ROLES = {
    "movie_app_user": "MOVIE_APP_USER_PASSWORD",
    "movie_admin": "MOVIE_ADMIN_PASSWORD",
}


def _reset(conn):
    """Called when a connection goes back to the pool: undo session settings."""
    conn.autocommit = False
    conn.read_only = None


@st.cache_resource(show_spinner=False)
def _pool(role):
    pool = ConnectionPool(
        kwargs={
            "host": os.environ["PG_HOST"],
            "port": os.environ["PG_PORT"],
            "dbname": os.environ["PG_DB"],
            "user": role,
            "password": os.environ[ROLES[role]],
            "connect_timeout": 5,
            "application_name": "movielens-dashboard",
        },
        min_size=1,
        max_size=4,
        timeout=5,                              # wait at most 5 s for a free connection
        reset=_reset,
        check=ConnectionPool.check_connection,  # drop connections the server closed
        name=role,
        open=True,
    )
    atexit.register(pool.close)
    return pool


@contextmanager
def _borrow(role, commit):
    with _pool(role).connection() as conn:     # commits on normal exit, rolls back on error
        yield conn
        if not commit:
            conn.rollback()


@contextmanager
def user_conn(user_id=None, commit=True):
    """Connect as movie_app_user. If user_id is given, tell the database who is
    logged in for this transaction; the row-level security policies on ratings
    compare against it, so only that user's ratings can be inserted or updated.
    """
    with _borrow("movie_app_user", commit) as conn:
        if user_id is not None:
            # is_local = true: the setting lasts only until this transaction ends.
            conn.execute("SELECT set_config('app.current_user_id', %s, true)", (str(user_id),))
        yield conn


@contextmanager
def admin_conn(commit=True):
    """Connect as movie_admin (Admin page only)."""
    with _borrow("movie_admin", commit) as conn:
        yield conn
