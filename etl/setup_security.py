"""Create the DB roles, grants, row-level security and demo accounts (Phase 5).

Usage:  python etl/setup_security.py

Runs as the superuser from .env. Re-runnable:
  1. apply sql/extensions.sql (pgcrypto) and sql/roles.sql (roles, grants,
     RLS policies, auth_login)
  2. set the passwords of movie_admin / movie_app_user from .env
  3. seed the demo accounts (INSERT ... ON CONFLICT updates them). Passwords
     are hashed INSIDE PostgreSQL with crypt(%s, gen_salt('bf', 12)), the same
     bcrypt implementation auth_login verifies with: one hashing scheme.

etl/load.py calls setup() after triggers.sql and analysis.sql, because a full
reload drops the tables and with them every grant, policy and demo account.
sql/roles.sql grants on the analysis objects, so they must exist first.
Passwords are never printed.
"""
import os

from psycopg import sql

from db import ROOT, get_connection, run_sql_file

BCRYPT_COST = 12                       # gen_salt('bf', 12): 2^12 bcrypt rounds
HASH = sql.SQL("crypt(%s, gen_salt('bf', {}))").format(sql.Literal(BCRYPT_COST))
DEMO_USERS = ["demo_user1", "demo_user2", "demo_user3"]
APP_USER_ID_START = 200000    # app accounts; MovieLens user ids are below this


def env(key):
    value = os.environ.get(key, "")
    if not value or value == "change-me":
        raise SystemExit(f"{key} is missing in .env (see .env.example)")
    return value


def password_key(username):
    """The .env key holding this demo account's password:
    admin -> DEMO_ADMIN_PASSWORD, demo_user1 -> DEMO_USER1_PASSWORD, ..."""
    if username in DEMO_USERS:
        return f"DEMO_USER{username.removeprefix('demo_user')}_PASSWORD"
    return "DEMO_ADMIN_PASSWORD"


def demo_password(username):
    """Each account has its own password. An older .env that only has the shared
    DEMO_USER_PASSWORD still works for the three demo users."""
    key = password_key(username)
    value = os.environ.get(key, "")
    if username in DEMO_USERS and (not value or value == "change-me"):
        key = "DEMO_USER_PASSWORD" if os.environ.get("DEMO_USER_PASSWORD") else key
    return env(key)


def set_role_passwords(conn):
    # ALTER ROLE cannot take a bind parameter, so the password is passed as a
    # quoted sql.Literal (never by string formatting).
    for role, key in [("movie_admin", "MOVIE_ADMIN_PASSWORD"),
                      ("movie_app_user", "MOVIE_APP_USER_PASSWORD")]:
        conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(env(key))))
        print(f"    password set for role {role}")


def release_dataset_users(conn):
    """Older versions attached demo_user1..3 to MovieLens users 1, 2 and 4, so
    the accounts showed those people's 2006/2019 ratings. Detach any demo login
    still sitting on a MovieLens id (< 200000): that user goes back to being an
    ordinary dataset user with no login, and keeps all of its ratings."""
    released = conn.execute("""
        UPDATE users SET username = NULL, password_hash = NULL, role = 'user'
         WHERE username = ANY(%s) AND user_id < %s
        RETURNING user_id""", (DEMO_USERS, APP_USER_ID_START)).fetchall()
    for (user_id,) in released:
        print(f"    MovieLens user {user_id} is no longer a demo login")


def seed_demo_accounts(conn):
    """admin and demo_user1..3 are new app accounts (ids from users_user_id_seq,
    >= 200000). The demo users start with no ratings: "My ratings" shows only
    what they rate in the app."""
    release_dataset_users(conn)
    for name, role in [(env("DEMO_ADMIN_USERNAME"), "admin")] + [(u, "user") for u in DEMO_USERS]:
        user_id = conn.execute(sql.SQL("""
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, {hash}, %s)
            ON CONFLICT (username) DO UPDATE
               SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role
            RETURNING user_id""").format(hash=HASH),
            (name, demo_password(name), role)).fetchone()[0]
        n = conn.execute("SELECT count(*) FROM ratings WHERE user_id = %s", (user_id,)).fetchone()[0]
        print(f"    {name:<12} role {role:<5}  user_id {user_id}  ({n} ratings)")


def setup(conn):
    """Apply all security settings on an open superuser connection."""
    run_sql_file(ROOT / "sql" / "extensions.sql", conn)
    run_sql_file(ROOT / "sql" / "roles.sql", conn)
    print("    applied sql/extensions.sql, sql/roles.sql")
    set_role_passwords(conn)
    seed_demo_accounts(conn)


def main():
    with get_connection() as conn:      # one transaction: commits on success
        setup(conn)
    print("security setup complete")


if __name__ == "__main__":
    main()
