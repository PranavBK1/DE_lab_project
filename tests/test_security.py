"""Phase 5 security tests: grants, row-level security, trigger, UTC, login.

Run:  pytest -v tests/test_security.py

Every test that writes runs in a transaction that is rolled back
(commit=False / the superuser_conn fixture), so the database is unchanged.
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from psycopg import errors, sql

from auth import login
from db import admin_conn, user_conn
from ratings import upsert_my_rating


# ----------------------------------------------------------------- reading
@pytest.mark.parametrize("table", ["movies", "ratings", "movie_stats", "genres", "tags",
                                   "links", "genome_tags", "genome_scores", "movie_genres"])
def test_app_user_can_select(table):
    query = sql.SQL("SELECT count(*) FROM (SELECT 1 FROM {} LIMIT 5) t").format(sql.Identifier(table))
    with user_conn(commit=False) as conn:
        assert conn.execute(query).fetchone()[0] > 0


def test_app_user_can_select_allowed_user_columns():
    with user_conn(commit=False) as conn:
        row = conn.execute("SELECT user_id, username, role, created_at FROM users "
                           "WHERE username = 'demo_user1'").fetchone()
    assert row[2] == "user"


@pytest.mark.parametrize("query", ["SELECT password_hash FROM users LIMIT 1",
                                   "SELECT * FROM users LIMIT 1"])
def test_app_user_cannot_read_password_hash(query):
    with user_conn(commit=False) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(query)


# ----------------------------------------------------------------- forbidden writes
@pytest.mark.parametrize("statement", [
    "UPDATE movies SET title = title WHERE movie_id = 1",
    "INSERT INTO tags (user_id, movie_id, tag, tagged_at) VALUES (1, 1, 'x', now())",
    "DELETE FROM ratings WHERE user_id = 1",
    "UPDATE movie_stats SET rating_count = rating_count WHERE movie_id = 1",
    "UPDATE ratings SET user_id = 2 WHERE user_id = 1",        # cannot move a rating
    "UPDATE users SET role = 'admin' WHERE user_id = 1",       # cannot promote itself
])
def test_app_user_cannot_write_other_tables(statement, demo1):
    with user_conn(demo1, commit=False) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(statement)


# ----------------------------------------------------------------- own ratings + trigger
def stats(conn, movie_id):
    return conn.execute("SELECT rating_count, rating_sum, avg_rating FROM movie_stats "
                        "WHERE movie_id = %s", (movie_id,)).fetchone()


def test_own_rating_insert_and_update_keep_movie_stats_current(demo1, unrated_movie):
    """Proves GAP 5: the SECURITY DEFINER trigger writes movie_stats even though
    movie_app_user has no write privilege on it."""
    with user_conn(demo1, commit=False) as conn:
        count0, sum0, _ = stats(conn, unrated_movie)

        cur = conn.execute("INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, 4.0)",
                           (demo1, unrated_movie))
        assert cur.rowcount == 1
        count1, sum1, avg1 = stats(conn, unrated_movie)
        assert count1 == count0 + 1
        assert sum1 == sum0 + Decimal("4.0")
        assert avg1 == round(sum1 / count1, 3)

        cur = conn.execute("UPDATE ratings SET rating = 2.5 WHERE user_id = %s AND movie_id = %s",
                           (demo1, unrated_movie))
        assert cur.rowcount == 1
        count2, sum2, avg2 = stats(conn, unrated_movie)
        assert count2 == count1                                 # an update is not a new rating
        assert sum2 == sum0 + Decimal("2.5")
        assert avg2 == round(sum2 / count2, 3)


def test_upsert_my_rating_inserts_then_updates(demo1, unrated_movie):
    first = upsert_my_rating(demo1, unrated_movie, 3.5, commit=False)
    assert first[:3] == (demo1, unrated_movie, Decimal("3.5"))
    # upsert of an EXISTING own rating goes through ON CONFLICT DO UPDATE
    with user_conn(commit=False) as conn:
        movie = conn.execute("SELECT movie_id FROM ratings WHERE user_id = %s LIMIT 1",
                             (demo1,)).fetchone()[0]
    changed = upsert_my_rating(demo1, movie, 0.5, commit=False)
    assert changed[:3] == (demo1, movie, Decimal("0.5"))


# ----------------------------------------------------------------- row-level security
def test_update_other_users_rating_affects_zero_rows(demo1, other_rating):
    other_user, movie, _ = other_rating
    with user_conn(demo1, commit=False) as conn:
        cur = conn.execute("UPDATE ratings SET rating = 1.0 WHERE user_id = %s AND movie_id = %s",
                           (other_user, movie))
        assert cur.rowcount == 0


def test_insert_rating_for_other_user_is_rls_violation(demo1, other_rating, unrated_movie):
    other_user = other_rating[0]
    with user_conn(demo1, commit=False) as conn:
        with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
            conn.execute("INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, 3.0)",
                         (other_user, unrated_movie))


def test_upsert_other_users_rating_is_rejected(demo1, other_rating):
    """The app function cannot be tricked either: the user set for the
    transaction is the one passed in, and RLS checks the row against it."""
    other_user, movie, _ = other_rating
    with user_conn(demo1, commit=False) as conn:
        with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
            conn.execute("""INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, 1.0)
                            ON CONFLICT (user_id, movie_id) DO UPDATE SET rating = EXCLUDED.rating""",
                         (other_user, movie))


def test_insert_without_current_user_fails(demo1, unrated_movie):
    with user_conn(commit=False) as conn:                       # app.current_user_id not set
        with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
            conn.execute("INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, 3.0)",
                         (demo1, unrated_movie))


# ----------------------------------------------------------------- validation
@pytest.mark.parametrize("bad", [0, 5.5, 3.3, -1])
def test_invalid_rating_rejected_in_python(demo1, unrated_movie, bad):
    with pytest.raises(ValueError):
        upsert_my_rating(demo1, unrated_movie, bad, commit=False)


@pytest.mark.parametrize("bad", ["0", "5.5"])
def test_invalid_rating_rejected_by_database(demo1, unrated_movie, bad):
    with user_conn(demo1, commit=False) as conn:
        with pytest.raises(errors.CheckViolation):
            conn.execute("INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, %s)",
                         (demo1, unrated_movie, bad))


# ----------------------------------------------------------------- admin
def test_admin_can_update_movies():
    with admin_conn(commit=False) as conn:
        cur = conn.execute("UPDATE movies SET title = title || ' (test)' WHERE movie_id = 1")
        assert cur.rowcount == 1


def test_admin_can_read_password_hash():
    with admin_conn(commit=False) as conn:
        assert conn.execute("SELECT password_hash FROM users WHERE username = 'demo_user1'").fetchone()[0]


# ----------------------------------------------------------------- UTC (GAP 4)
def test_new_rating_gets_utc_rated_at(demo1, unrated_movie):
    with user_conn(demo1, commit=False) as conn:
        rated_at, utc_now = conn.execute(
            "INSERT INTO ratings (user_id, movie_id, rating) VALUES (%s, %s, 4.0) "
            "RETURNING rated_at, now() AT TIME ZONE 'UTC'", (demo1, unrated_movie)).fetchone()
    assert rated_at == utc_now
    # and via the app function, compared with the clock of this machine
    row = upsert_my_rating(demo1, unrated_movie, 4.0, commit=False)
    python_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs(row[3] - python_utc) < timedelta(minutes=1)


# ----------------------------------------------------------------- login
def test_login_admin_succeeds():
    user = login(os.environ["DEMO_ADMIN_USERNAME"], os.environ["DEMO_ADMIN_PASSWORD"])
    assert user["role"] == "admin" and user["user_id"] >= 200000
    assert "password_hash" not in user


def test_login_demo_user_succeeds(demo1):
    user = login("demo_user1", os.environ["DEMO_USER_PASSWORD"])
    assert user == {"user_id": demo1, "role": "user", "username": "demo_user1"}


def test_login_wrong_password_fails():
    assert login("demo_user1", "wrong-password") is None


def test_login_unknown_user_fails():
    assert login("no_such_user", os.environ["DEMO_USER_PASSWORD"]) is None


def test_login_empty_input_fails():
    assert login("", "") is None


def test_login_movielens_user_without_password_fails(superuser_conn):
    """MovieLens users have no username and no hash. Give one a username (in a
    rolled-back transaction) to prove the NULL-hash branch also refuses."""
    user_id = superuser_conn.execute(
        "SELECT user_id FROM users WHERE username IS NULL AND password_hash IS NULL "
        "ORDER BY user_id LIMIT 1").fetchone()[0]
    superuser_conn.execute("UPDATE users SET username = 'ml_no_password' WHERE user_id = %s", (user_id,))
    row = superuser_conn.execute("SELECT * FROM auth_get_user('ml_no_password')").fetchone()
    assert row == (user_id, None, "user")
    assert login("ml_no_password", "", conn=superuser_conn) is None
    assert login("ml_no_password", "anything", conn=superuser_conn) is None


def test_auth_get_user_not_executable_by_public(superuser_conn):
    ok = superuser_conn.execute(
        "SELECT has_function_privilege('public', 'auth_get_user(text)', 'EXECUTE')").fetchone()[0]
    assert ok is False


def test_app_cannot_connect_as_superuser_by_mistake():
    """The app's connection helpers use the restricted roles only."""
    with user_conn(commit=False) as conn:
        assert conn.execute("SELECT current_user, rolsuper FROM pg_roles "
                            "WHERE rolname = current_user").fetchone() == ("movie_app_user", False)
    with admin_conn(commit=False) as conn:
        assert conn.execute("SELECT current_user, rolsuper FROM pg_roles "
                            "WHERE rolname = current_user").fetchone() == ("movie_admin", False)
