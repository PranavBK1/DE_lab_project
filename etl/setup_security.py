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
MIN_RATINGS, MAX_RATINGS = 50, 300     # demo users get a real, readable rating history


def env(key):
    value = os.environ.get(key, "")
    if not value or value == "change-me":
        raise SystemExit(f"{key} is missing in .env (see .env.example)")
    return value


def set_role_passwords(conn):
    # ALTER ROLE cannot take a bind parameter, so the password is passed as a
    # quoted sql.Literal (never by string formatting).
    for role, key in [("movie_admin", "MOVIE_ADMIN_PASSWORD"),
                      ("movie_app_user", "MOVIE_APP_USER_PASSWORD")]:
        conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(env(key))))
        print(f"    password set for role {role}")


def pick_demo_user_ids(conn):
    """demo_user1..3 -> MovieLens user_ids.

    An account that already exists keeps its user_id (its rating count changes
    once it rates movies in the app). The others take the lowest user_ids that
    have between 50 and 300 ratings and are not mapped yet.
    """
    existing = dict(conn.execute(
        "SELECT username, user_id FROM users WHERE username = ANY(%s)", (DEMO_USERS,)).fetchall())
    needed = len(DEMO_USERS) - len(existing)
    candidates = []
    if needed:
        candidates = [r[0] for r in conn.execute("""
            SELECT user_id FROM ratings
             GROUP BY user_id
            HAVING count(*) BETWEEN %s AND %s
               AND NOT (user_id = ANY(%s))
             ORDER BY user_id
             LIMIT %s""", (MIN_RATINGS, MAX_RATINGS, list(existing.values()), needed))]
    ids = {}
    for name in DEMO_USERS:
        ids[name] = existing[name] if name in existing else candidates.pop(0)
    return ids


def seed_demo_accounts(conn):
    admin_name = env("DEMO_ADMIN_USERNAME")
    # Admin: a new app account, id from users_user_id_seq (>= 200000).
    admin_id = conn.execute(sql.SQL("""
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, {hash}, 'admin')
        ON CONFLICT (username) DO UPDATE
           SET password_hash = EXCLUDED.password_hash, role = 'admin'
        RETURNING user_id""").format(hash=HASH),
        (admin_name, env("DEMO_ADMIN_PASSWORD"))).fetchone()[0]
    print(f"    {admin_name:<12} role admin  user_id {admin_id}")

    # Users: attached to EXISTING MovieLens user_ids, so they have rating histories.
    user_password = env("DEMO_USER_PASSWORD")
    for name, user_id in pick_demo_user_ids(conn).items():
        conn.execute(sql.SQL("""
            INSERT INTO users (user_id, username, password_hash, role)
            VALUES (%s, %s, {hash}, 'user')
            ON CONFLICT (user_id) DO UPDATE
               SET username = EXCLUDED.username,
                   password_hash = EXCLUDED.password_hash,
                   role = 'user'""").format(hash=HASH),
            (user_id, name, user_password))
        n = conn.execute("SELECT count(*) FROM ratings WHERE user_id = %s", (user_id,)).fetchone()[0]
        print(f"    {name:<12} role user   user_id {user_id}  ({n} ratings)")


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
