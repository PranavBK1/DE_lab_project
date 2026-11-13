# Security: roles, row-level security, login

Source: [sql/roles.sql](../sql/roles.sql), [etl/setup_security.py](../etl/setup_security.py),
[app/db.py](../app/db.py), [app/auth.py](../app/auth.py). Verified by 41 tests in
[tests/test_security.py](../tests/test_security.py).

## 1. Who can do what

The app never connects as the PostgreSQL superuser. It uses one of two login roles.

| table | movie_app_user (every logged-in user) | movie_admin (Admin page) |
|---|---|---|
| movies, genres, movie_genres, links | SELECT | ALL |
| tags, genome_tags, genome_scores | SELECT | ALL |
| movie_stats | SELECT (the trigger writes it, see §3) | ALL |
| users | SELECT on `user_id, username, role, created_at` only, **no `password_hash`** | ALL |
| **ratings** | SELECT; INSERT `(user_id, movie_id, rating, rated_at)`; UPDATE `(rating, rated_at)`; **only own rows (RLS)**; no DELETE | ALL, bypasses RLS |
| sequences | none | ALL |
| `auth_get_user(text)` | EXECUTE | none |

PUBLIC (any other role) cannot execute `auth_get_user`.

## 2. Row-level security on `ratings`

For every transaction the app first runs
`SELECT set_config('app.current_user_id', '<id>', true)`, and the database checks
each row against that setting:

```sql
ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;

CREATE POLICY ratings_select_all ON ratings FOR SELECT TO movie_app_user
    USING (true);                                         -- charts read all ratings
CREATE POLICY ratings_insert_own ON ratings FOR INSERT TO movie_app_user
    WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::int);
CREATE POLICY ratings_update_own ON ratings FOR UPDATE TO movie_app_user
    USING      (user_id = nullif(current_setting('app.current_user_id', true), '')::int)
    WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::int);
```

| attempt by demo_user1 | result |
|---|---|
| insert or update their own rating | allowed |
| update another user's rating | 0 rows affected (the row is invisible to UPDATE) |
| insert a rating for another user | error: `new row violates row-level security policy` |
| any write with no user set | refused (NULL never matches) |
| delete any rating | `permission denied` (no grant, no policy) |

The database enforces "users may modify only their own ratings". A bug in the
app's SQL cannot break the rule.

## 3. Why SECURITY DEFINER

A SECURITY DEFINER function runs with its **owner's** privileges, not the caller's.
Each one also sets `search_path = public`, so a caller cannot substitute their own
tables.

| function | why it needs it |
|---|---|
| `movie_stats_sync()`, `movie_stats_truncate()` (triggers) | movie_app_user has no write privilege on `movie_stats`. Without this, every rating change would fail with *permission denied*. |
| `auth_get_user(username)` | movie_app_user cannot read `password_hash`, but login must compare it. The function returns the id, hash and role for one username only. |

## 4. How passwords are stored

- App accounts store a **bcrypt hash** (cost 12, salted) in `users.password_hash`. Plain-text passwords are never stored.
- The 162,541 MovieLens users have `password_hash = NULL` and cannot log in.
- Demo and role passwords live only in `.env`, which is git-ignored. `.env.example` holds placeholders.
- `setup_security.py` sets role passwords with `ALTER ROLE … PASSWORD` and a quoted `sql.Literal`. They are never printed.
- All SQL is parameterised.

## 5. Login flow

1. The user types a username and password into the Streamlit form (`app/Home.py`).
2. `login()` connects as **movie_app_user** and runs `SELECT * FROM auth_get_user(%s)`.
3. The function returns `(user_id, password_hash, role)`, or no row.
4. `bcrypt.checkpw(password, hash)` runs in Python.
5. An unknown user, a wrong password or a NULL hash all give the same message:
   *"Invalid username or password."* A dummy bcrypt check keeps the timing similar.
6. On success, `st.session_state["user"] = {user_id, username, role}`.
7. Each page calls `require_login()` or `require_role("admin")`.
8. A user's writes go through `user_conn(user_id)`, which sets `app.current_user_id` (§2).
   Admin pages use `admin_conn()`.
9. Logout clears `st.session_state`.

## 6. Demo accounts

| username | role | user_id | note |
|---|---|---|---|
| admin | admin | 200000 | new app account (ids ≥ 200000) |
| demo_user1 | user | 1 | MovieLens user, 70 ratings |
| demo_user2 | user | 2 | MovieLens user, 184 ratings |
| demo_user3 | user | 4 | MovieLens user, 242 ratings |

The demo users are the 3 lowest MovieLens user_ids with 50–300 ratings. Passwords are in `.env`.

## 7. Known trade-off

`auth_get_user` returns a bcrypt hash to anyone holding the movie_app_user
credentials, if they know a username. The hash is salted and slow to crack, and the
credentials are only in `.env` on the server. A stricter design would verify the
password inside the database (for example with pgcrypto `crypt()`) and return only
true or false.
