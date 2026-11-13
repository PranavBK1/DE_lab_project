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
