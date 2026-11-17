"""Shared test setup: import the app modules, and a few database fixtures.

Nothing here commits: every connection is closed without commit (= rollback).
"""
import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))      # so "import db, auth, ratings" finds app/

from db import user_conn  # noqa: E402  (loads .env as a side effect)


@pytest.fixture
def superuser_conn():
    """Superuser connection for test setup only; always rolled back."""
    conn = psycopg.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"],
                           dbname=os.environ["PG_DB"], user=os.environ["PG_SUPERUSER"],
                           password=os.environ["PG_SUPERPASSWORD"])
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _demo_password(username):
    """The password of a demo login, as etl/setup_security.py seeds it:
    DEMO_ADMIN_PASSWORD, or DEMO_USER1..3_PASSWORD (older .env: the shared DEMO_USER_PASSWORD)."""
    if username.startswith("demo_user"):
        own = os.environ.get(f"DEMO_USER{username.removeprefix('demo_user')}_PASSWORD", "")
        return own if own and own != "change-me" else os.environ["DEMO_USER_PASSWORD"]
    return os.environ["DEMO_ADMIN_PASSWORD"]


@pytest.fixture(scope="session")
def demo_password():
    """demo_password("demo_user2") -> that account's password from .env."""
    return _demo_password


def _user_id(username):
    with user_conn(commit=False) as conn:
        row = conn.execute("SELECT user_id FROM users WHERE username = %s", (username,)).fetchone()
    assert row, f"{username} not found: run python etl/setup_security.py"
    return row[0]


@pytest.fixture(scope="session")
def demo1():
    return _user_id("demo_user1")


@pytest.fixture(scope="session")
def other_rating(demo1):
    """(user_id, movie_id, rating) of some rating that does NOT belong to demo_user1."""
    with user_conn(commit=False) as conn:
        return conn.execute(
            "SELECT user_id, movie_id, rating FROM ratings WHERE user_id <> %s "
            "ORDER BY user_id, movie_id LIMIT 1", (demo1,)).fetchone()


@pytest.fixture(scope="session")
def unrated_movie(demo1):
    """A movie demo_user1 has not rated yet, which already has ratings from others."""
    with user_conn(commit=False) as conn:
        return conn.execute("""
            SELECT s.movie_id FROM movie_stats s
             WHERE s.rating_count > 0
               AND NOT EXISTS (SELECT 1 FROM ratings r
                                WHERE r.user_id = %s AND r.movie_id = s.movie_id)
             ORDER BY s.movie_id LIMIT 1""", (demo1,)).fetchone()[0]
